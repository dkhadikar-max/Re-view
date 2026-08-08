"""Shared Concierge Agent interface.

    Agent.answer(context, guest_message) -> AgentResponse

Every concierge agent (Guest Memory, Revenue, and future ones —
Housekeeping, Maintenance, Local Guide, Loyalty) should return the same
shape so the eventual Concierge Router (roadmap step 7) can invoke each
one uniformly and either take the first `handled=True` response or
merge compatible ones, without knowing anything agent-specific.

`FAQAgent` predates this formalization and still returns its own
`FAQResponse` (`answer`/`confidence`/`source`/`should_escalate`) rather
than this shape. Refactoring it is intentionally deferred to its own
follow-up — the same reasoning `PDF_IMPORT.md` used for not retrofitting
CSV into the `Importer` Protocol (`app/services/importer.py`) in the
same change that shipped `PdfImporter`: don't repackage already-shipped,
reviewed code in the same pass that ships new functionality.
`GuestMemoryAgent` is this Protocol's first implementer.

`intent`/`confidence` are optional and set by the Concierge Router
(`concierge_router.py`), not by an individual agent — they record which
`IntentCategory` (`intent_classifier.py`) routed the message to this
agent in the first place, for observability (logging which intent was
recognized, comparing confidences later) without any agent needing to
know about intent classification itself. An agent's own `answer()`
never sets these; they default to `None` for exactly that reason.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from app.services.context_builder import ConciergeContext


class AgentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    handled: bool
    response: Optional[str] = None
    should_escalate: bool = False
    metadata: dict[str, Any] = {}
    intent: Optional[str] = None
    confidence: Optional[float] = None


@runtime_checkable
class Agent(Protocol):
    def answer(self, context: ConciergeContext, guest_message: str) -> AgentResponse: ...


@runtime_checkable
class ClarifiableAgent(Protocol):
    """A second, narrower interface for agents whose proposal can take
    more than one turn to assemble — MENU_ORDERING.md §7.2. Only an
    agent that owns a multi-turn workflow (Ordering Agent, so far)
    implements this alongside `Agent`; `Conversation Manager`
    (`conversation_manager.py`) is the only caller, and only when a
    `PendingAction.payload` marks itself incomplete
    (`payload["complete"] is False`).

    `clarify()` takes the guest's single latest reply plus the
    in-progress `payload` `Conversation Manager` already has on file —
    never the full conversation history — so the agent's own state
    machine stays deterministic and reproducible from `payload` alone.
    It returns an `AgentResponse` whose `metadata["payload"]` is the
    updated cart state, using the same "propose state via metadata"
    convention `GuestMemoryAgent.answer()`'s `memory_updates` already
    established for a single-turn proposal.
    """

    def clarify(
        self, context: ConciergeContext, message_body: str, payload: dict[str, Any]
    ) -> AgentResponse: ...
