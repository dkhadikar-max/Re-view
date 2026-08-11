"""Escalation Filter — CONCIERGE.md §5.4/§8, Week 1 remaining step 2.

Pure unit tests of the deterministic decision function (no database
involved at all — `evaluate_escalation` doesn't take one), plus
integration-level checks that a real inbound WhatsApp message wires
through to a staff Task and audit log entry exactly when it should.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import AuditLog, Guest, Property, PropertyKnowledgeBase, Task, Tenant
from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    ContextBuilder,
    GuestContext,
    KnowledgeBaseContext,
    PropertyContext,
)
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


def _make_context(
    knowledge_base: KnowledgeBaseContext | None = None,
    *,
    tenant_id: str = "hotel-x",
    guest_id: str = "guest-1",
    guest_name: str = "Guest",
) -> ConciergeContext:
    return ConciergeContext(
        tenant_id=tenant_id,
        property=PropertyContext(
            id="prop-1", name="Hotel X", timezone="UTC", currency="EUR", brand_voice="Warm"
        ),
        guest=GuestContext(
            id=guest_id,
            name=guest_name,
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
    assert decision.escalate is True
    assert decision.category == expected_category
    assert 0.0 < decision.confidence <= 1.0


def test_normal_faq_question_does_not_escalate():
    kb = KnowledgeBaseContext(wifi_password="guest123")
    decision = evaluate_escalation("What's the wifi password?", _make_context(kb))
    assert decision.escalate is False
    assert decision.category is None


def test_recognized_topic_with_no_answer_does_not_escalate_here_anymore():
    """As of the Concierge Router (concierge_router.py), this filter no
    longer runs its own KB-topic pass — a recognized-but-unanswerable
    topic is FAQAgent's own `should_escalate` to raise (see
    test_faq_agent.py's `test_recognized_topic_with_empty_field_escalates`),
    which the Router turns into a real staff escalation after giving
    FAQAgent (and only FAQAgent, since it's asked first) the chance to
    say so. This filter now only ever escalates for a hard safety/
    urgency pattern, regardless of Knowledge Base state."""
    kb = KnowledgeBaseContext(wifi_password=None)  # KB exists but field empty
    decision = evaluate_escalation("What's the wifi password?", _make_context(kb))
    assert decision.escalate is False


def test_no_knowledge_base_at_all_does_not_escalate_here_anymore():
    decision = evaluate_escalation("What's the wifi password?", _make_context(None))
    assert decision.escalate is False


def test_unrecognized_message_does_not_escalate_here_anymore():
    """As of the Concierge Router, an unrecognized message is no longer
    this filter's concern either — Ordering/Revenue/Guest Memory Agents
    each get a real chance to recognize it first; only the Router's own
    fallback (see test_concierge_router.py) escalates if none of the
    four agents do. "When in doubt, escalate" (CONCIERGE.md §0) still
    holds, just one layer up from here now."""
    decision = evaluate_escalation("Do you sell lottery tickets here?", _make_context())
    assert decision.escalate is False


def test_medical_pattern_takes_priority_over_complaint_pattern_overlap():
    # A real emergency phrase should still win even when a complaint-
    # adjacent word ("pool") also appears in the same message — patterns
    # are checked in the fixed, safety-first order defined in
    # _ESCALATION_PATTERNS (emergency before complaint).
    decision = evaluate_escalation(
        "Emergency — my child broke their arm by the pool", _make_context()
    )
    assert decision.category == EscalationCategory.emergency


def test_evaluate_escalation_is_stateless_and_makes_no_database_calls():
    """The filter takes a message + Context and returns a decision —
    nothing else. Calling it twice with the same inputs (as if two
    unrelated conversations asked the same question) gives identical,
    independent results; there's no session, cache, or history inside
    the function itself to produce drift."""
    ctx = _make_context()
    first = evaluate_escalation("I need an ambulance", ctx)
    second = evaluate_escalation("I need an ambulance", ctx)
    assert first == second


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


def test_escalate_to_staff_creates_critical_priority_task_and_audit_entry(db_session):
    db = db_session
    db.add(Tenant(id="hotel-y", name="hotel-y"))
    db.flush()
    context = _make_context(tenant_id="hotel-y", guest_id="guest-9", guest_name="Jane Doe")
    decision = evaluate_escalation("I need an ambulance", context)

    task = escalate_to_staff(
        db,
        context=context,
        message_body="I need an ambulance",
        decision=decision,
        correlation_id="corr-escalation-test",
    )

    assert task.priority.value == "critical"
    assert task.related_type == "guest"
    assert task.related_id == "guest-9"
    assert "emergency" in task.title.lower()
    # PILOT_READINESS.md §5 — the caller-generated correlation_id is
    # stored on the Task verbatim, ready for TASK_COMPLETED to reuse.
    assert task.correlation_id == "corr-escalation-test"

    audit_entries = db.query(AuditLog).filter(AuditLog.tenant_id == "hotel-y").all()
    assert len(audit_entries) == 1
    assert audit_entries[0].action == "escalate"
    assert audit_entries[0].entity_id == "guest-9"
    assert "emergency" in audit_entries[0].details
    assert "ambulance" in audit_entries[0].details


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


def test_multi_tenant_isolation_escalations_stay_scoped_per_tenant(db_session):
    """Two different hotels' guests both send a medical message —
    each escalation must land under its own tenant only, never leak
    into or get counted against the other."""
    db = db_session
    db.add(Tenant(id="hotel-m1", name="hotel-m1"))
    db.add(Tenant(id="hotel-m2", name="hotel-m2"))
    property_1 = Property(tenant_id="hotel-m1", name="Hotel M1", city="Berlin", country="Germany")
    property_2 = Property(tenant_id="hotel-m2", name="Hotel M2", city="Paris", country="France")
    db.add(property_1)
    db.add(property_2)
    db.flush()
    guest_1 = Guest(
        tenant_id="hotel-m1", property_id=property_1.id, name="Guest M1", phone="+15551110000"
    )
    guest_2 = Guest(
        tenant_id="hotel-m2", property_id=property_2.id, name="Guest M2", phone="+15552220000"
    )
    db.add(guest_1)
    db.add(guest_2)
    db.flush()

    ingest_inbound_whatsapp(
        db, tenant_id="hotel-m1", from_phone="+15551110000", body="I have a medical emergency"
    )
    ingest_inbound_whatsapp(
        db, tenant_id="hotel-m2", from_phone="+15552220000", body="I have a medical emergency"
    )

    tasks_1 = db.query(Task).filter(Task.tenant_id == "hotel-m1").all()
    tasks_2 = db.query(Task).filter(Task.tenant_id == "hotel-m2").all()
    assert len(tasks_1) == 1 and tasks_1[0].related_id == guest_1.id
    assert len(tasks_2) == 1 and tasks_2[0].related_id == guest_2.id

    audit_1 = db.query(AuditLog).filter(AuditLog.tenant_id == "hotel-m1").all()
    audit_2 = db.query(AuditLog).filter(AuditLog.tenant_id == "hotel-m2").all()
    assert len(audit_1) == 1 and audit_1[0].entity_id == guest_1.id
    assert len(audit_2) == 1 and audit_2[0].entity_id == guest_2.id
