"""Hotel trial signup — prospective hotels create an account to explore Revisit."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.entities import (
    AIDecision,
    Approval,
    ApprovalStatus,
    CelebrateRewardConfig,
    Connector,
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
    Task,
    TaskPriority,
    TaskStatus,
    Tenant,
    User,
    Workflow,
)
from app.schemas import UserOut
from app.services.currency import convert_from_eur, currency_for_country


class HotelSignupRequest(BaseModel):
    hotel_name: str = Field(min_length=2, max_length=255)
    your_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    city: str = Field(default="Berlin", max_length=128)
    country: str = Field(default="Germany", max_length=128)
    rooms: int = Field(default=48, ge=5, le=2000)
    # Accepted for API compatibility; trials always receive demo data.
    include_sample_data: bool = True


class HotelSignupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    dashboard_path: str = "/"
    message: str
    user: UserOut
    hotel_name: str
    property_name: str
    tenant_id: str
    currency: str = "EUR"


def _tenant_id_from_name(hotel_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", hotel_name.lower()).strip("-")[:40] or "hotel"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def ensure_trial_demo_data(db: Session, tenant_id: str) -> bool:
    """Seed rich demo data for a trial tenant if it has no guests yet.

    Returns True when data was seeded. Safe to call on every trial login.
    """
    guest_count = db.query(Guest).filter(Guest.tenant_id == tenant_id).count()
    if guest_count > 0:
        return False
    prop = db.query(Property).filter(Property.tenant_id == tenant_id).first()
    if not prop:
        return False
    seed_trial_demo_data(db, tenant_id, prop)
    return True


def seed_trial_demo_data(db: Session, tenant_id: str, prop: Property) -> None:
    """Rich sample so Operations, Intelligence, Celebrate, and ROI look alive."""
    today = date.today()
    now = datetime.utcnow()
    currency = (getattr(prop, "currency", None) or currency_for_country(prop.country)).upper()
    prop.currency = currency

    def money(eur: float) -> float:
        return convert_from_eur(eur, currency)

    samples = [
        {
            "name": "Marie Dupont",
            "email": f"marie@{tenant_id}.demo",
            "country": "France",
            "language": "fr",
            "travel_type": "luxury",
            "purpose": "anniversary",
            "room": "Sea View Suite",
            "dietary": "vegetarian",
            "ltv": 91,
            "sat": 95,
            "spend": 4800,
            "stays": 6,
            "pref": "whatsapp",
            "notes": (
                "Remembers: Room 302\n"
                "Remembers: Sparkling water\n"
                "Remembers: No feather pillows\n"
                "Remembers: Late checkout"
            ),
            "birthday": today + timedelta(days=11),
            "reviews": 2,
        },
        {
            "name": "Hans Mueller",
            "email": f"hans@{tenant_id}.demo",
            "country": "Germany",
            "language": "de",
            "travel_type": "business",
            "purpose": "business",
            "room": "Business King",
            "ltv": 82,
            "sat": 88,
            "spend": 2140,
            "stays": 4,
            "pref": "whatsapp",
            "notes": "Remembers: Early breakfast\nRemembers: Desk near window",
            "reviews": 0,
        },
        {
            "name": "The Rossi Family",
            "email": f"rossi@{tenant_id}.demo",
            "country": "Italy",
            "language": "it",
            "travel_type": "family",
            "purpose": "leisure",
            "room": "Family Suite",
            "ltv": 74,
            "sat": 80,
            "spend": 1650,
            "stays": 2,
            "pref": "whatsapp",
            "notes": "Remembers: Baby cot",
            "children": 2,
            "reviews": 1,
        },
        {
            "name": "Emily Chen",
            "email": f"emily@{tenant_id}.demo",
            "country": "USA",
            "language": "en",
            "travel_type": "leisure",
            "purpose": "leisure",
            "room": "Deluxe Double",
            "ltv": 48,
            "sat": 45,
            "spend": 890,
            "stays": 1,
            "pref": "email",
            "complaints": 2,
            "reviews": 0,
        },
        {
            "name": "Ana Silva",
            "email": f"ana@{tenant_id}.demo",
            "country": "Portugal",
            "language": "pt",
            "travel_type": "luxury",
            "purpose": "honeymoon",
            "room": "Honeymoon Suite",
            "ltv": 88,
            "sat": 92,
            "spend": 3100,
            "stays": 2,
            "pref": "whatsapp",
            "notes": "Remembers: Champagne on arrival",
            "reviews": 1,
        },
    ]

    guests: list[Guest] = []
    for g in samples:
        guest = Guest(
            tenant_id=tenant_id,
            property_id=prop.id,
            name=g["name"],
            email=g["email"],
            country=g["country"],
            language=g["language"],
            stay_count=g["stays"],
            lifetime_spend=money(g["spend"]),
            average_booking=money(g["spend"]) / max(g["stays"], 1),
            travel_type=g["travel_type"],
            purpose=g.get("purpose"),
            preferred_room=g.get("room"),
            dietary_preferences=g.get("dietary"),
            birthday=g.get("birthday"),
            notes=g.get("notes"),
            communication_preference=g["pref"],
            ltv_score=g["ltv"],
            satisfaction_score=g["sat"],
            complaint_history=g.get("complaints", 0),
            upsell_acceptance=0.4 if g["travel_type"] == "luxury" else 0.22,
            previous_reviews=g.get("reviews", 0),
            children=g.get("children", 0),
            review_reward_unlocked=g.get("reviews", 0) > 0,
            review_reward_unlocked_at=now - timedelta(days=20) if g.get("reviews", 0) > 0 else None,
        )
        db.add(guest)
        guests.append(guest)
    db.flush()

    # Marie celebrate dates locked for Celebrate demo
    guests[0].birthday_locked = True
    guests[0].celebrate_dates_confirmed_at = now - timedelta(days=18)

    specs = [
        (0, today - timedelta(days=1), today + timedelta(days=2), "checked_in", 890),
        (1, today, today + timedelta(days=3), "confirmed", 420),
        (2, today, today + timedelta(days=4), "confirmed", 780),
        (3, today - timedelta(days=4), today, "checked_out", 310),
        (4, today - timedelta(days=2), today + timedelta(days=1), "checked_in", 1200),
        (0, today - timedelta(days=40), today - timedelta(days=37), "checked_out", 820),
        (0, today + timedelta(days=21), today + timedelta(days=24), "confirmed", 1100),
        (1, today - timedelta(days=55), today - timedelta(days=52), "checked_out", 540),
    ]
    reservations: list[Reservation] = []
    for i, (idx, cin, cout, status, amount) in enumerate(specs):
        res = Reservation(
            tenant_id=tenant_id,
            property_id=prop.id,
            guest_id=guests[idx].id,
            external_id=f"TRIAL-{tenant_id[:8]}-{i}",
            source="direct" if i % 2 == 0 else "Booking.com",
            status=ReservationStatus(status),
            room_type=guests[idx].preferred_room or "Deluxe Double",
            check_in=cin,
            check_out=cout,
            adults=2,
            children=guests[idx].children,
            total_amount=money(amount),
            currency=currency,
            special_requests=(
                "Late checkout, sparkling water, no feather pillows"
                if idx == 0
                else None
            ),
        )
        db.add(res)
        reservations.append(res)
    db.flush()

    # Accepted spa upsell for Marie (past stay)
    past_marie = reservations[5]
    db.add(
        Offer(
            tenant_id=tenant_id,
            reservation_id=past_marie.id,
            name="Spa Package",
            category="upsell",
            description="90-minute couples spa",
            price=money(95.0),
            currency=currency,
            status=OfferStatus.accepted,
            confidence=0.91,
            accepted_at=now - timedelta(days=38),
            created_at=now - timedelta(days=39),
        )
    )
    db.add(
        Offer(
            tenant_id=tenant_id,
            reservation_id=reservations[0].id,
            name="Late Checkout",
            category="upsell",
            description="Checkout at 2 PM",
            price=money(40.0),
            currency=currency,
            status=OfferStatus.offered,
            confidence=0.84,
        )
    )

    db.add(
        Review(
            tenant_id=tenant_id,
            property_id=prop.id,
            guest_id=guests[0].id,
            reservation_id=past_marie.id,
            platform="google",
            rating=5,
            title="Exceptional stay",
            body="Staff remembered every preference. We will return for our anniversary.",
            sentiment=ReviewSentiment.positive,
            responded=True,
            published_response="Thank you — we look forward to welcoming you back.",
            created_at=now - timedelta(days=36),
        )
    )
    db.add(
        Review(
            tenant_id=tenant_id,
            property_id=prop.id,
            guest_id=guests[3].id,
            reservation_id=reservations[3].id,
            platform="google",
            rating=2,
            title="Room was noisy",
            body="AC was loud overnight and check-in took too long.",
            sentiment=ReviewSentiment.negative,
            responded=False,
            ai_draft_response=(
                "We're sorry your stay fell short. Our team will follow up personally "
                "and we'd like to make this right on your next visit."
            ),
            created_at=now - timedelta(days=1),
        )
    )

    welcome = Message(
        tenant_id=tenant_id,
        guest_id=guests[1].id,
        reservation_id=reservations[1].id,
        channel=MessageChannel.whatsapp,
        direction="outbound",
        language="de",
        subject="Welcome",
        body="Hallo Hans — your Business King is ready. Breakfast from 6:30.",
        status=MessageStatus.pending_approval,
        message_type="welcome",
        confidence=0.92,
        created_at=now - timedelta(hours=1),
    )
    db.add(welcome)
    db.flush()

    db.add(
        Approval(
            tenant_id=tenant_id,
            approval_type="message",
            title="Approve WhatsApp welcome — Hans Mueller",
            content=welcome.body,
            status=ApprovalStatus.pending,
            related_type="message",
            related_id=welcome.id,
            confidence=0.92,
        )
    )
    db.add(
        Approval(
            tenant_id=tenant_id,
            approval_type="review_response",
            title="Approve reply — Emily Chen 2★ review",
            content="Draft reply ready for the noisy-room review.",
            status=ApprovalStatus.pending,
            related_type="review",
            related_id=None,
            confidence=0.88,
        )
    )

    db.add(
        Message(
            tenant_id=tenant_id,
            guest_id=guests[0].id,
            reservation_id=reservations[0].id,
            channel=MessageChannel.whatsapp,
            direction="outbound",
            language="fr",
            body="Bonjour Marie — Sea View Suite ready. Sparkling water in room.",
            status=MessageStatus.sent,
            message_type="welcome",
            confidence=0.94,
            sent_at=now - timedelta(hours=6),
            created_at=now - timedelta(hours=7),
        )
    )

    db.add(
        Task(
            tenant_id=tenant_id,
            title="Follow up on Emily Chen negative review",
            description="Call or WhatsApp within 2 hours; offer room change credit.",
            status=TaskStatus.open,
            priority=TaskPriority.high,
            assignee="Front Office",
            due_at=now + timedelta(hours=4),
        )
    )
    db.add(
        Task(
            tenant_id=tenant_id,
            title="Prepare Marie Dupont birthday amenity",
            description="Vegetarian dessert + note; birthday in 11 days.",
            status=TaskStatus.open,
            priority=TaskPriority.medium,
            assignee="F&B",
            due_at=now + timedelta(days=9),
        )
    )

    db.add(
        AIDecision(
            tenant_id=tenant_id,
            reservation_id=reservations[1].id,
            guest_id=guests[1].id,
            action="Welcome",
            channel="whatsapp",
            language="de",
            timing="on confirmation",
            confidence=0.92,
            reasoning="Business guest arriving today — send concise WhatsApp welcome.",
            raw_output="{}",
            model_name="trial-demo",
            validated=True,
            executed=True,
            created_at=now - timedelta(hours=2),
        )
    )
    db.add(
        AIDecision(
            tenant_id=tenant_id,
            reservation_id=reservations[0].id,
            guest_id=guests[0].id,
            action="Upsell",
            channel="whatsapp",
            language="fr",
            offer="Spa Package",
            timing="day of arrival",
            confidence=0.89,
            reasoning="Luxury loyal guest — spa over discount.",
            raw_output="{}",
            model_name="trial-demo",
            validated=True,
            executed=True,
            created_at=now - timedelta(days=1),
        )
    )

    # Celebrate config uses the hotel country currency (not the INR default)
    existing_cfg = (
        db.query(CelebrateRewardConfig)
        .filter(CelebrateRewardConfig.tenant_id == tenant_id)
        .first()
    )
    if not existing_cfg:
        db.add(
            CelebrateRewardConfig(
                tenant_id=tenant_id,
                currency=currency,
                birthday_min_spend=money(80),
                anniversary_min_spend=money(150),
            )
        )
    else:
        existing_cfg.currency = currency
        existing_cfg.birthday_min_spend = money(80)
        existing_cfg.anniversary_min_spend = money(150)


def signup_hotel(db: Session, payload: HotelSignupRequest) -> HotelSignupResponse:
    email = str(payload.email).lower().strip()
    existing = (
        db.query(User)
        .filter(func.lower(User.email) == email)
        .first()
    )
    if existing:
        raise ValueError("An account with this email already exists. Please sign in.")

    tenant_id = _tenant_id_from_name(payload.hotel_name)
    while db.query(Tenant).filter(Tenant.id == tenant_id).first():
        tenant_id = _tenant_id_from_name(payload.hotel_name)

    hotel = payload.hotel_name.strip()
    country = payload.country.strip() or "Germany"
    currency = currency_for_country(country)
    db.add(
        Tenant(
            id=tenant_id,
            name=hotel,
            plan="trial",
            is_active=True,
        )
    )
    db.flush()

    user = User(
        tenant_id=tenant_id,
        email=email,
        name=payload.your_name.strip(),
        role="manager",
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)

    prop = Property(
        tenant_id=tenant_id,
        name=hotel,
        type="hotel",
        city=payload.city.strip() or "Berlin",
        country=country,
        currency=currency,
        timezone="UTC",
        brand_voice="Warm, professional hospitality — personal, never pushy.",
        google_rating=4.6,
        rooms=payload.rooms,
    )
    db.add(prop)
    db.flush()

    for provider in ["Cloudbeds", "WhatsApp", "Resend", "Stripe"]:
        db.add(
            Connector(
                tenant_id=tenant_id,
                provider=provider,
                status="pending",
            )
        )

    for name, trigger in [
        ("Pre-arrival Welcome", "ReservationCreated"),
        ("Checkout Review Request", "GuestCheckedOut"),
    ]:
        db.add(
            Workflow(
                tenant_id=tenant_id,
                name=name,
                trigger_event=trigger,
                status="active",
                definition='{"steps":["ai","send"]}',
                runs=0,
            )
        )

    # Always seed demo data for trials so clients understand the product
    seed_trial_demo_data(db, tenant_id, prop)

    db.commit()
    db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )
    return HotelSignupResponse(
        access_token=token,
        message=(
            f"Welcome to Revisit, {user.name.split()[0]}. "
            f"Your hotel workspace is ready in {currency} with sample guests "
            "so you can explore immediately."
        ),
        user=UserOut.model_validate(user),
        hotel_name=hotel,
        property_name=prop.name,
        tenant_id=tenant_id,
        currency=currency,
        dashboard_path="/",
    )
