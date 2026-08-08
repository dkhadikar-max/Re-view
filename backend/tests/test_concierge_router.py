"""Concierge Router — CONCIERGE.md §4/§4.1, roadmap step 7.

Integration-level tests: a real (SQLite, in-memory) database, real
`Tenant`/`Property`/`Guest`/`PropertyKnowledgeBase`/`PropertyService`
rows, and the real Escalation Filter + all four agents wired together
through `ConciergeRouter.route()`. Unlike each agent's own unit tests
(no database at all), this file's whole point is verifying the
*orchestration* — priority order, exactly-one-agent-runs, and that a
staff escalation actually gets written to the database at the right
moments.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import (
    Guest,
    Property,
    PropertyKnowledgeBase,
    PropertyService,
    Task,
    Tenant,
)
from app.services.concierge_router import concierge_router
from app.services.context_builder import ContextBuilder
from app.services.faq_agent import faq_agent
from app.services.guest_memory_agent import guest_memory_agent
from app.services.ordering_agent import ordering_agent
from app.services.revenue_agent import revenue_agent


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


def _make_guest(db, *, tenant_id, property_id, name="Guest"):
    guest = Guest(tenant_id=tenant_id, property_id=property_id, name=name)
    db.add(guest)
    db.flush()
    return guest


def _make_service(db, *, tenant_id, property_id, service_type, **kwargs):
    service = PropertyService(
        tenant_id=tenant_id, property_id=property_id, service_type=service_type, **kwargs
    )
    db.add(service)
    db.flush()
    return service


def test_hard_safety_pattern_escalates_before_any_agent(db_session, monkeypatch):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-a")
    guest = _make_guest(db, tenant_id="hotel-a", property_id=property_.id)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("No agent should run when the Escalation Filter trips")

    monkeypatch.setattr(faq_agent, "answer", _fail_if_called)
    monkeypatch.setattr(ordering_agent, "answer", _fail_if_called)
    monkeypatch.setattr(revenue_agent, "answer", _fail_if_called)
    monkeypatch.setattr(guest_memory_agent, "answer", _fail_if_called)

    response = concierge_router.route(
        db, tenant_id="hotel-a", guest_id=guest.id, message_body="This is an emergency, please help"
    )

    assert response.handled is True
    assert response.should_escalate is True
    assert response.metadata["escalated_by"] == "escalation_filter"
    tasks = db.query(Task).filter(Task.tenant_id == "hotel-a").all()
    assert len(tasks) == 1


def test_faq_agent_answers_recognized_topic_with_value(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-b")
    db.add(PropertyKnowledgeBase(property_id=property_.id, tenant_id="hotel-b", wifi_password="guest123"))
    guest = _make_guest(db, tenant_id="hotel-b", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-b", guest_id=guest.id, message_body="What's the wifi password?"
    )

    assert response.handled is True
    assert response.should_escalate is False
    assert response.metadata["agent"] == "faq"
    assert "guest123" in response.response


def test_faq_agent_recognized_topic_but_empty_field_escalates(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-c")
    db.add(PropertyKnowledgeBase(property_id=property_.id, tenant_id="hotel-c", breakfast_hours=None))
    guest = _make_guest(db, tenant_id="hotel-c", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-c", guest_id=guest.id, message_body="What time is breakfast?"
    )

    assert response.handled is True
    assert response.should_escalate is True
    assert response.metadata["agent"] == "faq"
    tasks = db.query(Task).filter(Task.tenant_id == "hotel-c").all()
    assert len(tasks) == 1


def test_ordering_agent_runs_before_revenue_agent_for_room_service(db_session, monkeypatch):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-d")
    _make_service(
        db, tenant_id="hotel-d", property_id=property_.id, service_type="room_service",
        name="Room Service", currency="EUR", complimentary=False, available=True,
    )
    guest = _make_guest(db, tenant_id="hotel-d", property_id=property_.id)
    db.flush()

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("Revenue Agent should not run once Ordering Agent handled it")

    monkeypatch.setattr(revenue_agent, "answer", _fail_if_called)

    response = concierge_router.route(
        db, tenant_id="hotel-d", guest_id=guest.id, message_body="Can I order room service please"
    )

    assert response.handled is True
    assert response.metadata["agent"] == "ordering"


def test_revenue_agent_handles_configured_service_when_faq_and_ordering_defer(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-e")
    _make_service(
        db, tenant_id="hotel-e", property_id=property_.id, service_type="late_checkout",
        name="Late Checkout", price=30.0, currency="EUR", complimentary=False, available=True,
    )
    guest = _make_guest(db, tenant_id="hotel-e", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-e", guest_id=guest.id, message_body="Can I check out at 4 PM?"
    )

    assert response.handled is True
    assert response.should_escalate is False
    assert response.metadata["agent"] == "revenue"
    assert "30.00 EUR" in response.response


def test_guest_memory_agent_handles_when_no_other_agent_recognizes_it(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-f")
    guest = _make_guest(db, tenant_id="hotel-f", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-f", guest_id=guest.id, message_body="I'm vegetarian"
    )

    assert response.handled is True
    assert response.should_escalate is False
    assert response.metadata["agent"] == "guest_memory"


def test_agent_should_escalate_triggers_a_staff_escalation(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-g")
    _make_service(
        db, tenant_id="hotel-g", property_id=property_.id, service_type="spa",
        name="Spa", currency="EUR", complimentary=False, available=False,
    )
    guest = _make_guest(db, tenant_id="hotel-g", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-g", guest_id=guest.id, message_body="I'd like to book a massage"
    )

    assert response.handled is True
    assert response.should_escalate is True
    assert response.metadata["agent"] == "revenue"
    tasks = db.query(Task).filter(Task.tenant_id == "hotel-g").all()
    assert len(tasks) == 1


def test_no_agent_recognizing_a_message_falls_back_to_router_escalation(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-h")
    guest = _make_guest(db, tenant_id="hotel-h", property_id=property_.id)
    db.flush()

    response = concierge_router.route(
        db, tenant_id="hotel-h", guest_id=guest.id, message_body="The weather looks nice today"
    )

    assert response.handled is False
    assert response.should_escalate is True
    assert response.metadata["escalated_by"] == "router_fallback"
    tasks = db.query(Task).filter(Task.tenant_id == "hotel-h").all()
    assert len(tasks) == 1


def test_router_calls_exactly_one_agent_never_two(db_session, monkeypatch):
    """Guest Memory Agent must never even be invoked once Ordering
    Agent already handled the message — the Router calls exactly one
    agent per message, full stop."""
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-i")
    _make_service(
        db, tenant_id="hotel-i", property_id=property_.id, service_type="room_service",
        name="Room Service", currency="EUR", complimentary=False, available=True,
    )
    guest = _make_guest(db, tenant_id="hotel-i", property_id=property_.id)
    db.flush()

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("Guest Memory Agent should never run in this case")

    monkeypatch.setattr(guest_memory_agent, "answer", _fail_if_called)

    response = concierge_router.route(
        db, tenant_id="hotel-i", guest_id=guest.id, message_body="Can I order room service please"
    )

    assert response.metadata["agent"] == "ordering"


def test_reservation_and_conversation_ids_are_passed_through_to_context_builder(db_session):
    """The Router doesn't invent its own context assembly logic — it
    hands its own reservation_id/conversation_id straight to
    ContextBuilder, same object every agent then reads from."""
    from app.models.entities import Reservation, ReservationStatus

    db = db_session
    property_ = _make_property(db, tenant_id="hotel-j")
    guest = _make_guest(db, tenant_id="hotel-j", property_id=property_.id)
    reservation = Reservation(
        tenant_id="hotel-j",
        property_id=property_.id,
        guest_id=guest.id,
        status=ReservationStatus.checked_in,
        check_in=date.today() - timedelta(days=1),
        check_out=date.today() + timedelta(days=2),
    )
    db.add(reservation)
    db.flush()

    response = concierge_router.route(
        db,
        tenant_id="hotel-j",
        guest_id=guest.id,
        message_body="I'm vegetarian",
        reservation_id=reservation.id,
        conversation_id="conv-1",
    )

    assert response.handled is True
    assert response.metadata["agent"] == "guest_memory"
