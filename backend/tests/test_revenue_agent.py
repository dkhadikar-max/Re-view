"""Revenue Agent — CONCIERGE.md §5.3, reworked to be hotel-configuration-
aware (see `revenue_agent.py` module docstring for the full spec this
supersedes v1's narrow "always hedge" behavior with).

No database session anywhere in this file, same as test_faq_agent.py
and test_guest_memory_agent.py — `RevenueAgent.answer()` takes a
`ConciergeContext` and a message string and returns a decision, nothing
else. All hotel configuration is passed in directly via `ServiceContext`
/`PackageContext`/`PreviousOfferContext` — no ORM objects anywhere here.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.agent_protocol import Agent
from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    GuestContext,
    PackageContext,
    PreviousOfferContext,
    PropertyContext,
    ServiceContext,
)
from app.services.revenue_agent import RevenueAgent, revenue_agent


def _make_context(
    services: list[ServiceContext] | None = None,
    packages: list[PackageContext] | None = None,
    previous_offers: list[PreviousOfferContext] | None = None,
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
        previous_offers=previous_offers or [],
    )


def _service(
    service_type: str,
    name: str,
    *,
    price: float | None = 25.0,
    currency: str = "EUR",
    complimentary: bool = False,
    available: bool = True,
) -> ServiceContext:
    return ServiceContext(
        id=f"svc-{service_type}",
        service_type=service_type,
        name=name,
        price=price,
        currency=currency,
        complimentary=complimentary,
        available=available,
    )


def _package(
    name: str,
    occasions: list[str],
    *,
    price: float | None = 150.0,
    currency: str = "EUR",
    available: bool = True,
) -> PackageContext:
    return PackageContext(
        id=f"pkg-{name.lower().replace(' ', '-')}",
        name=name,
        occasions=occasions,
        price=price,
        currency=currency,
        available=available,
    )


def test_implements_the_shared_agent_protocol():
    assert isinstance(revenue_agent, Agent)


def test_spec_example_late_checkout_configured_and_paid():
    """The exact example from the reviewed spec, now quoting a real
    configured price instead of hedging forever."""
    context = _make_context(
        services=[_service("late_checkout", "Late Checkout", price=30.0)]
    )
    response = revenue_agent.answer(context, "Can I check out at 4 PM?")

    assert response.handled is True
    assert response.should_escalate is False
    opp = response.metadata["service_opportunity"]
    assert opp["service_type"] == "late_checkout"
    assert opp["configured"] is True
    assert opp["available"] is True
    assert "30.00 EUR" in response.response


def test_complimentary_service_is_stated_as_free_not_priced():
    context = _make_context(
        services=[_service("late_checkout", "Late Checkout", complimentary=True)]
    )
    response = revenue_agent.answer(context, "Can I check out at 4 PM?")

    assert response.handled is True
    assert response.should_escalate is False
    assert "complimentary" in response.response.lower()
    assert response.metadata["service_opportunity"]["complimentary"] is True


def test_configured_but_unavailable_service_escalates():
    context = _make_context(
        services=[_service("spa", "Spa", available=False)]
    )
    response = revenue_agent.answer(context, "I'd like to book a massage")

    assert response.handled is True
    assert response.should_escalate is True
    assert response.metadata["service_opportunity"]["available"] is False


def test_unconfigured_service_never_invented_but_still_escalates():
    """The hotel doesn't have this service at all — never invent an
    offer, but an explicit ask still gets escalated for a human answer
    rather than silently dropped."""
    context = _make_context(services=[])
    response = revenue_agent.answer(context, "I need an airport transfer")

    assert response.handled is True
    assert response.should_escalate is True
    opp = response.metadata["service_opportunity"]
    assert opp["service_type"] == "airport_transfer"
    assert opp["configured"] is False


def test_any_configured_service_reachable_by_literal_name_fallback():
    """'Any service configured by the hotel' — a service type outside
    the fixed pattern list is still recognized if the guest literally
    names it, and only because it's genuinely configured."""
    context = _make_context(
        services=[_service("bike_rental", "Bike Rental", price=15.0)]
    )
    response = revenue_agent.answer(context, "Do you have bike rental available?")

    assert response.handled is True
    assert response.should_escalate is False
    assert response.metadata["service_opportunity"]["service_type"] == "bike_rental"


def test_short_service_names_do_not_cause_false_positive_fallback_matches():
    context = _make_context(services=[_service("gym", "Gym", price=10.0)])
    response = revenue_agent.answer(context, "Thanks so much, see you soon!")

    assert response.handled is False


def test_previous_active_offer_is_not_repeated():
    context = _make_context(
        services=[_service("late_checkout", "Late Checkout", price=30.0)],
        previous_offers=[
            PreviousOfferContext(
                id="offer-1",
                name="Late Checkout",
                category="late_checkout",
                status="offered",
                price=30.0,
                currency="EUR",
                created_at=datetime.utcnow(),
            )
        ],
    )
    response = revenue_agent.answer(context, "Can I check out at 4 PM?")

    assert response.handled is True
    assert response.should_escalate is False
    assert response.metadata["duplicate_suppressed"] is True
    assert "already" in response.response.lower()


def test_declined_previous_offer_can_be_offered_again():
    context = _make_context(
        services=[_service("late_checkout", "Late Checkout", price=30.0)],
        previous_offers=[
            PreviousOfferContext(
                id="offer-1",
                name="Late Checkout",
                category="late_checkout",
                status="declined",
                price=30.0,
                currency="EUR",
                created_at=datetime.utcnow(),
            )
        ],
    )
    response = revenue_agent.answer(context, "Can I check out at 4 PM?")

    assert response.metadata.get("duplicate_suppressed") is None
    assert "30.00 EUR" in response.response


