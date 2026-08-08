"""Concierge Router — CONCIERGE.md §4/§4.1, roadmap step 7.

    ConciergeRouter.route(db, *, tenant_id, guest_id, message_body,
                           reservation_id=None, conversation_id=None)
        -> AgentResponse

The orchestrator that turns the four independently-built agents into one
working concierge. Per CONCIERGE.md's own diagram:

    WhatsApp -> Tenant Routing -> Escalation Filter -> Context Builder ->
    Router -> [FAQ | Ordering | Revenue | Guest Memory] -> (Conversation
    Manager, not yet built) -> WhatsApp

This module owns exactly the "Router" box and nothing else: it contains
NO business logic of its own — every actual decision (what to say,
whether a specific service request needs escalating, what a guest's
memory update should be) belongs to the Escalation Filter or one of the
four agents. This file only decides which already-built component gets
to look at a message, in what order, and returns whatever that
component decided, unchanged.

Responsibilities:
- Run the Escalation Filter first, on the raw message, before any agent
  ever sees it (CONCIERGE.md §8) — a message that needs a human never
  reaches an agent at all.
- Build the `ConciergeContext` once per message and hand the exact same
  object to whichever agent runs — no agent builds or re-fetches its
  own context.
- Call agents in the priority order the reviewed spec established: FAQ
  -> Ordering (food/menu) -> Revenue (services & upsells) -> Guest
  Memory. First `handled=True` wins; the Router calls exactly one agent
  per message and never merges two agents' output or lets a "no" from
  one become a reason to also ask another the same question.
- Never let one agent call another, or see another's output — every
  agent only ever receives the same frozen `ConciergeContext`, nothing
  from a sibling agent.
- Escalate to staff (via the Escalation Filter's own `escalate_to_staff`
  — the Router never writes a `Task`/`AuditLog` row itself) whenever
  (a) the Escalation Filter's own check trips, or (b) the agent that
  handled the message set `should_escalate=True` on its own response
  (e.g. Revenue Agent's configured-but-unavailable case), or (c) no
  agent recognized the message at all. Case (c) is a deliberate Router-
  level decision, not copied from any single agent: CONCIERGE.md §0
  says to escalate rather than answer imperfectly, and a message no
  agent recognizes is exactly that — it must not just be silently
  dropped with nothing said and nobody notified.

FAQAgent predates the shared `Agent` Protocol and returns its own
`FAQResponse` shape (`agent_protocol.py`'s docstring explains why it
wasn't retrofitted). This is the one place that adapts it into the
unified `AgentResponse` every other agent already returns natively —
FAQAgent itself stays untouched.

Deliberately NOT this module's job (still roadmap steps ahead):
- Sending the winning response back to the guest over WhatsApp. Per
  CONCIERGE.md's diagram, that's the Conversation Manager's job (§5.5,
  not yet built — the very next roadmap step after this one). This
  Router returns a decision; it does not act on it. Wiring its output
  straight to an outbound WhatsApp send would start sending
  AI-generated replies to real guests before the component designed to
  own history/dedup/tone/throttling for that exists, which is a bigger
  step than "orchestrate the four agents" — left for that next step.
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
from app.services.ordering_agent import ordering_agent
from app.services.revenue_agent import revenue_agent

# No agent recognized the message at all. Not one of the Escalation
# Filter's own categories (those are about *why a human is needed*);
# this is the Router's own fallback, reusing the closest existing
# category rather than adding new schema for a single new case.
_NO_AGENT_MATCHED_REASON = "No agent recognized this message"


def _faq_response_as_agent_response(faq_response: FAQResponse) -> AgentResponse:
    """Adapts FAQAgent's own `FAQResponse` into the shared
    `AgentResponse` shape. `source` is set whenever FAQAgent recognized
    the message as one of its own Knowledge Base topics — whether or
    not that field actually had a value — so a recognized-but-empty
    topic (e.g. a WiFi question the hotel never configured) is treated
    as *handled by FAQ, escalate*, not as "FAQ has nothing, let Revenue
    Agent guess at a WiFi password." `source is None` is the only case
    that means "not FAQ's topic at all," which is when the Router
    should try the next agent instead.
    """
    topic_recognized = faq_response.source is not None
    return AgentResponse(
        handled=topic_recognized,
        response=faq_response.answer,
        should_escalate=faq_response.should_escalate,
        metadata={"source": faq_response.source, "confidence": faq_response.confidence},
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

        response = self._dispatch(context, message_body)

        if response.handled:
            if response.should_escalate:
                escalate_to_staff(
                    db,
                    context=context,
                    message_body=message_body,
                    decision=EscalationDecision(
                        escalate=True,
                        category=EscalationCategory.outside_knowledge_base,
                        reason=(
                            f"{response.metadata.get('agent', 'agent')} could not fulfill "
                            "this request"
                        ),
                        confidence=1.0,
                    ),
                )
            return response

        # No agent recognized this message at all — CONCIERGE.md §0:
        # escalate rather than leave a guest message unanswered and
        # unseen by anyone.
        escalate_to_staff(
            db,
            context=context,
            message_body=message_body,
            decision=EscalationDecision(
                escalate=True,
                category=EscalationCategory.outside_knowledge_base,
                reason=_NO_AGENT_MATCHED_REASON,
                confidence=0.0,
            ),
        )
        return AgentResponse(
            handled=False,
            response=None,
            should_escalate=True,
            metadata={"escalated_by": "router_fallback"},
        )

    def _dispatch(self, context: ConciergeContext, message_body: str) -> AgentResponse:
        """Priority order per the reviewed spec: FAQ answers questions,
        Ordering handles food, Revenue sells hotel services and
        fulfills service requests, Guest Memory learns from confirmed
        interactions. First `handled=True` wins — no agent ever sees
        another agent's output, only the same shared `context`."""
        faq_response = _faq_response_as_agent_response(faq_agent.answer(context, message_body))
        if faq_response.handled:
            return faq_response.model_copy(
                update={"metadata": {**faq_response.metadata, "agent": "faq"}}
            )

        for name, agent in (
            ("ordering", ordering_agent),
            ("revenue", revenue_agent),
            ("guest_memory", guest_memory_agent),
        ):
            response = agent.answer(context, message_body)
            if response.handled:
                return response.model_copy(
                    update={"metadata": {**response.metadata, "agent": name}}
                )

        return AgentResponse(handled=False, response=None, should_escalate=False, metadata={})


concierge_router = ConciergeRouter()
