"""Conversation Manager — CONCIERGE.md §5.5/§16, "the one component
that isn't an agent." The first *stateful* piece of the concierge:
every agent and the Router are stateless (§4.1), but a proposal that
needs a guest's confirmation has to be remembered across turns by
*something* — this is that something, and the only stateful AI
component in the codebase.

    ConversationManager.find_active(db, tenant_id, guest_id) -> Optional[PendingAction]
    ConversationManager.register_proposal(db, event=action_event) -> Optional[PendingAction]
    ConversationManager.resolve(db, context, pending, message_body) -> AgentResponse
    ConversationManager.expire_stale(db, tenant_id=None) -> list[PendingAction]

Scope is deliberately narrow (the user's own spec, repeated here so
future edits don't creep past it):

- Own all pending conversations (`PendingAction`).
- Resume an interrupted flow by remembering what was asked.
- Interpret a guest's confirmation/cancellation/clarification.
- Emit the next `ActionEvent`, sharing the original `correlation_id`.
- Create staff `Task`s when human execution is required.
- Nothing else.

It must NOT: look up FAQ answers, decide revenue offers or prices,
update guest memory, classify intent, or call an LLM. All of those stay
owned by the existing agents / Intent Classifier — this module only
ever sees a message *after* the Router has already determined a
`PendingAction` is active for that guest, and interprets that one
reply against fixed confirm/cancel patterns (same "no AI on this path"
discipline `escalation_filter.py` already uses for a different gate).

Event-sourced, not a mutating "conversation state" record: `PendingAction`
(`app/models/entities.py`) tracks only the single active workflow per
guest; `ActionEvent` (the Action Ledger) is the immutable history. A
transition here (accept/reject/expire) is always paired with a new
`ActionEvent` sharing the `PendingAction`'s own `correlation_id` — the
full lifecycle is replayable from the ledger alone even though this
table's own `status` only ever moves forward once.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    ActionEvent,
    ActionEventStatus,
    ActorType,
    PendingAction,
    PendingActionStatus,
    Task,
    TaskPriority,
    TaskStatus,
)
from app.services.action_logger import action_logger
from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext

# Only a `*_PROPOSED` action_type backed by a real guest-facing yes/no
# question creates a `PendingAction`. As of this module's introduction
# that's `OFFER_PROPOSED` (Revenue Agent — "Would you like me to book
# it?") only: `ORDER_PROPOSED` (Ordering Agent v0 — pure hand-off, e.g.
# "You can order room service anytime") and `MEMORY_PROPOSED` (applied
# later by the not-yet-built Memory Manager, never put to the guest as
# a question) are informational, not something awaiting an answer.
# Maps a confirmable origin `action_type` to the (accepted, rejected,
# expired) `action_type`s CONCIERGE.md's frozen v1 taxonomy reserves for
# that domain — this dict is the ONLY place that knows the mapping, so
# wiring up a second confirmable flow (once Ordering Agent's full
# build-out or Memory Manager actually ask a guest to confirm) means
# adding one line here, not touching any of the logic below it.
_CONFIRMABLE_ACTION_TYPES: dict[str, tuple[str, str, str]] = {
    "OFFER_PROPOSED": ("OFFER_ACCEPTED", "OFFER_REJECTED", "OFFER_EXPIRED"),
}

_DEFAULT_TTL = timedelta(hours=24)  # matches WhatsApp's own 24h messaging window

# Fixed patterns, not an LLM call — CONCIERGE.md §5.5 explicitly keeps
# this component out of the reasoning path. A reply matching neither is
# treated as unclear, not as a cancellation — silence or ambiguity
# should never be read as "no".
_CONFIRM_PATTERN = re.compile(
    r"\b(yes|yeah|yep|yup|sure|sounds good|please do|go ahead|book it|confirm(ed)?|ok(ay)?)\b",
    re.IGNORECASE,
)
_CANCEL_PATTERN = re.compile(
    r"\b(no|nah|nope|don'?t|cancel|never ?mind|not (now|interested)|skip it)\b",
    re.IGNORECASE,
)


class ConversationManager:
    """Stateless itself — holds no data between calls, same as every
    agent and the Router. `PendingAction` rows in the database are the
    actual state; one instance of this class is safe to reuse across
    every tenant, guest, and turn."""

    def find_active(self, db: Session, *, tenant_id: str, guest_id: str) -> Optional[PendingAction]:
        """The Router's own gate: called before Intent Classification
        on every message. A hit means this message is a reply to an
        open question, not a fresh request."""
        return (
            db.query(PendingAction)
            .filter(
                PendingAction.tenant_id == tenant_id,
                PendingAction.guest_id == guest_id,
                PendingAction.status == PendingActionStatus.pending,
            )
            .order_by(PendingAction.created_at.desc())
            .first()
        )

    def register_proposal(self, db: Session, *, event: ActionEvent) -> Optional[PendingAction]:
        """Called by the Router right after it logs a `*_PROPOSED`
        event. Returns the new `PendingAction`, or `None` when either
        (a) this `action_type` has no real confirmation flow yet (see
        `_CONFIRMABLE_ACTION_TYPES`), or (b) a `PendingAction` is
        already active for this guest — the new proposal's `ActionEvent`
        still exists in the ledger regardless (the Router logs every
        proposal unconditionally, before this is ever called); it
        simply never becomes the active conversational thread. This
        component should never have to guess which of two open
        questions a guest's "yes" answers.
        """
        if event.action_type not in _CONFIRMABLE_ACTION_TYPES:
            return None
        if self.find_active(db, tenant_id=event.tenant_id, guest_id=event.guest_id):
            return None

        pending = PendingAction(
            tenant_id=event.tenant_id,
            guest_id=event.guest_id,
            reservation_id=event.reservation_id,
            conversation_id=event.conversation_id,
            correlation_id=event.correlation_id,
            origin_action_type=event.action_type,
            origin_intent=event.intent,
            expires_at=datetime.utcnow() + _DEFAULT_TTL,
        )
        db.add(pending)
        db.flush()
        return pending

    def resolve(
        self,
        db: Session,
        context: ConciergeContext,
        pending: PendingAction,
        message_body: str,
    ) -> AgentResponse:
        """Interprets a guest's reply to the active `PendingAction`.
        Never calls an LLM, never touches FAQ/revenue/memory logic —
        confirm/cancel/unclear only, via `_CONFIRM_PATTERN`/
        `_CANCEL_PATTERN` above.
        """
        accepted_type, rejected_type, _ = _CONFIRMABLE_ACTION_TYPES[pending.origin_action_type]

        if _CONFIRM_PATTERN.search(message_body):
            return self._accept(db, context, pending, accepted_type)
        if _CANCEL_PATTERN.search(message_body):
            return self._reject(db, context, pending, rejected_type)

        # Unclear: nothing has actually happened yet, so nothing is
        # logged to the ledger — the PendingAction stays open and the
        # guest is asked again. Inventing a "CLARIFICATION_REQUESTED"
        # action_type for this would be exactly the kind of ad-hoc,
        # undocumented addition CONCIERGE.md's frozen taxonomy rule
        # warns against; this is a deliberate no-event turn, not an
        # oversight.
        return AgentResponse(
            handled=True,
            response="Sorry, could you confirm with a yes or no?",
            should_escalate=False,
            metadata={"pending_action_id": pending.id, "conversation_manager": "clarify"},
        )

    def _accept(
        self,
        db: Session,
        context: ConciergeContext,
        pending: PendingAction,
        accepted_type: str,
    ) -> AgentResponse:
        pending.status = PendingActionStatus.resolved
        pending.resolved_at = datetime.utcnow()
        db.flush()

        action_logger.log_action(
            db,
            tenant_id=pending.tenant_id,
            guest_id=pending.guest_id,
            reservation_id=pending.reservation_id,
            conversation_id=pending.conversation_id,
            correlation_id=pending.correlation_id,
            intent=pending.origin_intent,
            agent=None,
            action_type=accepted_type,
            actor=ActorType.guest,
            confidence=None,
            input_summary="Guest confirmed the pending proposal.",
            decision=f"Guest replied to confirm; logged {accepted_type}.",
            status=ActionEventStatus.accepted,
        )

        # No PMS integration exists yet to execute the confirmed action
        # automatically — a staff Task is the only execution path today
        # (CONCIERGE.md §5.5's own scope: "create staff Tasks when
        # human execution is required").
        task = Task(
            tenant_id=context.tenant_id,
            title=f"Process confirmed request: {context.guest.name}",
            description=(
                f"Guest confirmed a pending proposal (correlation_id={pending.correlation_id}). "
                "No PMS integration exists yet — a staff member must process this manually."
            ),
            status=TaskStatus.open,
            priority=TaskPriority.high,
            related_type="guest",
            related_id=context.guest.id,
        )
        db.add(task)
        db.flush()

        action_logger.log_action(
            db,
            tenant_id=pending.tenant_id,
            guest_id=pending.guest_id,
            reservation_id=pending.reservation_id,
            conversation_id=pending.conversation_id,
            correlation_id=pending.correlation_id,
            intent=pending.origin_intent,
            agent=None,
            action_type="TASK_CREATED",
            actor=ActorType.system,
            confidence=None,
            input_summary="No PMS integration exists yet to execute the confirmed action.",
            decision="Created a staff Task to process the confirmed request.",
            status=ActionEventStatus.completed,
            metadata={"task_id": task.id},
        )

        return AgentResponse(
            handled=True,
            response="Great, we've got that noted — our team will take care of it shortly.",
            should_escalate=False,
            metadata={
                "pending_action_id": pending.id,
                "conversation_manager": "accepted",
                "task_id": task.id,
            },
        )

    def _reject(
        self,
        db: Session,
        context: ConciergeContext,
        pending: PendingAction,
        rejected_type: str,
    ) -> AgentResponse:
        pending.status = PendingActionStatus.cancelled
        pending.resolved_at = datetime.utcnow()
        db.flush()

        action_logger.log_action(
            db,
            tenant_id=pending.tenant_id,
            guest_id=pending.guest_id,
            reservation_id=pending.reservation_id,
            conversation_id=pending.conversation_id,
            correlation_id=pending.correlation_id,
            intent=pending.origin_intent,
            agent=None,
            action_type=rejected_type,
            actor=ActorType.guest,
            confidence=None,
            input_summary="Guest declined the pending proposal.",
            decision=f"Guest replied to decline; logged {rejected_type}.",
            status=ActionEventStatus.rejected,
        )

        return AgentResponse(
            handled=True,
            response="No problem, let us know if you change your mind!",
            should_escalate=False,
            metadata={"pending_action_id": pending.id, "conversation_manager": "rejected"},
        )

    def expire_stale(self, db: Session, *, tenant_id: Optional[str] = None) -> list[PendingAction]:
        """Closes every `PendingAction` past its `expires_at`. Meant to
        run on a schedule (or be checked lazily before the next
        lookup) — this module doesn't wire up the scheduler itself.
        Logs one `<DOMAIN>_EXPIRED` event per row, sharing its
        `correlation_id`, so the ledger's lifecycle stays complete even
        for a proposal the guest never answered.
        """
        query = db.query(PendingAction).filter(
            PendingAction.status == PendingActionStatus.pending,
            PendingAction.expires_at <= datetime.utcnow(),
        )
        if tenant_id is not None:
            query = query.filter(PendingAction.tenant_id == tenant_id)

        expired = query.all()
        for pending in expired:
            _, _, expired_type = _CONFIRMABLE_ACTION_TYPES[pending.origin_action_type]
            pending.status = PendingActionStatus.expired
            pending.resolved_at = datetime.utcnow()
            action_logger.log_action(
                db,
                tenant_id=pending.tenant_id,
                guest_id=pending.guest_id,
                reservation_id=pending.reservation_id,
                conversation_id=pending.conversation_id,
                correlation_id=pending.correlation_id,
                intent=pending.origin_intent,
                agent=None,
                action_type=expired_type,
                actor=ActorType.system,
                confidence=None,
                input_summary="Guest never responded within the confirmation window.",
                decision=f"PendingAction expired unresolved; logged {expired_type}.",
                status=ActionEventStatus.failed,
            )
        db.flush()
        return expired


conversation_manager = ConversationManager()
