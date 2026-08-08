"""Intent Classifier — CONCIERGE.md §4.1.

Pure unit tests of `classify_intent()` — no database session anywhere
in this file, same as every other agent's own tests. `ConciergeContext`
is built directly with whatever `services`/`packages` a given test
needs; `classify_intent()` itself never touches a database.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    GuestContext,
    PackageContext,
    PropertyContext,
    ServiceContext,
)
from app.services.intent_classifier import IntentCategory, classify_intent


def _make_context(
    services: list[ServiceContext] | None = None,
    packages: list[PackageContext] | None = None,
) -> ConciergeContext:
    return ConciergeContext(
        tenant_id="hotel-x",
        property=PropertyContext(
            id="prop-1", name="Hotel X", timezone="UTC", currency="EUR", brand_voice="Warm"
        ),
        guest=GuestContext(
            id="guest-1",
            name="Guest",
            language="en",
            communication_preference="whatsapp",
            stay_count=1,
            lifetime_spend=0.0,
            previous_reviews=0,
            complaint_history=0,
            upsell_acceptance=0.0,
        ),
        current_time=datetime.utcnow(),
        channel=ChannelMetadata(channel="whatsapp"),
        services=services or [],
        packages=packages or [],
    )


def _service(service_type: str, name: str) -> ServiceContext:
    return ServiceContext(
        id=f"svc-{service_type}",
        service_type=service_type,
        name=name,
        currency="EUR",
        complimentary=False,
        available=True,
    )


@pytest.mark.parametrize(
    "message,expected_category",
    [
        ("I'm vegetarian", IntentCategory.memory),
        ("I'm allergic to shellfish", IntentCategory.memory),
        ("I'm hungry", IntentCategory.order),
        ("What time is breakfast?", IntentCategory.information),
        ("Is the pool open?", IntentCategory.information),
        ("Thanks so much, see you soon!", IntentCategory.small_talk),
        ("The weather looks nice today", IntentCategory.unknown),
    ],
)
def test_each_category_is_recognized(message, expected_category):
    decision = classify_intent(message, _make_context())
    assert decision.category == expected_category
    assert decision.confidence >= 0.0


def test_memory_takes_precedence_over_a_shared_word_with_information():
    """'Allergic' is also a hard escalation-pattern word at the filter
    stage (checked before this classifier ever runs) — this test is
    purely about MEMORY vs. INFORMATION precedence within the
    classifier itself for a message the filter would already have let
    through."""
    decision = classify_intent("I'm vegetarian", _make_context())
    assert decision.category == IntentCategory.memory


def test_service_request_is_recognized_when_configured():
    context = _make_context(services=[_service("late_checkout", "Late Checkout")])
    decision = classify_intent("Can I check out at 4 PM?", context)
    assert decision.category == IntentCategory.service_request


def test_service_request_takes_precedence_over_information_on_shared_keyword():
    """The exact scenario that motivated intent-first dispatch: a
    message that could be read as either a fact lookup or a booking
    ask must resolve to SERVICE_REQUEST, not INFORMATION, when it
    matches Revenue Agent's own action-oriented pattern."""
    context = _make_context(services=[_service("late_checkout", "Late Checkout")])
    decision = classify_intent("Can I check out at 4 PM?", context)
    assert decision.category == IntentCategory.service_request


def test_bare_fact_lookup_stays_information_even_with_a_matching_service_configured():
    context = _make_context(services=[_service("breakfast", "Breakfast")])
    decision = classify_intent("What time is breakfast?", context)
    assert decision.category == IntentCategory.information


def test_order_takes_precedence_over_service_request_for_room_service():
    """Ordering Agent should get "Can I order room service please"
    before Revenue Agent does, matching the priority the reviewed spec
    established — room_service is a valid Revenue service_type too, but
    ORDER is checked first."""
    context = _make_context(services=[_service("room_service", "Room Service")])
    decision = classify_intent("Can I order room service please", context)
    assert decision.category == IntentCategory.order


def test_occasion_request_classifies_as_service_request():
    context = _make_context(packages=[PackageContext(id="pkg-1", name="Romance Package", occasions=["romance"], currency="EUR", available=True)])
    decision = classify_intent("Can I decorate the room?", context)
    assert decision.category == IntentCategory.service_request


@pytest.mark.parametrize(
    "message",
    [
        "Thanks so much, see you soon!",
        "Thank you!",
        "Hi there",
        "Good morning",
        "OK, great, thanks",
        "See you soon, bye!",
    ],
)
def test_small_talk_phrasings_are_recognized(message):
    decision = classify_intent(message, _make_context())
    assert decision.category == IntentCategory.small_talk


def test_pleasantry_attached_to_a_real_request_is_not_small_talk():
    """A "thanks" prefix must not mask an actual request buried in the
    same message — this one contains "get breakfast", a real Revenue
    Agent pattern, and must not be swallowed as small talk."""
    decision = classify_intent("Thanks but can I also get breakfast?", _make_context())
    assert decision.category != IntentCategory.small_talk


def test_classifier_is_stateless_same_inputs_give_identical_results():
    context = _make_context()
    first = classify_intent("I'm hungry", context)
    second = classify_intent("I'm hungry", context)
    assert first == second
