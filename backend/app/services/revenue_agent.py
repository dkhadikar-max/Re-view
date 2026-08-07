"""Revenue Agent — CONCIERGE.md §5.3, roadmap step 6. The third
implementer of the shared `Agent` Protocol (`agent_protocol.py`), after
`GuestMemoryAgent`.

    RevenueAgent.answer(context, guest_message) -> AgentResponse

Its responsibility is recognition, not execution — kept exactly as
narrow as FAQAgent and GuestMemoryAgent. It identifies that a message
signals interest in a paid opportunity (late checkout, early check-in,
breakfast package, spa, airport transfer, parking, room upgrade, meal
reservation) and proposes it via `metadata["opportunities"]`. It never
acts on that opportunity itself.

This agent:
- Uses only `ConciergeContext` — never queries the database.
- Never sends a WhatsApp message (returns `response` text only; sending
  it is the Router's job, not yet built).
- Never calls a payment API (no import of `stripe_payments` or
  anything like it — there is nothing here that could).
- Never creates a `Reservation` or an `Order` (no write of any kind).
- Never modifies guest memories — that's `GuestMemoryAgent`'s
  `metadata["memory_updates"]` key; this agent's metadata key is
  `"opportunities"`, a deliberately different shape so a future Router
  can never confuse the two.
- Never overrides the Escalation Filter — `should_escalate` is always
  `False` here; by the time any agent runs, the Escalation Filter has
  already decided whether this message needed a human, and this agent
  has no basis to second-guess that decision.
- Never recommends unavailable services — enforced by never confirming
  availability at all. Every response hedges ("subject to
  availability... would you like me to check?"), because this agent
  has no inventory/availability data to check against yet. Whether
  availability is actually checked or a charge applied is later
  orchestration's job, per the exact framing in the spec this agent
  was reviewed against.

v1 is deterministic, same discipline as every other Concierge
component: recognizing an action-oriented request ("can I get X") is
closer to intent classification than generation, and a fixed,
honestly-hedged response template doesn't need a model call. Patterns
are deliberately action-oriented, not topic-oriented, to stay out of
FAQ Agent's territory: "what time is breakfast" is a fact lookup (FAQ
Agent's job); "can I add a breakfast package" is a sales opportunity
(this agent's job). The two are tested against each other explicitly.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext


class OpportunityType(str, Enum):
    late_checkout = "late_checkout"
    early_checkin = "early_checkin"
    breakfast_package = "breakfast_package"
    spa = "spa"
    airport_transfer = "airport_transfer"
    parking = "parking"
    room_upgrade = "room_upgrade"
    # Recognized now, forward-compatible with MENU_ORDERING.md's still-
    # frozen ordering system — this agent only ever recognizes the
    # signal; there is nothing yet to hand it off to, and that's fine,
    # the same way FAQ Agent's should_escalate doesn't require an
    # Escalation Filter category to exist for every possible topic.
    meal_reservation = "meal_reservation"


# Confidence is fixed per pattern, not computed — a regex match, not a
# model score, same convention as every other agent in this codebase.
# Action-oriented phrasing only ("can I get/add/book/upgrade X"), never
# a bare topic keyword — a bare "parking" or "breakfast" mention is
# FAQ Agent's territory (an information request), not a sales signal.
_OPPORTUNITY_PATTERNS: list[tuple[OpportunityType, "re.Pattern[str]", float]] = [
    (
        OpportunityType.late_checkout,
        re.compile(
            r"\b(late check.?out|check.?out (later|late)|check out at \d|"
            r"stay a bit longer)\b",
            re.IGNORECASE,
        ),
        0.85,
    ),
    (
        OpportunityType.early_checkin,
        re.compile(
            r"\b(early check.?in|check in (early|earlier)|arrive early)\b", re.IGNORECASE
        ),
        0.85,
    ),
    (
        OpportunityType.breakfast_package,
        re.compile(
            r"\b(add breakfast|breakfast package|include breakfast|breakfast option)\b",
            re.IGNORECASE,
        ),
        0.8,
    ),
    (
        OpportunityType.spa,
        re.compile(
            r"\bbook (a )?(spa|massage|treatment)\b|\bspa (appointment|booking)\b",
            re.IGNORECASE,
        ),
        0.8,
    ),
    (
        OpportunityType.airport_transfer,
        re.compile(
            r"\b(airport (transfer|pickup|pick.?up)|pick me up|"
            r"(ride|transfer) to the airport)\b",
            re.IGNORECASE,
        ),
        0.8,
    ),
    (
        OpportunityType.parking,
        re.compile(r"\b(book|reserve|need|want) .{0,15}parking\b", re.IGNORECASE),
        0.75,
    ),
    (
        OpportunityType.room_upgrade,
        re.compile(
            r"\b(upgrade my room|upgrade to a suite|bigger room|better room|room upgrade)\b",
            re.IGNORECASE,
        ),
        0.8,
    ),
    (
        OpportunityType.meal_reservation,
        re.compile(
            r"\b(reserve (a table|dinner)|book (a table|dinner)|dinner reservation|"
            r"table for \d)\b",
            re.IGNORECASE,
        ),
        0.75,
    ),
]

# Every response hedges — never confirms availability, never states a
# price. "Never recommend unavailable services" is enforced by never
# claiming anything IS available in the first place.
_RESPONSE_TEMPLATES: dict[OpportunityType, str] = {
    OpportunityType.late_checkout: (
        "We offer late checkout, subject to availability. "
        "Would you like me to check availability?"
    ),
    OpportunityType.early_checkin: (
        "Early check-in may be available. Would you like me to check?"
    ),
    OpportunityType.breakfast_package: (
        "We can add a breakfast package to your stay, subject to availability. "
        "Would you like details?"
    ),
    OpportunityType.spa: "Our spa may have availability. Would you like me to check?",
    OpportunityType.airport_transfer: (
        "We offer airport transfers, subject to availability. "
        "Would you like me to check?"
    ),
    OpportunityType.parking: (
        "Parking may be available at an additional charge. Would you like me to check?"
    ),
    OpportunityType.room_upgrade: (
        "A room upgrade may be available, subject to availability. "
        "Would you like me to check?"
    ),
    OpportunityType.meal_reservation: (
        "I can help arrange a dinner reservation, subject to availability. "
        "Would you like me to check?"
    ),
}


class Opportunity(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    confidence: float


class RevenueAgent:
    """Stateless — holds no data between calls, same as every other
    agent so far."""

    def answer(self, context: ConciergeContext, guest_message: str) -> AgentResponse:
        text = guest_message or ""

        for opportunity_type, pattern, confidence in _OPPORTUNITY_PATTERNS:
            if pattern.search(text):
                return AgentResponse(
                    handled=True,
                    response=_RESPONSE_TEMPLATES[opportunity_type],
                    should_escalate=False,
                    metadata={
                        "opportunities": [
                            Opportunity(
                                type=opportunity_type.value, confidence=confidence
                            ).model_dump()
                        ]
                    },
                )

        # No recognized opportunity — defers to the Router trying
        # another agent (e.g. FAQ Agent), not an escalation. Never
        # invents an opportunity that isn't clearly signaled.
        return AgentResponse(handled=False, response=None, should_escalate=False, metadata={})


revenue_agent = RevenueAgent()
