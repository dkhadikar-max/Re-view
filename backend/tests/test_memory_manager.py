"""Memory Manager — MEMORY_MANAGER.md's frozen v1 contract.

Unit tests of `MemoryManager` itself: confidence-band routing,
field-specific mutation rules (dietary/preferred_room/notes),
idempotency, tenant isolation, and the transactional guarantee. Router
integration is covered separately in
test_memory_manager_router_integration.py.
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
    Property,
    Task,
    Tenant,
)
from app.services.action_logger import action_logger
from app.services.memory_manager import memory_manager


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


def _log_memory_proposed(db, *, tenant_id, guest_id, correlation_id=None):
    return action_logger.log_action(
        db,
        tenant_id=tenant_id,
        guest_id=guest_id,
        intent="memory",
        agent="guest_memory",
        action_type="MEMORY_PROPOSED",
        actor=ActorType.ai,
        input_summary="Guest shared a preference.",
        decision="GuestMemoryAgent proposed updating a field.",
        status=ActionEventStatus.proposed,
        correlation_id=correlation_id,
    )


def _events_for(db, correlation_id):
    return db.query(ActionEvent).filter(ActionEvent.correlation_id == correlation_id).all()


# -- confidence-band routing --------------------------------------------------


def test_auto_apply_sets_empty_dietary_field(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-a")
    event = _log_memory_proposed(db, tenant_id="hotel-a", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "Vegetarian", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences == "Vegetarian"
    events = [e for e in _events_for(db, event.correlation_id) if e.action_type == "MEMORY_ACCEPTED"]
    assert len(events) == 1
    assert events[0].actor == ActorType.system
    assert events[0].status == ActionEventStatus.accepted


def test_hold_band_creates_task_and_does_not_mutate_guest(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-b")
    event = _log_memory_proposed(db, tenant_id="hotel-b", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "Vegetarian", "confidence": 0.75}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences is None

    task = db.query(Task).filter(Task.tenant_id == "hotel-b").one()
    assert task.related_id == guest.id

    events = [e for e in _events_for(db, event.correlation_id) if e.action_type == "MEMORY_HELD"]
    assert len(events) == 1
    assert events[0].actor == ActorType.system
    assert events[0].status == ActionEventStatus.escalated
    assert events[0].event_metadata  # metadata carries field/reason, checked below via json
    metadata = json.loads(events[0].event_metadata)
    assert metadata["field"] == "dietary_preferences"
    assert metadata["reason"] == "confidence_below_threshold"


def test_reject_below_hold_threshold_creates_no_task_no_mutation(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-c")
    event = _log_memory_proposed(db, tenant_id="hotel-c", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "Vegetarian", "confidence": 0.5}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences is None
    assert db.query(Task).filter(Task.tenant_id == "hotel-c").count() == 0

    events = [e for e in _events_for(db, event.correlation_id) if e.action_type == "MEMORY_REJECTED"]
    assert len(events) == 1
    assert events[0].actor == ActorType.system
    assert events[0].status == ActionEventStatus.rejected


def test_unrecognized_field_is_rejected_not_crashed(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-d")
    event = _log_memory_proposed(db, tenant_id="hotel-d", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "favorite_color", "value": "Blue", "confidence": 0.95}],
    )

    events = [e for e in _events_for(db, event.correlation_id) if e.action_type == "MEMORY_REJECTED"]
    assert len(events) == 1
    assert json.loads(events[0].event_metadata)["reason"] == "unrecognized_field"


# -- dietary_preferences (protected) ------------------------------------------


def test_dietary_appends_to_existing_value_never_replaces(db_session):
    """The explicit 'dietary safety' test: an existing dietary value is
    never overwritten, even by a high-confidence proposal."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-e", dietary_preferences="Allergic to peanuts")
    event = _log_memory_proposed(db, tenant_id="hotel-e", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "Vegan", "confidence": 0.99}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert "Allergic to peanuts" in refreshed.dietary_preferences
    assert "Vegan" in refreshed.dietary_preferences
    assert refreshed.dietary_preferences == "Allergic to peanuts; Vegan"


