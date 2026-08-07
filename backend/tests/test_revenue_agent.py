"""Revenue Agent — CONCIERGE.md §5.3, roadmap step 6.

No database session anywhere in this file, same as test_faq_agent.py
and test_guest_memory_agent.py — `RevenueAgent.answer()` takes a
`ConciergeContext` and a message string and returns a decision, nothing
else.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.agent_protocol import Agent
from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    GuestContext,
    PropertyContext,
)
from app.services.revenue_agent import RevenueAgent, revenue_agent


def _make_context() -> ConciergeContext:
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
    )


def test_implements_the_shared_agent_protocol():
    assert isinstance(revenue_agent, Agent)


def test_spec_example_late_checkout():
    """The exact example from the reviewed spec."""
    response = revenue_agent.answer(_make_context(), "Can I check out at 4 PM?")

    assert response.handled is True
    assert response.should_escalate is False
    opportunities = response.metadata["opportunities"]
    assert len(opportunities) == 1
    assert opportunities[0]["type"] == "late_checkout"
    assert opportunities[0]["confidence"] > 0
    assert "subject to availability" in response.response
    assert "check availability" in response.response


@pytest.mark.parametrize(
    "message,expected_type",
    [
        ("Can I check out at 4 PM?", "late_checkout"),
        ("Could I check in early tomorrow?", "early_checkin"),
        ("Can I add breakfast package to my stay?", "breakfast_package"),
        ("I'd like to book a massage", "spa"),
        ("Can you arrange an airport transfer for me?", "airport_transfer"),
        ("I need to book parking for my car", "parking"),
        ("Can I upgrade my room to a suite?", "room_upgrade"),
        ("I'd like to reserve a table for dinner", "meal_reservation"),
    ],
)
def test_each_opportunity_type_is_recognized(message, expected_type):
    response = revenue_agent.answer(_make_context(), message)

    assert response.handled is True
    assert response.metadata["opportunities"][0]["type"] == expected_type


def test_every_response_hedges_never_confirms_availability():
    """'Never recommend unavailable services' is enforced by never
    claiming anything IS available — every recognized opportunity's
    response must hedge, never assert."""
    for message in [
        "Can I check out at 4 PM?",
        "I'd like to book a massage",
        "Can I upgrade my room to a suite?",
    ]:
        response = revenue_agent.answer(_make_context(), message)
        lowered = response.response.lower()
        assert any(
            phrase in lowered
            for phrase in ("subject to availability", "may be available", "would you like")
        )


def test_metadata_key_is_opportunities_not_memory_updates():
    """Distinct from GuestMemoryAgent's metadata shape — a future
    Router must never confuse the two."""
    response = revenue_agent.answer(_make_context(), "Can I check out at 4 PM?")

    assert "opportunities" in response.metadata
    assert "memory_updates" not in response.metadata


def test_never_overrides_the_escalation_filter():
    """should_escalate is always False — this agent has no basis to
    second-guess a decision the Escalation Filter already made
    upstream, even for an ambiguous or unrecognized message."""
    for message in ["Can I check out at 4 PM?", "Something totally unrelated"]:
        response = revenue_agent.answer(_make_context(), message)
        assert response.should_escalate is False


def test_faq_style_question_is_not_treated_as_an_opportunity():
    """'What time is breakfast?' is a fact lookup (FAQ Agent's job), not
    a sales signal — the two agents must stay out of each other's
    territory even though both mention 'breakfast'."""
    response = revenue_agent.answer(_make_context(), "What time is breakfast?")

    assert response.handled is False
    assert response.metadata.get("opportunities", []) == []


def test_unrelated_message_is_not_handled():
    response = revenue_agent.answer(_make_context(), "Thanks so much, see you soon!")

    assert response.handled is False
    assert response.response is None
    assert response.metadata.get("opportunities", []) == []


def test_never_invents_an_opportunity_from_an_ambiguous_message():
    response = revenue_agent.answer(_make_context(), "The weather looks nice today")

    assert response.handled is False
    assert response.metadata.get("opportunities", []) == []


def test_agent_is_stateless_same_inputs_give_identical_results():
    context = _make_context()
    first = revenue_agent.answer(context, "Can I check out at 4 PM?")
    second = revenue_agent.answer(context, "Can I check out at 4 PM?")
    assert first == second


def test_multiple_agent_instances_share_no_state():
    context = _make_context()
    a = RevenueAgent()
    b = RevenueAgent()
    assert a.answer(context, "I'd like to book a massage") == b.answer(
        context, "I'd like to book a massage"
    )
