"""Guest Memory Evidence — Phase 4A, GUEST_MEMORY_EVIDENCE_CHAIN.md §3.

Covers `get_guest_memory_evidence`'s read path against the real Action
Ledger shape: an old-style `MEMORY_ACCEPTED` event logged before
`message_id` existed (no key in `event_metadata` at all) must degrade
gracefully rather than error, and a new-style event with `message_id`
must resolve the real guest quote from `Message`.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    ActionEvent,
    ActionEventStatus,
    ActorType,
    Guest,
    Message,
    MessageChannel,
    Property,
    Tenant,
)
from app.services.action_logger import action_logger
from app.services.guest_memory_evidence import get_guest_memory_evidence

_ACCEPTED = "MEMORY_ACCEPTED"


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


def _make_guest(db, *, tenant_id, **guest_kwargs):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest", **guest_kwargs)
    db.add(guest)
    db.flush()
    return guest


def _log_accepted(db, *, tenant_id, guest_id, field, message_id_in_metadata="__unset__"):
    """Mirrors memory_manager.py's own MEMORY_ACCEPTED call shape.
    `message_id_in_metadata` defaults to a sentinel (not None) so a
    test can omit the key entirely -- the real pre-Phase-4A shape --
    rather than always sending an explicit `"message_id": None`, which
    is a different (post-Phase-4A) metadata dict."""
    metadata = {"field": field, "reason": "applied"}
    if message_id_in_metadata != "__unset__":
        metadata["message_id"] = message_id_in_metadata
    return action_logger.log_action(
        db,
        tenant_id=tenant_id,
        guest_id=guest_id,
        intent="memory",
        agent=None,
        action_type=_ACCEPTED,
        actor=ActorType.system,
        input_summary=f"Guest memory proposal for {field}.",
        decision=f"Applied to Guest.{field}.",
        status=ActionEventStatus.accepted,
        metadata=metadata,
    )


def _make_message(db, *, tenant_id, guest_id, body, channel=MessageChannel.whatsapp):
    message = Message(
        tenant_id=tenant_id,
        guest_id=guest_id,
        channel=channel,
        direction="inbound",
        body=body,
    )
    db.add(message)
    db.flush()
    return message


# -- old memories: no message_id in metadata (pre-Phase-4A) -------------------


def test_old_style_event_with_no_message_id_key_degrades_gracefully(db_session):
    """An ActionEvent logged before this phase existed has no
    "message_id" key in its metadata at all -- not None, absent. The
    evidence query must not error on this and must return no quote."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-a", dietary_preferences="Vegetarian")
    _log_accepted(db, tenant_id="hotel-a", guest_id=guest.id, field="dietary_preferences")
    db.commit()

    results = get_guest_memory_evidence(db, tenant_id="hotel-a", guest_id=guest.id)

    assert len(results) == 1
    evidence = results[0]
    assert evidence.field == "dietary_preferences"
    assert evidence.value == "Vegetarian"
    assert evidence.confirmed is True
    assert evidence.evidence_quote is None
    assert evidence.evidence_channel is None
    assert evidence.evidence_date is None
    # Guest Insight is still produced -- it only needs the value, not
    # the underlying message.
    assert "Vegetarian" in evidence.insight


def test_event_with_explicit_none_message_id_also_degrades_gracefully(db_session):
    """A GuestMemoryAgent proposal made with no message in scope (e.g.
    a future non-message-driven caller) sends message_id=None
    explicitly, rather than omitting the key -- must behave the same
    as the fully-old-style case above."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-b", preferred_room="Prefers a quiet room")
    _log_accepted(
        db, tenant_id="hotel-b", guest_id=guest.id, field="preferred_room",
        message_id_in_metadata=None,
    )
    db.commit()

    results = get_guest_memory_evidence(db, tenant_id="hotel-b", guest_id=guest.id)

    assert len(results) == 1
    assert results[0].evidence_quote is None


# -- new memories: message_id present, resolves the real quote ----------------


def test_new_style_event_resolves_the_real_guest_quote(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-c", dietary_preferences="Vegetarian")
    message = _make_message(
        db, tenant_id="hotel-c", guest_id=guest.id, body="I'm vegetarian, just so you know!"
    )
    _log_accepted(
        db, tenant_id="hotel-c", guest_id=guest.id, field="dietary_preferences",
        message_id_in_metadata=message.id,
    )
    db.commit()

    results = get_guest_memory_evidence(db, tenant_id="hotel-c", guest_id=guest.id)

    assert len(results) == 1
    evidence = results[0]
    assert evidence.evidence_quote == "I'm vegetarian, just so you know!"
    assert evidence.evidence_channel == "whatsapp"
    assert evidence.evidence_date is not None


def test_dangling_message_id_degrades_gracefully_rather_than_erroring(db_session):
    """The referenced Message row doesn't exist (e.g. deleted, or a
    cross-tenant id) -- still not an error, just no quote."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-d", dietary_preferences="Vegan")
    _log_accepted(
        db, tenant_id="hotel-d", guest_id=guest.id, field="dietary_preferences",
        message_id_in_metadata="does-not-exist",
    )
    db.commit()

    results = get_guest_memory_evidence(db, tenant_id="hotel-d", guest_id=guest.id)

    assert len(results) == 1
    assert results[0].evidence_quote is None


