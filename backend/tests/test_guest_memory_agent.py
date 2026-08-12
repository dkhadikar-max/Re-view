"""Guest Memory Agent — CONCIERGE.md §5.2, roadmap step 5.

No database session anywhere in this file, same as test_faq_agent.py —
`GuestMemoryAgent.answer()` takes a `ConciergeContext` and a message
string and returns a decision; nothing else.
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
from app.services.guest_memory_agent import GuestMemoryAgent, guest_memory_agent


def _make_context(
    *,
    stay_count: int = 1,
    preferred_room: str | None = None,
    guest_name: str = "Guest",
) -> ConciergeContext:
    return ConciergeContext(
        tenant_id="hotel-x",
        property=PropertyContext(
            id="prop-1", name="Hotel X", timezone="UTC", currency="EUR", brand_voice="Warm"
        ),
        guest=GuestContext(
            id="guest-1",
            name=guest_name,
            language="en",
            communication_preference="whatsapp",
            stay_count=stay_count,
            lifetime_spend=0.0,
            previous_reviews=0,
            complaint_history=0,
            upsell_acceptance=0.0,
            preferred_room=preferred_room,
        ),
        current_time=datetime.utcnow(),
        channel=ChannelMetadata(channel="whatsapp"),
    )


def test_implements_the_shared_agent_protocol():
    assert isinstance(guest_memory_agent, Agent)


@pytest.mark.parametrize(
    "message,expected_value",
    [
        ("I'm vegetarian", "Vegetarian"),
        ("I'm vegan", "Vegan"),
        ("I'm gluten-free", "Gluten-free"),
        ("I'm lactose intolerant", "Lactose-intolerant"),
    ],
)
def test_explicit_dietary_statement_produces_memory_update(message, expected_value):
    response = guest_memory_agent.answer(_make_context(), message)

    assert response.handled is True
    assert response.should_escalate is False
    updates = response.metadata["memory_updates"]
    assert len(updates) == 1
    assert updates[0]["field"] == "dietary_preferences"
    assert updates[0]["value"] == expected_value
    assert updates[0]["confidence"] > 0


def test_allergy_statement_captures_the_named_allergen_verbatim():
    response = guest_memory_agent.answer(_make_context(), "I'm allergic to peanuts")

    updates = response.metadata["memory_updates"]
    assert updates[0]["field"] == "dietary_preferences"
    assert updates[0]["value"] == "Allergic to peanuts"


def test_room_preference_statement_produces_memory_update():
    response = guest_memory_agent.answer(_make_context(), "I prefer a quiet room")

    assert response.handled is True
    updates = response.metadata["memory_updates"]
    assert updates[0]["field"] == "preferred_room"
    assert "quiet" in updates[0]["value"].lower()


def test_late_checkout_mention_produces_a_notes_memory_update():
    response = guest_memory_agent.answer(
        _make_context(), "Late checkout would be great if possible"
    )

    assert response.handled is True
    updates = response.metadata["memory_updates"]
    assert updates[0]["field"] == "notes"


def test_unrelated_faq_question_is_not_handled():
    """Guest Memory Agent must defer to FAQ Agent for topics it has no
    business answering — never touches revenue or FAQ responsibilities."""
    response = guest_memory_agent.answer(_make_context(), "What time is breakfast?")

    assert response.handled is False
    assert response.response is None
    assert response.metadata.get("memory_updates", []) == []


def test_never_infers_from_indirect_signals():
    """Curiosity about a topic is not a self-reported trait — asking
    about vegan options is not the same as stating 'I'm vegan'."""
    response = guest_memory_agent.answer(
        _make_context(), "Do you have any vegan options at breakfast?"
    )

    assert response.metadata.get("memory_updates", []) == []


def test_ambiguous_mention_produces_no_memory_update():
    response = guest_memory_agent.answer(_make_context(), "The food here looks really good")

    assert response.handled is False
    assert response.metadata.get("memory_updates", []) == []


def test_returning_guest_phrase_triggers_welcome_back_with_known_preference():
    context = _make_context(stay_count=3, preferred_room="Deluxe Suite", guest_name="Mr. Smith")
    response = guest_memory_agent.answer(context, "I've stayed here before")

    assert response.handled is True
    assert "Mr. Smith" in response.response
    assert "Deluxe Suite" in response.response
    assert response.metadata.get("memory_updates", []) == []


def test_returning_guest_phrase_with_no_stay_history_is_not_handled():
    context = _make_context(stay_count=1)  # first stay, nothing to welcome back to
    response = guest_memory_agent.answer(context, "I've stayed here before")

    assert response.handled is False


def test_agent_is_stateless_same_inputs_give_identical_results():
    context = _make_context()
    first = guest_memory_agent.answer(context, "I'm vegetarian")
    second = guest_memory_agent.answer(context, "I'm vegetarian")
    assert first == second


def test_multiple_agent_instances_share_no_state():
    context = _make_context()
    a = GuestMemoryAgent()
    b = GuestMemoryAgent()
    assert a.answer(context, "I'm vegan") == b.answer(context, "I'm vegan")


# -- message_id provenance (GUEST_MEMORY_EVIDENCE_CHAIN.md §3) ---------------


def test_message_id_is_threaded_onto_every_memory_update():
    response = guest_memory_agent.answer(_make_context(), "I'm vegetarian", message_id="msg-1")

    updates = response.metadata["memory_updates"]
    assert len(updates) == 1
    assert updates[0]["message_id"] == "msg-1"


def test_message_id_defaults_to_none_when_not_provided():
    """Every existing call site that hasn't been updated to pass
    message_id yet (or ever synthesizes an update without one) must
    keep working exactly as before -- this is a tolerant default, not
    a new required argument."""
    response = guest_memory_agent.answer(_make_context(), "I'm vegetarian")

    updates = response.metadata["memory_updates"]
    assert updates[0]["message_id"] is None
