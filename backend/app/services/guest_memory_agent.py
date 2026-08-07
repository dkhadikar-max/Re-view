"""Guest Memory Agent — CONCIERGE.md §5.2, roadmap step 5. The first
implementer of the shared `Agent` Protocol (`agent_protocol.py`).

    GuestMemoryAgent.answer(context, guest_message) -> AgentResponse

Kept intentionally narrow for v1, matching the same discipline every
other Concierge component has used so far (Escalation Filter, FAQ
Agent): deterministic pattern matching, no LLM call, no database
access, no mutation of the frozen `ConciergeContext` it receives.

Reads only:
    preferred_room, dietary_preferences, birthday, anniversary,
    stay_count (previous stays), complaint_history, previous_offers
    (previous AI actions) — all already on `ConciergeContext`.

Writes nothing itself. "Writing a memory" means returning a proposed
update in `AgentResponse.metadata["memory_updates"]` — a plain list of
`{field, value, confidence}` dicts — for something else to apply. This
agent never touches the database, the same constraint every other
agent in this codebase has (`answer()` takes a Context and a string,
nothing else). Applying an update (and deciding whether its confidence
clears the bar to overwrite an existing value) is deliberately a
separate concern, not yet built — same reasoning FAQ Agent's `answer()`
doesn't send a WhatsApp message itself.

Only ever proposes a memory update for an explicit, literal
self-statement matching a known pattern (a closed, reviewed vocabulary
of dietary terms and room-preference phrasings) — never an inference
from indirect signals. A guest asking "do you have vegan options?" is
curiosity, not a self-reported trait, and produces no memory update;
"I'm vegan" does. This is the same "never invent, only what was
explicitly stated" principle FAQ Agent applies to its own answers.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext

# (pattern, stored value, confidence). Confidence is fixed per pattern,
# not computed — these are deterministic keyword matches, not model
# scores (same convention as the Escalation Filter and FAQ Agent).
# Whoever eventually applies a memory_update decides whether this
# confidence clears the bar to overwrite an existing value — "never
# overwrite without high confidence" is enforced there, not here; this
# agent's job is only to attach an honest confidence to what it found.
_DIETARY_PATTERNS: list[tuple["re.Pattern[str]", str, float]] = [
    (re.compile(r"\bi'?m (a )?vegetarian\b", re.IGNORECASE), "Vegetarian", 0.9),
    (re.compile(r"\bi'?m (a )?vegan\b", re.IGNORECASE), "Vegan", 0.9),
    (re.compile(r"\bi'?m gluten.?free\b", re.IGNORECASE), "Gluten-free", 0.85),
    (re.compile(r"\bi'?m lactose.?intolerant\b", re.IGNORECASE), "Lactose-intolerant", 0.85),
    (re.compile(r"\bi'?m (a )?pescatarian\b", re.IGNORECASE), "Pescatarian", 0.85),
    (re.compile(r"\bi (only )?eat halal\b", re.IGNORECASE), "Halal", 0.85),
    (re.compile(r"\bi (only )?eat kosher\b", re.IGNORECASE), "Kosher", 0.85),
]
# Captures the named allergen verbatim from the guest's own words — not
# a fixed vocabulary like the patterns above (allergens can't be
# enumerated in advance), but still only ever the literal text the guest
# used, never a paraphrase or an inferred category.
_ALLERGY_PATTERN = re.compile(
    r"\bi'?m allergic to ([a-zA-Z][a-zA-Z ]{1,30}?)\b[.,!]?(?:\s|$)", re.IGNORECASE
)

_ROOM_PREFERENCE_PATTERNS: list[tuple["re.Pattern[str]", str, float]] = [
    (re.compile(r"\bi prefer a quiet room\b", re.IGNORECASE), "Prefers a quiet room", 0.8),
    (re.compile(r"\ba room with a view\b", re.IGNORECASE), "Prefers a room with a view", 0.75),
    (re.compile(r"\ba high floor\b", re.IGNORECASE), "Prefers a high floor", 0.75),
    (re.compile(r"\b(a )?low floor\b", re.IGNORECASE), "Prefers a low floor", 0.75),
]

# Preferences worth remembering that don't have a dedicated Guest
# column — stored via field="notes", the same free-text catch-all
# messaging.py's inbound-WhatsApp handler already appends to, rather
# than inventing a new column for every possible stated preference.
_NOTE_WORTHY_PATTERNS: list[tuple["re.Pattern[str]", str, float]] = [
    (
        re.compile(
            r"\blate check.?out would be (great|nice|appreciated|helpful)\b", re.IGNORECASE
        ),
        "Guest mentioned wanting a late checkout",
        0.75,
    ),
]

_RETURNING_GUEST_TRIGGER = re.compile(
    r"\b(stayed (here|with you) before|last time i (was|stayed)|i'?ve been here before)\b",
    re.IGNORECASE,
)


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    value: str
    confidence: float


def _welcome_back_response(context: ConciergeContext) -> Optional[str]:
    guest = context.guest
    if guest.stay_count <= 1:
        return None
    parts = [f"Welcome back, {guest.name}!"]
    if guest.preferred_room:
        parts.append(f"We remember you enjoy the {guest.preferred_room}.")
    return " ".join(parts)


class GuestMemoryAgent:
    """Stateless — holds no data between calls, same as FAQAgent."""

    def answer(self, context: ConciergeContext, guest_message: str) -> AgentResponse:
        text = guest_message or ""
        memory_updates: list[dict] = []
        response_parts: list[str] = []

        dietary_matched = False
        for pattern, value, confidence in _DIETARY_PATTERNS:
            if pattern.search(text):
                memory_updates.append(
                    MemoryUpdate(
                        field="dietary_preferences", value=value, confidence=confidence
                    ).model_dump()
                )
                response_parts.append(f"Got it — we've noted you're {value.lower()}.")
                dietary_matched = True
                break
        if not dietary_matched:
            allergy_match = _ALLERGY_PATTERN.search(text)
            if allergy_match:
                allergen = allergy_match.group(1).strip()
                value = f"Allergic to {allergen}"
                memory_updates.append(
                    MemoryUpdate(
                        field="dietary_preferences", value=value, confidence=0.85
                    ).model_dump()
                )
                response_parts.append(
                    f"Thanks for letting us know — we've noted your allergy to {allergen}."
                )

        for pattern, value, confidence in _ROOM_PREFERENCE_PATTERNS:
            if pattern.search(text):
                memory_updates.append(
                    MemoryUpdate(
                        field="preferred_room", value=value, confidence=confidence
                    ).model_dump()
                )
                response_parts.append("Noted — we'll keep that in mind for your room.")
                break

        for pattern, value, confidence in _NOTE_WORTHY_PATTERNS:
            if pattern.search(text):
                memory_updates.append(
                    MemoryUpdate(field="notes", value=value, confidence=confidence).model_dump()
                )
                response_parts.append("Noted — we'll pass that along to our front desk team.")
                break

        if memory_updates:
            return AgentResponse(
                handled=True,
                response=" ".join(response_parts),
                should_escalate=False,
                metadata={"memory_updates": memory_updates},
            )

        if _RETURNING_GUEST_TRIGGER.search(text):
            welcome = _welcome_back_response(context)
            if welcome:
                return AgentResponse(
                    handled=True, response=welcome, should_escalate=False, metadata={}
                )

        # Nothing here for this agent to handle — defers to the Router
        # trying another agent (e.g. FAQ Agent), not an escalation.
        return AgentResponse(handled=False, response=None, should_escalate=False, metadata={})


guest_memory_agent = GuestMemoryAgent()
