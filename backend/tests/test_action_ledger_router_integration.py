"""Action Ledger — Router integration (CONCIERGE.md's "Action Ledger"
section). Verifies `ConciergeRouter.route()` records exactly one
`ActionEvent` per call, for every one of the seven scenarios named in
the spec: FAQ answered, Revenue offer proposed, Memory proposal, Order
proposal, Escalation, Small talk, Unknown.

Real (SQLite, in-memory) database, the real Escalation Filter, Intent
Classifier, and all four agents — same fixture pattern as
test_concierge_router.py. This file's only concern is the Action
Ledger's own record, not re-verifying dispatch correctness (already
covered there).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    ActionEvent,
    ActionEventStatus,
    Guest,
    Property,
    PropertyKnowledgeBase,
    PropertyService,
    Tenant,
)
from app.services.concierge_router import concierge_router
from app.services.context_builder import ContextBuilder


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


def _make_guest(db, *, tenant_id, property_id):
    guest = Guest(tenant_id=tenant_id, property_id=property_id, name="Guest")
    db.add(guest)
    db.flush()
    return guest


def _events(db, tenant_id):
    return db.query(ActionEvent).filter(ActionEvent.tenant_id == tenant_id).all()


def test_faq_answered_creates_one_completed_action_event(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-a")
    db.add(PropertyKnowledgeBase(property_id=property_.id, tenant_id="hotel-a", wifi_password="guest123"))
    guest = _make_guest(db, tenant_id="hotel-a", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-a", guest_id=guest.id, message_body="What's the wifi password?")

    events = _events(db, "hotel-a")
    assert len(events) == 1
    event = events[0]
    assert event.intent == "information"
    assert event.agent == "faq"
    assert event.action_type == "faq_answered"
    assert event.status == ActionEventStatus.completed
    assert "guest123" in event.output_summary


def test_revenue_offer_proposed_creates_one_proposed_action_event(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-b")
    db.add(
        PropertyService(
            tenant_id="hotel-b", property_id=property_.id, service_type="late_checkout",
            name="Late Checkout", price=30.0, currency="EUR", complimentary=False, available=True,
        )
    )
    guest = _make_guest(db, tenant_id="hotel-b", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-b", guest_id=guest.id, message_body="Can I check out at 4 PM?")

    events = _events(db, "hotel-b")
    assert len(events) == 1
    event = events[0]
    assert event.intent == "service_request"
    assert event.agent == "revenue"
    assert event.action_type == "revenue_offer_proposed"
    assert event.status == ActionEventStatus.proposed
    assert "30.00 EUR" in event.output_summary


def test_memory_proposal_creates_one_proposed_action_event(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-c")
    guest = _make_guest(db, tenant_id="hotel-c", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-c", guest_id=guest.id, message_body="I'm vegetarian")

    events = _events(db, "hotel-c")
    assert len(events) == 1
    event = events[0]
    assert event.intent == "memory"
    assert event.agent == "guest_memory"
    assert event.action_type == "memory_proposal"
    assert event.status == ActionEventStatus.proposed


def test_order_proposal_creates_one_proposed_action_event(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-d")
    db.add(
        PropertyService(
            tenant_id="hotel-d", property_id=property_.id, service_type="room_service",
            name="Room Service", currency="EUR", complimentary=False, available=True,
        )
    )
    guest = _make_guest(db, tenant_id="hotel-d", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-d", guest_id=guest.id, message_body="I'm hungry")

    events = _events(db, "hotel-d")
    assert len(events) == 1
    event = events[0]
    assert event.intent == "order"
    assert event.agent == "ordering"
    assert event.action_type == "order_proposal"
    assert event.status == ActionEventStatus.proposed


def test_escalation_creates_one_escalated_action_event(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-e")
    guest = _make_guest(db, tenant_id="hotel-e", property_id=property_.id)
    db.flush()

    concierge_router.route(
        db, tenant_id="hotel-e", guest_id=guest.id, message_body="This is an emergency, please help"
    )

    events = _events(db, "hotel-e")
    assert len(events) == 1
    event = events[0]
    assert event.intent == "escalation"
    assert event.agent is None
    assert event.action_type == "escalation"
    assert event.status == ActionEventStatus.escalated


def test_small_talk_creates_one_completed_action_event(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-f")
    guest = _make_guest(db, tenant_id="hotel-f", property_id=property_.id)
    db.flush()

    concierge_router.route(
        db, tenant_id="hotel-f", guest_id=guest.id, message_body="Thanks so much, see you soon!"
    )

    events = _events(db, "hotel-f")
    assert len(events) == 1
    event = events[0]
    assert event.intent == "small_talk"
    assert event.agent is None
    assert event.action_type == "small_talk_acknowledged"
    assert event.status == ActionEventStatus.completed


def test_unknown_intent_creates_one_escalated_action_event(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-g")
    guest = _make_guest(db, tenant_id="hotel-g", property_id=property_.id)
    db.flush()

    concierge_router.route(
        db, tenant_id="hotel-g", guest_id=guest.id, message_body="The weather looks nice today"
    )

    events = _events(db, "hotel-g")
    assert len(events) == 1
    event = events[0]
    assert event.intent == "unknown"
    assert event.agent is None
    assert event.action_type == "unknown_intent_escalated"
    assert event.status == ActionEventStatus.escalated


def test_agent_handled_but_should_escalate_creates_one_escalated_action_event(db_session):
    """A configured-but-unavailable service (Revenue Agent handles it,
    then sets should_escalate=True) is a distinct sixth path — still
    exactly one ActionEvent, tagged escalated with the agent recorded."""
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-h")
    db.add(
        PropertyService(
            tenant_id="hotel-h", property_id=property_.id, service_type="spa",
            name="Spa", currency="EUR", complimentary=False, available=False,
        )
    )
    guest = _make_guest(db, tenant_id="hotel-h", property_id=property_.id)
    db.flush()

    concierge_router.route(db, tenant_id="hotel-h", guest_id=guest.id, message_body="I'd like to book a massage")

    events = _events(db, "hotel-h")
    assert len(events) == 1
    event = events[0]
    assert event.agent == "revenue"
    assert event.action_type == "revenue_escalated"
    assert event.status == ActionEventStatus.escalated


def test_reservation_and_conversation_id_are_recorded_on_the_event(db_session):
    from datetime import date, timedelta

    from app.models.entities import Reservation, ReservationStatus

    db = db_session
    property_ = _make_property(db, tenant_id="hotel-i")
    guest = _make_guest(db, tenant_id="hotel-i", property_id=property_.id)
    reservation = Reservation(
        tenant_id="hotel-i", property_id=property_.id, guest_id=guest.id,
        status=ReservationStatus.checked_in,
        check_in=date.today() - timedelta(days=1), check_out=date.today() + timedelta(days=2),
    )
    db.add(reservation)
    db.flush()

    concierge_router.route(
        db, tenant_id="hotel-i", guest_id=guest.id, message_body="I'm vegetarian",
        reservation_id=reservation.id, conversation_id="conv-42",
    )

    events = _events(db, "hotel-i")
    assert len(events) == 1
    assert events[0].reservation_id == reservation.id
    assert events[0].conversation_id == "conv-42"
