from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    AIDecision,
    Approval,
    ApprovalStatus,
    Guest,
    Message,
    MessageChannel,
    MessageStatus,
    Offer,
    OfferStatus,
    Property,
    Reservation,
    Review,
    ReviewSentiment,
    Task,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {"Welcome", "Upsell", "ReviewRequest", "None"}
ALLOWED_CHANNELS = {"whatsapp", "email", "sms"}

LANGUAGE_GREETINGS = {
    "en": "Hello",
    "de": "Guten Tag",
    "fr": "Bonjour",
    "es": "Hola",
    "it": "Buongiorno",
    "pt": "Olá",
    "nl": "Goedendag",
}

UPSELL_CATALOG = {
    "family": [
        ("Airport Pickup", 45.0, "Door-to-door airport transfer for the family"),
        ("Baby Cot", 15.0, "Complimentary setup of a baby cot in your room"),
        ("Extra Bed", 35.0, "Additional bed for a child or companion"),
        ("Family Dinner", 89.0, "3-course family dinner at our restaurant"),
    ],
    "business": [
        ("Late Checkout", 40.0, "Checkout extended until 4 PM"),
        ("Meeting Room", 120.0, "2-hour private meeting room booking"),
        ("Airport Transfer", 55.0, "Private airport transfer"),
    ],
    "luxury": [
        ("Suite Upgrade", 150.0, "Upgrade to a junior suite with sea view"),
        ("Spa Package", 95.0, "60-minute spa treatment for two"),
        ("Champagne Welcome", 65.0, "Chilled champagne and fruit platter on arrival"),
        ("Private Dining", 180.0, "Private terrace dinner for two"),
    ],
    "default": [
        ("Late Checkout", 35.0, "Relax with a late checkout until 2 PM"),
        ("Breakfast Upgrade", 28.0, "Full buffet breakfast for your stay"),
        ("Airport Transfer", 50.0, "Comfortable private airport transfer"),
    ],
}


