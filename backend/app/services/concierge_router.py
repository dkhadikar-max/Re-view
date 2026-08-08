"""Concierge Router — CONCIERGE.md §4/§4.1, roadmap step 7.

    ConciergeRouter.route(db, *, tenant_id, guest_id, message_body,
                           reservation_id=None, conversation_id=None)
        -> AgentResponse

The orchestrator that turns the four independently-built agents into
one working concierge. Per CONCIERGE.md's own diagram:

    WhatsApp -> Tenant Routing -> Escalation Filter -> Context Builder ->
    Intent Classifier -> [FAQ | Ordering | Revenue | Guest Memory] ->
    (Conversation Manager, not yet built) -> WhatsApp

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
- Run the Escalation Filter first, on the raw message, before Context
  Builder or Intent Classifier ever runs (CONCIERGE.md §8) — a message
  that needs a human never reaches an agent at all.
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

FAQAgent predates the shared `Agent` Protocol and returns its own
`FAQResponse` shape (`agent_protocol.py`'s docstring explains why it
wasn't retrofitted). This is the one place that adapts it into the
unified `AgentResponse` every other agent already returns natively —
FAQAgent itself stays untouched.

`AgentResponse.intent`/`.confidence` are filled in here, from the
Intent Classifier's own decision, purely for observability — no agent
sets these itself (`agent_protocol.py`'s docstring).

Deliberately NOT this module's job (still roadmap steps ahead):
- Sending the winning response back to the guest over WhatsApp. Per
  CONCIERGE.md's diagram, that's the Conversation Manager's job (§5.5,
  not yet built — the very next roadmap step). This Router returns a
  decision; it does not act on it.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext, ContextBuilder
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

        intent_decision = classify_intent(message_body, context)

        if intent_decision.category == IntentCategory.small_talk:
            # A pure pleasantry ("thanks!", "see you soon!") doesn't
            # need a human — acknowledge without escalating, and
            # without any agent trying to turn it into a fact lookup,
            # a sale, or a memory update.
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
                db, context, message_body, intent_decision, _NO_INTENT_RECOGNIZED_REASON
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
                existing_response=response,
            )

        if response.should_escalate:
            escalate_to_staff(
                db,
                context=context,
                message_body=message_body,
                decision=EscalationDecision(
                    escalate=True,
                    category=EscalationCategory.outside_knowledge_base,
                    reason=_AGENT_COULD_NOT_HELP_REASON.format(
                        agent=response.metadata.get("agent", "agent")
                    ),
                    confidence=intent_decision.confidence,
                ),
            )

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
        existing_response: Optional[AgentResponse] = None,
    ) -> AgentResponse:
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
        base = existing_response or AgentResponse(handled=False, response=None)
        return base.model_copy(
            update={
                "should_escalate": True,
                "intent": intent_decision.category.value,
                "confidence": intent_decision.confidence,
                "metadata": {**base.metadata, "escalated_by": "router_fallback"},
            }
        )


concierge_router = ConciergeRouter()
