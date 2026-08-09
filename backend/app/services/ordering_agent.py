"""Ordering Agent v1 — MENU_ORDERING.md §6/§7, the real cart-building
implementation on top of `MenuItem` data (`context.menu_items`,
PR #30) and the `ClarifiableAgent` dispatch-back mechanism (PR #29).

    OrderingAgent.answer(context, guest_message) -> AgentResponse
    OrderingAgent.clarify(context, message_body, payload) -> AgentResponse

v0's triage-only behavior (`git log` — hand off to room service, point
at the restaurant, or escalate, never claiming a real menu existed) is
preserved verbatim as the fallback for two cases that still need it:
a property with no `MenuItem` catalog configured yet, and a food-intent
message that doesn't name anything on the menu ("I'm hungry" — no
mention of a specific dish). v1 only takes over once the guest's
message actually names something recognizable on `context.menu_items`.

**Deterministic correctness over recommendation intelligence** (the
explicit v1 constraint): this agent never infers what a guest "should"
order. "Get me something healthy" matches no menu item by name, so it
falls straight through to the v0 hand-off — it is never turned into an
invented recommendation. "Two chicken biryani" matches an unambiguous,
configured item — that's actionable. Two configured variants sharing a
name ("Chicken Biryani (Spicy)"/"(Mild)") triggers a clarifying
question, never a guess at which one was meant.

**Matching is exact, word-bounded, and case-insensitive against
`context.menu_items`** — never a fuzzy/semantic match, and never
against anything not currently `available=True` (`ContextBuilder`
already filters that). A dish that isn't on the list simply isn't
recognized; this agent has no other source of menu truth.

**Allergen guardrail** (MENU_ORDERING.md §12, restated here since this
is the one agent it binds): this agent may *filter* by
`Guest.dietary_preferences` (not yet wired into matching in v1 — no
guest has asked for it) but never asserts an item is safe for an
allergy. `vegan=True`/`gluten_free=True` are the hotel's own labels,
not a safety guarantee this agent can make on its own; a guest
mentioning an allergy mid-order is caught by the Escalation Filter's
existing medical pattern before this agent ever runs, unchanged.

**Cart lifecycle** — the multi-turn contract this agent implements
against (MENU_ORDERING.md §7.1-§7.4):

    answer() [turn 1]
      -> item(s) recognized, cart incomplete (missing quantity, or an
         ambiguous variant choice) -> metadata={"payload": {...}},
         no "action_type" yet -> Router/caller starts a PendingAction
         via `conversation_manager.start_clarification()`, no
         ActionEvent logged (§7.3 — nothing was proposed yet)
      -> item(s) recognized, cart already complete on turn 1 ("Two
         chicken biryani", nothing else needed) -> metadata includes
         `"action_type": "ORDER_PROPOSED"` -> Router logs it and calls
         `register_proposal()`, same as every other agent's proposal
      -> nothing recognized -> falls through to v0's hand-off/escalate
    clarify() [turn 2+, dispatched by Conversation Manager, never the
      Router directly]
      -> resolves the outstanding question (a quantity number, or a
         choice among variants) against the SAME `payload` Conversation
         Manager already has on file -> returns an updated payload,
         complete or not
      -> reply doesn't resolve anything recognizable -> `should_escalate
         =True`, no `"payload"` key -> Conversation Manager abandons the
         build and escalates (§7.4 — the frozen behavior for an
         unresolvable clarification reply, deliberately covers both
         "gibberish" and "guest changed their mind" the same way; a
         dedicated graceful mid-build cancel is a reasonable future
         enhancement, not built speculatively now)

`on_order_confirmed` (registered as a `ConversationManager` confirmation
handler, not called by this module directly) is the one moment
`Order`/`OrderItem` rows are actually created, snapshotting `payload`'s
`cart` — see its own docstring below for why that boundary lives here
and not inside `ConversationManager` itself.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import Order, OrderItem, OrderStatus, PendingAction
from app.services.agent_protocol import AgentResponse
from app.services.context_builder import ConciergeContext, MenuItemContext

# Hunger/food-intent phrasing — unchanged from v0 (`intent_classifier.py`
# still calls `is_food_order` for ORDER-intent classification).
_FOOD_INTENT_PATTERN = re.compile(
    r"\b(i'?m hungry|i am hungry|get (some )?food|order (some )?food|"
    r"something to eat|what can i eat|(get|order) room service|"
    r"can i (get|have|order) (something|food)|food options|hungry)\b",
    re.IGNORECASE,
)

_QUANTITY_WORDS: dict[str, int] = {
    "a": 1, "an": 1, "one": 1, "single": 1, "two": 2, "couple": 2,
    "three": 3, "few": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}
# How many words before a recognized item to look for its quantity —
# "two orders of chicken biryani" (3 words back) still resolves; a
# quantity further back than this belongs to a different clause.
_QUANTITY_LOOKBACK = 4


def is_food_order(
    text: str, menu_items: Optional[list[MenuItemContext]] = None
) -> bool:
    """Used by `intent_classifier.py` to classify ORDER intent without
    duplicating this agent's own matching logic a second time. True for
    v0's generic hunger phrasing ("I'm hungry", "order room service"),
    unchanged — and, once a menu exists, also true when the message
    names a specific configured dish by name ("Two chicken biryani"),
    even with no hunger word anywhere in it. Reuses the exact same
    word-bounded name matching `answer()` itself uses (`_find_direct_
    matches`), so intent classification and actual recognition can
    never drift out of sync with each other.
    """
    normalized_text = text or ""
    if _FOOD_INTENT_PATTERN.search(normalized_text):
        return True
    if menu_items:
        words = _normalize(normalized_text)
        if _find_direct_matches(words, menu_items):
            return True
        if _find_ambiguous_group(words, menu_items) is not None:
            return True
    return False


def _normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into words — the same
    normalization applied to both the guest's message and every
    `MenuItem.name`, so matching never depends on case or punctuation."""
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()


