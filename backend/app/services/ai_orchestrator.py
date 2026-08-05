from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

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


class AIOrchestrator:
    """AI decision engine. Uses heuristics for MVP when no API key is set."""

    def decide(
        self,
        db: Session,
        guest: Guest,
        reservation: Reservation,
        property_: Property,
        context: dict[str, Any] | None = None,
    ) -> AIDecision:
        context = context or {}
        travel = (guest.travel_type or guest.purpose or "default").lower()
        if guest.children > 0:
            travel = "family"
        catalog = UPSELL_CATALOG.get(travel, UPSELL_CATALOG["default"])
        offer_name, _, _ = catalog[0]

        days_to_arrival = (reservation.check_in - datetime.utcnow().date()).days
        if days_to_arrival > 3:
            action = "Upsell"
            timing = f"{min(days_to_arrival - 2, 7)} days before arrival"
        elif days_to_arrival >= 0:
            action = "Welcome"
            timing = "immediate"
            offer_name = None
        else:
            action = "ReviewRequest"
            timing = "8 hours after checkout"
            offer_name = None

        channel = guest.communication_preference or "whatsapp"
        language = guest.language or "en"
        confidence = 0.92 if guest.ltv_score > 60 else 0.78

        raw = {
            "action": action,
            "channel": channel.capitalize() if channel != "whatsapp" else "WhatsApp",
            "language": language,
            "timing": timing,
            "offer": offer_name,
            "confidence": confidence,
            "reasoning": (
                f"Guest {guest.name} from {guest.country or 'unknown'} "
                f"({travel} traveler, LTV {guest.ltv_score:.0f}). "
                f"Recommended {action} via {channel}."
            ),
        }

        decision = AIDecision(
            tenant_id=guest.tenant_id,
            reservation_id=reservation.id,
            guest_id=guest.id,
            action=action,
            channel=channel,
            language=language,
            timing=timing,
            offer=offer_name,
            confidence=confidence,
            reasoning=raw["reasoning"],
            raw_output=json.dumps(raw),
            validated=True,
            executed=False,
        )
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
        brand = property_.brand_voice

        templates = {
            "welcome": {
                "en": (
                    f"{greeting} {guest.name.split()[0]},\n\n"
                    f"We're delighted you'll be staying at {property_.name} "
                    f"from {reservation.check_in} to {reservation.check_out}. "
                    f"Your {reservation.room_type} is ready for you.\n\n"
                    f"Reply anytime if you need anything before arrival.\n\n"
                    f"— The {property_.name} team"
                ),
                "de": (
                    f"{greeting} {guest.name.split()[0]},\n\n"
                    f"Wir freuen uns auf Ihren Aufenthalt im {property_.name} "
                    f"vom {reservation.check_in} bis {reservation.check_out}. "
                    f"Ihr {reservation.room_type} ist für Sie vorbereitet.\n\n"
                    f"Melden Sie sich gerne, wenn Sie vor der Anreise etwas brauchen.\n\n"
                    f"— Das Team von {property_.name}"
                ),
                "fr": (
                    f"{greeting} {guest.name.split()[0]},\n\n"
                    f"Nous sommes ravis de vous accueillir au {property_.name} "
                    f"du {reservation.check_in} au {reservation.check_out}. "
                    f"Votre {reservation.room_type} vous attend.\n\n"
                    f"N'hésitez pas à nous écrire avant votre arrivée.\n\n"
                    f"— L'équipe {property_.name}"
                ),
            },
            "upsell": {
                "en": (
                    f"{greeting} {guest.name.split()[0]},\n\n"
                    f"Looking forward to your stay at {property_.name}! "
                    f"We thought you might enjoy our {offer_name or 'special offer'}—"
                    f"perfect for your trip. Would you like us to add it?\n\n"
                    f"Just reply YES and we'll take care of everything.\n\n"
                    f"— {property_.name}"
                ),
                "de": (
                    f"{greeting} {guest.name.split()[0]},\n\n"
                    f"Wir freuen uns auf Ihren Aufenthalt! "
                    f"Vielleicht interessiert Sie unser Angebot: {offer_name or 'Sonderangebot'}. "
                    f"Sollen wir es für Sie hinzufügen?\n\n"
                    f"Antworten Sie einfach mit JA.\n\n"
                    f"— {property_.name}"
                ),
            },
            "review_request": {
                "en": (
                    f"{greeting} {guest.name.split()[0]},\n\n"
                    f"Thank you for staying at {property_.name}. "
                    f"We hope everything was wonderful. "
                    f"If you have a moment, a short Google review would mean the world to us.\n\n"
                    f"We're always here if you need anything for a future visit.\n\n"
                    f"— The {property_.name} team"
                ),
                "de": (
                    f"{greeting} {guest.name.split()[0]},\n\n"
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
            "upsell": f"A special offer for your stay",
            "review_request": f"How was your stay at {property_.name}?",
        }
        return {
            "subject": subject_map.get(message_type, f"Message from {property_.name}"),
            "body": body,
            "language": lang,
            "brand_voice_applied": brand,
        }

    def draft_review_response(
        self, review: Review, property_: Property, guest: Guest
    ) -> str:
        if review.rating <= 2:
            return (
                f"Dear {guest.name.split()[0]},\n\n"
                f"We're truly sorry your experience at {property_.name} didn't meet expectations. "
                f"Your feedback about this stay matters deeply to us, and we'd like to make it right. "
                f"Please contact our manager directly so we can address your concerns personally.\n\n"
                f"With sincere apologies,\n{property_.name}"
            )
        if review.rating == 3:
            return (
                f"Dear {guest.name.split()[0]},\n\n"
                f"Thank you for taking the time to share your thoughts. "
                f"We're glad you stayed with us and are actively working on the areas you mentioned. "
                f"We hope to welcome you back for an even better experience.\n\n"
                f"— {property_.name}"
            )
        return (
            f"Dear {guest.name.split()[0]},\n\n"
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


def execute_decision(
    db: Session,
    decision: AIDecision,
    guest: Guest,
    reservation: Reservation,
    property_: Property,
) -> dict[str, Any]:
    """Validate then act — AI never executes directly without this gate."""
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
            scheduled_at=datetime.utcnow() + timedelta(hours=1),
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
