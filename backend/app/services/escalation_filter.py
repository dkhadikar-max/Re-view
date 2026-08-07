"""Escalation Filter — CONCIERGE.md §5.4/§8, Week 1 remaining step 2.

    WhatsApp Webhook -> Tenant Routing -> Context Builder ->
    Escalation Filter -> FAQ Agent (not yet built)

A binary gate, checked BEFORE any AI-generated reply exists: does this
message need a human, or can it proceed toward an answer? Per explicit
direction, v1 is deterministic (rule-based pattern matching), not an
LLM call — same "don't call a model for what a regex can answer for
free" discipline as everywhere else in this app, and a safety gate is
exactly the kind of decision that should be auditable and predictable,
not probabilistic.

"No AI. Ever." on the escalated path means exactly that: escalating
creates a Task for staff and the pipeline stops there. No agent runs,
no reply is generated, until a human has responded. Since the FAQ Agent
itself doesn't exist yet (that's the next step after this one), a
message that clears this gate today simply doesn't get an automated
reply yet either — this PR's deliverable is that unsafe/out-of-scope
messages get flagged to staff starting now, not that safe ones get
answered starting now.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models.entities import Task, TaskPriority, TaskStatus
from app.services.context_builder import ConciergeContext


class EscalationCategory(str, Enum):
    medical = "medical"
    safety = "safety"
    emergency = "emergency"
    complaint = "complaint"
    refund_billing = "refund_billing"
    threat_abuse_harassment = "threat_abuse_harassment"
    human_requested = "human_requested"
    outside_knowledge_base = "outside_knowledge_base"
    none = "none"


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
_ESCALATION_PATTERNS: list[tuple[EscalationCategory, "re.Pattern[str]"]] = [
    (
        EscalationCategory.emergency,
        re.compile(
            r"\b(emergency|ambulance|call\s*911|dying|can'?t breathe)\b", re.IGNORECASE
        ),
    ),
    (
        EscalationCategory.medical,
        re.compile(
            r"\b(allerg\w*|medic\w*|medication|doctor|hospital|injur\w*|"
            r"bleed\w*|chest pain|seizure|diabetic|asthma attack)\b",
            re.IGNORECASE,
        ),
    ),
    (
        EscalationCategory.safety,
        re.compile(
            r"\b(unsafe|danger\w*|break.?in|intruder|smoke alarm|gas leak|"
            r"suspicious person)\b",
            re.IGNORECASE,
        ),
    ),
    (
        EscalationCategory.threat_abuse_harassment,
        re.compile(
            r"\b(threat\w*|abus\w*|harass\w*|assault\w*|violent|violence|"
            r"racist|discriminat\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        EscalationCategory.refund_billing,
        re.compile(
            r"\b(refund\w*|reimburse\w*|overcharg\w*|billing (issue|problem|dispute)|"
            r"charged (twice|wrong)|dispute\w* (charge|payment))\b",
            re.IGNORECASE,
        ),
    ),
    (
        EscalationCategory.complaint,
        re.compile(
            r"\b(complain\w*|unhappy|disappointed|terrible|awful|worst stay|"
            r"dirty room|not clean|broken|not working|too (loud|noisy))\b",
            re.IGNORECASE,
        ),
    ),
    (
        EscalationCategory.human_requested,
        re.compile(
            r"\b(speak (to|with) (a )?(human|person|staff|manager|someone)|"
            r"talk to (a )?(human|person|staff|manager)|real person|"
            r"customer service)\b",
            re.IGNORECASE,
        ),
    ),
]

# Recognized Knowledge Base topics and the keywords that indicate a
# guest is asking about one. Used only for the "outside_knowledge_base"
# category below: a recognized topic with an EMPTY field still
# escalates (can't answer, won't guess — same convention as the FAQ
# Agent will use once it exists); no topic match at all also escalates,
# per CONCIERGE.md §0 ("when in doubt, escalate") and because there's no
# FAQ Agent yet to hand an unrecognized message to regardless.
_KNOWLEDGE_BASE_TOPICS: dict[str, "re.Pattern[str]"] = {
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

    needs_human: bool
    category: EscalationCategory
    reason: str


def evaluate_escalation(message_body: str, context: ConciergeContext) -> EscalationDecision:
    """The binary gate. Deterministic — never calls an LLM (see module
    docstring). `context` is only consulted for the Knowledge Base check;
    the hard-trigger categories don't need it at all."""
    text = message_body or ""

    for category, pattern in _ESCALATION_PATTERNS:
        if pattern.search(text):
            return EscalationDecision(
                needs_human=True,
                category=category,
                reason=f"Matched {category.value} pattern",
            )

    matched_field: Optional[str] = None
    for field_name, pattern in _KNOWLEDGE_BASE_TOPICS.items():
        if pattern.search(text):
            matched_field = field_name
            break

    if matched_field is not None:
        kb = context.knowledge_base
        field_value = getattr(kb, matched_field, None) if kb else None
        if field_value:
            return EscalationDecision(
                needs_human=False,
                category=EscalationCategory.none,
                reason=(
                    f"Recognized knowledge-base topic '{matched_field}' with an "
                    "answer available"
                ),
            )
        return EscalationDecision(
            needs_human=True,
            category=EscalationCategory.outside_knowledge_base,
            reason=(
                f"Recognized topic '{matched_field}' but the property's knowledge "
                "base has no answer for it"
            ),
        )

    return EscalationDecision(
        needs_human=True,
        category=EscalationCategory.outside_knowledge_base,
        reason="Message didn't match any recognized knowledge-base topic",
    )


def escalate_to_staff(
    db: Session,
    *,
    tenant_id: str,
    guest_id: str,
    guest_name: str,
    message_body: str,
    decision: EscalationDecision,
) -> Task:
    """Creates the staff-queue item. Reuses the existing `Task` model —
    the same one Approvals-adjacent staff work already uses — rather
    than inventing a parallel "concierge inbox" table for something that
    is, at its core, a task someone needs to act on.
    """
    priority = (
        TaskPriority.critical
        if decision.category in _CRITICAL_CATEGORIES
        else TaskPriority.high
    )
    task = Task(
        tenant_id=tenant_id,
        title=f"WhatsApp escalation ({decision.category.value}): {guest_name}",
        description=f'Guest message: "{message_body}"\n\nEscalation reason: {decision.reason}',
        status=TaskStatus.open,
        priority=priority,
        related_type="guest",
        related_id=guest_id,
    )
    db.add(task)
    db.flush()
    return task
