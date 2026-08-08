"""Revenue Agent — CONCIERGE.md §5.3, reworked per the fuller spec that
supersedes the narrow "recognition only" v1 (see git history for that
version — commit `18ab1b1` on `feature/revenue-agent`).

    RevenueAgent.answer(context, guest_message) -> AgentResponse

The hotel's own configuration (`context.services`, `context.packages` —
`ContextBuilder`, backed by `PropertyService`/`PropertyPackage`) is now
the source of truth this agent recommends from, not a fixed, hedged
opportunity list. Router priority order (CONCIERGE.md, not yet built):

    Escalation Filter -> FAQ Agent -> Ordering Agent (food/menu) ->
    Revenue Agent (services & upsells) -> Guest Memory Agent -> Human

This agent:
- Uses only `ConciergeContext` — never queries the database.
- Never invents a service or package. A `service_type` with no matching
  configured row simply doesn't exist for this property; a package
  whose occasion tag doesn't match any configured package simply isn't
  offered. "Any service configured by the hotel" (the open-ended tail
  of the spec's service list) is handled by a literal-name fallback
  match against `context.services`, never a guess.
- Quotes only real, configured prices — never a placeholder or an
  estimate. Complimentary services are stated as free, not priced.
- Escalates (`should_escalate=True`) when a guest explicitly asks for
  something the hotel configuration says is currently unavailable, or
  for a named service/package this property hasn't configured at all —
  per CONCIERGE.md §0 ("escalate rather than answer imperfectly"), a
  definite ask deserves a definite answer, and this agent has none to
  give in either case. This is a deliberate change from the narrow v1,
  which never escalated at all. It still never *overrides* the
  Escalation Filter, which already ran earlier in the pipeline and had
  first say on this message — this agent only ever adds its own
  domain-specific escalation for requests that reach it unescalated.
- Never sends a WhatsApp message, calls a payment API, or creates a
  `Reservation`/`Order`/`Offer` row — recommending is this agent's job;
  acting on the recommendation is later orchestration's, same as v1.
- Never modifies guest memories — that's `GuestMemoryAgent`'s
  `metadata["memory_updates"]` key; this agent's keys are
  `"service_opportunity"`/`"package_opportunity"`.
- Checks `context.previous_offers` before recommending, so it doesn't
  repeat an offer already made and still pending or already accepted.

Food and drink ordering ("I'm hungry", "can I get room service") is
deliberately NOT this agent's territory even though "Breakfast", "Dinner"
and "Room service" appear in the hotel-services list this agent can
quote as bookable add-ons — active food ordering is the Ordering
Agent's job (`ordering_agent.py`), which the Router dispatches before
this agent for exactly that reason.

v1 stays deterministic, same discipline as every other Concierge
component: matching a configured service/package by keyword is intent
classification, not generation, and every price/availability fact comes
from configuration data, not a model's guess.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext, PackageContext, ServiceContext

# Statuses on a previous `Offer` that mean "don't repeat this" — the
# guest either already has it pending an answer or already said yes.
# `declined`/`expired` are fair game to offer again.
_ACTIVE_OFFER_STATUSES = {"offered", "accepted"}

# Canonical `service_type` slugs this agent recognizes by phrasing, per
# the spec's "Hotel services" list. Action/request-oriented, not topic-
# oriented — "what time is breakfast" is FAQ Agent's territory (a fact
# lookup); "can I add breakfast" is this agent's (a sales/service ask).
# A hotel-configured service outside this fixed list is still
# reachable via the literal-name fallback in `_match_service`.
#
# Public (not module-private) for the same reason
# `KNOWLEDGE_BASE_TOPIC_PATTERNS` is (escalation_filter.py): FAQAgent
# imports this dict to tell "what time is checkout" (its own fact-
# lookup territory) apart from "can I check out at 4pm" (this agent's
# territory) for the topics where the two collide on a bare keyword —
# reusing these already-tested patterns rather than a second, parallel
# heuristic that could drift out of sync with them. A dict (not a list
# of tuples) so FAQAgent can look one up by service_type directly;
# insertion order is still what `_match_service` iterates in below, so
# first-match priority is unchanged.
SERVICE_TYPE_PATTERNS: dict[str, "re.Pattern[str]"] = {
    "late_checkout": re.compile(
        r"\b(late check.?out|check.?out (later|late)|check out at \d|"
        r"stay a bit longer)\b",
        re.IGNORECASE,
    ),
    "early_checkin": re.compile(
        r"\b(early check.?in|check in (early|earlier)|arrive early)\b", re.IGNORECASE
    ),
    "breakfast": re.compile(
        r"\b(add breakfast|breakfast package|include breakfast|"
        r"(get|book|can i (get|have)) breakfast)\b",
        re.IGNORECASE,
    ),
    "dinner": re.compile(
        r"\b(reserve (a table|dinner)|book (a table|dinner)|dinner reservation|"
        r"table for \d)\b",
        re.IGNORECASE,
    ),
    "room_service": re.compile(
        r"\b(order room service|room service (please|order))\b", re.IGNORECASE
    ),
    "laundry": re.compile(
        r"\b(laundry service|do my laundry|laundry pickup|get my laundry)\b",
        re.IGNORECASE,
    ),
    "spa": re.compile(
        r"\bbook (a )?(spa|massage|treatment)\b|\bspa (appointment|booking)\b",
        re.IGNORECASE,
    ),
    "airport_transfer": re.compile(
        r"\b(airport (transfer|pickup|pick.?up)|pick me up|"
        r"(ride|transfer) to the airport|need an? (airport )?transfer)\b",
        re.IGNORECASE,
    ),
    "parking": re.compile(r"\b(book|reserve|need|want) .{0,15}parking\b", re.IGNORECASE),
    "kids_activities": re.compile(
        r"\b(kids? (club|activities)|activities for (my|our) (kids|children))\b",
        re.IGNORECASE,
    ),
    "tours": re.compile(
        r"\b(book a tour|city tour|sightseeing tour|guided tour)\b", re.IGNORECASE
    ),
    "gym": re.compile(
        r"\b(gym package|fitness package|personal train(er|ing))\b", re.IGNORECASE
    ),
    "cab_booking": re.compile(
        r"\b(book a cab|call a taxi|arrange a taxi|cab booking)\b", re.IGNORECASE
    ),
}

# Explicit asks tied to an occasion/package — a definite request that
# deserves a definite answer, so a miss here escalates rather than
# silently dropping the guest's ask.
_OCCASION_REQUEST_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("romance", re.compile(r"\bdecorate?(ion)? (the |our |my )?room\b", re.IGNORECASE)),
    (
        "romance",
        re.compile(r"\b(romantic|romance) (package|setup|surprise)\b", re.IGNORECASE),
    ),
    (
        "celebration",
        re.compile(r"\b(celebration|anniversary|birthday) package\b", re.IGNORECASE),
    ),
]

# Passive occasion mentions — informational, not a request. A miss here
# just defers (e.g. to Guest Memory Agent), it never escalates.
_OCCASION_MENTION_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("anniversary", re.compile(r"\b(it'?s|its) (our |my )?anniversary\b", re.IGNORECASE)),
    (
        "honeymoon",
        re.compile(r"\b(on (our )?honeymoon|honeymooners?)\b", re.IGNORECASE),
    ),
    ("birthday", re.compile(r"\b(it'?s|its) (my |our )?birthday\b", re.IGNORECASE)),
    (
        "celebration",
        re.compile(r"\bwe'?re celebrating\b", re.IGNORECASE),
    ),
]

# Minimum literal-name length for the "any service configured by the
# hotel" fallback — guards against a 2-3 character service name (e.g.
# "spa" already covered by a fixed pattern) matching almost anything.
_MIN_FALLBACK_NAME_LENGTH = 4

# The literal-name fallback also requires one of these action/inquiry
# words somewhere in the message. Without this gate, a bare topic
# mention of a configured service's name (e.g. "What time is
# breakfast?", with "Breakfast" configured) would wrongly fall into
# this agent's territory instead of FAQ Agent's — the same book-vs-ask
# distinction the fixed patterns above already draw explicitly.
_FALLBACK_ACTION_WORDS = re.compile(
    r"\b(book|add|arrange|order|reserve|need|want|get|have|offer|available|"
    r"avail|include|charge|price|cost|buy|schedule)\b",
    re.IGNORECASE,
)


class ServiceOpportunity(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_type: str
    service_id: Optional[str] = None
    name: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    complimentary: bool = False
    configured: bool
    available: Optional[bool] = None


class PackageOpportunity(BaseModel):
    model_config = ConfigDict(frozen=True)

    package_id: str
    name: str
    occasion: str
    price: Optional[float] = None
    currency: Optional[str] = None


def _money(price: float, currency: str) -> str:
    return f"{price:.2f} {currency}"


def _match_service(
    guest_message: str, services: list[ServiceContext]
) -> tuple[Optional[str], Optional[ServiceContext]]:
    """Returns (service_type, matching configured row or None). A
    non-None service_type with a None row means the guest clearly asked
    for something this property hasn't configured at all."""
    for service_type, pattern in SERVICE_TYPE_PATTERNS.items():
        if pattern.search(guest_message):
            row = next(
                (s for s in services if s.service_type.strip().lower() == service_type),
                None,
            )
            return service_type, row

    # "Any service configured by the hotel" — a literal mention of a
    # configured service's own name, for service types outside the
    # fixed list above. Never matches against anything not configured,
    # and only when paired with an action/inquiry word — a bare name
    # mention with no ask ("What time is breakfast?") stays FAQ Agent's
    # territory even for a configured service, same distinction the
    # fixed patterns above draw explicitly.
    lowered = guest_message.lower()
    if _FALLBACK_ACTION_WORDS.search(guest_message):
        for service in services:
            name = service.name.strip().lower()
            if len(name) >= _MIN_FALLBACK_NAME_LENGTH and name in lowered:
                return service.service_type, service

    return None, None