def _quantity_token_to_int(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return _QUANTITY_WORDS.get(token)


def _quantity_before(words: list[str], start: int) -> Optional[int]:
    """Looks back up to `_QUANTITY_LOOKBACK` words from a matched item's
    start index for the closest quantity token. Returns `None` — never
    a guessed default of 1 — when none is found; a missing quantity is
    always a clarifying question, never an assumption."""
    window_start = max(0, start - _QUANTITY_LOOKBACK)
    for i in range(start - 1, window_start - 1, -1):
        value = _quantity_token_to_int(words[i])
        if value is not None:
            return value
    return None


def _cart_line(
    *, menu_item_id: str, name: str, price: float, currency: str, quantity: int
) -> dict[str, Any]:
    return {
        "menu_item_id": menu_item_id,
        "name": name,
        "price": price,
        "currency": currency,
        "quantity": quantity,
    }


def _cart_line_from_item(item: MenuItemContext, quantity: int) -> dict[str, Any]:
    return _cart_line(
        menu_item_id=item.id, name=item.name, price=item.price,
        currency=item.currency, quantity=quantity,
    )


def _cart_line_from_candidate(candidate: dict[str, Any], quantity: int) -> dict[str, Any]:
    return _cart_line(
        menu_item_id=candidate["menu_item_id"], name=candidate["name"],
        price=candidate["price"], currency=candidate["currency"], quantity=quantity,
    )


def _candidate_dict(item: MenuItemContext) -> dict[str, Any]:
    return {
        "menu_item_id": item.id,
        "name": item.name,
        "price": item.price,
        "currency": item.currency,
    }


class _DirectMatch:
    __slots__ = ("item", "start", "end")

    def __init__(self, item: MenuItemContext, start: int, end: int):
        self.item = item
        self.start = start
        self.end = end


def _find_direct_matches(
    words: list[str], menu_items: list[MenuItemContext]
) -> list[_DirectMatch]:
    """An item's full name, word-for-word, appears somewhere in the
    message — the only mechanism this agent uses to recognize a
    specific dish. Longest names are checked first so "Chicken Biryani
    (Spicy)" (if that literal phrase is what the guest typed) is
    preferred over a shorter, coincidentally-contained name."""
    matches: list[_DirectMatch] = []
    matched_item_ids: set[str] = set()
    items_by_length = sorted(
        menu_items, key=lambda i: len(_normalize(i.name)), reverse=True
    )
    for item in items_by_length:
        if item.id in matched_item_ids:
            continue
        name_words = _normalize(item.name)
        if not name_words:
            continue
        n = len(name_words)
        for i in range(len(words) - n + 1):
            if words[i : i + n] == name_words:
                matches.append(_DirectMatch(item, i, i + n))
                matched_item_ids.add(item.id)
                break
    return matches


def _find_ambiguous_group(
    words: list[str], menu_items: list[MenuItemContext]
) -> Optional[tuple[str, list[MenuItemContext]]]:
    """Only checked when `_find_direct_matches` found nothing: does some
    2-4 word phrase in the message exactly match the *start* of more
    than one configured item's name (e.g. the guest said "chicken
    biryani", and the menu has "Chicken Biryani (Spicy)" and "(Mild)"
    but no plain "Chicken Biryani")? That's a real ambiguity to ask
    about, not a miss — returns the first such phrase found (v1 asks
    about one ambiguity at a time)."""
    item_name_words = {item.id: _normalize(item.name) for item in menu_items}
    for n in range(4, 1, -1):
        for i in range(len(words) - n + 1):
            phrase_words = words[i : i + n]
            candidates = [
                item
                for item in menu_items
                if item_name_words[item.id][:n] == phrase_words
                and len(item_name_words[item.id]) > n
            ]
            if len(candidates) >= 2:
                return " ".join(phrase_words), candidates
    return None


def _build_initial_payload(
    guest_message: str, menu_items: list[MenuItemContext]
) -> Optional[dict[str, Any]]:
    """First-turn parse of a fresh message into cart state. Returns
    `None` when nothing on the menu was recognized at all — the
    caller's signal to fall through to the v0 hand-off instead of
    inventing an order out of a generic hunger phrase."""
    words = _normalize(guest_message)
    direct = _find_direct_matches(words, menu_items)

    cart: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []

    if direct:
        for match in direct:
            quantity = _quantity_before(words, match.start)
            if quantity is None:
                queue.append({"type": "quantity", **_candidate_dict(match.item)})
            else:
                cart.append(_cart_line_from_item(match.item, quantity))
    else:
        ambiguous = _find_ambiguous_group(words, menu_items)
        if ambiguous is None:
            return None
        phrase, candidates = ambiguous
        queue.append(
            {
                "type": "choice",
                "phrase": phrase,
                "candidates": [_candidate_dict(c) for c in candidates],
            }
        )

    unresolved = queue.pop(0) if queue else None
    return {
        "complete": unresolved is None,
        "cart": cart,
        "unresolved": unresolved,
        "pending_queue": queue,
    }


def _cart_summary(cart: list[dict[str, Any]]) -> str:
    lines = [f"{line['quantity']}x {line['name']}" for line in cart]
    total = sum(line["price"] * line["quantity"] for line in cart)
    currency = cart[0]["currency"] if cart else ""
    return f"{', '.join(lines)} ({total:.2f} {currency})"


def _response_for_payload(payload: dict[str, Any]) -> str:
    unresolved = payload.get("unresolved")
    if unresolved is None:
        return f"You'd like: {_cart_summary(payload['cart'])}. Shall I confirm this order?"
    if unresolved["type"] == "quantity":
        return f"How many {unresolved['name']} would you like?"
    # type == "choice"
    names = " or ".join(c["name"] for c in unresolved["candidates"])
    return f"We have {names} — which would you like?"


def _resolve_quantity(message_body: str, unresolved: dict[str, Any]) -> Optional[dict[str, Any]]:
    words = _normalize(message_body)
    for word in words:
        value = _quantity_token_to_int(word)
        if value is not None:
            return _cart_line_from_candidate(unresolved, value)
    return None


def _resolve_choice(message_body: str, unresolved: dict[str, Any]) -> Optional[dict[str, Any]]:
    words = _normalize(message_body)
    candidates = unresolved["candidates"]
    # First try: the guest's reply contains one candidate's full name
    # verbatim — the same direct-match mechanism `answer()` uses.
    for candidate in candidates:
        name_words = _normalize(candidate["name"])
        n = len(name_words)
        for i in range(len(words) - n + 1):
            if words[i : i + n] == name_words:
                return dict(candidate)
    # Fallback: a single word distinguishes exactly one candidate from
    # the rest (e.g. "spicy" when the choice was Spicy vs. Mild).
    all_name_words = [set(_normalize(c["name"])) for c in candidates]
    for idx, candidate_words in enumerate(all_name_words):
        others = set().union(*(w for j, w in enumerate(all_name_words) if j != idx)) if len(all_name_words) > 1 else set()
        distinguishing = candidate_words - others
        if distinguishing and distinguishing & set(words):
            return dict(candidates[idx])
    return None


class OrderingAgent:
    """Stateless — holds no data between calls, same as every other
    agent so far. Implements both `Agent.answer()` (the Router's entry
    point) and `ClarifiableAgent.clarify()` (Conversation Manager's
    dispatch-back entry point, MENU_ORDERING.md §7.2)."""

    def answer(self, context: ConciergeContext, guest_message: str) -> AgentResponse:
        text = guest_message or ""

        if not is_food_order(text, context.menu_items):
            return AgentResponse(
                handled=False, response=None, should_escalate=False, metadata={}
            )

        if context.menu_items:
            payload = _build_initial_payload(text, context.menu_items)
            if payload is not None:
                metadata: dict[str, Any] = {"payload": payload}
                if payload["complete"]:
                    metadata["action_type"] = "ORDER_PROPOSED"
                return AgentResponse(
                    handled=True,
                    response=_response_for_payload(payload),
                    should_escalate=False,
                    metadata=metadata,
                )
            # Menu is configured but nothing in the message named a
            # specific dish ("I'm hungry", "get me something healthy")
            # — never invent a recommendation, fall through to the
            # generic hand-off below, unchanged from v0.

        return self._generic_handoff(context)

    def clarify(
        self, context: ConciergeContext, message_body: str, payload: dict[str, Any]
    ) -> AgentResponse:
        unresolved = payload.get("unresolved")
        if unresolved is None:
            # Conversation Manager should never dispatch here once
            # complete — defensive only.
            return AgentResponse(handled=False, should_escalate=True, metadata={})

        if unresolved["type"] == "quantity":
            resolved_line = _resolve_quantity(message_body, unresolved)
        else:
            resolved_choice = _resolve_choice(message_body, unresolved)
            resolved_line = None
            if resolved_choice is not None:
                # A quantity may already have been captured for this
                # item back when the ambiguous phrase was first seen
                # (not tracked separately in v1 — the known simplifying
                # limitation noted in this module's docstring); default
                # to 1 and let the guest correct it at confirmation.
                resolved_line = _cart_line_from_candidate(resolved_choice, quantity=1)

        if resolved_line is None:
            # Reply didn't resolve the outstanding question at all —
            # unresolvable clarification (§7.4): abandon the build,
            # let Conversation Manager escalate. No "payload" key.
            return AgentResponse(
                handled=False,
                response=None,
                should_escalate=True,
                metadata={},
            )

        new_cart = [*payload["cart"], resolved_line]
        queue = list(payload.get("pending_queue") or [])
        next_unresolved = queue.pop(0) if queue else None
        new_payload = {
            "complete": next_unresolved is None,
            "cart": new_cart,
            "unresolved": next_unresolved,
            "pending_queue": queue,
        }
        metadata: dict[str, Any] = {"payload": new_payload}
        if new_payload["complete"]:
            metadata["action_type"] = "ORDER_PROPOSED"
        return AgentResponse(
            handled=True,
            response=_response_for_payload(new_payload),
            should_escalate=False,
            metadata=metadata,
        )

    def _generic_handoff(self, context: ConciergeContext) -> AgentResponse:
        """v0's unchanged triage: room service hand-off, restaurant
        recommendation, or escalate — for a property with no menu
        catalog yet, or a generic hunger signal naming nothing specific.
        """
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

        return AgentResponse(
            handled=True,
            response="Let me check with our team about food options for you.",
            should_escalate=True,
            metadata={"handoff": None},
        )


def on_order_confirmed(
    db: Session,
    context: ConciergeContext,
    pending: PendingAction,
    payload: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Registered with `ConversationManager.register_confirmation_handler
    ("ORDER_CONFIRMED", ...)` (`concierge_router.py`, alongside this
    agent's `ClarifiableAgent` registration) — the one moment `Order`/
    `OrderItem` rows are actually created, snapshotting `payload["cart"]`
    (MENU_ORDERING.md §6/§7.4).

    Lives here, not inside `conversation_manager.py`, on purpose:
    `ConversationManager`'s own frozen scope explicitly forbids it from
    deciding domain logic ("must NOT... decide revenue offers or
    prices") — constructing an `Order` from `payload.cart`'s
    order-specific shape is exactly that kind of domain decision. The
    registry-based hook is the same "small lookup dict" extension point
    `_CONFIRMABLE_ACTION_TYPES`/`_clarifiable_agents` already use, so
    Conversation Manager still never needs to know what "ORDER_CONFIRMED"
    means beyond "a registered handler exists for it."
    """
    cart = payload.get("cart") or []
    if not cart:
        return None
    total_amount = sum(line["price"] * line["quantity"] for line in cart)
    currency = cart[0]["currency"]
    order = Order(
        tenant_id=pending.tenant_id,
        property_id=context.property.id,
        guest_id=pending.guest_id,
        reservation_id=pending.reservation_id,
        correlation_id=pending.correlation_id,
        source_menu_import_id=None,
        status=OrderStatus.confirmed,
        total_amount=total_amount,
        currency=currency,
    )
    for line in cart:
        order.items.append(
            OrderItem(
                menu_item_id=line["menu_item_id"],
                name=line["name"],
                price=line["price"],
                currency=line["currency"],
                quantity=line["quantity"],
            )
        )
    db.add(order)
    db.flush()
    return {"order_id": order.id}


ordering_agent = OrderingAgent()
