from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    Approval,
    ApprovalStatus,
    Campaign,
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
    User,
    Workflow,
)
from app.services.ai_orchestrator import (
    ai_orchestrator,
    execute_decision,
    handle_negative_review,
)
from app.services.event_bus import event_bus


def _on_reservation_created(db: Session, event, payload: dict) -> None:
    reservation = db.get(Reservation, payload["reservation_id"])
    guest = db.get(Guest, payload["guest_id"])
    property_ = db.get(Property, payload["property_id"])
    if not (reservation and guest and property_):
        return
    decision = ai_orchestrator.decide(db, guest, reservation, property_)
    execute_decision(db, decision, guest, reservation, property_)
    wf = (
        db.query(Workflow)
        .filter(
            Workflow.tenant_id == guest.tenant_id,
            Workflow.trigger_event == "ReservationCreated",
        )
        .first()
    )
    if wf:
        wf.runs += 1


def register_handlers() -> None:
    event_bus.subscribe("ReservationCreated", _on_reservation_created)


def seed_database(db: Session) -> None:
    if db.query(Property).first():
        return

    tenant = settings.default_tenant_id
    today = date.today()

    user = User(
        tenant_id=tenant,
        email="manager@azurecoast.demo",
        name="Sofia Marino",
        role="manager",
    )
    db.add(user)

    prop = Property(
        tenant_id=tenant,
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
                tenant_id=tenant,
                provider=provider,
                status="connected" if provider != "Stripe" else "pending",
                last_sync_at=datetime.utcnow() - timedelta(hours=2)
                if provider == "Cloudbeds"
                else None,
            )
        )

    workflows = [
        ("Pre-arrival Welcome", "ReservationCreated"),
        ("Checkout Review Request", "GuestCheckedOut"),
        ("Negative Review Escalation", "NegativeReviewReceived"),
        ("Cross-sell Reminder", "GuestCheckedOut"),
    ]
    for name, trigger in workflows:
        db.add(
            Workflow(
                tenant_id=tenant,
                name=name,
                trigger_event=trigger,
                status="active",
                definition=json.dumps({"trigger": trigger, "steps": ["wait", "ai", "send"]}),
                runs=12 if trigger == "ReservationCreated" else 5,
            )
        )

    db.add(
        Campaign(
            tenant_id=tenant,
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
            "pref": "email",
            "dietary": "vegetarian",
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
            "ltv": 55,
            "sat": 62,
            "spend": 890,
            "stays": 1,
            "pref": "email",
            "complaints": 1,
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
        },
    ]

    guests: list[Guest] = []
    for g in guests_data:
        guest = Guest(
            tenant_id=tenant,
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
            children=g["children"],
            dietary_preferences=g.get("dietary"),
            communication_preference=g["pref"],
            ltv_score=g["ltv"],
            satisfaction_score=g["sat"],
            complaint_history=g.get("complaints", 0),
            upsell_acceptance=0.35 if g["travel_type"] == "luxury" else 0.2,
            previous_reviews=1 if g["stays"] > 1 else 0,
        )
        db.add(guest)
        guests.append(guest)
    db.flush()

    reservations_spec = [
        (0, today, today + timedelta(days=3), "confirmed", "Deluxe Double", "Booking.com", 420),
        (1, today - timedelta(days=1), today + timedelta(days=2), "checked_in", "Junior Suite", "direct", 890),
        (2, today, today + timedelta(days=5), "confirmed", "Family Suite", "Airbnb", 780),
        (3, today - timedelta(days=4), today, "checked_out", "Standard Twin", "Expedia", 310),
        (4, today + timedelta(days=2), today + timedelta(days=5), "confirmed", "Business King", "direct", 540),
        (5, today - timedelta(days=2), today + timedelta(days=1), "checked_in", "Honeymoon Suite", "Website", 1200),
        (0, today - timedelta(days=40), today - timedelta(days=37), "checked_out", "Deluxe Double", "Booking.com", 380),
        (1, today + timedelta(days=14), today + timedelta(days=18), "confirmed", "Junior Suite", "direct", 1100),
    ]

    reservations: list[Reservation] = []
    for idx, cin, cout, status, room, source, amount in reservations_spec:
        res = Reservation(
            tenant_id=tenant,
            property_id=prop.id,
            guest_id=guests[idx].id,
            external_id=f"CB-{1000 + len(reservations)}",
            source=source,
            status=ReservationStatus(status),
            room_type=room,
            check_in=cin,
            check_out=cout,
            adults=2,
            children=guests[idx].children,
            total_amount=amount,
            currency="EUR",
            special_requests="Quiet room preferred" if idx == 1 else None,
        )
        db.add(res)
        reservations.append(res)
    db.flush()

    # Messages
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
                tenant_id=tenant,
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

    # Offers
    for r_idx, name, price, st in [
        (0, "Airport Transfer", 55.0, OfferStatus.offered),
        (1, "Spa Package", 95.0, OfferStatus.accepted),
        (2, "Baby Cot", 15.0, OfferStatus.offered),
        (5, "Champagne Welcome", 65.0, OfferStatus.offered),
        (1, "Late Checkout", 40.0, OfferStatus.accepted),
    ]:
        offer = Offer(
            tenant_id=tenant,
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
        db.add(offer)

    # Reviews
    reviews_data = [
        (
            3,
            3,
            2,
            "Noisy room near the elevator",
            "The location was great but our room was very noisy at night and the WiFi kept dropping. Staff were polite though.",
            ReviewSentiment.negative,
        ),
        (
            0,
            6,
            5,
            "Perfect business stay",
            "Excellent breakfast, fast check-in, and a quiet room. Will definitely return for my next trip to Nice.",
            ReviewSentiment.positive,
        ),
        (
            1,
            None,
            5,
            "Anniversary magic",
            "The spa and restaurant were outstanding. Clean rooms, beautiful pool, and the staff made our anniversary unforgettable.",
            ReviewSentiment.positive,
        ),
        (
            4,
            None,
            4,
            "Solid stay",
            "Good location and clean rooms. Parking was a bit tight but overall a pleasant stay.",
            ReviewSentiment.positive,
        ),
        (
            3,
            None,
            1,
            "Disappointing checkout",
            "Checkout was chaotic and nobody helped with our luggage. Very frustrated.",
            ReviewSentiment.negative,
        ),
    ]

    for g_idx, r_idx, rating, title, body, sentiment in reviews_data:
        review = Review(
            tenant_id=tenant,
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
                    tenant_id=tenant,
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

    # Pending message approvals
    pending_msgs = (
        db.query(Message)
        .filter(Message.status == MessageStatus.pending_approval)
        .all()
    )
    for msg in pending_msgs:
        guest = db.get(Guest, msg.guest_id)
        db.add(
            Approval(
                tenant_id=tenant,
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
            tenant_id=tenant,
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
            tenant_id=tenant,
            title="1★ review received",
            body="Emily Chen left a critical review about checkout. Escalation task created.",
            level="critical",
        )
    )
    db.add(
        Notification(
            tenant_id=tenant,
            title="Upsell accepted",
            body="Marie Dupont accepted Spa Package (+€95) and Late Checkout (+€40).",
            level="success",
        )
    )
    db.add(
        Notification(
            tenant_id=tenant,
            title="Cloudbeds sync complete",
            body="3 new reservations imported from Cloudbeds.",
            level="info",
        )
    )

    # Emit events for a couple of upcoming reservations to show event trail
    for res in reservations[:3]:
        event_bus.publish(
            db,
            tenant,
            "ReservationCreated",
            {
                "reservation_id": res.id,
                "guest_id": res.guest_id,
                "property_id": res.property_id,
            },
            source="seed",
        )

    db.commit()
