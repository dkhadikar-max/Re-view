"""Webhook idempotency — PILOT_READINESS.md §1.

Meta retries WhatsApp webhook delivery on timeout or a non-2xx
response. `ingest_inbound_whatsapp` must treat a replayed webhook
(same `tenant_id` + `provider_message_id`) as a no-op: return the
already-stored `Message`, never re-run the Concierge Router, never
create a second `ActionEvent`/`Task`, never append a second
guest-memory note.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import ActionEvent, Guest, Message, Property, Task, Tenant
from app.services.context_builder import ContextBuilder
from app.services.messaging import ingest_inbound_whatsapp


@pytest.fixture(autouse=True)
def _clear_context_cache():
    ContextBuilder.clear_cache()
    yield
    ContextBuilder.clear_cache()


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_guest(db, *, tenant_id, phone):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(
        tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany"
    )
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest", phone=phone)
    db.add(guest)
    db.flush()
    return guest


def test_replayed_webhook_returns_existing_message_not_a_new_one(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-dup", phone="+15551110000")

    first = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dup",
        from_phone=guest.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.ABC123",
    )
    second = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dup",
        from_phone=guest.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.ABC123",
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert db.query(Message).filter(Message.tenant_id == "hotel-dup").count() == 1


def test_replayed_webhook_does_not_create_duplicate_action_event_or_task(db_session):
    """A medical-emergency message trips the Escalation Filter, creating
    exactly one ActionEvent and one Task. A replayed webhook for the
    same provider_message_id must not create a second of either."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-dup2", phone="+15552220000")

    ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dup2",
        from_phone=guest.phone,
        body="I have a medical emergency",
        provider_message_id="wamid.MED1",
    )
    ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dup2",
        from_phone=guest.phone,
        body="I have a medical emergency",
        provider_message_id="wamid.MED1",
    )

    assert db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-dup2").count() == 1
    assert db.query(Task).filter(Task.tenant_id == "hotel-dup2").count() == 1


def test_replayed_webhook_does_not_append_a_second_memory_note(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-dup3", phone="+15553330000")

    ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dup3",
        from_phone=guest.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.NOTE1",
    )
    notes_after_first = guest.notes

    ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dup3",
        from_phone=guest.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.NOTE1",
    )

    assert guest.notes == notes_after_first


def test_messages_without_provider_message_id_are_never_deduplicated(db_session):
    """Some inbound event shapes may lack a provider_message_id — two
    such messages must never be treated as duplicates of each other,
    since None can't distinguish them."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-nopid", phone="+15554440000")

    first = ingest_inbound_whatsapp(
        db, tenant_id="hotel-nopid", from_phone=guest.phone, body="What time is breakfast?"
    )
    second = ingest_inbound_whatsapp(
        db, tenant_id="hotel-nopid", from_phone=guest.phone, body="What time is the pool open?"
    )

    assert first.id != second.id
    assert db.query(Message).filter(Message.tenant_id == "hotel-nopid").count() == 2


def test_dedup_is_tenant_scoped(db_session):
    """The same provider_message_id under two different tenants must
    never collide — Meta's IDs are globally unique per WABA in
    practice, but the dedup key is deliberately (tenant_id,
    provider_message_id), not provider_message_id alone, so a bug can
    never leak an existence check across a tenant boundary."""
    db = db_session
    guest_a = _make_guest(db, tenant_id="hotel-a", phone="+15555550000")
    guest_b = _make_guest(db, tenant_id="hotel-b", phone="+15556660000")

    msg_a = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-a",
        from_phone=guest_a.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.SHARED",
    )
    msg_b = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-b",
        from_phone=guest_b.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.SHARED",
    )

    assert msg_a.id != msg_b.id
    assert db.query(Message).filter(Message.provider_message_id == "wamid.SHARED").count() == 2


def test_replayed_webhook_increments_duplicate_webhook_count(db_session):
    """PILOT_READINESS.md §4 — a duplicate delivery is handled correctly
    (no reprocessing), but it must still be visible to an operator via
    Message.duplicate_webhook_count, recorded on the original row."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-dupcount", phone="+15557770000")

    first = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dupcount",
        from_phone=guest.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.COUNT1",
    )
    assert first.duplicate_webhook_count == 0

    second = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dupcount",
        from_phone=guest.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.COUNT1",
    )
    assert second.duplicate_webhook_count == 1

    third = ingest_inbound_whatsapp(
        db,
        tenant_id="hotel-dupcount",
        from_phone=guest.phone,
        body="What time is breakfast?",
        provider_message_id="wamid.COUNT1",
    )
    assert third.duplicate_webhook_count == 2
