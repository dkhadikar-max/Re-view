"""FAQ Agent — CONCIERGE.md §5.1, roadmap step 4: the first concierge
agent that actually talks to guests.

    FAQAgent.answer(context, guest_message) -> FAQResponse

Deliberately narrow: answers hotel FAQs from the Knowledge Base already
assembled onto `ConciergeContext`, and nothing else.

- Never queries the database — only reads from the `ConciergeContext`
  it's given, which is frozen and couldn't be modified even if
  something tried.
- Never invents information — the answer text is always the stored
  Knowledge Base fact, wrapped in a fixed template sentence, never
  generated or embellished.
- Escalates when the answer isn't in the Knowledge Base, via
  `should_escalate` — its own safety net. This agent is only ever
  called for INFORMATION-intent messages (`intent_classifier.py`
  decides that before this agent ever runs), so a bare-keyword match
  here is safe — a booking-shaped message like "can I add a breakfast
  package" is classified SERVICE_REQUEST and routed to Revenue Agent
  before FAQ Agent ever sees it, not something this agent has to detect
  and defer on itself.
- Returns structured output only. It does not send a WhatsApp message
  and does not decide the outcome on the pipeline's behalf — that's the
  Concierge Router's job (`concierge_router.py`). This agent is one
  input to that decision, adapted into the Router's shared
  `AgentResponse` shape there (this agent keeps its own `FAQResponse`
  — see `agent_protocol.py`'s docstring for why it wasn't retrofitted).

v1 is deterministic, same discipline as the Escalation Filter: matching
a guest's question to a Knowledge Base topic is closer to keyword
classification than generation, and templating a stored fact into a
sentence doesn't need a model call. An LLM phrasing pass (via the same
AIGateway contract used elsewhere) is a reasonable future addition —
but only to phrase the one supplied fact, never to add anything not in
it — and isn't needed to ship a correct v1.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.services.context_builder import ConciergeContext
from app.services.escalation_filter import KNOWLEDGE_BASE_TOPIC_PATTERNS

# Wraps the raw stored fact in a short sentence. The wrapper text is
# fixed and never guest- or context-specific beyond the {value}
# substitution — nothing is invented, only formatted.
_ANSWER_TEMPLATES: dict[str, str] = {
    "wifi_password": "Our WiFi password is: {value}",
    "breakfast_hours": "Breakfast is served {value}.",
    "pool_hours": "The pool is open {value}.",
    "gym_hours": "The gym is open {value}.",
    "spa_hours": "The spa is open {value}.",
    "parking_info": "{value}",
    "checkin_time": "Check-in time is {value}.",
    "checkout_time": "Check-out time is {value}.",
    "late_checkout_policy": "{value}",
    "airport_transfer_info": "{value}",
    "pet_policy": "{value}",
    "house_rules": "{value}",
    "restaurants": "Here are some restaurant recommendations: {value}",
    "cafes": "Here are some cafe recommendations: {value}",
    "nearby_attractions": "Here are some nearby recommendations: {value}",
    "services": "{value}",
    "room_service_hours": "Room service is available {value}.",
    "emergency_contacts": "{value}",
}

# Confidence is fixed per outcome, not computed — same reasoning as the
# Escalation Filter: these are deterministic keyword/field matches, not
# model scores. Internal only (CONCIERGE.md §8's convention); never
# surfaced to a guest or hotel.
_ANSWERED_CONFIDENCE = 0.85
_NO_ANSWER_CONFIDENCE = 0.0


class FAQResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: Optional[str] = None
    confidence: float
    source: Optional[str] = None
    should_escalate: bool


class FAQAgent:
    """Stateless — holds no data between calls. One instance is safe to
    reuse across guests, properties, and turns; nothing here depends on
    what a previous call was for."""

    def answer(self, context: ConciergeContext, guest_message: str) -> FAQResponse:
        text = guest_message or ""
        matched_field = self._match_topic(text)

        if matched_field is None:
            return FAQResponse(
                answer=None,
                confidence=_NO_ANSWER_CONFIDENCE,
                source=None,
                should_escalate=True,
            )

        kb = context.knowledge_base
        field_value = getattr(kb, matched_field, None) if kb else None
        if not field_value:
            return FAQResponse(
                answer=None,
                confidence=_NO_ANSWER_CONFIDENCE,
                source=matched_field,
                should_escalate=True,
            )

        template = _ANSWER_TEMPLATES.get(matched_field, "{value}")
        return FAQResponse(
            answer=template.format(value=field_value),
            confidence=_ANSWERED_CONFIDENCE,
            source=matched_field,
            should_escalate=False,
        )

    @staticmethod
    def _match_topic(text: str) -> Optional[str]:
        for field_name, pattern in KNOWLEDGE_BASE_TOPIC_PATTERNS.items():
            if pattern.search(text):
                return field_name
        return None


faq_agent = FAQAgent()
