"""Conversation Manager — CONCIERGE.md §5.5/§16.

Unit tests of `ConversationManager` itself: which action_types create a
`PendingAction`, the confirm/cancel/unclear resolution paths, and
expiry. Router integration (the reorder that checks for an active
`PendingAction` before Intent Classification) is covered separately in
test_conversation_manager_router_integration.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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
    PendingAction,
    PendingActionStatus,
    Property,
    Task,
    Tenant,
)
from app.services.action_logger import action_logger
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


def _make_guest(db, *, tenant_id):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest")
    db.add(guest)
    db.flush()
    return guest


def _log_offer_proposed(db, *, tenant_id, guest_id, correlation_id=None):
    return action_logger.log_action(
        db,
        tenant_id=tenant_id,
        guest_id=guest_id,
        intent="service_request",
        agent="revenue",
        action_type="OFFER_PROPOSED",
        actor=ActorType.ai,
        input_summary="Guest requested late checkout.",
        decision="RevenueAgent proposed paid late checkout.",
        status=ActionEventStatus.proposed,
        correlation_id=correlation_id,
    )


def _build_context(db, *, tenant_id, guest_id):
    return ContextBuilder(db).build(tenant_id=tenant_id, guest_id=guest_id)


def test_register_proposal_creates_pending_action_for_offer_proposed(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-a")
    event = _log_offer_proposed(db, tenant_id="hotel-a", guest_id=guest.id)

    pending = conversation_manager.register_proposal(db, event=event)

    assert pending is not None
    assert pending.tenant_id == "hotel-a"
    assert pending.guest_id == guest.id
    assert pending.origin_action_type == "OFFER_PROPOSED"
    assert pending.origin_intent == "service_request"
    assert pending.correlation_id == event.correlation_id
    assert pending.status == PendingActionStatus.pending
    assert pending.expires_at > datetime.utcnow()


@pytest.mark.parametrize("action_type,agent", [("ORDER_PROPOSED", "ordering"), ("MEMORY_PROPOSED", "guest_memory"), ("FAQ_ANSWERED", "faq")])
def test_register_proposal_returns_none_for_non_confirmable_action_types(db_session, action_type, agent):
    """ORDER_PROPOSED and MEMORY_PROPOSED are informational today (no
    agent asks the guest a real yes/no question yet) — no PendingAction
    should be created for them, even though their ActionEvent exists."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-b")
    event = action_logger.log_action(
        db, tenant_id="hotel-b", guest_id=guest.id, intent="order", agent=agent,
        action_type=action_type, actor=ActorType.ai,
        input_summary="Guest message.", decision="Agent responded.",
    )

    pending = conversation_manager.register_proposal(db, event=event)

    assert pending is None


def test_register_proposal_defers_a_second_proposal_while_one_is_active(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-c")
    first_event = _log_offer_proposed(db, tenant_id="hotel-c", guest_id=guest.id)
    first_pending = conversation_manager.register_proposal(db, event=first_event)
    assert first_pending is not None

    second_event = _log_offer_proposed(db, tenant_id="hotel-c", guest_id=guest.id)
    second_pending = conversation_manager.register_proposal(db, event=second_event)

    # The second proposal's ActionEvent still exists in the ledger...
    assert second_event.id is not None
    assert second_event.action_type == "OFFER_PROPOSED"
    # ...it just never became the active conversational thread.
    assert second_pending is None
    active = conversation_manager.find_active(db, tenant_id="hotel-c", guest_id=guest.id)
    assert active.id == first_pending.id


def test_resolve_confirm_creates_offer_accepted_and_task_created_events(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-d")
    event = _log_offer_proposed(db, tenant_id="hotel-d", guest_id=guest.id)
    pending = conversation_manager.register_proposal(db, event=event)
    context = _build_context(db, tenant_id="hotel-d", guest_id=guest.id)

    response = conversation_manager.resolve(db, context, pending, "Yes please, go ahead")

    assert response.handled is True
    assert response.should_escalate is False

    events = db.query(ActionEvent).filter(ActionEvent.correlation_id == event.correlation_id).all()
    by_type = {e.action_type: e for e in events}
    assert set(by_type) == {"OFFER_PROPOSED", "OFFER_ACCEPTED", "TASK_CREATED"}
    assert by_type["OFFER_ACCEPTED"].actor == ActorType.guest
    assert by_type["TASK_CREATED"].actor == ActorType.system

    refreshed = db.query(PendingAction).filter(PendingAction.id == pending.id).one()
    assert refreshed.status == PendingActionStatus.resolved
    assert refreshed.resolved_at is not None

    task = db.query(Task).filter(Task.tenant_id == "hotel-d").one()
    assert task.related_id == guest.id


def test_resolve_cancel_creates_offer_rejected_event(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-e")
    event = _log_offer_proposed(db, tenant_id="hotel-e", guest_id=guest.id)
    pending = conversation_manager.register_proposal(db, event=event)
    context = _build_context(db, tenant_id="hotel-e", guest_id=guest.id)

    response = conversation_manager.resolve(db, context, pending, "No thanks, never mind")

    assert response.handled is True
    events = db.query(ActionEvent).filter(ActionEvent.correlation_id == event.correlation_id).all()
    action_types = {e.action_type for e in events}
    assert action_types == {"OFFER_PROPOSED", "OFFER_REJECTED"}

    refreshed = db.query(PendingAction).filter(PendingAction.id == pending.id).one()
    assert refreshed.status == PendingActionStatus.cancelled

    # No staff Task for a decline — nothing needs executing.
    assert db.query(Task).filter(Task.tenant_id == "hotel-e").count() == 0


def test_resolve_unclear_reply_logs_nothing_and_stays_pending(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-f")
    event = _log_offer_proposed(db, tenant_id="hotel-f", guest_id=guest.id)
    pending = conversation_manager.register_proposal(db, event=event)
    context = _build_context(db, tenant_id="hotel-f", guest_id=guest.id)

    response = conversation_manager.resolve(db, context, pending, "What time is breakfast?")

    assert response.handled is True
    events = db.query(ActionEvent).filter(ActionEvent.correlation_id == event.correlation_id).all()
    assert [e.action_type for e in events] == ["OFFER_PROPOSED"]

    refreshed = db.query(PendingAction).filter(PendingAction.id == pending.id).one()
    assert refreshed.status == PendingActionStatus.pending


def test_expire_stale_closes_past_due_pending_actions(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-g")
    event = _log_offer_proposed(db, tenant_id="hotel-g", guest_id=guest.id)
    pending = conversation_manager.register_proposal(db, event=event)
    pending.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()

    expired = conversation_manager.expire_stale(db, tenant_id="hotel-g")

    assert len(expired) == 1
    assert expired[0].id == pending.id
    assert expired[0].status == PendingActionStatus.expired

    events = db.query(ActionEvent).filter(ActionEvent.correlation_id == event.correlation_id).all()
    action_types = {e.action_type for e in events}
    assert action_types == {"OFFER_PROPOSED", "OFFER_EXPIRED"}
    expired_event = next(e for e in events if e.action_type == "OFFER_EXPIRED")
    assert expired_event.actor == ActorType.system


def test_expire_stale_leaves_unexpired_pending_actions_alone(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-h")
    event = _log_offer_proposed(db, tenant_id="hotel-h", guest_id=guest.id)
    conversation_manager.register_proposal(db, event=event)

    expired = conversation_manager.expire_stale(db, tenant_id="hotel-h")

    assert expired == []
    active = conversation_manager.find_active(db, tenant_id="hotel-h", guest_id=guest.id)
    assert active is not None