@pytest.mark.parametrize(
    "message,expected_type",
    [
        ("Can I check out at 4 PM?", "late_checkout"),
        ("Could I check in early tomorrow?", "early_checkin"),
        ("Can I add breakfast package to my stay?", "breakfast"),
        ("I'd like to reserve a table for dinner", "dinner"),
        ("Can I order room service please", "room_service"),
        ("Can I get my laundry done today?", "laundry"),
        ("I'd like to book a massage", "spa"),
        ("Can you arrange an airport transfer for me?", "airport_transfer"),
        ("I need to book parking for my car", "parking"),
        ("Do you have activities for my kids?", "kids_activities"),
        ("I'd like to book a city tour", "tours"),
        ("Do you offer a gym package?", "gym"),
        ("Can you book a cab for me?", "cab_booking"),
    ],
)
def test_each_service_type_is_recognized_when_configured(message, expected_type):
    context = _make_context(
        services=[_service(expected_type, expected_type.replace("_", " ").title())]
    )
    response = revenue_agent.answer(context, message)

    assert response.handled is True
    assert response.metadata["service_opportunity"]["service_type"] == expected_type


def test_romance_package_offered_for_explicit_decoration_request():
    context = _make_context(
        packages=[_package("Romance Package", ["romance"], price=80.0)]
    )
    response = revenue_agent.answer(context, "Can I decorate the room?")

    assert response.handled is True
    assert response.should_escalate is False
    assert "80.00 EUR" in response.response
    assert response.metadata["package_opportunity"]["occasion"] == "romance"


def test_explicit_decoration_request_escalates_when_no_package_configured():
    context = _make_context(packages=[])
    response = revenue_agent.answer(context, "Can I decorate the room for my wife?")

    assert response.handled is True
    assert response.should_escalate is True
    assert response.metadata["package_opportunity"]["configured"] is False


def test_celebration_package_offered_for_anniversary_mention():
    context = _make_context(
        packages=[_package("Celebration Package", ["anniversary", "birthday"], price=120.0)]
    )
    response = revenue_agent.answer(context, "It's our anniversary this weekend!")

    assert response.handled is True
    assert response.should_escalate is False
    assert "120.00 EUR" in response.response


def test_passive_occasion_mention_defers_when_no_package_configured():
    """An anniversary mention with nothing configured to offer is not
    escalated — it's information, not a request; Guest Memory Agent
    (later in the Router) is the right place for it to land."""
    context = _make_context(packages=[])
    response = revenue_agent.answer(context, "It's our anniversary this weekend!")

    assert response.handled is False
    assert response.should_escalate is False


def test_unavailable_package_is_not_offered_on_passive_mention():
    context = _make_context(
        packages=[_package("Celebration Package", ["anniversary"], available=False)]
    )
    response = revenue_agent.answer(context, "It's our anniversary this weekend!")

    assert response.handled is False


def test_faq_style_question_is_not_treated_as_an_opportunity():
    """'What time is breakfast?' is a fact lookup (FAQ Agent's job), not
    a sales signal — the two agents must stay out of each other's
    territory even though both mention 'breakfast'."""
    context = _make_context(services=[_service("breakfast", "Breakfast")])
    response = revenue_agent.answer(context, "What time is breakfast?")

    assert response.handled is False
    assert "service_opportunity" not in response.metadata


def test_unrelated_message_is_not_handled():
    response = revenue_agent.answer(_make_context(), "Thanks so much, see you soon!")

    assert response.handled is False
    assert response.response is None
    assert response.should_escalate is False


def test_never_invents_an_opportunity_from_an_ambiguous_message():
    context = _make_context(
        services=[_service("late_checkout", "Late Checkout")],
        packages=[_package("Romance Package", ["romance"])],
    )
    response = revenue_agent.answer(context, "The weather looks nice today")

    assert response.handled is False
    assert response.metadata == {}


def test_metadata_key_is_not_memory_updates():
    """Distinct from GuestMemoryAgent's metadata shape — a future
    Router must never confuse the two."""
    context = _make_context(services=[_service("late_checkout", "Late Checkout")])
    response = revenue_agent.answer(context, "Can I check out at 4 PM?")

    assert "memory_updates" not in response.metadata


def test_only_escalates_for_its_own_configured_or_unavailable_reasons():
    """should_escalate is False for anything this agent doesn't
    recognize or fully handle — it never second-guesses the Escalation
    Filter's prior decision, it only ever adds escalation for a
    configured-but-unavailable or wholly-unconfigured explicit ask."""
    context = _make_context()
    for message in ["Something totally unrelated", "Thanks so much, see you soon!"]:
        response = revenue_agent.answer(context, message)
        assert response.should_escalate is False


def test_agent_is_stateless_same_inputs_give_identical_results():
    context = _make_context(services=[_service("spa", "Spa")])
    first = revenue_agent.answer(context, "I'd like to book a massage")
    second = revenue_agent.answer(context, "I'd like to book a massage")
    assert first == second


def test_multiple_agent_instances_share_no_state():
    context = _make_context(services=[_service("spa", "Spa")])
    a = RevenueAgent()
    b = RevenueAgent()
    assert a.answer(context, "I'd like to book a massage") == b.answer(
        context, "I'd like to book a massage"
    )