def test_dietary_case_insensitive_duplicate_is_ignored(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-f", dietary_preferences="Vegetarian")
    event = _log_memory_proposed(db, tenant_id="hotel-f", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "vegetarian", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences == "Vegetarian"  # unchanged, not doubled
    events = [e for e in _events_for(db, event.correlation_id) if e.action_type == "MEMORY_REJECTED"]
    assert len(events) == 1
    assert json.loads(events[0].event_metadata)["reason"] == "duplicate_ignored"


def test_dietary_no_semantic_inference_between_values(db_session):
    """Vegan does not collapse into an existing Vegetarian value -- both
    are stored verbatim, per the frozen spec's explicit non-goal."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-g", dietary_preferences="Vegetarian")
    event = _log_memory_proposed(db, tenant_id="hotel-g", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "Vegan", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences == "Vegetarian; Vegan"


# -- preferred_room (not protected) -------------------------------------------


def test_preferred_room_set_when_empty(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-h")
    event = _log_memory_proposed(db, tenant_id="hotel-h", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "preferred_room", "value": "Prefers a quiet room", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.preferred_room == "Prefers a quiet room"


def test_preferred_room_replaced_by_newer_explicit_preference(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-i", preferred_room="Prefers a quiet room")
    event = _log_memory_proposed(db, tenant_id="hotel-i", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "preferred_room", "value": "Prefers a high floor", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.preferred_room == "Prefers a high floor"


def test_preferred_room_identical_value_is_idempotent(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-j", preferred_room="Prefers a quiet room")
    event = _log_memory_proposed(db, tenant_id="hotel-j", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "preferred_room", "value": "Prefers a quiet room", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.preferred_room == "Prefers a quiet room"
    events = [e for e in _events_for(db, event.correlation_id) if e.action_type == "MEMORY_REJECTED"]
    assert len(events) == 1


# -- notes (append-only) -------------------------------------------------------


def test_notes_appended_with_timestamp_when_empty(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-k")
    event = _log_memory_proposed(db, tenant_id="hotel-k", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "notes", "value": "Guest mentioned wanting a late checkout", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert "Guest mentioned wanting a late checkout" in refreshed.notes
    assert refreshed.notes.startswith("[")  # timestamp prefix


def test_notes_appended_not_overwritten_when_existing(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-l", notes="[2026-01-01] Earlier note")
    event = _log_memory_proposed(db, tenant_id="hotel-l", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "notes", "value": "New note", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert "Earlier note" in refreshed.notes
    assert "New note" in refreshed.notes


def test_notes_duplicate_text_is_ignored(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-m", notes="[2026-01-01] Guest wants late checkout")
    event = _log_memory_proposed(db, tenant_id="hotel-m", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "notes", "value": "Guest wants late checkout", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.notes.count("Guest wants late checkout") == 1


# -- idempotency (general) -----------------------------------------------------


def test_identical_proposal_submitted_twice_never_double_applies(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-n")
    event = _log_memory_proposed(db, tenant_id="hotel-n", guest_id=guest.id)

    update = {"field": "dietary_preferences", "value": "Vegetarian", "confidence": 0.9}
    memory_manager.apply_or_hold(db, event=event, memory_updates=[update])
    memory_manager.apply_or_hold(db, event=event, memory_updates=[update])

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences == "Vegetarian"


# -- tenant isolation -----------------------------------------------------------


def test_guest_in_another_tenant_is_never_mutated(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-o")
    # An event claiming a different tenant than the guest actually belongs to.
    event = _log_memory_proposed(db, tenant_id="hotel-o-imposter", guest_id=guest.id)

    memory_manager.apply_or_hold(
        db, event=event,
        memory_updates=[{"field": "dietary_preferences", "value": "Vegetarian", "confidence": 0.9}],
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences is None
    # No ledger noise for a guest that was never found under that tenant.
    assert _events_for(db, event.correlation_id) == [event]


# -- transactional guarantee ----------------------------------------------------


def test_guest_mutation_and_ledger_event_roll_back_together(db_session, monkeypatch):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-p")
    event = _log_memory_proposed(db, tenant_id="hotel-p", guest_id=guest.id)
    # Commit the setup first -- in production this data would already
    # exist from an earlier request. Only the memory-update attempt
    # itself should be what a later rollback undoes; without this
    # commit, rolling back would also wipe the guest/event this test
    # just created, which isn't what "transaction consistency" means.
    db.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated Action Ledger failure")

    monkeypatch.setattr(action_logger, "log_action", boom)

    with pytest.raises(RuntimeError):
        memory_manager.apply_or_hold(
            db, event=event,
            memory_updates=[{"field": "dietary_preferences", "value": "Vegetarian", "confidence": 0.9}],
        )
    db.rollback()

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences is None
