"""Demo guest onboarding — create a rich Living Guest Intelligence profile."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.db.seed import DEMO_TENANT
from app.models.entities import (
    Guest,
    Message,
    MessageChannel,
    MessageStatus,
    Offer,
    OfferStatus,
    Property,
    Reservation,
    ReservationStatus,
    Review,
    ReviewSentiment,
)
from app.services.guest_intelligence import GuestIntelligence, build_intelligence


class DemoOnboardRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=64)
    country: Optional[str] = Field(default="Germany", max_length=128)
    language: str = Field(default="en", min_length=2, max_length=8)
    travel_type: Literal["leisure", "business", "family", "luxury"] = "luxury"
    purpose: Optional[str] = Field(default="leisure", max_length=64)
    preferred_room: Optional[str] = Field(default="Sea View Suite", max_length=128)
    dietary_preferences: Optional[str] = Field(default=None, max_length=255)
    birthday: Optional[date] = None
    anniversary: Optional[date] = None
    children: int = Field(default=0, ge=0, le=10)
    pets: bool = False
    communication_preference: Literal["whatsapp", "email", "sms"] = "whatsapp"
    favorite_wine: Optional[str] = Field(default=None, max_length=64)
    remembers: list[str] = Field(default_factory=list, max_length=12)
    company_or_hotel: Optional[str] = Field(default=None, max_length=128)
    open_dashboard: bool = True


class DemoOnboardResponse(BaseModel):
    guest: GuestIntelligence
    dashboard_path: str
    message: str
    access_token: Optional[str] = None
    token_type: str = "bearer"
    property_name: str = "Azure Coast Resort"


def _default_remembers(payload: DemoOnboardRequest) -> list[str]:
    items = [r.strip() for r in payload.remembers if r and r.strip()]
    if payload.preferred_room:
        items.insert(0, payload.preferred_room)
    if payload.dietary_preferences:
        items.append(payload.dietary_preferences.title())
    if payload.pets:
        items.append("Travels with pets")
    # Demo defaults that make Remembers feel alive
    defaults = ["Late checkout", "Sparkling water", "No feather pillows"]
    for d in defaults:
        if d.lower() not in " ".join(items).lower():
            items.append(d)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        key = i.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(i)
    return out[:8]


def _scores_for_travel(travel: str) -> tuple[float, float, float, int, float]:
    """ltv, sat, upsell_acceptance, stay_count, avg_spend."""
    if travel == "luxury":
        return 91.0, 94.0, 0.45, 4, 820.0
    if travel == "business":
        return 78.0, 86.0, 0.28, 3, 540.0
    if travel == "family":
        return 74.0, 82.0, 0.22, 2, 680.0
    return 68.0, 78.0, 0.2, 2, 420.0


def onboard_demo_guest(db: Session, payload: DemoOnboardRequest) -> Guest:
    prop = (
        db.query(Property)
        .filter(Property.tenant_id == DEMO_TENANT)
        .order_by(Property.created_at.asc())
        .first()
    )
    if not prop:
        raise RuntimeError("Demo property not seeded. Restart API with seed_on_startup.")

    today = date.today()
    ltv, sat, upsell, stays, avg = _scores_for_travel(payload.travel_type)
    remembers = _default_remembers(payload)
    notes_lines = [f"Remembers: {r}" for r in remembers]
    if payload.favorite_wine:
        notes_lines.append(f"Favorite wine: {payload.favorite_wine}")
    if payload.company_or_hotel:
        notes_lines.append(f"Demo visitor from: {payload.company_or_hotel}")

    birthday = payload.birthday
    if birthday is None:
        # Birthday in ~12 days → Next Best Action pops
        birthday = today + timedelta(days=12)

    guest: Guest | None = None
    if payload.email:
        guest = (
            db.query(Guest)
            .filter(
                Guest.tenant_id == DEMO_TENANT,
                Guest.email == str(payload.email).lower(),
            )
            .first()
        )

    room = payload.preferred_room or "Sea View Suite"
    lifetime = round(avg * stays, 2)
    special = ", ".join(remembers[:4])

    if guest:
        guest.name = payload.name.strip()
        guest.phone = payload.phone or guest.phone
        guest.country = payload.country or guest.country
        guest.language = payload.language
        guest.travel_type = payload.travel_type
        guest.purpose = payload.purpose
        guest.preferred_room = room
        guest.dietary_preferences = payload.dietary_preferences
        guest.birthday = birthday
        guest.anniversary = payload.anniversary or guest.anniversary
        guest.children = payload.children
        guest.pets = payload.pets
        guest.communication_preference = payload.communication_preference
        guest.notes = "\n".join(notes_lines)
        guest.ltv_score = max(float(guest.ltv_score or 0), ltv)
        guest.satisfaction_score = max(float(guest.satisfaction_score or 0), sat)
        guest.upsell_acceptance = max(float(guest.upsell_acceptance or 0), upsell)
        guest.stay_count = max(guest.stay_count or 0, stays)
        guest.lifetime_spend = max(float(guest.lifetime_spend or 0), lifetime)
        guest.average_booking = avg
        guest.previous_reviews = max(guest.previous_reviews or 0, 1)
        guest.review_reward_unlocked = True
        if not guest.review_reward_unlocked_at:
            guest.review_reward_unlocked_at = datetime.utcnow()
    else:
        guest = Guest(
            tenant_id=DEMO_TENANT,
            property_id=prop.id,
            name=payload.name.strip(),
            email=str(payload.email).lower() if payload.email else None,
            phone=payload.phone,
            country=payload.country,
            language=payload.language,
            stay_count=stays,
            lifetime_spend=lifetime,
            average_booking=avg,
            travel_type=payload.travel_type,
            purpose=payload.purpose,
            preferred_room=room,
            children=payload.children,
            pets=payload.pets,
            dietary_preferences=payload.dietary_preferences,
            birthday=birthday,
            anniversary=payload.anniversary,
            communication_preference=payload.communication_preference,
            previous_reviews=1,
            complaint_history=0,
            upsell_acceptance=upsell,
            ltv_score=ltv,
            satisfaction_score=sat,
            notes="\n".join(notes_lines),
            review_reward_unlocked=True,
            review_reward_unlocked_at=datetime.utcnow(),
        )
        db.add(guest)
        db.flush()

        # Past stay
        past = Reservation(
            tenant_id=DEMO_TENANT,
            property_id=prop.id,
            guest_id=guest.id,
            external_id=f"DEMO-{guest.id[:8]}-PAST",
            source="direct",
            status=ReservationStatus.checked_out,
            room_type=room,
            check_in=today - timedelta(days=48),
            check_out=today - timedelta(days=45),
            adults=2,
            children=payload.children,
            total_amount=avg,
            currency="EUR",
            special_requests=special,
        )
        db.add(past)
        db.flush()

        # Upcoming / current stay
        upcoming = Reservation(
            tenant_id=DEMO_TENANT,
            property_id=prop.id,
            guest_id=guest.id,
            external_id=f"DEMO-{guest.id[:8]}-NEXT",
            source="Website",
            status=ReservationStatus.confirmed,
            room_type=room,
            check_in=today + timedelta(days=14),
            check_out=today + timedelta(days=17),
            adults=2,
            children=payload.children,
            total_amount=round(avg * 1.15, 2),
            currency="EUR",
            special_requests=special,
        )
        db.add(upcoming)
        db.flush()

        # Accepted spa offer on past stay
        db.add(
            Offer(
                tenant_id=DEMO_TENANT,
                reservation_id=past.id,
                name="Spa Package",
                category="upsell",
                description="90-minute couples spa with welcome wine",
                price=95.0,
                currency="EUR",
                status=OfferStatus.accepted,
                confidence=0.91,
                accepted_at=datetime.utcnow() - timedelta(days=46),
            )
        )

        # 5★ review
        db.add(
            Review(
                tenant_id=DEMO_TENANT,
                property_id=prop.id,
                guest_id=guest.id,
                reservation_id=past.id,
                platform="google",
                rating=5,
                title="Exceptional stay",
                body=(
                    f"{guest.name.split()[0]} loved the {room}. "
                    "Staff remembered every preference — that is Revisit."
                ),
                sentiment=ReviewSentiment.positive,
                themes="service,room,spa",
                responded=True,
                published_response="Thank you — we look forward to welcoming you back.",
                created_at=datetime.utcnow() - timedelta(days=44),
            )
        )

        channel = {
            "whatsapp": MessageChannel.whatsapp,
            "email": MessageChannel.email,
            "sms": MessageChannel.sms,
        }.get(payload.communication_preference, MessageChannel.whatsapp)

        db.add(
            Message(
                tenant_id=DEMO_TENANT,
                guest_id=guest.id,
                reservation_id=upcoming.id,
                channel=channel,
                direction="outbound",
                language=payload.language,
                subject="Welcome back",
                body=(
                    f"Hi {guest.name.split()[0]}, your {room} is ready. "
                    "We've noted your preferences for this stay."
                ),
                status=MessageStatus.sent,
                message_type="welcome",
                confidence=0.94,
                sent_at=datetime.utcnow() - timedelta(hours=2),
            )
        )

    db.commit()
    db.refresh(guest)
    return guest


def build_onboard_response(
    db: Session, guest: Guest, access_token: str | None = None
) -> DemoOnboardResponse:
    prop = db.query(Property).filter(Property.id == guest.property_id).first()
    intel = build_intelligence(db, guest)
    return DemoOnboardResponse(
        guest=intel,
        dashboard_path=f"/guests?guest={guest.id}",
        message=(
            f"{guest.name.split()[0]}, you're in Guest Intelligence. "
            "Open the hotel view to see what AI knows about you."
        ),
        access_token=access_token,
        property_name=prop.name if prop else "Azure Coast Resort",
    )
