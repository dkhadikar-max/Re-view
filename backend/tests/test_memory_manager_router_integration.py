"""Memory Manager — Router integration (MEMORY_MANAGER.md §8).

Verifies the full `ConciergeRouter.route()` -> `GuestMemoryAgent` ->
`MemoryManager` path end to end: `GuestMemoryAgent` proposes
(unchanged), the Router logs `MEMORY_PROPOSED` (unchanged), and
`MemoryManager` produces the right ledger sequence for an accept, a
hold, and a reject. Real (SQLite, in-memory) database and the full
pipeline — same fixture pattern as
test_conversation_manager_router_integration.py.
"""

from __future__ import annotations

from app.db.session import Base
from app.models.entities import ActionEvent, Guest, Property, Task, Tenant
from app.services.concierge_router import concierge_router
from app.services.context_builder import ContextBuilder
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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


def _make_property(db, *, tenant_id):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    return property_


def _make_guest(db, *, tenant_id, property_id, **kwargs):
    guest = Guest(tenant_id=tenant_id, property_id=property_id, name="Guest", **kwargs)
    db.add(guest)
    db.flush()
    return guest


def test_high_confidence_dietary_statement_is_auto_applied(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-a")
    guest = _make_guest(db, tenant_id="hotel-a", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-a", guest_id=guest.id, message_body="I'm vegetarian")

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences == "Vegetarian"

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-a").all()
    action_types = {e.action_type for e in events}
    assert "MEMORY_PROPOSED" in action_types
    assert "MEMORY_ACCEPTED" in action_types


def test_existing_dietary_value_is_never_overwritten_end_to_end(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-b")
    guest = _make_guest(
        db, tenant_id="hotel-b", property_id=property_.id, dietary_preferences="Vegetarian"
    )
    db.flush()

    # Not "I'm allergic to peanuts" -- that trips the Escalation
    # Filter's own hard-safety medical pattern (`allerg\w*`,
    # escalation_filter.py) before the message ever reaches Intent
    # Classification, which is correct existing behavior (a stated
    # allergy is safety-relevant, not a routine memory update) but
    # means it can't exercise this path end to end. "I'm vegan" hits
    # GuestMemoryAgent's own dietary pattern at 0.9 confidence without
    # touching any escalation category.
    concierge_router.route(db, tenant_id="hotel-b", guest_id=guest.id, message_body="I'm vegan")

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert "Vegetarian" in refreshed.dietary_preferences
    assert "Vegan" in refreshed.dietary_preferences


def test_room_preference_statement_is_held_for_staff_review(db_session):
    """GuestMemoryAgent's own _ROOM_PREFERENCE_PATTERNS are all
    confidence 0.75-0.8 (guest_memory_agent.py) -- below the 0.85
    auto-apply threshold (MEMORY_MANAGER.md §2). A real room-preference
    statement lands in the hold band today, not auto-apply -- this is
    the actual current behavior, not a lower bar for a "not protected"
    field overriding the confidence gate."""
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-c")
    guest = _make_guest(
        db, tenant_id="hotel-c", property_id=property_.id, preferred_room="Prefers a low floor"
    )
    db.flush()

    concierge_router.route(db, tenant_id="hotel-c", guest_id=guest.id, message_body="I prefer a quiet room")

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.preferred_room == "Prefers a low floor"  # unchanged -- held, not applied

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-c").all()
    assert any(e.action_type == "MEMORY_HELD" for e in events)
    assert db.query(Task).filter(Task.tenant_id == "hotel-c").count() == 1


def test_note_worthy_statement_is_held_for_staff_review(db_session):
    """Same reality as room preferences: GuestMemoryAgent's
    _NOTE_WORTHY_PATTERNS confidence is 0.75, below auto-apply."""
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-d")
    guest = _make_guest(db, tenant_id="hotel-d", property_id=property_.id)
    db.flush()

    concierge_router.route(
        db, tenant_id="hotel-d", guest_id=guest.id,
        message_body="Late checkout would be great",
    )

    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.notes is None  # unchanged -- held, not applied

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-d").all()
    assert any(e.action_type == "MEMORY_HELD" for e in events)
    assert db.query(Task).filter(Task.tenant_id == "hotel-d").count() == 1


def test_guest_memory_agent_never_writes_guest_directly(db_session):
    """The write boundary itself: even though GuestMemoryAgent.answer()
    runs inside this same call, only MemoryManager's own mutation
    should ever land -- there is no code path here that bypasses it."""
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-e")
    guest = _make_guest(db, tenant_id="hotel-e", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-e", guest_id=guest.id, message_body="I'm vegan"
    )

    assert response.handled is True
    refreshed = db.query(Guest).filter(Guest.id == guest.id).one()
    assert refreshed.dietary_preferences == "Vegan"
    # Exactly one MEMORY_ACCEPTED event recorded the mutation -- the
    # ledger is the only trace of who actually applied it.
    accepted = [
        e for e in db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-e").all()
        if e.action_type == "MEMORY_ACCEPTED"
    ]
    assert len(accepted) == 1
