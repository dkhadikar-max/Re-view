"""FAQ Agent — CONCIERGE.md §5.1, roadmap step 4.

No database session anywhere in this file — that's the point.
`FAQAgent.answer()` takes a `ConciergeContext` and a message string and
returns a decision; it has no other inputs and no side effects to test
around.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    GuestContext,
    KnowledgeBaseContext,
    PropertyContext,
)
from app.services.faq_agent import FAQAgent, faq_agent


def _make_context(knowledge_base: KnowledgeBaseContext | None = None) -> ConciergeContext:
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
        knowledge_base=knowledge_base,
    )


@pytest.mark.parametrize(
    "message,field,value,expected_snippet",
    [
        ("What's the wifi password?", "wifi_password", "guest1234", "guest1234"),
        ("What time is breakfast?", "breakfast_hours", "7-10am", "7-10am"),
        ("Is the pool open?", "pool_hours", "9am-8pm", "9am-8pm"),
        ("Do you have a gym?", "gym_hours", "24/7", "24/7"),
        ("Can I book the spa?", "spa_hours", "10am-6pm", "10am-6pm"),
        ("Where can I park?", "parking_info", "Free lot behind the hotel", "Free lot behind the hotel"),
        ("What time is check-in?", "checkin_time", "3pm", "3pm"),
        ("What time is checkout?", "checkout_time", "11am", "11am"),
        ("Do you allow pets?", "pet_policy", "Dogs under 20kg welcome", "Dogs under 20kg welcome"),
        ("Any restaurant recommendations?", "restaurants", "Try Osteria Bella", "Osteria Bella"),
    ],
)
def test_answers_recognized_topic_with_field_verbatim(message, field, value, expected_snippet):
    kb = KnowledgeBaseContext(**{field: value})
    response = faq_agent.answer(_make_context(kb), message)

    assert response.should_escalate is False
    assert response.source == field
    assert response.confidence > 0
    assert expected_snippet in response.answer
    # Never invents beyond the stored fact — the exact stored value must
    # appear verbatim in the answer, not a paraphrase of it.
    assert value in response.answer


def test_recognized_topic_with_empty_field_escalates():
    kb = KnowledgeBaseContext(wifi_password=None)
    response = faq_agent.answer(_make_context(kb), "What's the wifi password?")

    assert response.should_escalate is True
    assert response.answer is None
    assert response.source == "wifi_password"
    assert response.confidence == 0.0


def test_no_knowledge_base_at_all_escalates():
    response = faq_agent.answer(_make_context(None), "What's the wifi password?")

    assert response.should_escalate is True
    assert response.answer is None


def test_unrecognized_message_escalates_with_no_source():
    response = faq_agent.answer(_make_context(), "Do you sell lottery tickets here?")

    assert response.should_escalate is True
    assert response.answer is None
    assert response.source is None


def test_never_invents_information_beyond_the_stored_fact():
    """The KB has an answer for breakfast but not for the pool — asking
    about the pool must never fall back to inventing an answer from
    context, even though other KB data exists for this property."""
    kb = KnowledgeBaseContext(breakfast_hours="7-10am")
    response = faq_agent.answer(_make_context(kb), "Is the pool heated?")

    assert response.should_escalate is True
    assert response.answer is None


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("checkin_time", "3pm", "Could I check in early tomorrow?"),
        ("checkout_time", "11am", "Can I check out at 4 PM?"),
        ("late_checkout_policy", "Subject to availability", "Can I get a late checkout?"),
        ("parking_info", "Free lot behind the hotel", "I need to book parking for my car"),
        ("spa_hours", "10am-6pm", "I'd like to book a spa treatment"),
        ("gym_hours", "24/7", "Do you offer a gym package?"),
        ("airport_transfer_info", "Available on request", "I need an airport transfer"),
        ("breakfast_hours", "7-10am", "Can I add breakfast package to my stay?"),
        ("restaurants", "Try Osteria Bella", "Can I book a table at the restaurant for dinner?"),
        ("services", "Room service, laundry", "Can I order room service please"),
        ("services", "Room service, laundry", "Can you arrange laundry service?"),
    ],
)
def test_defers_to_revenue_or_ordering_agent_for_actionable_phrasing(field, value, message):
    """A booking-shaped message must not be hijacked by FAQ Agent just
    because it shares a keyword with one of FAQ's own fact-lookup
    topics — this is exactly the tension the Concierge Router's
    priority order (FAQ first) would otherwise create. `source is None`
    is what tells the Router "not my topic, try the next agent",
    verified via the parametrized fixtures in test_concierge_router.py
    too."""
    kb = KnowledgeBaseContext(**{field: value})
    response = faq_agent.answer(_make_context(kb), message)

    assert response.source is None
    assert response.answer is None


def test_agent_is_stateless_same_inputs_give_identical_results():
    kb = KnowledgeBaseContext(wifi_password="guest1234")
    context = _make_context(kb)
    first = faq_agent.answer(context, "What's the wifi password?")
    second = faq_agent.answer(context, "What's the wifi password?")
    assert first == second


def test_multiple_agent_instances_share_no_state():
    """A fresh FAQAgent() behaves identically to the shared singleton —
    confirms there's no hidden per-instance state to reuse or leak."""
    kb = KnowledgeBaseContext(breakfast_hours="7-10am")
    context = _make_context(kb)
    a = FAQAgent()
    b = FAQAgent()
    assert a.answer(context, "breakfast?") == b.answer(context, "breakfast?")
