"""Conversation Manager's dispatch-back mechanism — MENU_ORDERING.md
§7.2/§7.3/§7.4. `start_clarification()` and `resolve()`'s dispatch-back
branch, tested against a stub `ClarifiableAgent` — no Ordering Agent
logic here at all, mirroring test_conversation_manager.py's own "no AI
on this path" discipline for the pre-existing confirm/cancel flow.

`_CONFIRMABLE_ACTION_TYPES` is monkeypatched with a throwaway
"STUB_PROPOSED" entry for the tests that need a cart to actually
complete — this keeps the mechanism itself provably generic (it never
hardcodes "ORDER_PROPOSED" or any other domain value) without adding a
real taxonomy entry ahead of the Ordering Agent that would use it.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    ActionEvent,
    ActorType,
    Guest,
    PendingAction,
    PendingActionStatus,
    Property,
    Tenant,
)
from app.services import conversation_manager as conversation_manager_module
from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ContextBuilder
from app.services.conversation_manager import conversation_manager


@pytest.fixture(autouse=True)
def _clear_context_cache():
    ContextBuilder.clear_cache()
    yield
    ContextBuilder.clear_cache()


@pytest.fixture(autouse=True)
def _clear_clarifiable_agent_registry():
    """The registry lives on the module-level singleton — reset it
    around every test so one test's stub never leaks into another's."""
    conversation_manager._clarifiable_agents.clear()
    yield
    conversation_manager._clarifiable_agents.clear()


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


class _StubClarifiableAgent:
    """Test double for `ClarifiableAgent` — records every call and
    returns whatever the test configured next. No menu/cart logic."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.next_response: AgentResponse | None = None

    def clarify(self, context, message_body, payload):
        self.calls.append((message_body, dict(payload)))
        assert self.next_response is not None, "test forgot to set next_response"
        return self.next_response


def _make_guest(db, *, tenant_id):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest")
    db.add(guest)
    db.flush()
    return guest


def _build_context(db, *, tenant_id, guest_id):
    return ContextBuilder(db).build(tenant_id=tenant_id, guest_id=guest_id)


def _start(db, *, tenant_id, guest_id, payload, origin_agent="stub"):
    return conversation_manager.start_clarification(
        db,
        tenant_id=tenant_id,
        guest_id=guest_id,
        origin_agent=origin_agent,
        intent="ordering",
        payload=payload,
    )


# ---------------------------------------------------------------------------
# start_clarification
# ---------------------------------------------------------------------------


