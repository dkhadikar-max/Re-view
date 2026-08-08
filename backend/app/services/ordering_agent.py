"""Ordering Agent v0 — MENU_ORDERING.md, minimal triage only.

    OrderingAgent.answer(context, guest_message) -> AgentResponse

MENU_ORDERING.md's full system (MenuItem catalog, cart, multi-turn
confirmation, Conversation Manager) stays frozen — this is deliberately
NOT that. This is the minimal piece the Router priority order the user
specified requires to exist before Revenue Agent runs:

    Escalation Filter -> FAQ Agent -> Ordering Agent (food/menu) ->
    Revenue Agent (services & upsells) -> Guest Memory Agent -> Human

Its only job is recognizing a food/hunger signal and triaging it three
ways, using nothing beyond what's already on `ConciergeContext`:

1. Room service is configured (`PropertyService` with
   `service_type == "room_service"`, available) -> hand off with an
   invitation to order, not an actual menu (there is no `MenuItem`
   catalog yet — MENU_ORDERING.md step 51 still owns that).
2. No room service, but the Knowledge Base has restaurant information
   -> recommend it, quoting the stored fact verbatim (never invents a
   restaurant name or hours), same "wrap the raw fact" convention as
   `FAQAgent`.
3. Neither -> escalate. A hungry guest with nothing configured to offer
   is exactly the "escalate rather than answer imperfectly" case from
   CONCIERGE.md §0.

This agent:
- Uses only `ConciergeContext` — never queries the database.
- Never invents a menu, a dish, or a price — there is no menu data
  source yet, so it never claims to have one.
- Never sends a WhatsApp message or creates an `Order` — that's later
  orchestration's job once MENU_ORDERING.md's Order model and
  Conversation Manager actually exist (still frozen, roadmap steps
  55-57).
- Never overrides the Escalation Filter's own prior decision — it only
  ever adds its own escalation for the "neither configured" case.

v1 is deterministic, same discipline as every other Concierge
component: recognizing "I'm hungry"-shaped phrasing is intent
classification, not generation.
"""

from __future__ import annotations

import re

from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext

# Hunger/food-intent phrasing — deliberately broad ("I'm hungry", "what
# can I eat", "order some food") since this agent's only downstream
# actions are hand off to room service, point at the restaurant, or
# escalate; there's no wrong dish to invent, so a wider net than the
# Revenue Agent's action-oriented patterns is safe here.
#
# Public (not module-private) for the same reason
# `revenue_agent.SERVICE_TYPE_PATTERNS` is: FAQAgent imports this to
# tell a genuine "what services do you offer" fact lookup apart from an
# actual food-ordering ask that happens to share the word "service".
FOOD_INTENT_PATTERN = re.compile(
    r"\b(i'?m hungry|i am hungry|get (some )?food|order (some )?food|"
    r"something to eat|what can i eat|(get|order) room service|"
    r"can i (get|have|order) (something|food)|food options|hungry)\b",
    re.IGNORECASE,
)


class OrderingAgent:
    """Stateless — holds no data between calls, same as every other
    agent so far."""

    def answer(self, context: ConciergeContext, guest_message: str) -> AgentResponse:
        text = guest_message or ""

        if not FOOD_INTENT_PATTERN.search(text):
            return AgentResponse(
                handled=False, response=None, should_escalate=False, metadata={}
            )

        room_service = next(
            (
                s
                for s in context.services
                if s.service_type.strip().lower() == "room_service" and s.available
            ),
            None,
        )
        if room_service is not None:
            return AgentResponse(
                handled=True,
                response=(
                    f"You can order {room_service.name} anytime — let me know what "
                    "you'd like and I'll get it started for you."
                ),
                should_escalate=False,
                metadata={"handoff": "room_service", "service_id": room_service.id},
            )

        restaurants = context.knowledge_base.restaurants if context.knowledge_base else None
        if restaurants:
            return AgentResponse(
                handled=True,
                response=f"Room service isn't available, but our restaurant can help: {restaurants}",
                should_escalate=False,
                metadata={"handoff": "restaurant"},
            )

        # Neither room service nor restaurant information is
        # configured — never invent an option, escalate instead.
        return AgentResponse(
            handled=True,
            response="Let me check with our team about food options for you.",
            should_escalate=True,
            metadata={"handoff": None},
        )


ordering_agent = OrderingAgent()
