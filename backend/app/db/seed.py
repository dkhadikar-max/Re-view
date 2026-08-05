from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.entities import (
    Approval,
    ApprovalStatus,
    Campaign,
    CelebrateDateAudit,
    CelebrateRewardConfig,
    Connector,
    Guest,
    Message,
    MessageChannel,
    MessageStatus,
    Notification,
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
from app.services.ai_orchestrator import (
    ai_orchestrator,
    execute_decision,
    handle_negative_review,
)
from app.services.celebrate_rewards import (
    CelebrateDatesIn,
    confirm_and_lock_dates,
    get_or_create_config,
    unlock_after_review,
)
from app.services.connectors import store_connector_secret
from app.services.event_bus import event_bus
from app.services.workflow_engine import register_workflow_handlers

DEMO_TENANT = "demo-hotel"
LEGACY_DEMO_EMAILS = (
    "manager@azurecoast.demo",
    "staff@azurecoast.demo",
    "admin@azurecoast.demo",
)
TEST_MANAGER_EMAIL = "manager@revisit.example"


def _owner_email() -> str:
    return (settings.owner_email or "dkhadikar@gmail.com").strip().lower()


def _owner_name() -> str:
    return (settings.owner_name or "Deepanshu").strip() or "Owner"


def _owner_password() -> str:
    if settings.owner_password:
        return settings.owner_password
    if settings.environment == "test":
        return "test-owner-password"
    if settings.environment == "development":
        return "LocalDevOwnerPass1!"
    return "ChangeMe-Set-OWNER_PASSWORD"


# Resolved at import for tests; ensure_owner_account always uses live settings.
DEMO_EMAIL = _owner_email()
DEMO_PASSWORD = _owner_password()


def ensure_owner_account(db: Session) -> None:
    """Upsert platform owner as admin; disable legacy azurecoast demo logins."""
    if not db.query(Tenant).filter(Tenant.id == DEMO_TENANT).first():
        return

    email = _owner_email()
    password = _owner_password()
    name = _owner_name()

    legacy = (
        db.query(User)
        .filter(
            User.tenant_id == DEMO_TENANT,
            func.lower(User.email).in_([e.lower() for e in LEGACY_DEMO_EMAILS]),
        )
        .all()
    )
    for user in legacy:
        # Rename manager → owner when owner row does not exist yet
        if user.email.lower() == "manager@azurecoast.demo":
            existing_owner = (
                db.query(User)
                .filter(User.tenant_id == DEMO_TENANT, func.lower(User.email) == email)
                .first()
            )
            if not existing_owner:
                user.email = email
                user.name = name
                user.role = "admin"
                user.is_active = True
                user.password_hash = hash_password(password)
                continue
        user.is_active = False

    owner = (
        db.query(User)
        .filter(User.tenant_id == DEMO_TENANT, func.lower(User.email) == email)
        .first()
    )
    if owner:
        owner.name = name
        owner.role = "admin"
        owner.is_active = True
        owner.password_hash = hash_password(password)
    else:
        db.add(
            User(
                tenant_id=DEMO_TENANT,
                email=email,
                name=name,
                role="admin",
                password_hash=hash_password(password),
                is_active=True,
            )
        )

    if settings.environment == "test":
        mgr = (
            db.query(User)
            .filter(
                User.tenant_id == DEMO_TENANT,
                func.lower(User.email) == TEST_MANAGER_EMAIL.lower(),
            )
            .first()
        )
        if not mgr:
            db.add(
                User(
                    tenant_id=DEMO_TENANT,
                    email=TEST_MANAGER_EMAIL,
                    name="Test Manager",
                    role="manager",
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )

    db.commit()


def _on_reservation_created(db: Session, event, payload: dict) -> None:
    reservation = (
        db.query(Reservation)
        .filter(
            Reservation.id == payload["reservation_id"],
            Reservation.tenant_id == event.tenant_id,
        )
        .first()
    )
    guest = (
        db.query(Guest)
        .filter(Guest.id == payload["guest_id"], Guest.tenant_id == event.tenant_id)
        .first()
    )
    property_ = (
        db.query(Property)
        .filter(Property.id == payload["property_id"], Property.tenant_id == event.tenant_id)
        .first()
    )
    if not (reservation and guest and property_):
        return
    decision = ai_orchestrator.decide(db, guest, reservation, property_)
    execute_decision(db, decision, guest, reservation, property_)


def _on_guest_checked_out(db: Session, event, payload: dict) -> None:
    reservation = (
        db.query(Reservation)
        .filter(
            Reservation.id == payload["reservation_id"],
            Reservation.tenant_id == event.tenant_id,
        )
        .first()
    )
    guest = (
        db.query(Guest)
        .filter(Guest.id == payload["guest_id"], Guest.tenant_id == event.tenant_id)
        .first()
    )
    if not reservation or not guest:
        return
    property_ = (
        db.query(Property)
        .filter(Property.id == reservation.property_id, Property.tenant_id == event.tenant_id)
        .first()
    )
    if not property_:
        return
    decision = ai_orchestrator.decide(
        db, guest, reservation, property_, context={"force_action": "ReviewRequest"}
    )
    # Force review request path via validated decision override only if needed
    if decision.validated and decision.action != "ReviewRequest":
        # Create an explicit review-request decision
        from app.models.entities import AIDecision

        forced = AIDecision(
            tenant_id=event.tenant_id,
            reservation_id=reservation.id,
            guest_id=guest.id,
            action="ReviewRequest",
            channel=guest.communication_preference
            if guest.communication_preference in {"whatsapp", "email", "sms"}
            else "email",
            language=guest.language or "en",
            timing="8 hours after checkout",
            confidence=0.94,
            reasoning="Checkout event triggered review request workflow.",
            raw_output=json.dumps(
                {
                    "action": "ReviewRequest",
                    "channel": guest.communication_preference
                    if guest.communication_preference in {"whatsapp", "email", "sms"}
                    else "email",
                    "language": guest.language or "en",
                    "timing": "8 hours after checkout",
                    "offer": None,
                    "confidence": 0.94,
                    "reasoning": "Checkout event triggered review request workflow.",
                    "execute_at": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
                }
            ),
            model_name="workflow-v1",
            validated=True,
        )
        db.add(forced)
        db.flush()
        execute_decision(db, forced, guest, reservation, property_)
    else:
        execute_decision(db, decision, guest, reservation, property_)


def _on_negative_review(db: Session, event, payload: dict) -> None:
    review = (
        db.query(Review)
        .filter(Review.id == payload["review_id"], Review.tenant_id == event.tenant_id)
        .first()
    )
    if not review or review.ai_draft_response:
        return
    guest = (
        db.query(Guest)
        .filter(Guest.id == review.guest_id, Guest.tenant_id == event.tenant_id)
        .first()
    )
    property_ = (
        db.query(Property)
        .filter(Property.id == review.property_id, Property.tenant_id == event.tenant_id)
        .first()
    )
    if guest and property_:
        handle_negative_review(db, review, guest, property_)


def register_handlers() -> None:
    event_bus.reset()
    event_bus.subscribe("ReservationCreated", _on_reservation_created)
    event_bus.subscribe("GuestCheckedOut", _on_guest_checked_out)
    event_bus.subscribe("NegativeReviewReceived", _on_negative_review)
    register_workflow_handlers()


def seed_database(db: Session) -> None:
    if db.query(Tenant).filter(Tenant.id == DEMO_TENANT).first():
        ensure_owner_account(db)
        return

    today = date.today()
    db.add(Tenant(id=DEMO_TENANT, name="Azure Coast Hospitality", plan="growth"))
    db.flush()

    db.add(
        User(
            tenant_id=DEMO_TENANT,
            email=_owner_email(),
            name=_owner_name(),
            role="admin",
            password_hash=hash_password(_owner_password()),
            is_active=True,
        )
    )
    if settings.environment == "test":
        db.add(
            User(
                tenant_id=DEMO_TENANT,
                email=TEST_MANAGER_EMAIL,
                name="Test Manager",
                role="manager",
                password_hash=hash_password(_owner_password()),
                is_active=True,
            )
        )

    prop = Property(
        tenant_id=DEMO_TENANT,
        name="Azure Coast Resort",
        type="resort",
        city="Nice",
        country="France",
        timezone="Europe/Paris",
        brand_voice="Warm Mediterranean hospitality — elegant, personal, never pushy.",
        google_rating=4.7,
        rooms=68,
    )
    db.add(prop)
    db.flush()

    for provider in ["Cloudbeds", "Google Sheets", "WhatsApp", "Resend", "Stripe"]:
        db.add(
            Connector(
                tenant_id=DEMO_TENANT,
                provider=provider,
                status="connected" if provider != "Stripe" else "pending",
                config_encrypted=store_connector_secret(f"{provider}-demo-token"),
                last_sync_at=datetime.utcnow() - timedelta(hours=2)
                if provider == "Cloudbeds"
                else None,
                sync_cursor="0" if provider == "Cloudbeds" else None,
            )
        )

    for name, trigger, steps in [
        ("Pre-arrival Welcome", "ReservationCreated", ["wait", "ai", "send", "complete"]),
        ("Checkout Review Request", "GuestCheckedOut", ["wait", "ai", "send", "complete"]),
        ("Negative Review Escalation", "NegativeReviewReceived", ["notify", "ai", "complete"]),
        ("Cross-sell Reminder", "GuestCheckedOut", ["wait", "notify", "complete"]),
    ]:
        db.add(
            Workflow(
                tenant_id=DEMO_TENANT,
                name=name,
                trigger_event=trigger,
                status="active",
                definition=json.dumps({"trigger": trigger, "steps": steps}),
                runs=0,
            )
        )

    db.add(
        Campaign(
            tenant_id=DEMO_TENANT,
            name="45-Day Return Offer",
            type="cross_sell",
            status="active",
            description="Personalized rebooking offer 45 days after checkout",
            conversions=8,
            revenue=3240.0,
        )
    )

    guests_data = [
        {
            "name": "Hans Mueller",
            "email": "hans.mueller@email.de",
            "phone": "+49 170 1112233",
            "country": "Germany",
            "language": "de",
            "travel_type": "business",
            "purpose": "business",
            "children": 0,
            "ltv": 82,
            "sat": 88,
            "spend": 2140,
            "stays": 4,
            "pref": "whatsapp",
            "room": "Business King",
            "reviews": 0,
            "notes": "Remembers: Early breakfast\nRemembers: Desk near window",
        },
        {
            "name": "Marie Dupont",
            "email": "marie.dupont@email.fr",
            "phone": "+33 6 12 34 56 78",
            "country": "France",
            "language": "fr",
            "travel_type": "luxury",
            "purpose": "anniversary",
            "children": 0,
            "ltv": 91,
            "sat": 95,
            "spend": 4800,
            "stays": 6,
            "pref": "whatsapp",
            "dietary": "vegetarian",
            "room": "Sea View Suite",
            "birthday": today + timedelta(days=11),
            "anniversary": date(today.year, 6, 5),
            "reviews": 2,
            "notes": (
                "Remembers: Room 302\n"
                "Remembers: Sparkling water\n"
                "Remembers: No feather pillows\n"
                "Remembers: Late checkout\n"
                "Remembers: Anniversary package"
            ),
        },
        {
            "name": "The Rossi Family",
            "email": "rossi.family@email.it",
            "phone": "+39 333 9876543",
            "country": "Italy",
            "language": "it",
            "travel_type": "family",
            "purpose": "leisure",
            "children": 2,
            "ltv": 74,
            "sat": 80,
            "spend": 1650,
            "stays": 2,
            "pref": "whatsapp",
            "room": "Family Suite",
            "notes": "Remembers: Baby cot\nRemembers: Connecting rooms",
        },
        {
            "name": "Emily Chen",
            "email": "emily.chen@email.com",
            "phone": "+1 415 555 0199",
            "country": "USA",
            "language": "en",
            "travel_type": "leisure",
            "purpose": "leisure",
            "children": 0,
            "ltv": 48,
            "sat": 45,
            "spend": 890,
            "stays": 1,
            "pref": "email",
            "complaints": 2,
            "room": "Standard Twin",
            "reviews": 0,
        },
        {
            "name": "Lars Johansson",
            "email": "lars.j@email.se",
            "phone": "+46 70 123 4567",
            "country": "Sweden",
            "language": "en",
            "travel_type": "business",
            "purpose": "business",
            "children": 0,
            "ltv": 68,
            "sat": 75,
            "spend": 1320,
            "stays": 3,
            "pref": "whatsapp",
            "room": "Business King",
            "birthday": today + timedelta(days=40),
        },
        {
            "name": "Ana Silva",
            "email": "ana.silva@email.pt",
            "phone": "+351 912 345 678",
            "country": "Portugal",
            "language": "pt",
            "travel_type": "luxury",
            "purpose": "honeymoon",
            "children": 0,
            "ltv": 88,
            "sat": 92,
            "spend": 3100,
            "stays": 2,
            "pref": "whatsapp",
            "room": "Honeymoon Suite",
            "anniversary": date(today.year, 9, 12),
            "notes": "Remembers: Champagne on arrival\nRemembers: Rose petals",
        },
    ]

    guests: list[Guest] = []
    for g in guests_data:
        guest = Guest(
            tenant_id=DEMO_TENANT,
            property_id=prop.id,
            name=g["name"],
            email=g["email"],
            phone=g["phone"],
            country=g["country"],
            language=g["language"],
            stay_count=g["stays"],
            lifetime_spend=g["spend"],
            average_booking=g["spend"] / max(g["stays"], 1),
            travel_type=g["travel_type"],
            purpose=g.get("purpose"),
            preferred_room=g.get("room"),
            children=g["children"],
            dietary_preferences=g.get("dietary"),
            birthday=g.get("birthday"),
            anniversary=g.get("anniversary"),
            notes=g.get("notes"),
            communication_preference=g["pref"],
            ltv_score=g["ltv"],
            satisfaction_score=g["sat"],
            complaint_history=g.get("complaints", 0),
            upsell_acceptance=0.35 if g["travel_type"] == "luxury" else 0.2,
            previous_reviews=g.get("reviews", 1 if g["stays"] > 1 else 0),
        )
        db.add(guest)
        guests.append(guest)
    db.flush()

    reservations_spec = [
        (0, today, today + timedelta(days=3), "confirmed", "Deluxe Double", "Booking.com", 420, "BC-1001"),
        (1, today - timedelta(days=1), today + timedelta(days=2), "checked_in", "Junior Suite", "direct", 890, "DR-1002"),
        (2, today, today + timedelta(days=5), "confirmed", "Family Suite", "Airbnb", 780, "AB-1003"),
        (3, today - timedelta(days=4), today, "checked_out", "Standard Twin", "Expedia", 310, "EX-1004"),
        (4, today + timedelta(days=2), today + timedelta(days=5), "confirmed", "Business King", "direct", 540, "DR-1005"),
        (5, today - timedelta(days=2), today + timedelta(days=1), "checked_in", "Honeymoon Suite", "Website", 1200, "WB-1006"),
        (0, today - timedelta(days=40), today - timedelta(days=37), "checked_out", "Deluxe Double", "Booking.com", 380, "BC-1007"),
        (1, today + timedelta(days=14), today + timedelta(days=18), "confirmed", "Junior Suite", "direct", 1100, "DR-1008"),
    ]

    reservations: list[Reservation] = []
    for idx, cin, cout, status, room, source, amount, external in reservations_spec:
        res = Reservation(
            tenant_id=DEMO_TENANT,
            property_id=prop.id,
            guest_id=guests[idx].id,
            external_id=external,
            source=source,
            status=ReservationStatus(status),
            room_type=room,
            check_in=cin,
            check_out=cout,
            adults=2,
            children=guests[idx].children,
            total_amount=amount,
            currency="EUR",
            special_requests=(
                "Late checkout, sparkling water, no feather pillows"
                if idx == 1
                else ("Quiet room preferred" if idx == 0 else None)
            ),
        )
        db.add(res)
        reservations.append(res)
    db.flush()

    msg_specs = [
        (0, 0, "welcome", "de", MessageStatus.sent, "whatsapp"),
        (0, 0, "upsell", "de", MessageStatus.pending_approval, "whatsapp"),
        (1, 1, "welcome", "fr", MessageStatus.sent, "email"),
        (2, 2, "welcome", "en", MessageStatus.queued, "whatsapp"),
        (3, 3, "review_request", "en", MessageStatus.sent, "email"),
        (5, 5, "upsell", "en", MessageStatus.pending_approval, "whatsapp"),
    ]
    for g_idx, r_idx, mtype, lang, status, channel in msg_specs:
        content = ai_orchestrator.generate_message(
            guests[g_idx],
            reservations[r_idx],
            prop,
            mtype,
            "Airport Transfer" if mtype == "upsell" else None,
            lang,
        )
        db.add(
            Message(
                tenant_id=DEMO_TENANT,
                guest_id=guests[g_idx].id,
                reservation_id=reservations[r_idx].id,
                channel=MessageChannel(channel),
                language=lang,
                subject=content["subject"],
                body=content["body"],
                status=status,
                message_type=mtype,
                confidence=0.93,
                sent_at=datetime.utcnow() - timedelta(hours=6)
                if status == MessageStatus.sent
                else None,
                scheduled_at=datetime.utcnow() + timedelta(hours=2)
                if status == MessageStatus.queued
                else None,
            )
        )

    for r_idx, name, price, st in [
        (0, "Airport Transfer", 55.0, OfferStatus.offered),
        (1, "Spa Package", 95.0, OfferStatus.accepted),
        (2, "Baby Cot", 15.0, OfferStatus.offered),
        (5, "Champagne Welcome", 65.0, OfferStatus.offered),
        (1, "Late Checkout", 40.0, OfferStatus.accepted),
    ]:
        db.add(
            Offer(
                tenant_id=DEMO_TENANT,
                reservation_id=reservations[r_idx].id,
                name=name,
                category="upsell",
                description=f"{name} for your stay",
                price=price,
                status=st,
                confidence=0.9,
                accepted_at=datetime.utcnow() - timedelta(hours=12)
                if st == OfferStatus.accepted
                else None,
            )
        )

    reviews_data = [
        (3, 3, 2, "Noisy room near the elevator",
         "The location was great but our room was very noisy at night and the WiFi kept dropping. Staff were polite though.",
         ReviewSentiment.negative),
        (0, 6, 5, "Perfect business stay",
         "Excellent breakfast, fast check-in, and a quiet room. Will definitely return for my next trip to Nice.",
         ReviewSentiment.positive),
        (1, None, 5, "Anniversary magic",
         "The spa and restaurant were outstanding. Clean rooms, beautiful pool, and the staff made our anniversary unforgettable.",
         ReviewSentiment.positive),
        (4, None, 4, "Solid stay",
         "Good location and clean rooms. Parking was a bit tight but overall a pleasant stay.",
         ReviewSentiment.positive),
        (3, None, 1, "Disappointing checkout",
         "Checkout was chaotic and nobody helped with our luggage. Very frustrated.",
         ReviewSentiment.negative),
    ]

    for g_idx, r_idx, rating, title, body, sentiment in reviews_data:
        review = Review(
            tenant_id=DEMO_TENANT,
            property_id=prop.id,
            guest_id=guests[g_idx].id,
            reservation_id=reservations[r_idx].id if r_idx is not None else None,
            platform="google",
            rating=rating,
            title=title,
            body=body,
            sentiment=sentiment,
            themes=json.dumps(ai_orchestrator.analyze_review_themes(body)),
            ai_draft_response=ai_orchestrator.draft_review_response(
                Review(
                    tenant_id=DEMO_TENANT,
                    property_id=prop.id,
                    guest_id=guests[g_idx].id,
                    rating=rating,
                    body=body,
                    sentiment=sentiment,
                ),
                prop,
                guests[g_idx],
            ),
            responded=rating >= 4,
            published_response="Thank you for your kind words!" if rating >= 4 else None,
        )
        db.add(review)
        db.flush()
        if rating <= 2:
            handle_negative_review(db, review, guests[g_idx], prop)

    pending_msgs = (
        db.query(Message)
        .filter(
            Message.tenant_id == DEMO_TENANT,
            Message.status == MessageStatus.pending_approval,
        )
        .all()
    )
    for msg in pending_msgs:
        guest = db.get(Guest, msg.guest_id)
        db.add(
            Approval(
                tenant_id=DEMO_TENANT,
                approval_type="message",
                title=f"Approve {msg.message_type} to {guest.name if guest else 'guest'}",
                content=msg.body,
                status=ApprovalStatus.pending,
                related_type="message",
                related_id=msg.id,
                confidence=msg.confidence,
            )
        )

    db.add(
        Task(
            tenant_id=DEMO_TENANT,
            title="Confirm family suite baby cot setup",
            description="Rossi Family arriving today — ensure baby cot is prepared.",
            status=TaskStatus.open,
            priority=TaskPriority.medium,
            assignee="Front Desk",
            due_at=datetime.utcnow() + timedelta(hours=4),
        )
    )
    db.add(
        Notification(
            tenant_id=DEMO_TENANT,
            title="1★ review received",
            body="Emily Chen left a critical review about checkout. Escalation task created.",
            level="critical",
        )
    )
    db.add(
        Notification(
            tenant_id=DEMO_TENANT,
            title="Upsell accepted",
            body="Marie Dupont accepted Spa Package (+€95) and Late Checkout (+€40).",
            level="success",
        )
    )
    db.add(
        Notification(
            tenant_id=DEMO_TENANT,
            title="Cloudbeds sync complete",
            body="Connector healthy. Use Sync to pull new reservations.",
            level="info",
        )
    )

    for res in reservations[:3]:
        event_bus.publish_and_process(
            db,
            DEMO_TENANT,
            "ReservationCreated",
            {
                "reservation_id": res.id,
                "guest_id": res.guest_id,
                "property_id": res.property_id,
            },
            source="seed",
            idempotency_key=f"seed:ReservationCreated:{res.id}",
        )

    # Celebrate Rewards: merchant config + one enrolled guest (Marie)
    config = get_or_create_config(db, DEMO_TENANT)
    config.currency = "EUR"
    config.birthday_min_spend = 100
    config.anniversary_min_spend = 150
    marie = guests[1]
    marie.review_reward_unlocked = True
    marie.review_reward_unlocked_at = datetime.utcnow()
    db.add(
        CelebrateDateAudit(
            tenant_id=DEMO_TENANT,
            guest_id=marie.id,
            field_name="review_reward_unlocked",
            old_value="false",
            new_value="true",
            changed_by="seed",
            action="unlock_reward",
            reason="Seed: prior verified Google review participation",
        )
    )
    confirm_and_lock_dates(
        db,
        marie,
        CelebrateDatesIn(
            birthday=date(1988, 8, 12),
            anniversary=date(2015, 8, 20),
            confirm=True,
        ),
        actor="seed",
    )
    # Hans unlocked but not yet enrolled — for invite demo
    hans = guests[0]
    hans.review_reward_unlocked = True
    hans.review_reward_unlocked_at = datetime.utcnow()

    db.commit()