def test_message_from_another_tenant_is_not_leaked_as_evidence(db_session):
    """Tenant isolation: even if a message_id happened to collide with
    another tenant's Message row, the evidence query is tenant-scoped
    and must not join across tenants."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-e", dietary_preferences="Vegetarian")
    other_guest = _make_guest(db, tenant_id="hotel-f")
    other_message = _make_message(
        db, tenant_id="hotel-f", guest_id=other_guest.id, body="Secret from another hotel"
    )
    _log_accepted(
        db, tenant_id="hotel-e", guest_id=guest.id, field="dietary_preferences",
        message_id_in_metadata=other_message.id,
    )
    db.commit()

    results = get_guest_memory_evidence(db, tenant_id="hotel-e", guest_id=guest.id)

    assert len(results) == 1
    assert results[0].evidence_quote is None


# -- multiple accepted events per field ----------------------------------------


def test_latest_accepted_event_wins_when_a_field_has_several(db_session):
    """dietary_preferences is append-only -- a second MEMORY_ACCEPTED
    event for the same field means a genuinely new fact was appended
    (e.g. an allergy stated after the original diet), not a restated
    duplicate (MEMORY_MANAGER.md's duplicate-detection intercepts
    those as MEMORY_REJECTED before they ever reach here). The most
    recent event is the best evidence for the field's current,
    combined value."""
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-g", dietary_preferences="Vegetarian; Allergic to peanuts"
    )
    first_message = _make_message(
        db, tenant_id="hotel-g", guest_id=guest.id, body="I'm vegetarian"
    )
    _log_accepted(
        db, tenant_id="hotel-g", guest_id=guest.id, field="dietary_preferences",
        message_id_in_metadata=first_message.id,
    )
    second_message = _make_message(
        db, tenant_id="hotel-g", guest_id=guest.id, body="Also, I'm allergic to peanuts"
    )
    _log_accepted(
        db, tenant_id="hotel-g", guest_id=guest.id, field="dietary_preferences",
        message_id_in_metadata=second_message.id,
    )
    db.commit()

    results = get_guest_memory_evidence(db, tenant_id="hotel-g", guest_id=guest.id)

    assert len(results) == 1
    assert results[0].evidence_quote == "Also, I'm allergic to peanuts"


# -- fields with no current value, and notes exclusion -------------------------


def test_field_with_no_current_value_produces_no_evidence_row(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-h")  # no dietary_preferences, no preferred_room

    results = get_guest_memory_evidence(db, tenant_id="hotel-h", guest_id=guest.id)

    assert results == []


def test_notes_field_is_never_included_in_the_evidence_chain(db_session):
    """notes is an append-only free-text log, not a single current
    value -- deliberately excluded (guest_memory_evidence.py's own
    module docstring)."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-i", notes="[2026-01-01] Guest wants late checkout")

    results = get_guest_memory_evidence(db, tenant_id="hotel-i", guest_id=guest.id)

    assert results == []


def test_guest_insight_is_evidence_grounded_not_a_recurrence_claim(db_session):
    """Guest Insight must never claim a preference is "recurring" --
    the ledger can't actually distinguish "stated once" from "stated
    identically many times" (duplicate-detection intercepts repeats as
    MEMORY_REJECTED), so that would be an unverifiable overclaim."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-j", dietary_preferences="Vegetarian")
    _log_accepted(db, tenant_id="hotel-j", guest_id=guest.id, field="dietary_preferences")
    db.commit()

    results = get_guest_memory_evidence(db, tenant_id="hotel-j", guest_id=guest.id)

    assert "recurring" not in results[0].insight.lower()
    assert "confirmed" in results[0].insight.lower()


# -- tenant isolation on the guest itself --------------------------------------


def test_guest_in_another_tenant_returns_no_evidence(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-k", dietary_preferences="Vegetarian")

    results = get_guest_memory_evidence(db, tenant_id="hotel-k-imposter", guest_id=guest.id)

    assert results == []
