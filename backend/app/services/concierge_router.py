"""Concierge Router — CONCIERGE.md §4/§4.1, roadmap step 7.

    ConciergeRouter.route(db, *, tenant_id, guest_id, message_body,
                           reservation_id=None, conversation_id=None)
        -> AgentResponse

The orchestrator that turns the four independently-built agents into
one working concierge. Per CONCIERGE.md's own diagram:

    WhatsApp -> Tenant Routing -> Escalation Filter ->
    Conversation Manager gate (active PendingAction?) ->
    Context Builder -> Intent Classifier ->
    [FAQ | Ordering | Revenue | Guest Memory] ->
    Action Logger -> Conversation Manager -> WhatsApp

This module owns exactly the "Router" box and nothing else: it contains
NO business logic of its own — every actual decision (what to say,
which intent a message is, whether a specific service request needs
escalating, what a guest's memory update should be) belongs to the
Escalation Filter, the Intent Classifier, or one of the four agents.
This file only decides which already-built component gets to look at a
message, in what order, and returns whatever that component decided,
unchanged.

**Intent-first dispatch, not "try each agent until one claims it".**
An earlier version of this Router tried each agent in a fixed priority
order and took the first `handled=True` response — which meant FAQ
Agent, running first, needed to know about Revenue/Ordering Agent's own
patterns just to defer correctly on messages that shared a keyword
("breakfast" appears in both "what time is breakfast" and "can I add a
breakfast package"). That's exactly the kind of cross-agent coupling
this design avoids: `intent_classifier.py` classifies the message
*once*, and the Router calls **exactly one** agent — the one that owns
that intent — which never even sees a message outside its territory.

Responsibilities:
- Run the Escalation Filter first, on the raw message, before Intent
  Classifier ever runs (CONCIERGE.md §8) — a message that needs a
  human never reaches an agent at all.
- Check the Conversation Manager's own gate next (CONCIERGE.md §5.5/
  §16): is there an active `PendingAction` for this guest? If so, this
  message is a reply to an already-open question, not a fresh
  request — hand it straight to `ConversationManager.resolve()` and
  skip Intent Classification and agent dispatch entirely. A guest's
  "yes" to a late-checkout offer must never get re-classified as
  SMALL_TALK just because it superficially resembles one.
- Build the `ConciergeContext` once per message and hand the exact same
  object to the Intent Classifier and whichever agent runs.
- Classify intent, then call the one agent mapped to that intent
  category: INFORMATION -> FAQ, ORDER -> Ordering, SERVICE_REQUEST ->
  Revenue, MEMORY -> Guest Memory. SMALL_TALK is acknowledged without
  escalating (a "thanks!" doesn't need staff); UNKNOWN escalates
  immediately, same as an agent that was dispatched but still
  couldn't help — under intent-first routing there's no second agent
  to fall back to, so "the mapped agent returned handled=False" and
  "no intent was recognized at all" both mean the same thing: escalate.
- Never let one agent call another, or see another's output — the
  agent selected by intent only ever receives the shared, frozen
  `ConciergeContext`, nothing from a sibling agent.
- Escalate to staff (via the Escalation Filter's own `escalate_to_staff`
  — the Router never writes a `Task`/`AuditLog` row itself) whenever
  (a) the Escalation Filter's own check trips, (b) the intent's mapped
  agent set `should_escalate=True` on its own response, or (c) intent
  classification came back UNKNOWN or the mapped agent still returned
  `handled=False`. CONCIERGE.md §0: escalate rather than answer
  imperfectly, never silently drop a message.
- Record exactly one `ActionEvent` per call, via `ActionLogger`
  (`action_logger.py`) — the Action Ledger, CONCIERGE.md's own section.
  Purely an operational record for later analysis (and, eventually,
  Argus); it plays no part in what this Router decides. Every exit
  point below logs before returning, so a turn is never silently
  un-recorded, but this Router never reads an `ActionEvent` back — it's
  a write-only observer of what already happened. `input_summary`/
  `decision`/`output_summary` are built by this module's own
  `_summarize_*` helpers from each agent's *structured* metadata (a
  service name, a KB topic, a memory field) — never the guest's raw
  message text, and never a secret KB value (a topic like
  `wifi_password` is referenced by name only, never the fact itself).

FAQAgent predates the shared `Agent` Protocol and returns its own
`FAQResponse` shape (`agent_protocol.py`'s docstring explains why it
wasn't retrofitted). This is the one place that adapts it into the
unified `AgentResponse` every other agent already returns natively —
FAQAgent itself stays untouched.

`AgentResponse.intent`/`.confidence` are filled in here, from the
Intent Classifier's own decision, purely for observability — no agent
sets these itself (`agent_protocol.py`'s docstring).

Deliberately NOT this module's job:
- Sending the winning response back to the guest over WhatsApp. Per
  CONCIERGE.md's diagram, that's a later orchestration step's job —
  this Router (and, when it runs instead, the Conversation Manager)
  returns a decision; neither one sends it.
- Anything the Conversation Manager itself owns once its gate fires:
  interpreting a guest's confirmation/cancellation, creating a staff
  `Task` for a confirmed action, or deciding which `action_type` a
  resolution logs. This Router only asks "is one active?" and, if so,
  gets out of the way (`app/services/conversation_manager.py`).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import ActionEvent, ActionEventStatus, ActorType
from app.services.action_logger import action_logger
from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext, ContextBuilder
from app.services.conversation_manager import conversation_manager
from app.services.memory_manager import memory_manager
from app.services.escalation_filter import (
    EscalationCategory,
    EscalationDecision,
    escalate_to_staff,
    evaluate_escalation,
)
from app.services.faq_agent import FAQResponse, faq_agent
from app.services.guest_memory_agent import guest_memory_agent
from app.services.intent_classifier import IntentCategory, IntentDecision, classify_intent
from app.services.ordering_agent import ordering_agent
from app.services.revenue_agent import revenue_agent

_NO_INTENT_RECOGNIZED_REASON = "No intent was recognized for this message"
_AGENT_COULD_NOT_HELP_REASON = "{agent} could not fulfill this request"

# action_type answers a different question than intent/agent do: intent
# is what the guest wanted, agent is who handled it, action_type is
# what actually happened (PR #18/#19 review). Frozen as of PR #19 —
# CONCIERGE.md's Action Ledger section lists the full v1 vocabulary,
# including values reserved for the Conversation Manager/Memory Manager
# that this Router doesn't emit yet. New capabilities should reuse an
# existing value where possible; a genuinely new one is a deliberate,
# documented addition, not an ad-hoc string invented at a call site.
#
# ESCALATED covers every "an agent tried and couldn't help" path (an
# agent returning handled=False, an agent's own should_escalate, or the
# Escalation Filter's own hard-safety trip) — the *why* already lives in
# `decision`/`intent`/`agent`. UNKNOWN is kept separate: it specifically
# means the Intent Classifier itself had no opinion at all, a fact worth
# distinguishing from "an agent had an opinion and still couldn't help."
# Both still result in a staff Task today (`status=escalated` either
# way) — that's an infrastructure fact, not what action_type encodes.
_ACTION_TYPE_ESCALATED = "ESCALATED"
_ACTION_TYPE_UNKNOWN = "UNKNOWN"
_ACTION_TYPE_SMALL_TALK = "SMALL_TALK"
_ACTION_TYPE_AGENT_RESPONDED = "AGENT_RESPONDED"

# Per-agent (action_type, terminal status) for a handled, non-escalating
# response. FAQ's answer is a complete, self-contained response
# (nothing further needs to happen), so it's logged completed; the
# other three are proposals awaiting some later resolution (a booking
# confirmation, the Memory Manager applying its own threshold, a guest
# reply to a hand-off) — proposed, not completed. When that resolution
# happens (once the Conversation Manager exists), it must be logged as
# a *new* ActionEvent (e.g. action_type=OFFER_ACCEPTED) sharing the
# original's correlation_id — never by mutating this row's status in
# place, even though `ActionLogger.log_accept`/etc. exist and could
# technically do that. A mutated status loses the event stream Argus
# needs ("OFFER_PROPOSED then OFFER_ACCEPTED", not "OFFER_PROPOSED that
# quietly became something else").
_SUCCESS_ACTION_TYPE: dict[str, tuple[str, ActionEventStatus]] = {
    "faq": ("FAQ_ANSWERED", ActionEventStatus.completed),
    "revenue": ("OFFER_PROPOSED", ActionEventStatus.proposed),
    "guest_memory": ("MEMORY_PROPOSED", ActionEventStatus.proposed),
    "ordering": ("ORDER_PROPOSED", ActionEventStatus.proposed),
}


def _faq_response_as_agent_response(faq_response: FAQResponse) -> AgentResponse:
    """Adapts FAQAgent's own `FAQResponse` into the shared
    `AgentResponse` shape. `source` is set whenever FAQAgent recognized
    the message as one of its own Knowledge Base topics — whether or
    not that field actually had a value. Since FAQAgent is only ever
    called here for INFORMATION-intent messages (the same
    `KNOWLEDGE_BASE_TOPIC_PATTERNS` the Intent Classifier already
    checked), `source` should always be set in practice — this stays
    defensive rather than assuming, the same "refuse to guess" instinct
    FAQAgent's own docstring describes.
    """
    return AgentResponse(
        handled=faq_response.source is not None,
        response=faq_response.answer,
        should_escalate=faq_response.should_escalate,
        metadata={"source": faq_response.source, "confidence": faq_response.confidence},
    )


def _with_agent_tag(response: AgentResponse, agent_name: str) -> AgentResponse:
    return response.model_copy(update={"metadata": {**response.metadata, "agent": agent_name}})


def _readable(label: Optional[str]) -> str:
    return (label or "a topic").replace("_", " ")


def _summarize_faq(metadata: dict[str, Any], response_text: Optional[str]) -> tuple[str, str, Optional[str]]:
    topic = _readable(metadata.get("source"))
    input_summary = f"Guest asked about {topic}."
    if response_text:
        # Never store the actual KB fact (a wifi password, an emergency
        # contact number) — topic only, the fact itself already lives
        # in PropertyKnowledgeBase, not duplicated here.
        return input_summary, f"FAQAgent answered from knowledge base topic '{metadata.get('source')}'.", f"Answered {topic} question."
    return input_summary, f"FAQAgent had no configured answer for '{metadata.get('source')}'.", None


def _summarize_revenue(metadata: dict[str, Any], response_text: Optional[str]) -> tuple[str, str, Optional[str]]:
    service = metadata.get("service_opportunity")
    package = metadata.get("package_opportunity")
    if service:
        name = service.get("name") or _readable(service.get("service_type"))
        input_summary = f"Guest requested {name}."
        if metadata.get("duplicate_suppressed"):
            decision = f"RevenueAgent noted {name} was already offered."
        elif service.get("configured") is False:
            decision = f"RevenueAgent found {name} not configured, escalated."
        elif service.get("available") is False:
            decision = f"RevenueAgent found {name} unavailable, escalated."
        elif service.get("complimentary"):
            decision = f"RevenueAgent confirmed {name} as complimentary."
        else:
            decision = f"RevenueAgent proposed paid {name}."
        return input_summary, decision, response_text
    if package:
        name = package.get("name")
        occasion = package.get("occasion", "an occasion")
        if name:
            input_summary = f"Guest asked about {name} for {occasion}."
            decision = (
                f"RevenueAgent noted {name} was already offered."
                if metadata.get("duplicate_suppressed")
                else f"RevenueAgent proposed {name}."
            )
        else:
            input_summary = f"Guest asked about a package for {occasion}."
            decision = "RevenueAgent found no package configured for this occasion, escalated."
        return input_summary, decision, response_text
    return "Guest made a service-related request.", "RevenueAgent responded.", response_text


def _summarize_guest_memory(metadata: dict[str, Any], response_text: Optional[str]) -> tuple[str, str, Optional[str]]:
    updates = metadata.get("memory_updates") or []
    if updates:
        fields = ", ".join(_readable(u.get("field")) for u in updates)
        return f"Guest shared a {fields} preference.", f"GuestMemoryAgent proposed updating {fields}.", response_text
    return "Guest mentioned a previous stay.", "GuestMemoryAgent acknowledged a returning guest.", response_text


def _summarize_ordering(metadata: dict[str, Any], response_text: Optional[str]) -> tuple[str, str, Optional[str]]:
    handoff = metadata.get("handoff")
    input_summary = "Guest expressed interest in food or room service."
    if handoff == "room_service":
        decision = "OrderingAgent handed off to room service."
    elif handoff == "restaurant":
        decision = "OrderingAgent recommended the restaurant."
    else:
        decision = "OrderingAgent found no food option configured, escalated."
    return input_summary, decision, response_text


_SUMMARIZERS = {
    "faq": _summarize_faq,
    "revenue": _summarize_revenue,
    "guest_memory": _summarize_guest_memory,
    "ordering": _summarize_ordering,
}


def _summarize_agent_response(
    agent_name: Optional[str], metadata: dict[str, Any], response_text: Optional[str]
) -> tuple[str, str, Optional[str]]:
    summarizer = _SUMMARIZERS.get(agent_name or "")
    if summarizer:
        return summarizer(metadata, response_text)
    return (
        f"Guest message classified for {agent_name or 'an agent'}.",
        f"{agent_name or 'Agent'} responded.",
        response_text,
    )


class ConciergeRouter:
    """Stateless — holds no data between calls, same as every agent it
    orchestrates. One instance is safe to reuse across every tenant,
    guest, and turn."""

    def route(
        self,
        db: Session,
        *,
        tenant_id: str,
        guest_id: str,
        message_body: str,
        reservation_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> AgentResponse:
        context = ContextBuilder(db).build(
            tenant_id=tenant_id,
            guest_id=guest_id,
            reservation_id=reservation_id,
            conversation_id=conversation_id,
        )

        decision = evaluate_escalation(message_body, context)
        if decision.escalate:
            escalate_to_staff(db, context=context, message_body=message_body, decision=decision)
            category = decision.category.value if decision.category else "safety"
            self._log(
                db,
                context,
                intent="escalation",
                agent=None,
                action_type=_ACTION_TYPE_ESCALATED,
                status=ActionEventStatus.escalated,
                actor=ActorType.system,
                confidence=decision.confidence,
                input_summary=f"Guest message matched a {category} escalation pattern.",
                decision_text=decision.reason,
                output_summary=None,
            )
            return AgentResponse(
                handled=True,
                response=None,
                should_escalate=True,
                metadata={
                    "escalated_by": "escalation_filter",
                    "category": decision.category.value if decision.category else None,
                    "reason": decision.reason,
                },
            )

        # Conversation Manager's own gate — checked before Intent
        # Classification, not after (CONCIERGE.md §5.5/§16): a reply to
        # an open question must never get re-classified as a fresh
        # intent (a guest's "yes" to a late-checkout offer is not
        # SMALL_TALK just because it superficially resembles one).
        pending = conversation_manager.find_active(
            db, tenant_id=context.tenant_id, guest_id=context.guest.id
        )
        if pending is not None:
            return conversation_manager.resolve(db, context, pending, message_body)

        intent_decision = classify_intent(message_body, context)

        if intent_decision.category == IntentCategory.small_talk:
            # A pure pleasantry ("thanks!", "see you soon!") doesn't
            # need a human — acknowledge without escalating, and
            # without any agent trying to turn it into a fact lookup,
            # a sale, or a memory update.
            self._log(
                db,
                context,
                intent=intent_decision.category.value,
                agent=None,
                action_type=_ACTION_TYPE_SMALL_TALK,
                status=ActionEventStatus.completed,
                actor=ActorType.system,
                confidence=intent_decision.confidence,
                input_summary="Guest sent a conversational pleasantry.",
                decision_text="Acknowledged as small talk, no escalation needed",
                output_summary=None,
            )
            return AgentResponse(
                handled=False,
                response=None,
                should_escalate=False,
                intent=intent_decision.category.value,
                confidence=intent_decision.confidence,
                metadata={},
            )

        if intent_decision.category == IntentCategory.unknown:
            return self._escalate_unhandled(
                db,
                context,
                message_body,
                intent_decision,
                _NO_INTENT_RECOGNIZED_REASON,
                input_summary="Guest message did not match any recognized intent.",
                action_type=_ACTION_TYPE_UNKNOWN,
                # No agent ever ran — the Intent Classifier itself had no
                # opinion, so this is the Router/Classifier deciding, not
                # an AI agent.
                actor=ActorType.system,
            )

        response = self._dispatch(intent_decision.category, context, message_body)
        response = response.model_copy(
            update={"intent": intent_decision.category.value, "confidence": intent_decision.confidence}
        )

        if not response.handled:
            # The one agent mapped to this intent still couldn't help —
            # under intent-first routing there's no second agent to try,
            # so this means the same thing as an unrecognized message.
            return self._escalate_unhandled(
                db,
                context,
                message_body,
                intent_decision,
                _AGENT_COULD_NOT_HELP_REASON.format(
                    agent=response.metadata.get("agent", "the selected agent")
                ),
                input_summary=f"Guest message classified as {intent_decision.category.value}.",
                existing_response=response,
                # An agent DID run here, and its own handled=False is why
                # this is escalating — the AI made the call, even though
                # the call was "I can't help."
                actor=ActorType.ai,
            )

        agent_name = response.metadata.get("agent")
        input_summary, decision_text, output_summary = _summarize_agent_response(
            agent_name, response.metadata, response.response
        )

        if response.should_escalate:
            reason = _AGENT_COULD_NOT_HELP_REASON.format(agent=agent_name or "agent")
            escalate_to_staff(
                db,
                context=context,
                message_body=message_body,
                decision=EscalationDecision(
                    escalate=True,
                    category=EscalationCategory.outside_knowledge_base,
                    reason=reason,
                    confidence=intent_decision.confidence,
                ),
            )
            self._log(
                db,
                context,
                intent=intent_decision.category.value,
                agent=agent_name,
                action_type=_ACTION_TYPE_ESCALATED,
                status=ActionEventStatus.escalated,
                # The agent ran and made the call to escalate itself.
                actor=ActorType.ai,
                confidence=intent_decision.confidence,
                input_summary=input_summary,
                decision_text=decision_text,
                output_summary=output_summary,
            )
            return response

        action_type, status = _SUCCESS_ACTION_TYPE.get(
            agent_name or "", (_ACTION_TYPE_AGENT_RESPONDED, ActionEventStatus.proposed)
        )
        event = self._log(
            db,
            context,
            intent=intent_decision.category.value,
            agent=agent_name,
            action_type=action_type,
            status=status,
            # An agent produced this outcome — every success path today
            # is the AI acting, never a guest or staff member (those are
            # reserved for the Conversation Manager).
            actor=ActorType.ai,
            confidence=intent_decision.confidence,
            input_summary=input_summary,
            decision_text=decision_text,
            output_summary=output_summary,
            metadata=response.metadata,
        )
        # Conversation Manager decides for itself whether this
        # action_type has a real confirmation flow yet (today, only
        # OFFER_PROPOSED does) — the Router doesn't need to know that
        # distinction, it just always offers the freshly-logged event.
        conversation_manager.register_proposal(db, event=event)
        # Same pattern for memory proposals: only a guest_memory
        # response ever sets this metadata key, so an empty/missing
        # list elsewhere is a safe no-op — the Router doesn't need to
        # know which agent it dispatched to. GuestMemoryAgent remains
        # structurally incapable of writing Guest itself; this is the
        # only call that can turn its proposal into a mutation
        # (MEMORY_MANAGER.md §8).
        memory_updates = response.metadata.get("memory_updates")
        if memory_updates:
            memory_manager.apply_or_hold(db, event=event, memory_updates=memory_updates)
        return response

    def _dispatch(
        self, category: IntentCategory, context: ConciergeContext, message_body: str
    ) -> AgentResponse:
        if category == IntentCategory.information:
            return _with_agent_tag(
                _faq_response_as_agent_response(faq_agent.answer(context, message_body)), "faq"
            )
        if category == IntentCategory.order:
            return _with_agent_tag(ordering_agent.answer(context, message_body), "ordering")
        if category == IntentCategory.service_request:
            return _with_agent_tag(revenue_agent.answer(context, message_body), "revenue")
        if category == IntentCategory.memory:
            return _with_agent_tag(guest_memory_agent.answer(context, message_body), "guest_memory")
        raise AssertionError(
            f"No agent mapped for intent category {category!r} — small_talk/unknown are "
            "handled before this is ever called"
        )

    def _escalate_unhandled(
        self,
        db: Session,
        context: ConciergeContext,
        message_body: str,
        intent_decision: IntentDecision,
        reason: str,
        *,
        input_summary: str,
        actor: ActorType,
        action_type: str = _ACTION_TYPE_ESCALATED,
        existing_response: Optional[AgentResponse] = None,
    ) -> AgentResponse:
        # escalate_to_staff needs the guest's real message — staff have
        # to act on what was actually said. `input_summary` below is a
        # different consumer (the Action Ledger) with a different need
        # (never a raw transcript) — the two must not be conflated.
        escalate_to_staff(
            db,
            context=context,
            message_body=message_body,
            decision=EscalationDecision(
                escalate=True,
                category=EscalationCategory.outside_knowledge_base,
                reason=reason,
                confidence=intent_decision.confidence,
            ),
        )
        agent_name = existing_response.metadata.get("agent") if existing_response else None
        self._log(
            db,
            context,
            intent=intent_decision.category.value,
            agent=agent_name,
            action_type=action_type,
            status=ActionEventStatus.escalated,
            actor=actor,
            confidence=intent_decision.confidence,
            input_summary=input_summary,
            decision_text=reason,
            output_summary=None,
        )
        base = existing_response or AgentResponse(handled=False, response=None)
        return base.model_copy(
            update={
                "should_escalate": True,
                "intent": intent_decision.category.value,
                "confidence": intent_decision.confidence,
                "metadata": {**base.metadata, "escalated_by": "router_fallback"},
            }
        )

    def _log(
        self,
        db: Session,
        context: ConciergeContext,
        *,
        intent: str,
        agent: Optional[str],
        action_type: str,
        status: ActionEventStatus,
        actor: ActorType,
        confidence: Optional[float],
        input_summary: str,
        decision_text: str,
        output_summary: Optional[str],
        metadata: Optional[dict] = None,
    ) -> ActionEvent:
        """One `ActionEvent` per `route()` call — see this module's own
        docstring and `action_logger.py`. `input_summary`/`decision_text`/
        `output_summary` are always already-built, structured summaries
        by the time they reach here (`_summarize_*` above) — never the
        guest's raw message text. Failure to log is deliberately not
        allowed to fail the turn itself; if this ever needs try/except
        around it, that decision belongs to whoever wires `route()` into
        a real request path, not silently swallowed here.

        `actor` is required at every call site, not defaulted here —
        each one is a deliberate choice (an agent ran and decided, vs.
        the Router/Classifier/Escalation Filter decided without one),
        and a shared default would hide that distinction instead of
        forcing every new call site to state it.

        Returns the created event so a caller (today, just the agent
        success branch below) can hand it to `ConversationManager` —
        the Router itself never reads it back.
        """
        return action_logger.log_action(
            db,
            tenant_id=context.tenant_id,
            guest_id=context.guest.id,
            reservation_id=context.reservation.id if context.reservation else None,
            conversation_id=context.channel.conversation_id,
            intent=intent,
            agent=agent,
            action_type=action_type,
            actor=actor,
            confidence=confidence,
            input_summary=input_summary,
            decision=decision_text,
            output_summary=output_summary,
            status=status,
            metadata=metadata,
        )


concierge_router = ConciergeRouter()
