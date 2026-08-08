"""Action Ledger — CONCIERGE.md's "Action Ledger" section.

Unit tests of `ActionLogger` itself: creation, the four allowed status
transitions, immutability of every other field, tenant isolation, and
timestamps. No Router or agent involved here — that integration is
covered separately in test_concierge_router.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import ActionEvent, ActionEventStatus, Guest, Property, Tenant
from app.services.action_logger import action_logger


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


def test_log_action_creates_a_row_with_every_field(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-a")

    event = action_logger.log_action(
        db,
        tenant_id="hotel-a",
        guest_id=guest.id,
        reservation_id="res-1",
        conversation_id="conv-1",
        intent="information",
        agent="faq",
        action_type="faq_answered",
        confidence=0.85,
        input_summary="What's the wifi password?",
        decision="Answered from knowledge_base.wifi_password",
        output_summary="Our WiFi password is: guest123",
        status=ActionEventStatus.completed,
        metadata={"source": "wifi_password"},
    )

    assert event.id is not None
    assert event.tenant_id == "hotel-a"
    assert event.guest_id == guest.id
    assert event.reservation_id == "res-1"
    assert event.conversation_id == "conv-1"
    assert event.intent == "information"
    assert event.agent == "faq"
    assert event.action_type == "faq_answered"
    assert event.confidence == 0.85
    assert event.input_summary == "What's the wifi password?"
    assert event.decision == "Answered from knowledge_base.wifi_password"
    assert event.output_summary == "Our WiFi password is: guest123"
    assert event.status == ActionEventStatus.completed
    assert json.loads(event.event_metadata) == {"source": "wifi_password", "agent_version": "v1"}
    assert isinstance(event.created_at, datetime)
    assert event.correlation_id

    stored = db.query(ActionEvent).filter(ActionEvent.id == event.id).one()
    assert stored.tenant_id == "hotel-a"


def test_log_action_defaults_to_proposed_status(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-b")

    event = action_logger.log_action(
        db,
        tenant_id="hotel-b",
        guest_id=guest.id,
        intent="service_request",
        agent="revenue",
        action_type="revenue_offer_proposed",
        input_summary="Can I check out at 4 PM?",
        decision="Offered late checkout at 30.00 EUR",
    )

    assert event.status == ActionEventStatus.proposed


@pytest.mark.parametrize(
    "method_name,expected_status",
    [
        ("log_accept", ActionEventStatus.accepted),
        ("log_reject", ActionEventStatus.rejected),
        ("log_complete", ActionEventStatus.completed),
        ("log_failure", ActionEventStatus.failed),
    ],
)
def test_transitions_change_only_status(db_session, method_name, expected_status):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-c")

    event = action_logger.log_action(
        db,
        tenant_id="hotel-c",
        guest_id=guest.id,
        intent="service_request",
        agent="revenue",
        action_type="revenue_offer_proposed",
        input_summary="Can I check out at 4 PM?",
        decision="Offered late checkout",
        output_summary="Would you like to book it?",
        metadata={"price": 30.0},
    )
    original_snapshot = {
        "tenant_id": event.tenant_id,
        "guest_id": event.guest_id,
        "correlation_id": event.correlation_id,
        "intent": event.intent,
        "agent": event.agent,
        "action_type": event.action_type,
        "input_summary": event.input_summary,
        "decision": event.decision,
        "output_summary": event.output_summary,
        "event_metadata": event.event_metadata,
        "created_at": event.created_at,
    }

    transition = getattr(action_logger, method_name)
    updated = transition(db, event)

    assert updated.status == expected_status
    for field, original_value in original_snapshot.items():
        assert getattr(updated, field) == original_value, f"{field} must not change on transition"


def test_immutable_fields_survive_multiple_transitions(db_session):
    """Even a sequence of transitions (proposed -> accepted -> completed)
    must never touch anything but status."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-d")

    event = action_logger.log_action(
        db,
        tenant_id="hotel-d",
        guest_id=guest.id,
        intent="order",
        agent="ordering",
        action_type="order_proposal",
        input_summary="I'm hungry",
        decision="Handed off to room service",
    )
    original_decision = event.decision
    original_input = event.input_summary

    action_logger.log_accept(db, event)
    action_logger.log_complete(db, event)

    assert event.status == ActionEventStatus.completed
    assert event.decision == original_decision
    assert event.input_summary == original_input


