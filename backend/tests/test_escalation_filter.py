"""Escalation Filter — CONCIERGE.md §5.4/§8, Week 1 remaining step 2.

Pure unit tests of the deterministic decision function, plus one
integration-level check that a real inbound WhatsApp message wires
through to a staff Task exactly when it should.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import Guest, Property, PropertyKnowledgeBase, Task, Tenant
from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    GuestContext,
    KnowledgeBaseContext,
    PropertyContext,
)
from app.services.context_builder import ContextBuilder
from app.services.escalation_filter import (
    EscalationCategory,
    escalate_to_staff,
    evaluate_escalation,
)
from app.services.messaging import ingest_inbound_whatsapp


@pytest.fixture(autouse=True)
def _clear_context_cache():
    ContextBuilder.clear_cache()
    yield
    ContextBuilder.clear_cache()


def _make_context(knowledge_base: KnowledgeBaseContext | None = None) -> ConciergeContext:
    return ConciergeContext(
        tenant_id="hotel-x",
        property=PropertyContext(
            id="prop-1", name="Hotel X", timezone="UTC", currency="EUR", brand_voice="Warm"
        ),
        guest=GuestContext(
            id="guest-1",
            name="Guest",
            language="en",
            communication_preference="whatsapp",
            stay_count=1,
            lifetime_spend=0.0,
            previous_reviews=0,
            complaint_history=0,
            upsell_acceptance=0.0,
        ),
        current_time=datetime.utcnow(),
        channel=ChannelMetadata(channel="whatsapp"),
        knowledge_base=knowledge_base,
    )


@pytest.mark.parametrize(
    "message,expected_category",
    [
        ("I think I'm having an allergic reaction", EscalationCategory.medical),
        ("There's a gas leak in my room", EscalationCategory.safety),
        ("This is an emergency, please help", EscalationCategory.emergency),
        ("I want a refund, you overcharged me", EscalationCategory.refund_billing),
        ("The room was dirty and the shower is broken", EscalationCategory.complaint),
        ("Someone is harassing me in the lobby", EscalationCategory.threat_abuse_harassment),
        ("Can I speak to a manager please", EscalationCategory.human_requested),
    ],
)
def test_hard_trigger_categories_always_escalate(message, expected_category):
    decision = evaluate_escalation(message, _make_context())
    assert decision.needs_human is True
    assert decision.category == expected_category


def test_recognized_topic_with_answer_does_not_escalate():
    kb = KnowledgeBaseContext(wifi_password="guest123")
    decision = evaluate_escalation("What's the wifi password?", _make_context(kb))
    assert decision.needs_human is False
    assert decision.category == EscalationCategory.none


def test_recognized_topic_with_no_answer_escalates():
    kb = KnowledgeBaseContext(wifi_password=None)  # KB exists but field empty
    decision = evaluate_escalation("What's the wifi password?", _make_context(kb))
    assert decision.needs_human is True
    assert decision.category == EscalationCategory.outside_knowledge_base


def test_no_knowledge_base_at_all_escalates_recognized_topic():
    decision = evaluate_escalation("What's the wifi password?", _make_context(None))
    assert decision.needs_human is True
    assert decision.category == EscalationCategory.outside_knowledge_base


def test_unrecognized_message_escalates():
    decision = evaluate_escalation("Do you sell lottery tickets here?", _make_context())
    assert decision.needs_human is True
    assert decision.category == EscalationCategory.outside_knowledge_base


def test_medical_pattern_takes_priority_over_knowledge_base_topic_overlap():
    # "broken" is a complaint-pattern word, but a real emergency phrase
    # should still win if it appears — patterns are checked before any
    # KB-topic matching, and emergency is checked before complaint.
    decision = evaluate_escalation(
        "Emergency — my child broke their arm by the pool", _make_context()
    )
    assert decision.category == EscalationCategory.emergency


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


def test_escalate_to_staff_creates_critical_priority_task(db_session):
    db = db_session
    db.add(Tenant(id="hotel-y", name="hotel-y"))
    db.flush()
    decision = evaluate_escalation("I need an ambulance", _make_context())
    task = escalate_to_staff(
        db,
        tenant_id="hotel-y",
        guest_id="guest-9",
        guest_name="Jane Doe",
        message_body="I need an ambulance",
        decision=decision,
    )
    assert task.priority.value == "critical"
    assert task.related_type == "guest"
    assert task.related_id == "guest-9"
    assert "emergency" in task.title.lower()


def test_inbound_whatsapp_escalation_creates_task_for_unsafe_message(db_session):
    db = db_session
    db.add(Tenant(id="hotel-z", name="hotel-z"))
    property_ = Property(
        tenant_id="hotel-z", name="Hotel Z", city="Berlin", country="Germany"
    )
    db.add(property_)
    db.flush()
    guest = Guest(
        tenant_id="hotel-z", property_id=property_.id, name="Guest Z", phone="+15551234567"
    )
    db.add(guest)
    db.flush()

    ingest_inbound_whatsapp(
        db, tenant_id="hotel-z", from_phone="+15551234567", body="I have a complaint about the noise"
    )

    tasks = db.query(Task).filter(Task.tenant_id == "hotel-z").all()
    assert len(tasks) == 1
    assert tasks[0].related_id == guest.id


def test_inbound_whatsapp_recognized_answerable_topic_creates_no_task(db_session):
    db = db_session
    db.add(Tenant(id="hotel-w", name="hotel-w"))
    property_ = Property(
        tenant_id="hotel-w", name="Hotel W", city="Berlin", country="Germany"
    )
    db.add(property_)
    db.flush()
    db.add(
        PropertyKnowledgeBase(
            property_id=property_.id, tenant_id="hotel-w", breakfast_hours="7-10am"
        )
    )
    guest = Guest(
        tenant_id="hotel-w", property_id=property_.id, name="Guest W", phone="+15559876543"
    )
    db.add(guest)
    db.flush()

    ingest_inbound_whatsapp(
        db, tenant_id="hotel-w", from_phone="+15559876543", body="What time is breakfast?"
    )

    tasks = db.query(Task).filter(Task.tenant_id == "hotel-w").all()
    assert len(tasks) == 0
