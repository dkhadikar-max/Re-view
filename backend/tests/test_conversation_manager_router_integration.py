"""Conversation Manager — Router integration (CONCIERGE.md §5.5/§16).

Verifies the Router reorder: `ConciergeRouter.route()` checks for an
active `PendingAction` *before* Intent Classification, and hands a
reply to `ConversationManager` instead of re-classifying it. Real
(SQLite, in-memory) database and the full pipeline — same fixture
pattern as test_action_ledger_router_integration.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    ActionEvent,
    Guest,
    PendingAction,
    PendingActionStatus,
    Property,
    PropertyService,
    Task,
    Tenant,
)
from app.services.concierge_router import concierge_router
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import conversation_manager


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


def _make_property_with_late_checkout(db, *, tenant_id):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    db.add(
        PropertyService(
            tenant_id=tenant_id, property_id=property_.id, service_type="late_checkout",
            name="Late Checkout", price=30.0, currency="EUR", complimentary=False, available=True,
        )
    )
    return property_


def _make_guest(db, *, tenant_id, property_id):
    guest = Guest(tenant_id=tenant_id, property_id=property_id, name="Guest")
    db.add(guest)
    db.flush()
    return guest


def test_offer_proposed_creates_a_pending_action(db_session):
    db = db_session
    property_ = _make_property_with_late_checkout(db, tenant_id="hotel-a")
    guest = _make_guest(db, tenant_id="hotel-a", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-a", guest_id=guest.id, message_body="Can I check out at 4 PM?")

    pending = conversation_manager.find_active(db, tenant_id="hotel-a", guest_id=guest.id)
    assert pending is not None
    assert pending.origin_action_type == "OFFER_PROPOSED"


def test_guest_confirming_an_offer_is_never_reclassified(db_session):
    """The core of the reorder: a reply that would otherwise be
    ambiguous or match SMALL_TALK must be interpreted as a confirmation
    of the open offer, not re-classified from scratch."""
    db = db_session
    property_ = _make_property_with_late_checkout(db, tenant_id="hotel-b")
    guest = _make_guest(db, tenant_id="hotel-b", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-b", guest_id=guest.id, message_body="Can I check out at 4 PM?")
    response = concierge_router.route(db, tenant_id="hotel-b", guest_id=guest.id, message_body="Yes, thank you!")

    assert response.handled is True
    assert response.metadata.get("conversation_manager") == "accepted"

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-b").all()
    action_types = {e.action_type for e in events}
    assert "OFFER_ACCEPTED" in action_types
    assert "TASK_CREATED" in action_types
    # Never classified as small talk despite "thank you" — it resolved
    # the pending offer instead.
    assert "SMALL_TALK" not in action_types

    pending = db.query(PendingAction).filter(PendingAction.tenant_id == "hotel-b").one()
    assert pending.status == PendingActionStatus.resolved

    task = db.query(Task).filter(Task.tenant_id == "hotel-b").one()
    assert task.related_id == guest.id


def test_guest_declining_an_offer_is_handled_by_conversation_manager(db_session):
    db = db_session
    property_ = _make_property_with_late_checkout(db, tenant_id="hotel-c")
    guest = _make_guest(db, tenant_id="hotel-c", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-c", guest_id=guest.id, message_body="Can I check out at 4 PM?")
    response = concierge_router.route(db, tenant_id="hotel-c", guest_id=guest.id, message_body="No, never mind")

    assert response.metadata.get("conversation_manager") == "rejected"
    pending = db.query(PendingAction).filter(PendingAction.tenant_id == "hotel-c").one()
    assert pending.status == PendingActionStatus.cancelled

    events = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-c").all()
    assert any(e.action_type == "OFFER_REJECTED" for e in events)


def test_ambiguous_reply_while_pending_never_reaches_intent_classification(db_session):
    """Once a PendingAction is active, the reorder means EVERY reply
    goes to ConversationManager.resolve() first — an ambiguous reply
    can never be re-classified into a fresh intent (no second agent
    call, no new ActionEvent, no second PendingAction), it just leaves
    the original offer open and asks the guest to clarify. This is a
    different guarantee than "a second real proposal gets deferred"
    (that path only exists inside ConversationManager itself, exercised
    directly in test_conversation_manager.py, since the Router's own
    reorder means an agent is never even called while a PendingAction
    is active)."""
    db = db_session
    property_ = _make_property_with_late_checkout(db, tenant_id="hotel-d")
    guest = _make_guest(db, tenant_id="hotel-d", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-d", guest_id=guest.id, message_body="Can I check out at 4 PM?")
    first_pending = conversation_manager.find_active(db, tenant_id="hotel-d", guest_id=guest.id)
    assert first_pending is not None
    events_before = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-d").count()

    response = concierge_router.route(
        db, tenant_id="hotel-d", guest_id=guest.id, message_body="What about the pool hours?"
    )

    assert response.metadata.get("conversation_manager") == "clarify"
    events_after = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-d").count()
    assert events_after == events_before  # the unclear reply logged nothing new

    still_active = conversation_manager.find_active(db, tenant_id="hotel-d", guest_id=guest.id)
    assert still_active is not None
    assert still_active.id == first_pending.id


def test_pending_action_survives_across_separate_route_calls(db_session):
    """Resuming an interrupted flow — CONCIERGE.md §5.5's own wording —
    means the state has to persist across separate `route()` calls, not
    just within one. Three-turn conversation: propose, ask something
    else the Conversation Manager still treats as a pending reply,
    then finally confirm."""
    db = db_session
    property_ = _make_property_with_late_checkout(db, tenant_id="hotel-e")
    guest = _make_guest(db, tenant_id="hotel-e", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-e", guest_id=guest.id, message_body="Can I check out at 4 PM?")
    concierge_router.route(db, tenant_id="hotel-e", guest_id=guest.id, message_body="Hmm let me think")
    response = concierge_router.route(db, tenant_id="hotel-e", guest_id=guest.id, message_body="OK yes, go ahead")

    assert response.metadata.get("conversation_manager") == "accepted"
    pending = db.query(PendingAction).filter(PendingAction.tenant_id == "hotel-e").one()
    assert pending.status == PendingActionStatus.resolved