def test_tenant_isolation(db_session):
    db = db_session
    guest_1 = _make_guest(db, tenant_id="hotel-e1")
    guest_2 = _make_guest(db, tenant_id="hotel-e2")

    action_logger.log_action(
        db, tenant_id="hotel-e1", guest_id=guest_1.id, intent="memory", agent="guest_memory",
        action_type="memory_proposal", input_summary="I'm vegetarian", decision="Proposed dietary_preferences",
    )
    action_logger.log_action(
        db, tenant_id="hotel-e2", guest_id=guest_2.id, intent="memory", agent="guest_memory",
        action_type="memory_proposal", input_summary="I'm vegan", decision="Proposed dietary_preferences",
    )

    events_1 = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-e1").all()
    events_2 = db.query(ActionEvent).filter(ActionEvent.tenant_id == "hotel-e2").all()

    assert len(events_1) == 1 and events_1[0].guest_id == guest_1.id
    assert len(events_2) == 1 and events_2[0].guest_id == guest_2.id


def test_created_at_is_set_and_monotonic_across_events(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-f")

    first = action_logger.log_action(
        db, tenant_id="hotel-f", guest_id=guest.id, intent="unknown", agent=None,
        action_type="unknown_intent_escalated", input_summary="asdf", decision="No intent recognized",
        status=ActionEventStatus.escalated,
    )
    second = action_logger.log_action(
        db, tenant_id="hotel-f", guest_id=guest.id, intent="small_talk", agent=None,
        action_type="small_talk_acknowledged", input_summary="thanks!", decision="Acknowledged",
        status=ActionEventStatus.completed,
    )

    assert first.created_at <= second.created_at
    assert datetime.utcnow() - first.created_at < timedelta(seconds=10)


def test_metadata_defaults_to_just_the_agent_version_stamp(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-g")

    event = action_logger.log_action(
        db, tenant_id="hotel-g", guest_id=guest.id, intent="small_talk", agent=None,
        action_type="small_talk_acknowledged", input_summary="thanks!", decision="Acknowledged",
    )

    assert json.loads(event.event_metadata) == {"agent_version": "v1"}


def test_metadata_agent_version_stamp_does_not_override_a_caller_supplied_one(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-g2")

    event = action_logger.log_action(
        db, tenant_id="hotel-g2", guest_id=guest.id, intent="service_request", agent="revenue",
        action_type="revenue_offer_proposed", input_summary="Guest requested late checkout.",
        decision="RevenueAgent proposed paid late checkout.",
        metadata={"agent_version": "v2", "service_type": "late_checkout"},
    )

    stored = json.loads(event.event_metadata)
    assert stored["agent_version"] == "v2"
    assert stored["service_type"] == "late_checkout"


def test_correlation_id_defaults_to_a_fresh_value_per_event(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-h")

    first = action_logger.log_action(
        db, tenant_id="hotel-h", guest_id=guest.id, intent="service_request", agent="revenue",
        action_type="revenue_offer_proposed", input_summary="Guest requested late checkout.",
        decision="RevenueAgent proposed paid late checkout.",
    )
    second = action_logger.log_action(
        db, tenant_id="hotel-h", guest_id=guest.id, intent="memory", agent="guest_memory",
        action_type="memory_proposal", input_summary="Guest shared a dietary preference.",
        decision="GuestMemoryAgent proposed updating dietary preference.",
    )

    assert first.correlation_id
    assert second.correlation_id
    assert first.correlation_id != second.correlation_id


def test_correlation_id_can_be_passed_through_explicitly(db_session):
    """Once the Conversation Manager exists, resuming a pending state
    reuses the original event's correlation_id — verified here at the
    ActionLogger level, independent of that not-yet-built component."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-i")
    shared_id = "shared-correlation-123"

    first = action_logger.log_action(
        db, tenant_id="hotel-i", guest_id=guest.id, intent="service_request", agent="revenue",
        action_type="revenue_offer_proposed", input_summary="Guest requested late checkout.",
        decision="RevenueAgent proposed paid late checkout.", correlation_id=shared_id,
    )
    second = action_logger.log_action(
        db, tenant_id="hotel-i", guest_id=guest.id, intent="service_request", agent="revenue",
        action_type="revenue_confirmed", input_summary="Guest confirmed late checkout.",
        decision="RevenueAgent flagged staff to process late checkout.", correlation_id=shared_id,
    )

    assert first.correlation_id == shared_id
    assert second.correlation_id == shared_id
