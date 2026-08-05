"""Hotel trial signup — prospective hotels create an account to explore Revisit."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.entities import (
    Connector,
    Guest,
    Property,
    Reservation,
    ReservationStatus,
    Review,
    ReviewSentiment,
    Tenant,
    User,
    Workflow,
)
from app.schemas import UserOut


class HotelSignupRequest(BaseModel):
    hotel_name: str = Field(min_length=2, max_length=255)
    your_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    city: str = Field(default="Berlin", max_length=128)
    country: str = Field(default="Germany", max_length=128)
    rooms: int = Field(default=48, ge=5, le=2000)
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


def _tenant_id_from_name(hotel_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", hotel_name.lower()).strip("-")[:40] or "hotel"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def _seed_sample_guests(db: Session, tenant_id: str, prop: Property) -> None:
    """Compact sample so Guest Intelligence / Operations look alive on first login."""
    today = date.today()
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
            "notes": "Remembers: Early breakfast",
        },
        {
            "name": "Emily Chen",
            "email": f"emily@{tenant_id}.demo",
            "country": "USA",
            "language": "en",
            "travel_type": "leisure",
            "purpose": "leisure",
            "room": "Deluxe Double",
            "ltv": 52,
            "sat": 48,
            "spend": 890,
            "stays": 1,
            "pref": "email",
            "complaints": 1,
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
            lifetime_spend=g["spend"],
            average_booking=g["spend"] / max(g["stays"], 1),
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
            upsell_acceptance=0.35 if g["travel_type"] == "luxury" else 0.2,
            previous_reviews=1 if g["stays"] > 1 else 0,
            children=0,
        )
        db.add(guest)
        guests.append(guest)
    db.flush()

    # Mix of live / past / upcoming stays
    specs = [
        (0, today - timedelta(days=1), today + timedelta(days=2), "checked_in", 890),
        (1, today, today + timedelta(days=3), "confirmed", 420),
        (2, today - timedelta(days=5), today - timedelta(days=2), "checked_out", 310),
        (0, today + timedelta(days=21), today + timedelta(days=24), "confirmed", 1100),
    ]
    for idx, cin, cout, status, amount in specs:
        db.add(
            Reservation(
                tenant_id=tenant_id,
                property_id=prop.id,
                guest_id=guests[idx].id,
                external_id=f"TRIAL-{tenant_id[:8]}-{idx}-{cin.isoformat()}",
                source="direct",
                status=ReservationStatus(status),
                room_type=guests[idx].preferred_room or "Deluxe Double",
                check_in=cin,
                check_out=cout,
                adults=2,
                children=0,
                total_amount=amount,
                currency="EUR",
                special_requests="Late checkout" if idx == 0 else None,
            )
        )
    db.flush()

    db.add(
        Review(
            tenant_id=tenant_id,
            property_id=prop.id,
            guest_id=guests[0].id,
            platform="google",
            rating=5,
            title="Wonderful stay",
            body="Staff remembered every preference. We will return.",
            sentiment=ReviewSentiment.positive,
            responded=True,
            published_response="Thank you — we can't wait to welcome you again.",
        )
    )


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
    # Extremely unlikely collision, but be safe
    while db.query(Tenant).filter(Tenant.id == tenant_id).first():
        tenant_id = _tenant_id_from_name(payload.hotel_name)

    hotel = payload.hotel_name.strip()
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
        city=payload.city.strip(),
        country=payload.country.strip(),
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

    if payload.include_sample_data:
        _seed_sample_guests(db, tenant_id, prop)

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
        message=f"Welcome to Revisit, {user.name.split()[0]}. Your hotel workspace is ready.",
        user=UserOut.model_validate(user),
        hotel_name=hotel,
        property_name=prop.name,
        tenant_id=tenant_id,
        dashboard_path="/",
    )