def test_start_clarification_creates_pending_action_with_no_origin_action_type(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-a")

    pending = _start(db, tenant_id="hotel-a", guest_id=guest.id, payload={"complete": False})

    assert pending is not None
    assert pending.origin_action_type is None
    assert pending.origin_agent == "stub"
    assert json.loads(pending.payload) == {"complete": False}
    assert pending.status == PendingActionStatus.pending
    # Nothing was proposed yet -- no ActionEvent should exist.
    assert db.query(ActionEvent).count() == 0


def test_start_clarification_defers_second_workflow_while_one_is_active(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-b")
    first = _start(db, tenant_id="hotel-b", guest_id=guest.id, payload={"complete": False})

    second = _start(db, tenant_id="hotel-b", guest_id=guest.id, payload={"complete": False})

    assert second is None
    active = conversation_manager.find_active(db, tenant_id="hotel-b", guest_id=guest.id)
    assert active.id == first.id


# ---------------------------------------------------------------------------
# resolve() dispatch-back
# ---------------------------------------------------------------------------


def test_resolve_dispatches_incomplete_cart_to_registered_agent(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-c")
    pending = _start(db, tenant_id="hotel-c", guest_id=guest.id, payload={"complete": False, "items": []})
    context = _build_context(db, tenant_id="hotel-c", guest_id=guest.id)

    stub = _StubClarifiableAgent()
    stub.next_response = AgentResponse(
        handled=True, response="Anything else?",
        metadata={"payload": {"complete": False, "items": ["burger"]}},
    )
    conversation_manager.register_clarifiable_agent("stub", stub)

    response = conversation_manager.resolve(db, context, pending, "a burger")

    assert stub.calls == [("a burger", {"complete": False, "items": []})]
    assert response.response == "Anything else?"
    refreshed = db.query(PendingAction).filter(PendingAction.id == pending.id).one()
    assert json.loads(refreshed.payload) == {"complete": False, "items": ["burger"]}
    assert refreshed.origin_action_type is None
    assert refreshed.status == PendingActionStatus.pending
    # Still incomplete -- no ActionEvent logged yet.
    assert db.query(ActionEvent).count() == 0


def test_resolve_dispatch_back_logs_action_type_when_cart_becomes_complete(db_session, monkeypatch):
    monkeypatch.setitem(
        conversation_manager_module._CONFIRMABLE_ACTION_TYPES,
        "STUB_PROPOSED",
        ("STUB_CONFIRMED", "STUB_REJECTED", "STUB_EXPIRED"),
    )
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-d")
    pending = _start(db, tenant_id="hotel-d", guest_id=guest.id, payload={"complete": False, "items": ["burger"]})
    context = _build_context(db, tenant_id="hotel-d", guest_id=guest.id)

    stub = _StubClarifiableAgent()
    stub.next_response = AgentResponse(
        handled=True, response="Confirm your order?",
        metadata={
            "payload": {"complete": True, "items": ["burger"]},
            "action_type": "STUB_PROPOSED",
        },
    )
    conversation_manager.register_clarifiable_agent("stub", stub)

    response = conversation_manager.resolve(db, context, pending, "that's all")

    assert response.response == "Confirm your order?"
    refreshed = db.query(PendingAction).filter(PendingAction.id == pending.id).one()
    assert refreshed.origin_action_type == "STUB_PROPOSED"
    assert json.loads(refreshed.payload)["complete"] is True
    # Exactly one ActionEvent -- minted the turn the cart first became complete.
    events = db.query(ActionEvent).filter(ActionEvent.correlation_id == pending.correlation_id).all()
    assert len(events) == 1
    assert events[0].action_type == "STUB_PROPOSED"
    assert events[0].actor == ActorType.ai


def test_resolve_falls_through_to_confirm_cancel_once_cart_is_complete(db_session, monkeypatch):
    """Once origin_action_type is set (the cart just became a real
    proposal), the NEXT resolve() call must use ordinary confirm/cancel
    matching, not dispatch back again -- even though origin_agent is
    still set on the row."""
    monkeypatch.setitem(
        conversation_manager_module._CONFIRMABLE_ACTION_TYPES,
        "STUB_PROPOSED",
        ("STUB_CONFIRMED", "STUB_REJECTED", "STUB_EXPIRED"),
    )
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-e")
    pending = _start(db, tenant_id="hotel-e", guest_id=guest.id, payload={"complete": False})
    context = _build_context(db, tenant_id="hotel-e", guest_id=guest.id)

    stub = _StubClarifiableAgent()
    stub.next_response = AgentResponse(
        handled=True, response="Confirm?",
        metadata={"payload": {"complete": True}, "action_type": "STUB_PROPOSED"},
    )
    conversation_manager.register_clarifiable_agent("stub", stub)
    conversation_manager.resolve(db, context, pending, "that's everything")

    response = conversation_manager.resolve(db, context, pending, "yes please")

    assert len(stub.calls) == 1  # not called a second time
    assert response.metadata["conversation_manager"] == "accepted"
    events = {
        e.action_type
        for e in db.query(ActionEvent).filter(ActionEvent.correlation_id == pending.correlation_id)
    }
    assert events == {"STUB_PROPOSED", "STUB_CONFIRMED", "TASK_CREATED"}


def test_resolve_dispatch_back_abandons_pending_action_on_unresolvable_clarification(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-f")
    pending = _start(db, tenant_id="hotel-f", guest_id=guest.id, payload={"complete": False})
    context = _build_context(db, tenant_id="hotel-f", guest_id=guest.id)

    stub = _StubClarifiableAgent()
    stub.next_response = AgentResponse(handled=False, should_escalate=True, response=None)
    conversation_manager.register_clarifiable_agent("stub", stub)

    response = conversation_manager.resolve(db, context, pending, "asdkjhasd")

    assert response.should_escalate is True
    refreshed = db.query(PendingAction).filter(PendingAction.id == pending.id).one()
    assert refreshed.status == PendingActionStatus.cancelled
    # An abandoned build, not a rejected proposal -- nothing was ever
    # proposed, so nothing is logged.
    assert db.query(ActionEvent).count() == 0


def test_resolve_escalates_when_origin_agent_is_not_registered(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-g")
    pending = _start(db, tenant_id="hotel-g", guest_id=guest.id, payload={"complete": False}, origin_agent="nobody_registered_this")
    context = _build_context(db, tenant_id="hotel-g", guest_id=guest.id)

    response = conversation_manager.resolve(db, context, pending, "anything")

    assert response.should_escalate is True
    assert db.query(ActionEvent).count() == 0


# ---------------------------------------------------------------------------
# expire_stale
# ---------------------------------------------------------------------------


def test_expire_stale_closes_incomplete_cart_without_logging_an_event(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-h")
    pending = _start(db, tenant_id="hotel-h", guest_id=guest.id, payload={"complete": False})
    pending.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()

    expired = conversation_manager.expire_stale(db, tenant_id="hotel-h")

    assert len(expired) == 1
    assert expired[0].status == PendingActionStatus.expired
    # Nothing was ever proposed -- nothing "expired" in the ledger's sense.
    assert db.query(ActionEvent).count() == 0


def test_expire_stale_still_logs_expired_event_for_a_complete_but_unconfirmed_cart(db_session, monkeypatch):
    monkeypatch.setitem(
        conversation_manager_module._CONFIRMABLE_ACTION_TYPES,
        "STUB_PROPOSED",
        ("STUB_CONFIRMED", "STUB_REJECTED", "STUB_EXPIRED"),
    )
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-i")
    pending = _start(db, tenant_id="hotel-i", guest_id=guest.id, payload={"complete": False})
    context = _build_context(db, tenant_id="hotel-i", guest_id=guest.id)
    stub = _StubClarifiableAgent()
    stub.next_response = AgentResponse(
        handled=True, response="Confirm?",
        metadata={"payload": {"complete": True}, "action_type": "STUB_PROPOSED"},
    )
    conversation_manager.register_clarifiable_agent("stub", stub)
    conversation_manager.resolve(db, context, pending, "that's everything")
    pending.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()

    expired = conversation_manager.expire_stale(db, tenant_id="hotel-i")

    assert len(expired) == 1
    events = {
        e.action_type
        for e in db.query(ActionEvent).filter(ActionEvent.correlation_id == pending.correlation_id)
    }
    assert events == {"STUB_PROPOSED", "STUB_EXPIRED"}