def _match_occasion_package(
    occasion: str, packages: list[PackageContext]
) -> Optional[PackageContext]:
    occasion = occasion.lower()
    for package in packages:
        if not package.available:
            continue
        if occasion in (tag.lower() for tag in package.occasions):
            return package
    return None


def _has_active_offer(
    context: ConciergeContext, category: str
) -> bool:
    return any(
        offer.category == category and offer.status in _ACTIVE_OFFER_STATUSES
        for offer in context.previous_offers
    )


class RevenueAgent:
    """Stateless — holds no data between calls, same as every other
    agent so far."""

    def answer(self, context: ConciergeContext, guest_message: str) -> AgentResponse:
        text = guest_message or ""

        service_response = self._handle_service(context, text)
        if service_response is not None:
            return service_response

        occasion_response = self._handle_occasion(context, text)
        if occasion_response is not None:
            return occasion_response

        # No recognized service or occasion signal — defers to the
        # Router trying another agent, not an escalation. Never invents
        # an opportunity that isn't clearly signaled.
        return AgentResponse(handled=False, response=None, should_escalate=False, metadata={})

    def _handle_service(
        self, context: ConciergeContext, text: str
    ) -> Optional[AgentResponse]:
        service_type, row = _match_service(text, context.services)
        if service_type is None:
            return None

        if row is None:
            # Explicit ask, nothing configured — never invent an offer,
            # but a definite ask still deserves a definite answer.
            return AgentResponse(
                handled=True,
                response=(
                    "Let me check with our team about that for you — I don't have "
                    "that set up as a bookable service yet."
                ),
                should_escalate=True,
                metadata={
                    "service_opportunity": ServiceOpportunity(
                        service_type=service_type, configured=False
                    ).model_dump()
                },
            )

        if _has_active_offer(context, service_type):
            return AgentResponse(
                handled=True,
                response=(
                    f"You already have {row.name} on your stay — no need to ask again! "
                    "Let me know if you'd like anything changed."
                ),
                should_escalate=False,
                metadata={
                    "service_opportunity": ServiceOpportunity(
                        service_type=service_type,
                        service_id=row.id,
                        name=row.name,
                        price=row.price,
                        currency=row.currency,
                        complimentary=row.complimentary,
                        configured=True,
                        available=row.available,
                    ).model_dump(),
                    "duplicate_suppressed": True,
                },
            )

        if not row.available:
            return AgentResponse(
                handled=True,
                response=(
                    f"{row.name} isn't available right now — let me check with our "
                    "team and get back to you."
                ),
                should_escalate=True,
                metadata={
                    "service_opportunity": ServiceOpportunity(
                        service_type=service_type,
                        service_id=row.id,
                        name=row.name,
                        configured=True,
                        available=False,
                    ).model_dump()
                },
            )

        if row.complimentary:
            response = f"{row.name} is complimentary for your stay. Would you like me to arrange it?"
        else:
            price_text = _money(row.price, row.currency) if row.price is not None else None
            response = (
                f"{row.name} is available for {price_text}. Would you like me to book it?"
                if price_text
                else f"{row.name} is available. Would you like me to check pricing for you?"
            )

        return AgentResponse(
            handled=True,
            response=response,
            should_escalate=False,
            metadata={
                "service_opportunity": ServiceOpportunity(
                    service_type=service_type,
                    service_id=row.id,
                    name=row.name,
                    price=row.price,
                    currency=row.currency,
                    complimentary=row.complimentary,
                    configured=True,
                    available=True,
                ).model_dump()
            },
        )

    def _handle_occasion(
        self, context: ConciergeContext, text: str
    ) -> Optional[AgentResponse]:
        for occasion, pattern in _OCCASION_REQUEST_PATTERNS:
            if pattern.search(text):
                return self._occasion_response(
                    context, occasion, escalate_if_missing=True
                )

        for occasion, pattern in _OCCASION_MENTION_PATTERNS:
            if pattern.search(text):
                return self._occasion_response(
                    context, occasion, escalate_if_missing=False
                )

        return None

    def _occasion_response(
        self, context: ConciergeContext, occasion: str, *, escalate_if_missing: bool
    ) -> Optional[AgentResponse]:
        package = _match_occasion_package(occasion, context.packages)

        if package is None:
            if not escalate_if_missing:
                # A passive mention with nothing configured to offer —
                # defer, e.g. to Guest Memory Agent, rather than fail.
                return None
            return AgentResponse(
                handled=True,
                response=(
                    "Let me check with our team about arranging something special "
                    "for you."
                ),
                should_escalate=True,
                metadata={"package_opportunity": {"occasion": occasion, "configured": False}},
            )

        if _has_active_offer(context, f"package:{package.id}"):
            return AgentResponse(
                handled=True,
                response=(
                    f"You're already set up with our {package.name} — let me know if "
                    "you'd like anything changed."
                ),
                should_escalate=False,
                metadata={
                    "package_opportunity": PackageOpportunity(
                        package_id=package.id,
                        name=package.name,
                        occasion=occasion,
                        price=package.price,
                        currency=package.currency,
                    ).model_dump(),
                    "duplicate_suppressed": True,
                },
            )

        if package.price is not None:
            response = (
                f"We have a {package.name} for {_money(package.price, package.currency)} — "
                "would you like me to arrange it for you?"
            )
        else:
            response = (
                f"We have a {package.name} available — would you like me to share the "
                "details?"
            )

        return AgentResponse(
            handled=True,
            response=response,
            should_escalate=False,
            metadata={
                "package_opportunity": PackageOpportunity(
                    package_id=package.id,
                    name=package.name,
                    occasion=occasion,
                    price=package.price,
                    currency=package.currency,
                ).model_dump()
            },
        )


revenue_agent = RevenueAgent()
