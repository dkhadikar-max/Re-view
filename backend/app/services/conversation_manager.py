"""Conversation Manager — CONCIERGE.md §5.5/§16, "the one component
that isn't an agent." The first *stateful* piece of the concierge:
every agent and the Router are stateless (§4.1), but a proposal that
needs a guest's confirmation has to be remembered across turns by
*something* — this is that something, and the only stateful AI
component in the codebase.

    ConversationManager.find_active(db, tenant_id, guest_id) -> Optional[PendingAction]
    ConversationManager.register_proposal(db, event=action_event) -> Optional[PendingAction]
    ConversationManager.start_clarification(db, tenant_id, guest_id, origin_agent, intent, payload, ...) -> Optional[PendingAction]
    ConversationManager.register_clarifiable_agent(name, agent) -> None
    ConversationManager.register_confirmation_handler(accepted_type, handler) -> None
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

`start_clarification`/`resolve`'s dispatch-back branch (MENU_ORDERING.md
§7.2) extend this to a second, earlier case: a multi-turn proposal that
isn't complete enough to have been proposed yet at all. This module
still never reasons about *what* a cart or any other payload contains —
`payload`'s shape is opaque, owned entirely by whichever
`ClarifiableAgent` created it (`agent_protocol.py`); the one thing this
module ever inspects is a shared `"complete": bool` convention, and
dispatch itself is a plain `{name: agent}` registry lookup, the same
"small lookup dict" shape `_CONFIRMABLE_ACTION_TYPES` already uses.
Nothing here is order-specific.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Callable, Optional

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
from app.services.agent_protocol import AgentResponse, ClarifiableAgent
from app.services.context_builder import ConciergeContext

# Only a `*_PROPOSED` action_type backed by a real guest-facing yes/no
# question creates a `PendingAction`. `OFFER_PROPOSED` (Revenue Agent —
# "Would you like me to book it?") and `ORDER_PROPOSED` (Ordering Agent
# v1 — a complete, unambiguous cart, MENU_ORDERING.md §7.4) both are;
# `MEMORY_PROPOSED` (Memory Manager resolves it synchronously, never put
# to the guest as a question) stays informational.
# Maps a confirmable origin `action_type` to the (accepted, rejected,
# expired) `action_type`s CONCIERGE.md's frozen v1 taxonomy reserves for
# that domain — this dict is the ONLY place that knows the mapping, so
# wiring up a second confirmable flow means adding one line here, not
# touching any of the logic below it.
_CONFIRMABLE_ACTION_TYPES: dict[str, tuple[str, str, str]] = {
    "OFFER_PROPOSED": ("OFFER_ACCEPTED", "OFFER_REJECTED", "OFFER_EXPIRED"),
    "ORDER_PROPOSED": ("ORDER_CONFIRMED", "ORDER_REJECTED", "ORDER_EXPIRED"),
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
    every tenant, guest, and turn.

    `_clarifiable_agents`/`_confirmation_handlers` are the one exception,
    and neither is per-request state — both are static configuration,
    registered once at startup (or once per test), mirroring
    `_CONFIRMABLE_ACTION_TYPES`'s own "small lookup dict" shape. Neither
    ever varies by tenant, guest, or turn.
    """

    def __init__(self) -> None:
        self._clarifiable_agents: dict[str, ClarifiableAgent] = {}
        # accepted_type -> callable(db, context, pending, payload) -> extra
        # metadata dict | None. Lets a confirmed proposal trigger domain-
        # specific side effects (e.g. creating an Order/OrderItem snapshot)
        # without this module ever having to know what that means — the
        # same reasoning `_clarifiable_agents` already established. Most
        # accepted_types (e.g. OFFER_ACCEPTED) have no handler at all;
        # the generic staff Task still gets created for those exactly as
        # before.
        self._confirmation_handlers: dict[
            str, Callable[[Session, ConciergeContext, PendingAction, dict], Optional[dict]]
        ] = {}

    def register_clarifiable_agent(self, name: str, agent: ClarifiableAgent) -> None:
        """Registers which agent's `clarify()` a `PendingAction.origin_agent`
        value dispatches back to (MENU_ORDERING.md §7.2). Called once at
        startup for each real `ClarifiableAgent` that exists; tests
        register a stub directly instead of importing a real agent."""
        self._clarifiable_agents[name] = agent

    def register_confirmation_handler(
        self,
        accepted_type: str,
        handler: Callable[[Session, ConciergeContext, PendingAction, dict], Optional[dict]],
    ) -> None:
        """Registers a side effect to run when `accepted_type` is
        confirmed (`_accept()`, below), after its `ActionEvent` is
        logged and before the generic staff `Task` is created. `payload`
        is `{}` when `pending.payload` was never set (most confirmable
        flows today — e.g. Revenue Agent's offers never build one); a
        handler that doesn't need it can simply ignore it. This module
        never decides what a handler does or interprets its return
        value beyond merging it into the response metadata — deciding
        domain logic (e.g. "what does confirming an order mean") stays
        the originating agent's job, not this one's."""
        self._confirmation_handlers[accepted_type] = handler

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

        If the triggering event's own metadata included a `"payload"`
        key (a cart that happened to be complete on its very first
        turn — MENU_ORDERING.md §7.1 — rather than one built up via
        `start_clarification`/dispatch-back), it's carried onto this
        row unchanged, so a later confirmation handler still has it to
        work with (`_accept()`, below). This module still never
        inspects what's inside it.
        """
        if event.action_type not in _CONFIRMABLE_ACTION_TYPES:
            return None
        if self.find_active(db, tenant_id=event.tenant_id, guest_id=event.guest_id):
            return None

        event_metadata = json.loads(event.event_metadata) if event.event_metadata else {}
        payload = event_metadata.get("payload")

        pending = PendingAction(
            tenant_id=event.tenant_id,
            guest_id=event.guest_id,
            reservation_id=event.reservation_id,
            conversation_id=event.conversation_id,
            correlation_id=event.correlation_id,
            origin_action_type=event.action_type,
            origin_intent=event.intent,
            payload=json.dumps(payload) if payload is not None else None,
            expires_at=datetime.utcnow() + _DEFAULT_TTL,
        )
        db.add(pending)
        db.flush()
        return pending

    def start_clarification(
        self,
        db: Session,
        *,
        tenant_id: str,
        guest_id: str,
        origin_agent: str,
        intent: str,
        payload: dict,
        reservation_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[PendingAction]:
        """Starts a multi-turn proposal that isn't complete enough to
        have been proposed yet at all (MENU_ORDERING.md §7.1/§7.3) — the
        earlier counterpart to `register_proposal`, for a cart still
        being assembled rather than one already logged as a `*_PROPOSED`
        `ActionEvent`. Deliberately takes no `event`: there is nothing to
        log yet, and logging one prematurely (before the proposal is
        actually complete) would be exactly the "abandoned cart looks
        like a business transaction" problem §6/§7.3 exist to prevent.

        Same "defer, don't replace" policy as `register_proposal`: a
        second workflow starting while one is already active for this
        guest returns `None` rather than creating a competing row —
        this component should never have to guess which of two open
        threads a guest's reply continues.

        Generic across any future `ClarifiableAgent`, not order-specific
        — `origin_agent` and `payload`'s shape are entirely the caller's
        business; this method only ever stores `payload` verbatim.
        """
        if self.find_active(db, tenant_id=tenant_id, guest_id=guest_id):
            return None

        pending = PendingAction(
            tenant_id=tenant_id,
            guest_id=guest_id,
            reservation_id=reservation_id,
            conversation_id=conversation_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            origin_action_type=None,
            origin_intent=intent,
            origin_agent=origin_agent,
            payload=json.dumps(payload),
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

        One exception, checked first: a `pending.origin_agent` with an
        incomplete `payload` (MENU_ORDERING.md §7.2) means this isn't a
        yes/no question yet at all — dispatch to `_dispatch_back`
        instead of pattern-matching. Everything below this check is
        unchanged from before that mechanism existed.
        """
        if pending.origin_agent and not self._payload_complete(pending):
            return self._dispatch_back(db, context, pending, message_body)

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

        # A registered handler (e.g. Ordering Agent creating an
        # Order/OrderItem snapshot) runs before the generic Task below,
        # so the Task's own description can reference whatever it
        # produced. Most accepted_types have no handler — nothing here
        # changes for them.
        handler = self._confirmation_handlers.get(accepted_type)
        handler_metadata: dict = {}
        if handler is not None:
            payload = json.loads(pending.payload) if pending.payload else {}
            handler_metadata = handler(db, context, pending, payload) or {}

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
            # PILOT_READINESS.md §5 — same id as the OFFER_ACCEPTED/
            # ORDER_CONFIRMED/TASK_CREATED events below, so staff
            # completion (TASK_COMPLETED) can rejoin the same chain.
            correlation_id=pending.correlation_id,
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
                **handler_metadata,
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

    @staticmethod
    def _payload_complete(pending: PendingAction) -> bool:
        """A `PendingAction` with no `payload` at all predates this
        mechanism (Revenue Agent's offers) or never went through
        `start_clarification` — treated as complete so `resolve()`
        falls through to its original confirm/cancel matching, exactly
        as it always has."""
        if not pending.payload:
            return True
        return bool(json.loads(pending.payload).get("complete", True))

    def _dispatch_back(
        self,
        db: Session,
        context: ConciergeContext,
        pending: PendingAction,
        message_body: str,
    ) -> AgentResponse:
        """Hands an incomplete cart's reply to whichever agent started
        it (MENU_ORDERING.md §7.2), instead of confirm/cancel pattern
        matching. This method still never reasons about *what* the
        payload contains — only whether the agent says it's now
        complete, and if so, what `action_type` to log for it.
        """
        agent = self._clarifiable_agents.get(pending.origin_agent)
        payload = json.loads(pending.payload) if pending.payload else {}

        if agent is None:
            # Misconfigured — an origin_agent with no registered
            # implementer. Not a guest-facing failure to hide silently;
            # escalate the same way an agent's own should_escalate does.
            return AgentResponse(
                handled=False,
                should_escalate=True,
                metadata={
                    "pending_action_id": pending.id,
                    "conversation_manager": "dispatch_back_unregistered",
                },
            )

        response = agent.clarify(context, message_body, payload)
        new_payload = response.metadata.get("payload")

        if response.should_escalate or new_payload is None:
            # Unresolvable clarification (§7.4): clarify() couldn't
            # make sense of the reply at all. Abandon the build — no
            # Order was ever created, and nothing was ever proposed, so
            # there's nothing to log; the PendingAction simply closes.
            pending.status = PendingActionStatus.cancelled
            pending.resolved_at = datetime.utcnow()
            db.flush()
            return AgentResponse(
                handled=response.handled,
                response=response.response,
                should_escalate=True,
                metadata={
                    **response.metadata,
                    "pending_action_id": pending.id,
                    "conversation_manager": "dispatch_back_abandoned",
                },
            )

        pending.payload = json.dumps(new_payload)

        if new_payload.get("complete"):
            # First time this proposal is complete enough to be a real
            # proposal — mint its ActionEvent now, not before (§7.3).
            # The action_type to log is the agent's own business, not
            # something this module hardcodes; it only requires that
            # value already be a recognized confirmable type so the
            # existing confirm/cancel matching can take over next turn.
            action_type = response.metadata.get("action_type")
            if action_type in _CONFIRMABLE_ACTION_TYPES:
                action_logger.log_action(
                    db,
                    tenant_id=pending.tenant_id,
                    guest_id=pending.guest_id,
                    reservation_id=pending.reservation_id,
                    conversation_id=pending.conversation_id,
                    correlation_id=pending.correlation_id,
                    intent=pending.origin_intent,
                    agent=pending.origin_agent,
                    action_type=action_type,
                    actor=ActorType.ai,
                    confidence=response.confidence,
                    input_summary="Guest's reply completed a multi-turn proposal.",
                    decision=f"Cart became complete; logged {action_type}.",
                    status=ActionEventStatus.proposed,
                )
                pending.origin_action_type = action_type

        db.flush()
        return response

    def expire_stale(self, db: Session, *, tenant_id: Optional[str] = None) -> list[PendingAction]:
        """Closes every `PendingAction` past its `expires_at`. Meant to
        run on a schedule (or be checked lazily before the next
        lookup) — this module doesn't wire up the scheduler itself.
        Logs one `<DOMAIN>_EXPIRED` event per row, sharing its
        `correlation_id`, so the ledger's lifecycle stays complete even
        for a proposal the guest never answered.

        A row still incomplete when it expires (`origin_action_type` is
        `None` — a cart that was still being assembled, never
        completed) is simply closed instead (MENU_ORDERING.md §7.3):
        nothing was ever proposed, so there's nothing to log as expired.
        """
        query = db.query(PendingAction).filter(
            PendingAction.status == PendingActionStatus.pending,
            PendingAction.expires_at <= datetime.utcnow(),
        )
        if tenant_id is not None:
            query = query.filter(PendingAction.tenant_id == tenant_id)

        expired = query.all()
        for pending in expired:
            pending.status = PendingActionStatus.expired
            pending.resolved_at = datetime.utcnow()
            if pending.origin_action_type is None:
                continue
            _, _, expired_type = _CONFIRMABLE_ACTION_TYPES[pending.origin_action_type]
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
