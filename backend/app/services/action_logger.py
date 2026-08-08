"""Action Ledger — the operational record for ReVisit and the future
learning dataset for Argus (ReVisit's parent product). It is **not**
used for runtime decision-making by anything in this codebase — no
agent, the Router, or the Escalation Filter ever reads an `ActionEvent`
back to decide what to do next. This module's only job is capturing
what already happened, as structured data, for later analysis. It does
no analytics, no aggregation, no ML — that is explicitly out of scope
here and left for Argus to build on top of this foundation.

    ActionLogger.log_action(db, ...) -> ActionEvent
    ActionLogger.log_accept(db, event) -> ActionEvent
    ActionLogger.log_reject(db, event) -> ActionEvent
    ActionLogger.log_complete(db, event) -> ActionEvent
    ActionLogger.log_failure(db, event) -> ActionEvent

This is the **only** place allowed to create an `ActionEvent` row, and
the only place allowed to change one after creation — and even then,
only the `status` field (see `ActionEvent`'s own docstring in
`entities.py`). Every other field is set once, at `log_action()` time,
and never rewritten by this module or anything calling it. Nothing else
in this codebase should ever call `db.add(ActionEvent(...))` directly.

Deliberately does not interpret hotel business logic and does not know
about Concierge concepts like intent categories or agent names beyond
treating them as opaque strings to store — same "closed vocabulary
today, extensible tomorrow" convention as `PropertyService.service_type`.

`input_summary`/`decision`/`output_summary` are expected to already be
short, structured descriptions by the time they reach `log_action` —
this module doesn't summarize or sanitize them itself, that's the
caller's job (`concierge_router.py`'s `_summarize_*` helpers build them
from each agent's own structured metadata, never the guest's raw
message text or a secret KB value). This module only caps length as a
safety net against a single pathological value bloating a row — not a
truncation strategy meant to be clever about what it keeps.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import ActionEvent, ActionEventStatus, ActorType

_MAX_TEXT_LENGTH = 2000

# Stamped into every event's metadata unless the caller already set one
# — one place to bump when agent logic changes meaningfully, so Argus
# can eventually tell "v1 decided this" apart from "v2 decided this"
# without every call site needing to remember to say so.
_AGENT_VERSION = "v1"


def _cap(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return text[:_MAX_TEXT_LENGTH]


class ActionLogger:
    """Stateless — holds no data between calls, same as every other
    service in this codebase. One instance is safe to reuse across
    every tenant, guest, and turn."""

    def log_action(
        self,
        db: Session,
        *,
        tenant_id: str,
        guest_id: str,
        intent: str,
        actor: ActorType,
        input_summary: str,
        decision: str,
        reservation_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        agent: Optional[str] = None,
        action_type: str,
        confidence: Optional[float] = None,
        output_summary: Optional[str] = None,
        status: ActionEventStatus = ActionEventStatus.proposed,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionEvent:
        """Creates one immutable `ActionEvent` row. This is the only
        method in this module (or anywhere else) that should ever
        construct an `ActionEvent` — every other method here only
        transitions `status` on a row this method already created.

        `actor` is required, not optional — "every ActionEvent should
        identify who performed the action" (review after PR #20), a
        platform contract same as `action_type`. See `ActionEvent`'s own
        docstring in `entities.py` for the `ActorType.ai`/`.system`
        distinction this codebase's callers use today.

        `correlation_id` groups every event from the same guest
        interaction, even across separate turns (`ActionEvent`'s own
        docstring). Defaults to a fresh id — the common case today,
        since only one event is logged per turn. A caller that already
        has one to continue (the Conversation Manager, once it exists,
        resuming a pending state) passes it through explicitly instead.
        """
        event = ActionEvent(
            tenant_id=tenant_id,
            guest_id=guest_id,
            reservation_id=reservation_id,
            conversation_id=conversation_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            intent=intent,
            agent=agent,
            action_type=action_type,
            actor=actor,
            confidence=confidence,
            input_summary=_cap(input_summary) or "",
            decision=_cap(decision) or "",
            output_summary=_cap(output_summary),
            status=status,
            event_metadata=json.dumps({"agent_version": _AGENT_VERSION, **(metadata or {})}),
        )
        db.add(event)
        db.flush()
        return event

    def _transition(self, db: Session, event: ActionEvent, status: ActionEventStatus) -> ActionEvent:
        # The one allowed mutation post-creation, per ActionEvent's own
        # docstring — every other field was set once, in log_action(),
        # and is never touched here.
        event.status = status
        db.flush()
        return event

    def log_accept(self, db: Session, event: ActionEvent) -> ActionEvent:
        return self._transition(db, event, ActionEventStatus.accepted)

    def log_reject(self, db: Session, event: ActionEvent) -> ActionEvent:
        return self._transition(db, event, ActionEventStatus.rejected)

    def log_complete(self, db: Session, event: ActionEvent) -> ActionEvent:
        return self._transition(db, event, ActionEventStatus.completed)

    def log_failure(self, db: Session, event: ActionEvent) -> ActionEvent:
        return self._transition(db, event, ActionEventStatus.failed)


action_logger = ActionLogger()
