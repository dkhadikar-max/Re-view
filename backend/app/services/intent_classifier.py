"""Intent Classifier — CONCIERGE.md §4.1, replacing the earlier
"try each agent, first one to claim it wins" Router design.

    classify_intent(message_body, context) -> IntentDecision

The root problem this fixes: agents were competing over vocabulary, not
owning intent. "Breakfast" appears in an information question ("what
time is breakfast"), a service request ("can I add breakfast"), and an
order ("I'd like breakfast delivered to my room") — under the old
design, whichever agent ran first in a fixed priority order would claim
any message containing a keyword it recognized, and FAQ Agent (which
had to run first) needed to import Revenue/Ordering Agent's own
patterns just to know when to defer. That's the Router untangling
conflicts that shouldn't exist in the first place.

Classifying intent once, up front, and dispatching directly to the one
agent that owns that intent means no agent ever sees a message outside
its own territory — FAQ Agent never sees "I'd like breakfast delivered
to my room," Revenue Agent never sees "what time is breakfast." Each
agent still does its own finer-grained resolution once selected (which
KB field, which configured service_type, which dietary pattern) — that
part hasn't changed and doesn't need to, only the top-level dispatch
does.

Reuses each agent's own already-tested detection logic rather than a
second, parallel set of patterns that could drift out of sync:
- INFORMATION: `escalation_filter.KNOWLEDGE_BASE_TOPIC_PATTERNS` (the
  same dict FAQAgent's own `_match_topic` checks).
- ORDER: `ordering_agent.is_food_order`.
- SERVICE_REQUEST: `revenue_agent.is_service_request` (covers the fixed
  service_type patterns, the context-aware literal-name fallback, and
  the occasion/package trigger patterns).
- MEMORY: `guest_memory_agent.is_memory_signal`.
- SMALL_TALK: this module's own small set of pure-pleasantry phrases
  (greetings, thanks, acknowledgments, farewells) — no existing agent
  owns this, so there's nothing to reuse.
- UNKNOWN: none of the above matched.

Checked in this order — MEMORY, ORDER, SERVICE_REQUEST, INFORMATION,
SMALL_TALK — because the more specific/action-oriented signals should
win over the broadest one (INFORMATION's bare keyword patterns). This
is the one central place that decision lives now, instead of scattered
across every agent that used to need to know about its neighbors'
vocabulary.

v1 is deterministic, same discipline as every other Concierge
component — classifying a message's shape is closer to keyword
classification than generation. An LLM classification fallback for
messages that land in UNKNOWN remains a reasonable future addition, not
needed to ship a correct v1 (an UNKNOWN message escalates instead,
CONCIERGE.md §0's safe default).
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.services.context_builder import ConciergeContext
from app.services.escalation_filter import KNOWLEDGE_BASE_TOPIC_PATTERNS
from app.services.guest_memory_agent import is_memory_signal
from app.services.ordering_agent import is_food_order
from app.services.revenue_agent import is_service_request

# Confidence is fixed per category, not computed — same convention as
# every other deterministic component in this codebase. Internal only
# (CONCIERGE.md §8's convention); never surfaced to a guest or hotel.
_MEMORY_CONFIDENCE = 0.9
_ORDER_CONFIDENCE = 0.85
_SERVICE_REQUEST_CONFIDENCE = 0.85
_INFORMATION_CONFIDENCE = 0.85
_SMALL_TALK_CONFIDENCE = 0.7
_UNKNOWN_CONFIDENCE = 0.0

# A whole message segment that's nothing but a pleasantry — greeting,
# thanks, acknowledgment, or farewell. Matched with `fullmatch` per
# segment (not `search`), deliberately stricter than every other
# pattern in this codebase: "Thanks but can I also get breakfast?" must
# NOT classify as small talk just because it starts with "thanks".
_SMALL_TALK_SEGMENT = re.compile(
    r"^((hi|hello|hey)( there)?|good (morning|afternoon|evening)|"
    r"thanks?( you)?( so much)?|"
    r"ok(ay)?|great|perfect|awesome|sounds good|got it|noted|"
    r"see you( soon)?|bye|goodbye|have a (great|good) (day|stay|night))$",
    re.IGNORECASE,
)
_SMALL_TALK_SPLIT = re.compile(r"[,.!]+\s*|\s+and\s+", re.IGNORECASE)


def _is_small_talk(text: str) -> bool:
    """True only when *every* segment of the message (split on commas,
    periods, exclamation marks, or "and") is itself a pure pleasantry —
    a compound greeting like "Thanks so much, see you soon!" still
    counts, but a pleasantry attached to a real request does not."""
    normalized = (text or "").strip().rstrip("!.?")
    if not normalized:
        return False
    segments = [s.strip() for s in _SMALL_TALK_SPLIT.split(normalized) if s.strip()]
    if not segments:
        return False
    return all(_SMALL_TALK_SEGMENT.fullmatch(segment) for segment in segments)


def _is_information_request(text: str) -> bool:
    return any(pattern.search(text) for pattern in KNOWLEDGE_BASE_TOPIC_PATTERNS.values())


class IntentCategory(str, Enum):
    information = "information"
    service_request = "service_request"
    order = "order"
    memory = "memory"
    small_talk = "small_talk"
    unknown = "unknown"


class IntentDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: IntentCategory
    confidence: float


def classify_intent(message_body: str, context: ConciergeContext) -> IntentDecision:
    """Pure — no database access, no state, no AI call, no mutation of
    `context` (which is frozen regardless), same discipline as
    `evaluate_escalation`. Checked in fixed precedence order; the first
    category that matches wins."""
    text = message_body or ""

    if is_memory_signal(text):
        return IntentDecision(category=IntentCategory.memory, confidence=_MEMORY_CONFIDENCE)

    if is_food_order(text):
        return IntentDecision(category=IntentCategory.order, confidence=_ORDER_CONFIDENCE)

    if is_service_request(text, context):
        return IntentDecision(
            category=IntentCategory.service_request, confidence=_SERVICE_REQUEST_CONFIDENCE
        )

    if _is_information_request(text):
        return IntentDecision(
            category=IntentCategory.information, confidence=_INFORMATION_CONFIDENCE
        )

    if _is_small_talk(text):
        return IntentDecision(
            category=IntentCategory.small_talk, confidence=_SMALL_TALK_CONFIDENCE
        )

    return IntentDecision(category=IntentCategory.unknown, confidence=_UNKNOWN_CONFIDENCE)