class AIDecisionSchema(BaseModel):
    action: Literal["Welcome", "Upsell", "ReviewRequest", "None"]
    channel: Literal["whatsapp", "email", "sms"]
    language: str = Field(min_length=2, max_length=8)
    timing: str
    offer: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    execute_at: Optional[datetime] = None

    @field_validator("language")
    @classmethod
    def normalize_language(cls, v: str) -> str:
        return v.lower()[:8]


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    def decide(
        self,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class HeuristicAIProvider(AIProvider):
    name = "heuristic-v1"

    def decide(
        self,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        travel = (guest.travel_type or guest.purpose or "default").lower()
        if guest.children > 0:
            travel = "family"
        catalog = UPSELL_CATALOG.get(travel, UPSELL_CATALOG["default"])
        offer_name, _, _ = catalog[0]

        days_to_arrival = (reservation.check_in - datetime.utcnow().date()).days
        now = datetime.utcnow()
        if days_to_arrival > 3:
            action = "Upsell"
            delay_days = min(max(days_to_arrival - 2, 1), 7)
            timing = f"{delay_days} days before arrival"
            execute_at = datetime.combine(reservation.check_in, datetime.min.time()) - timedelta(
                days=delay_days
            )
        elif days_to_arrival >= 0:
            action = "Welcome"
            timing = "immediate"
            offer_name = None
            execute_at = now
        else:
            action = "ReviewRequest"
            timing = "8 hours after checkout"
            offer_name = None
            execute_at = now + timedelta(hours=8)

        channel = (guest.communication_preference or "whatsapp").lower()
        if channel not in ALLOWED_CHANNELS:
            channel = "email"
        language = (guest.language or "en").lower()
        confidence = 0.92 if float(guest.ltv_score) > 60 else 0.78

        return {
            "action": action,
            "channel": channel,
            "language": language,
            "timing": timing,
            "offer": offer_name if action == "Upsell" else None,
            "confidence": confidence,
            "reasoning": (
                f"Guest {guest.name} from {guest.country or 'unknown'} "
                f"({travel} traveler, LTV {float(guest.ltv_score):.0f}) at {property_.name}. "
                f"Recommended {action} via {channel}."
            ),
            "execute_at": execute_at.isoformat(),
        }


class OpenAIProvider(AIProvider):
    """Optional live provider. Falls back to heuristic if unavailable."""

    name = "openai-gpt"

    def decide(
        self,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY missing; falling back to heuristic")
            return HeuristicAIProvider().decide(guest, reservation, property_, context)
        # Keep dependency-free: structured fallback until SDK is configured.
        raw = HeuristicAIProvider().decide(guest, reservation, property_, context)
        raw["reasoning"] = f"[openai-mode] {raw['reasoning']}"
        return raw


def get_ai_provider() -> AIProvider:
    if settings.use_mock_ai or not settings.openai_api_key:
        return HeuristicAIProvider()
    return OpenAIProvider()


class AIOrchestrator:
    def __init__(self, provider: AIProvider | None = None) -> None:
        self.provider = provider or get_ai_provider()

    def decide(
        self,
        db: Session,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        context: dict[str, Any] | None = None,
    ) -> AIDecision:
        raw = self.provider.decide(guest, reservation, property_, context)
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
            model_name=self.provider.name,
            validated=False,
            executed=False,
        )

        try:
            parsed = AIDecisionSchema.model_validate(raw)
            # Policy: offer required for Upsell, forbidden otherwise
            if parsed.action == "Upsell" and not parsed.offer:
                raise ValueError("Upsell requires an offer")
            if parsed.action != "Upsell" and parsed.offer:
                parsed.offer = None
            offer_names = {n for items in UPSELL_CATALOG.values() for n, _, _ in items}
            if parsed.offer and parsed.offer not in offer_names:
                raise ValueError(f"Offer not in catalog: {parsed.offer}")

            decision.action = parsed.action
            decision.channel = parsed.channel
            decision.language = parsed.language
            decision.timing = parsed.timing
            decision.offer = parsed.offer
            decision.confidence = parsed.confidence
            decision.reasoning = parsed.reasoning
            decision.validated = True
            decision.validation_error = None
            decision.raw_output = parsed.model_dump_json()
        except (ValidationError, ValueError) as exc:
            decision.validated = False
            decision.validation_error = str(exc)
            logger.warning("AI decision validation failed: %s", exc)

        db.add(decision)
        db.flush()
        return decision

    def generate_message(
        self,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        message_type: str,
        offer_name: str | None = None,
        language: str | None = None,
    ) -> dict[str, str]:
        lang = language or guest.language or "en"
        greeting = LANGUAGE_GREETINGS.get(lang, "Hello")
        first = guest.name.split()[0]
        voice = property_.brand_voice

        templates = {
            "welcome": {
                "en": (
                    f"{greeting} {first},\n\n"
                    f"We're delighted you'll be staying at {property_.name} "
                    f"from {reservation.check_in} to {reservation.check_out}. "
                    f"Your {reservation.room_type} is ready for you.\n\n"
                    f"({voice})\n\n"
                    f"Reply anytime if you need anything before arrival.\n\n"
                    f"— The {property_.name} team"
                ),
                "de": (
                    f"{greeting} {first},\n\n"
                    f"Wir freuen uns auf Ihren Aufenthalt im {property_.name} "
                    f"vom {reservation.check_in} bis {reservation.check_out}. "
                    f"Ihr {reservation.room_type} ist für Sie vorbereitet.\n\n"
                    f"— Das Team von {property_.name}"
                ),
                "fr": (
                    f"{greeting} {first},\n\n"
                    f"Nous sommes ravis de vous accueillir au {property_.name} "
                    f"du {reservation.check_in} au {reservation.check_out}. "
                    f"Votre {reservation.room_type} vous attend.\n\n"
                    f"— L'équipe {property_.name}"
                ),
            },
            "upsell": {
                "en": (
                    f"{greeting} {first},\n\n"
                    f"Looking forward to your stay at {property_.name}! "
                    f"We thought you might enjoy our {offer_name or 'special offer'}—"
                    f"perfect for your trip. Would you like us to add it?\n\n"
                    f"Just reply YES and we'll take care of everything.\n\n"
                    f"— {property_.name}"
                ),
                "de": (
                    f"{greeting} {first},\n\n"
                    f"Wir freuen uns auf Ihren Aufenthalt! "
                    f"Vielleicht interessiert Sie unser Angebot: {offer_name or 'Sonderangebot'}. "
                    f"Sollen wir es für Sie hinzufügen?\n\n"
                    f"Antworten Sie einfach mit JA.\n\n"
                    f"— {property_.name}"
                ),
            },
            "review_request": {
                "en": (
                    f"{greeting} {first},\n\n"
                    f"Thank you for staying at {property_.name}. "
                    f"We hope everything was wonderful. "
                    f"If you have a moment, a short Google review would mean the world to us.\n\n"
                    f"— The {property_.name} team"
                ),
                "de": (
                    f"{greeting} {first},\n\n"
                    f"Vielen Dank für Ihren Aufenthalt im {property_.name}. "
                    f"Eine kurze Google-Bewertung würde uns sehr helfen.\n\n"
                    f"— Das Team von {property_.name}"
                ),
            },
        }
        type_templates = templates.get(message_type, templates["welcome"])
        body = type_templates.get(lang) or type_templates.get("en", "")
        subject_map = {
            "welcome": f"Welcome to {property_.name}",
            "upsell": "A special offer for your stay",
            "review_request": f"How was your stay at {property_.name}?",
        }
        return {
            "subject": subject_map.get(message_type, f"Message from {property_.name}"),
            "body": body,
            "language": lang,
            "brand_voice_applied": voice,
        }

    def draft_review_response(
        self, review: Review, property_: Property, guest: Guest
    ) -> str:
        first = guest.name.split()[0]
        if review.rating <= 2:
            return (
                f"Dear {first},\n\n"
                f"We're truly sorry your experience at {property_.name} didn't meet expectations. "
                f"Your feedback matters deeply to us, and we'd like to make it right. "
                f"Please contact our manager directly so we can address your concerns personally.\n\n"
                f"With sincere apologies,\n{property_.name}"
            )
        if review.rating == 3:
            return (
                f"Dear {first},\n\n"
                f"Thank you for sharing your thoughts. "
                f"We're actively working on the areas you mentioned and hope to welcome you back.\n\n"
                f"— {property_.name}"
            )
        return (
            f"Dear {first},\n\n"
            f"Thank you so much for your wonderful review! "
            f"It means a great deal to our team at {property_.name}. "
            f"We can't wait to welcome you back.\n\n"
            f"Warm regards,\n{property_.name}"
        )

    def analyze_review_themes(self, body: str) -> list[str]:
        themes = []
        keywords = {
            "breakfast": ["breakfast", "frühstück", "petit-déjeuner"],
            "pool": ["pool", "piscine", "schwimmbad"],
            "staff": ["staff", "team", "reception", "friendly", "personal"],
            "location": ["location", "lage", "central", "beach"],
            "noise": ["noise", "noisy", "laut", "bruyant"],
            "wifi": ["wifi", "wi-fi", "internet"],
            "spa": ["spa", "massage", "wellness"],
            "restaurant": ["restaurant", "dinner", "food", "essen"],
            "cleanliness": ["clean", "sauber", "propre", "housekeeping"],
            "parking": ["parking", "parkplatz"],
            "check-in": ["check-in", "checkin", "arrival", "ankunft"],
        }
        lower = body.lower()
        for theme, words in keywords.items():
            if any(w in lower for w in words):
                themes.append(theme)
        return themes or ["general"]


ai_orchestrator = AIOrchestrator()


def _parse_execute_at(raw: str, fallback: datetime) -> datetime:
    try:
        data = json.loads(raw)
        value = data.get("execute_at")
        if not value:
            return fallback
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", ""))
    except Exception:  # noqa: BLE001
        return fallback
    return fallback


def execute_decision(
    db: Session,
    decision: AIDecision,
    guest: Guest,
    reservation: Reservation,
    property_: Property,
) -> dict[str, Any]:
    if not decision.validated:
        return {
            "decision_id": decision.id,
            "actions": [],
            "skipped": True,
            "reason": decision.validation_error or "Decision failed validation",
        }
    if decision.executed:
        return {
            "decision_id": decision.id,
            "actions": [],
            "skipped": True,
            "reason": "Already executed",
        }

    results: dict[str, Any] = {"decision_id": decision.id, "actions": []}
    if decision.action in ("Welcome", "Upsell", "ReviewRequest"):
        msg_type = {
            "Welcome": "welcome",
            "Upsell": "upsell",
            "ReviewRequest": "review_request",
        }[decision.action]
        content = ai_orchestrator.generate_message(
            guest, reservation, property_, msg_type, decision.offer, decision.language
        )
        channel = MessageChannel(decision.channel or "whatsapp")
        needs_approval = decision.confidence < 0.85 or decision.action == "Upsell"
        scheduled = _parse_execute_at(
            decision.raw_output, datetime.utcnow() + timedelta(hours=1)
        )

        message = Message(
            tenant_id=guest.tenant_id,
            guest_id=guest.id,
            reservation_id=reservation.id,
            channel=channel,
            language=content["language"],
            subject=content["subject"],
            body=content["body"],
            status=MessageStatus.pending_approval if needs_approval else MessageStatus.queued,
            message_type=msg_type,
            confidence=decision.confidence,
            scheduled_at=scheduled,
        )
        db.add(message)
        db.flush()
        results["actions"].append({"type": "message", "id": message.id})

        if needs_approval:
            approval = Approval(
                tenant_id=guest.tenant_id,
                approval_type="message",
                title=f"{decision.action}: {guest.name}",
                content=content["body"],
                status=ApprovalStatus.pending,
                related_type="message",
                related_id=message.id,
                confidence=decision.confidence,
            )
            db.add(approval)
            results["actions"].append({"type": "approval", "id": approval.id})

        if decision.action == "Upsell" and decision.offer:
            travel = (guest.travel_type or "default").lower()
            if guest.children > 0:
                travel = "family"
            catalog = UPSELL_CATALOG.get(travel, UPSELL_CATALOG["default"])
            price = next((p for n, p, _ in catalog if n == decision.offer), 50.0)
            desc = next((d for n, _, d in catalog if n == decision.offer), "")
            offer = Offer(
                tenant_id=guest.tenant_id,
                reservation_id=reservation.id,
                name=decision.offer,
                category="upsell",
                description=desc,
                price=price,
                status=OfferStatus.offered,
                confidence=decision.confidence,
            )
            db.add(offer)
            results["actions"].append({"type": "offer", "id": offer.id})

    decision.executed = True
    db.flush()
    return results


def handle_negative_review(
    db: Session, review: Review, guest: Guest, property_: Property
) -> None:
    draft = ai_orchestrator.draft_review_response(review, property_, guest)
    review.ai_draft_response = draft
    review.themes = json.dumps(ai_orchestrator.analyze_review_themes(review.body))
    if review.sentiment != ReviewSentiment.negative and review.rating <= 2:
        review.sentiment = ReviewSentiment.negative

    task = Task(
        tenant_id=review.tenant_id,
        title=f"Negative review ({review.rating}★) — {guest.name}",
        description=f"Platform: {review.platform}\n\n{review.body}\n\nSuggested response:\n{draft}",
        status=TaskStatus.open,
        priority=TaskPriority.critical if review.rating == 1 else TaskPriority.high,
        related_type="review",
        related_id=review.id,
        assignee="Duty Manager",
        due_at=datetime.utcnow() + timedelta(hours=2),
    )
    db.add(task)
    approval = Approval(
        tenant_id=review.tenant_id,
        approval_type="review_response",
        title=f"Respond to {review.rating}★ review from {guest.name}",
        content=draft,
        status=ApprovalStatus.pending,
        related_type="review",
        related_id=review.id,
        confidence=0.88,
    )
    db.add(approval)
    db.flush()
