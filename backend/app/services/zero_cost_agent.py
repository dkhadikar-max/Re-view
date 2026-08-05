"""Zero-cost guest agent — templates + guest memory, no LLM calls.

Handles repetitive hospitality flows without OpenAI:
  - Welcome / pre-arrival
  - Booking reminders
  - Upsell offers (catalog pick from travel type)
  - Review / feedback requests
  - Standard review reply drafts

Call GPT only when context.require_llm is True (or config opts in).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    AIDecision,
    Guest,
    Property,
    Reservation,
)
from app.services.ai_orchestrator import (
    ALLOWED_CHANNELS,
    UPSELL_CATALOG,
    AIDecisionSchema,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "zero-cost-agent-v1"

# Actions this agent owns end-to-end (no token spend).
ROUTINE_ACTIONS = {
    "Welcome",
    "BookingReminder",
    "Upsell",
    "ReviewRequest",
    "FeedbackRequest",
    "None",
}


def _channel_for(guest: Guest) -> str:
    channel = (guest.communication_preference or "whatsapp").lower()
    return channel if channel in ALLOWED_CHANNELS else "email"


def _language_for(guest: Guest) -> str:
    return (guest.language or "en").lower()[:8]


def _travel_bucket(guest: Guest) -> str:
    travel = (guest.travel_type or guest.purpose or "default").lower()
    if guest.children and guest.children > 0:
        return "family"
    if travel in UPSELL_CATALOG:
        return travel
    return "default"


def _pick_offer(guest: Guest) -> tuple[str, float, str]:
    catalog = UPSELL_CATALOG.get(_travel_bucket(guest), UPSELL_CATALOG["default"])
    return catalog[0]


def retrieve_guest_context(
    guest: Guest, reservation: Reservation, property_: Property
) -> dict[str, Any]:
    """Lightweight 'RAG': structured retrieval from DB memory, not embeddings."""
    return {
        "guest_first_name": (guest.name or "Guest").split()[0],
        "guest_name": guest.name,
        "guest_country": guest.country,
        "guest_language": _language_for(guest),
        "guest_channel": _channel_for(guest),
        "guest_prefs": guest.communication_preference,
        "travel_type": _travel_bucket(guest),
        "ltv": float(guest.ltv_score or 0),
        "stay_count": guest.stay_count or 0,
        "hotel": property_.name,
        "city": property_.city,
        "brand_voice": property_.brand_voice or "",
        "room_type": reservation.room_type,
        "check_in": reservation.check_in.isoformat()
        if hasattr(reservation.check_in, "isoformat")
        else str(reservation.check_in),
        "check_out": reservation.check_out.isoformat()
        if hasattr(reservation.check_out, "isoformat")
        else str(reservation.check_out),
    }


def choose_routine_action(
    guest: Guest,
    reservation: Reservation,
    context: dict[str, Any] | None = None,
) -> str:
    ctx = context or {}
    forced = ctx.get("force_action")
    if forced in ROUTINE_ACTIONS:
        return str(forced)

    today = datetime.utcnow().date()
    days_to_arrival = (reservation.check_in - today).days
    days_since_checkout = (today - reservation.check_out).days

    if days_since_checkout >= 0 and days_to_arrival < 0:
        # Already checked out (or checkout day past arrival logic)
        if ctx.get("intent") == "feedback":
            return "FeedbackRequest"
        return "ReviewRequest"

    if days_to_arrival > 5:
        # Far from arrival — reminder or soft upsell
        if ctx.get("intent") == "reminder":
            return "BookingReminder"
        return "Upsell" if float(guest.ltv_score or 0) >= 40 else "BookingReminder"
    if days_to_arrival >= 0:
        return "Welcome"
    return "ReviewRequest"


def build_decision_payload(
    guest: Guest,
    reservation: Reservation,
    property_: Property,
    *,
    action: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a schema-compatible decision using templates + retrieved memory only."""
    memory = retrieve_guest_context(guest, reservation, property_)
    channel = memory["guest_channel"]
    language = memory["guest_language"]
    now = datetime.utcnow()
    offer_name: Optional[str] = None
    timing = "immediate"
    execute_at = now
    confidence = 0.96

    if action == "Upsell":
        offer_name, _, _ = _pick_offer(guest)
        days_to_arrival = (reservation.check_in - now.date()).days
        delay_days = min(max(days_to_arrival - 2, 1), 7)
        timing = f"{delay_days} days before arrival"
        execute_at = datetime.combine(reservation.check_in, datetime.min.time()) - timedelta(
            days=delay_days
        )
        confidence = 0.88
    elif action == "BookingReminder":
        timing = "3 days before arrival"
        execute_at = datetime.combine(reservation.check_in, datetime.min.time()) - timedelta(
            days=3
        )
        if execute_at < now:
            execute_at = now
            timing = "immediate"
    elif action == "Welcome":
        timing = "immediate"
        execute_at = now
    elif action in {"ReviewRequest", "FeedbackRequest"}:
        timing = "8 hours after checkout"
        execute_at = now + timedelta(hours=8)
    elif action == "None":
        timing = "n/a"
        confidence = 1.0

    # Map extended actions onto validator-friendly actions for persistence
    # while keeping the intended message_type for execute_decision.
    schema_action = action
    message_type = {
        "Welcome": "welcome",
        "BookingReminder": "booking_reminder",
        "Upsell": "upsell",
        "ReviewRequest": "review_request",
        "FeedbackRequest": "feedback_request",
        "None": "none",
    }.get(action, "welcome")

    if action == "BookingReminder":
        schema_action = "Welcome"
    elif action == "FeedbackRequest":
        schema_action = "ReviewRequest"

    reasoning = (
        f"{AGENT_NAME}: {action} via templates + guest memory "
        f"(no LLM). {memory['guest_first_name']} @ {memory['hotel']}, "
        f"{memory['travel_type']} traveler, channel={channel}."
    )

    return {
        "action": schema_action,
        "channel": channel,
        "language": language,
        "timing": timing,
        "offer": offer_name if schema_action == "Upsell" else None,
        "confidence": confidence,
        "reasoning": reasoning,
        "execute_at": execute_at.isoformat(),
        "message_type": message_type,
        "agent": AGENT_NAME,
        "cost_usd": 0.0,
        "memory_keys": list(memory.keys()),
        "requested_action": action,
    }


