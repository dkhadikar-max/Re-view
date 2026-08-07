"""Ordering Agent v0 — MENU_ORDERING.md, minimal triage only (see
`ordering_agent.py` module docstring). No database session anywhere in
this file, same as every other agent test — `OrderingAgent.answer()`
takes a `ConciergeContext` and a message string and returns a decision.
"""

from __future__ import annotations

from datetime import datetime

from app.services.agent_protocol import Agent
from app.services.context_builder import (
    ChannelMetadata,
    ConciergeContext,
    GuestContext,
    KnowledgeBaseContext,
    PropertyContext,
    ServiceContext,
)
from app.services.ordering_agent import OrderingAgent, ordering_agent


def _make_context(
    services: list[ServiceContext] | None = None,
    knowledge_base: KnowledgeBaseContext | None = None,
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
        knowledge_base=knowledge_base,
    )


def _room_service(available: bool = True) -> ServiceContext:
    return ServiceContext(
        id="svc-room-service",
        service_type="room_service",
        name="Room Service",
        currency="EUR",
        complimentary=False,
        available=available,
    )


def test_implements_the_shared_agent_protocol():
    assert isinstance(ordering_agent, Agent)


def test_hands_off_to_room_service_when_configured():
    context = _make_context(services=[_room_service()])
    response = ordering_agent.answer(context, "I'm hungry")

    assert response.handled is True
    assert response.should_escalate is False
    assert response.metadata["handoff"] == "room_service"
    assert "Room Service" in response.response


def test_recommends_restaurant_when_no_room_service_but_kb_has_one():
    context = _make_context(
        knowledge_base=KnowledgeBaseContext(restaurants="The Olive Grove, open till 11pm")
    )
    response = ordering_agent.answer(context, "I'm hungry")

    assert response.handled is True
    assert response.should_escalate is False
    assert response.metadata["handoff"] == "restaurant"
    assert "The Olive Grove, open till 11pm" in response.response


def test_never_invents_a_restaurant_name():
    """No KB restaurant text and no room service — must never invent a
    name or hours, must escalate instead."""
    context = _make_context()
    response = ordering_agent.answer(context, "I'm hungry")

    assert response.handled is True
    assert response.should_escalate is True
    assert response.metadata["handoff"] is None


def test_unavailable_room_service_falls_through_to_restaurant():
    context = _make_context(
        services=[_room_service(available=False)],
        knowledge_base=KnowledgeBaseContext(restaurants="The Olive Grove"),
    )
    response = ordering_agent.answer(context, "I'm hungry")

    assert response.metadata["handoff"] == "restaurant"


def test_room_service_takes_priority_over_restaurant_when_both_exist():
    context = _make_context(
        services=[_room_service()],
        knowledge_base=KnowledgeBaseContext(restaurants="The Olive Grove"),
    )
    response = ordering_agent.answer(context, "I'm hungry")

    assert response.metadata["handoff"] == "room_service"


def test_non_food_message_is_not_handled():
    context = _make_context(services=[_room_service()])
    response = ordering_agent.answer(context, "Can I check out at 4 PM?")

    assert response.handled is False
    assert response.response is None
    assert response.should_escalate is False


def test_never_overrides_escalation_filter_for_unrelated_messages():
    context = _make_context()
    response = ordering_agent.answer(context, "Thanks so much, see you soon!")
    assert response.should_escalate is False


def test_agent_is_stateless_same_inputs_give_identical_results():
    context = _make_context(services=[_room_service()])
    first = ordering_agent.answer(context, "I'm hungry")
    second = ordering_agent.answer(context, "I'm hungry")
    assert first == second


def test_multiple_agent_instances_share_no_state():
    context = _make_context(services=[_room_service()])
    a = OrderingAgent()
    b = OrderingAgent()
    assert a.answer(context, "I'm hungry") == b.answer(context, "I'm hungry")
