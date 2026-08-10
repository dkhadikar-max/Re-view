"""Outbound delivery reliability — PILOT_READINESS.md §2.

`process_due_messages` retries a `failed` outbound message a bounded
number of times (`MAX_OUTBOUND_RETRIES`), then leaves it alone —
queryable/visible for §4's monitoring, never silently retried forever
and never silently dropped.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import Guest, Message, MessageChannel, MessageStatus, Property, Tenant
from app.services.messaging import MAX_OUTBOUND_RETRIES, process_due_messages


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


def _make_guest(db, *, tenant_id, phone, whatsapp_configured):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(
        tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany"
    )
    if whatsapp_configured:
        property_.whatsapp_phone_number_id = f"{tenant_id}-wa-number"
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest", phone=phone)
    db.add(guest)
    db.flush()
    return guest


def _make_failed_message(db, *, tenant_id, guest_id, retry_count=0):
    message = Message(
        tenant_id=tenant_id,
        guest_id=guest_id,
        channel=MessageChannel.whatsapp,
        direction="outbound",
        body="Your order is confirmed.",
        status=MessageStatus.failed,
        retry_count=retry_count,
    )
    db.add(message)
    db.flush()
    return message


def test_failed_message_is_retried_and_succeeds_once_deliverable(db_session):
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-retry-ok", phone="+15550001111", whatsapp_configured=True
    )
    message = _make_failed_message(db, tenant_id="hotel-retry-ok", guest_id=guest.id)

    count = process_due_messages(db)

    assert count == 1
    assert message.status == MessageStatus.sent
    assert message.retry_count == 1


def test_failed_message_retried_and_fails_again_increments_retry_count(db_session):
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-retry-fail", phone="+15550002222", whatsapp_configured=False
    )
    message = _make_failed_message(db, tenant_id="hotel-retry-fail", guest_id=guest.id)

    count = process_due_messages(db)

    assert count == 0
    assert message.status == MessageStatus.failed
    assert message.retry_count == 1


def test_message_at_retry_cap_is_never_retried_again(db_session):
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-retry-cap", phone="+15550003333", whatsapp_configured=True
    )
    message = _make_failed_message(
        db, tenant_id="hotel-retry-cap", guest_id=guest.id, retry_count=MAX_OUTBOUND_RETRIES
    )

    count = process_due_messages(db)

    assert count == 0
    assert message.status == MessageStatus.failed
    assert message.retry_count == MAX_OUTBOUND_RETRIES


def test_repeated_failures_stop_retrying_once_the_cap_is_reached(db_session):
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-retry-exhaust", phone="+15550004444", whatsapp_configured=False
    )
    message = _make_failed_message(db, tenant_id="hotel-retry-exhaust", guest_id=guest.id)

    for _ in range(MAX_OUTBOUND_RETRIES + 2):
        process_due_messages(db)

    # Never exceeds the cap, and never silently succeeds/vanishes —
    # it's exactly MAX_OUTBOUND_RETRIES and still `failed`.
    assert message.status == MessageStatus.failed
    assert message.retry_count == MAX_OUTBOUND_RETRIES


def test_queued_messages_are_unaffected_by_the_retry_path(db_session):
    """A normal, never-failed `queued` message must still be delivered
    exactly as before — the retry path only ever touches `failed`
    messages, never interferes with the existing queued-message flow."""
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-retry-noop", phone="+15550005555", whatsapp_configured=True
    )
    message = Message(
        tenant_id="hotel-retry-noop",
        guest_id=guest.id,
        channel=MessageChannel.whatsapp,
        direction="outbound",
        body="What time is breakfast?",
        status=MessageStatus.queued,
    )
    db.add(message)
    db.flush()

    count = process_due_messages(db)

    assert count == 1
    assert message.status == MessageStatus.sent
    assert message.retry_count == 0