class ZeroCostAgent:
    """Automates repetitive guest ops at $0 AI cost."""

    name = AGENT_NAME

    def can_handle(self, context: dict[str, Any] | None = None) -> bool:
        ctx = context or {}
        if ctx.get("require_llm"):
            return False
        if not settings.zero_cost_agent_enabled:
            return False
        if ctx.get("force_action") == "Upsell" and settings.llm_for_upsells:
            return False
        return True

    def decide_raw(
        self,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = choose_routine_action(guest, reservation, context)
        return build_decision_payload(
            guest, reservation, property_, action=action, context=context
        )

    def decide(
        self,
        db: Session,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        context: dict[str, Any] | None = None,
    ) -> AIDecision:
        raw = self.decide_raw(guest, reservation, property_, context)
        decision = AIDecision(
            tenant_id=guest.tenant_id,
            reservation_id=reservation.id,
            guest_id=guest.id,
            action=str(raw.get("action", "None")),
            channel=raw.get("channel"),
            language=raw.get("language"),
            timing=raw.get("timing"),
            offer=raw.get("offer"),
            confidence=float(raw.get("confidence") or 0),
            reasoning=raw.get("reasoning"),
            raw_output=json.dumps(raw, default=str),
            model_name=self.name,
            validated=False,
            executed=False,
        )
        try:
            parsed = AIDecisionSchema.model_validate(
                {
                    "action": raw["action"],
                    "channel": raw["channel"],
                    "language": raw["language"],
                    "timing": raw["timing"],
                    "offer": raw.get("offer"),
                    "confidence": raw["confidence"],
                    "reasoning": raw["reasoning"],
                    "execute_at": raw.get("execute_at"),
                }
            )
            decision.action = parsed.action
            decision.channel = parsed.channel
            decision.language = parsed.language
            decision.timing = parsed.timing
            decision.offer = parsed.offer
            decision.confidence = parsed.confidence
            decision.reasoning = parsed.reasoning
            decision.validated = True
            decision.validation_error = None
        except Exception as exc:  # noqa: BLE001
            decision.validated = False
            decision.validation_error = str(exc)
            logger.warning("Zero-cost decision failed validation: %s", exc)

        db.add(decision)
        db.flush()
        return decision


zero_cost_agent = ZeroCostAgent()
