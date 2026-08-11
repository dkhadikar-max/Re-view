"""Escalation Filter — CONCIERGE.md §5.4/§8, Week 1 remaining step 2.

    WhatsApp Webhook -> Tenant Routing -> Context Builder ->
    Escalation Filter -> Concierge Router (concierge_router.py)

`evaluate_escalation()` is the filter itself: one pure function, no
database access, no state, no AI call. It does exactly one thing —

    Message + ConciergeContext -> EscalationDecision

— and nothing else. It doesn't generate an AI reply, doesn't do FAQ
lookup, doesn't modify the Context it was given (which is frozen and
couldn't be modified even if something tried), and doesn't write
anything to the database. `escalate_to_staff()` is a **separate**
function for the side effect that happens *after* a decision says
`escalate=True` — creating the staff Task and the audit trail. Keeping
these two functions separate, not one function that decides-and-acts,
is what keeps `evaluate_escalation()` trivially testable and reusable
(the Conversation Manager, once it exists, calls the same pure decision
function without needing a database at all).

Per explicit direction, v1 is fully deterministic (regex pattern
matching), not an LLM call — same "don't call a model for what a regex
can answer for free" discipline as everywhere else in this app, and a
safety gate is exactly the kind of decision that should be auditable
and predictable, not probabilistic.

Stateless by design: no conversation history is read or required here.
Whether the *same* topic was already asked and answered five messages
ago is the Conversation Manager's job, not this filter's — evaluate()
only ever looks at the current message and the current Context.

**Scope, revised for the Concierge Router (concierge_router.py):**
`evaluate_escalation()` checks only the hard safety/urgency categories
below (`_ESCALATION_PATTERNS`) — genuine "a human must see this now"
signals that pre-empt every agent, full stop. It used to *also* run its
own duplicate pass over `KNOWLEDGE_BASE_TOPIC_PATTERNS` and escalate
any message that wasn't a recognized-and-answerable KB fact-lookup —
correct back when FAQAgent was the only agent that existed (PR #13),
but wrong now: "not a KB topic" and "no agent can help" stopped being
the same thing the moment Ordering/Revenue/Guest Memory Agents existed
to try first. That logic was removed from here; it isn't lost, it moved
to where it actually belongs — FAQAgent already escalates itself when
a recognized topic has no configured value (its own `should_escalate`,
independent of this filter, per its own docstring), and the Router's
own fallback escalates when *no* agent recognizes a message at all, but
only after Ordering/Revenue/Guest Memory each get a real chance first.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.entities import Task, TaskPriority, TaskStatus
from app.services.audit import write_audit
from app.services.context_builder import ConciergeContext


class EscalationCategory(str, Enum):
    medical = "medical"
    safety = "safety"
    emergency = "emergency"
    complaint = "complaint"
    refund_billing = "refund_billing"
    threat_abuse_harassment = "threat_abuse_harassment"
    # Not in the original 7-category list — kept because "let me speak
    # to someone" is a distinct, high-confidence signal worth its own
    # category rather than folding into complaint/outside_knowledge_base
    # and losing that specificity in the staff queue and audit log.
    human_requested = "human_requested"
    outside_knowledge_base = "outside_knowledge_base"


# The four categories where "escalated late" is qualitatively worse than
# "escalated a beat late for a billing question" — get Task.priority
# bumped to critical instead of merely high.
_CRITICAL_CATEGORIES = {
    EscalationCategory.medical,
    EscalationCategory.safety,
    EscalationCategory.emergency,
    EscalationCategory.threat_abuse_harassment,
}

# Order matters: checked top to bottom, first match wins. Safety-critical
# categories are listed first so a message that could plausibly match
# more than one pattern is never mis-triaged toward the less urgent one.
# Confidence is fixed per category, not computed — these are regex
# matches, not model scores; the number exists so logging/tuning has
# something to look at (§8's "internal only", never surfaced to a
# guest or hotel), not because a match is more or less "sure" than
# another match of the same kind.
_ESCALATION_PATTERNS: list[tuple[EscalationCategory, "re.Pattern[str]", float]] = [
    (
        EscalationCategory.emergency,
        re.compile(
            r"\b(emergency|ambulance|call\s*911|dying|can'?t breathe)\b", re.IGNORECASE
        ),
        0.95,
    ),
    (
        EscalationCategory.medical,
        re.compile(
            r"\b(allerg\w*|medic\w*|medication|doctor|hospital|injur\w*|"
            r"bleed\w*|chest pain|seizure|diabetic|asthma attack)\b",
            re.IGNORECASE,
        ),
        0.9,
    ),
    (
        EscalationCategory.safety,
        re.compile(
            r"\b(unsafe|danger\w*|break.?in|intruder|smoke alarm|gas leak|"
            r"suspicious person)\b",
            re.IGNORECASE,
        ),
        0.9,
    ),
    (
        EscalationCategory.threat_abuse_harassment,
        re.compile(
            r"\b(threat\w*|abus\w*|harass\w*|assault\w*|violent|violence|"
            r"racist|discriminat\w*)\b",
            re.IGNORECASE,
        ),
        0.9,
    ),
    (
        EscalationCategory.refund_billing,
        re.compile(
            r"\b(refund\w*|reimburse\w*|overcharg\w*|billing (issue|problem|dispute)|"
            r"charged (twice|wrong)|dispute\w* (charge|payment))\b",
            re.IGNORECASE,
        ),
        0.85,
    ),
    (
        EscalationCategory.complaint,
        re.compile(
            r"\b(complain\w*|unhappy|disappointed|terrible|awful|worst stay|"
            r"dirty room|not clean|broken|not working|too (loud|noisy))\b",
            re.IGNORECASE,
        ),
        0.75,
    ),
    (
        EscalationCategory.human_requested,
        re.compile(
            r"\b(speak (to|with) (a )?(human|person|staff|manager|someone)|"
            r"talk to (a )?(human|person|staff|manager)|real person|"
            r"customer service)\b",
            re.IGNORECASE,
        ),
        0.95,
    ),
]

# Recognized Knowledge Base topics and the keywords that indicate a
# guest is asking about one. Public (not module-private) because
# faq_agent.py imports this same mapping — one source of truth for
# "what regex means what topic" rather than two copies that could drift
# apart. Used here for the "outside_knowledge_base" category: a
# recognized topic with an EMPTY field still escalates (can't answer,
# won't guess — the same convention the FAQ Agent applies to itself);
# no topic match at all also escalates, per CONCIERGE.md §0 ("when in
# doubt, escalate").
KNOWLEDGE_BASE_TOPIC_PATTERNS: dict[str, "re.Pattern[str]"] = {
    "wifi_password": re.compile(
        r"\b(wifi|wi-fi|internet password|network password)\b", re.IGNORECASE
    ),
    "breakfast_hours": re.compile(r"\bbreakfast\b", re.IGNORECASE),
    "pool_hours": re.compile(r"\bpool\b", re.IGNORECASE),
    "gym_hours": re.compile(r"\b(gym|fitness (room|center|centre))\b", re.IGNORECASE),
    "spa_hours": re.compile(r"\bspa\b", re.IGNORECASE),
    "parking_info": re.compile(r"\bpark(ing)?\b", re.IGNORECASE),
    "checkin_time": re.compile(r"\bcheck.?in\b", re.IGNORECASE),
    "checkout_time": re.compile(r"\bcheck.?out\b", re.IGNORECASE),
    "late_checkout_policy": re.compile(r"\blate check.?out\b", re.IGNORECASE),
    "airport_transfer_info": re.compile(r"\b(airport|shuttle|transfer)\b", re.IGNORECASE),
    "pet_policy": re.compile(r"\b(pet|dog|cat)s?\b", re.IGNORECASE),
    "house_rules": re.compile(r"\bhouse rules?\b", re.IGNORECASE),
    "restaurants": re.compile(r"\brestaurant\b", re.IGNORECASE),
    "cafes": re.compile(r"\bcaf[eé]\b", re.IGNORECASE),
    "nearby_attractions": re.compile(
        r"\b(attraction|things to do|sightsee\w*|what.{0,10}(see|visit|do))\b",
        re.IGNORECASE,
    ),
    "services": re.compile(r"\b(room service|service)\b", re.IGNORECASE),
    "emergency_contacts": re.compile(r"\bemergency (contact|number)\b", re.IGNORECASE),
}


class EscalationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    escalate: bool
    category: Optional[EscalationCategory] = None
    reason: str
    # Internal only (CONCIERGE.md §8) — never surfaced to a guest or
    # hotel, same "no raw confidence number" convention as everywhere
    # else in this app. Exists for logging/tuning once real pilot
    # conversations show what's actually being missed.
    confidence: float


def evaluate_escalation(message_body: str, context: ConciergeContext) -> EscalationDecision:
    """The filter. Pure — no database access, no state, no AI call, no
    mutation of `context` (which is frozen regardless). See module
    docstring for why the database-writing half lives in a separate
    function, and for why this no longer also runs its own KB-topic
    pass (that moved to FAQAgent + the Concierge Router's own fallback).
    """
    text = message_body or ""

    for category, pattern, confidence in _ESCALATION_PATTERNS:
        if pattern.search(text):
            return EscalationDecision(
                escalate=True,
                category=category,
                reason=f"Matched {category.value} pattern",
                confidence=confidence,
            )

    # No hard safety/urgency signal — let the Concierge Router try each
    # agent (FAQ, Ordering, Revenue, Guest Memory) before anything here
    # decides a human is needed. `context` is still part of this
    # function's signature (kept for interface stability — callers and
    # tests already pass it, and a future hard-trigger pattern may need
    # it) even though this branch doesn't currently read it.
    return EscalationDecision(
        escalate=False,
        category=None,
        reason="No hard safety/urgency pattern matched",
        confidence=1.0,
    )


def escalate_to_staff(
    db: Session,
    *,
    context: ConciergeContext,
    message_body: str,
    decision: EscalationDecision,
    correlation_id: str,
) -> Task:
    """The side effect half. Creates the staff-queue Task (reusing the
    existing `Task` model — the same one Approvals-adjacent staff work
    already uses — rather than a parallel "concierge inbox" table) and
    an audit log entry recording tenant_id, guest_id, reservation_id (if
    present), category, the triggering text, and a timestamp — pilot
    data for refining the rules, per the same review that asked for it.

    `correlation_id` is generated by the caller (`concierge_router.py`,
    before this function runs) and reused for both this Task and the
    ESCALATED `ActionEvent` the caller logs immediately afterward —
    PILOT_READINESS.md §5: without it, the ESCALATED event and its Task
    would have no way to be tied back together once staff complete it.
    """
    assert decision.category is not None  # only called when escalate=True
    priority = (
        TaskPriority.critical
        if decision.category in _CRITICAL_CATEGORIES
        else TaskPriority.high
    )
    task = Task(
        tenant_id=context.tenant_id,
        title=f"WhatsApp escalation ({decision.category.value}): {context.guest.name}",
        description=f'Guest message: "{message_body}"\n\nEscalation reason: {decision.reason}',
        status=TaskStatus.open,
        priority=priority,
        related_type="guest",
        related_id=context.guest.id,
        correlation_id=correlation_id,
    )
    db.add(task)
    db.flush()

    write_audit(
        db,
        tenant_id=context.tenant_id,
        actor="escalation_filter",
        action="escalate",
        entity_type="guest",
        entity_id=context.guest.id,
        details={
            "category": decision.category.value,
            "reservation_id": context.reservation.id if context.reservation else None,
            "triggering_text": message_body,
            "task_id": task.id,
        },
    )
    return task
