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


@runtime_checkable
class Agent(Protocol):
    def answer(self, context: ConciergeContext, guest_message: str) -> AgentResponse: ...
