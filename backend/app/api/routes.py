from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import (
    AIDecision,
    Approval,
    ApprovalStatus,
    Connector,
    Event,
    Guest,
    Message,
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
    TaskStatus,
    Workflow,
)
from app.schemas import (
    AIDecisionOut,
    ApprovalAction,
    ApprovalOut,
    ConnectorOut,
    DashboardStats,
    DecideResult,
    EventOut,
    GuestOut,
    IntelligenceReport,
    IntelligenceTheme,
    MessageOut,
    NotificationOut,
    OfferOut,
    PropertyOut,
    ReservationCreate,
    ReservationOut,
    ReviewCreate,
    ReviewOut,
    SyncResult,
    TaskOut,
    WorkflowOut,
)
from app.services.ai_orchestrator import (
    ai_orchestrator,
    execute_decision,
    handle_negative_review,
)
from app.services.event_bus import event_bus

router = APIRouter()


def tenant_filter(model, tenant_id: str = settings.default_tenant_id):
    return model.tenant_id == tenant_id


# ---------- Dashboard ----------
@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    tenant = settings.default_tenant_id
    today = date.today()
    prop = db.query(Property).filter(Property.tenant_id == tenant).first()

    arrivals = (
        db.query(Reservation)
        .filter(Reservation.tenant_id == tenant, Reservation.check_in == today)
        .filter(Reservation.status != ReservationStatus.cancelled)
        .count()
    )
    departures = (
        db.query(Reservation)
        .filter(Reservation.tenant_id == tenant, Reservation.check_out == today)
        .count()
    )
    pending_messages = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant,
            Message.status.in_(
                [MessageStatus.queued, MessageStatus.pending_approval, MessageStatus.draft]
            ),
        )
        .count()
    )
    negative_reviews = (
        db.query(Review)
        .filter(Review.tenant_id == tenant, Review.rating <= 2, Review.responded.is_(False))
        .count()
    )
    pending_approvals = (
        db.query(Approval)
        .filter(Approval.tenant_id == tenant, Approval.status == ApprovalStatus.pending)
        .count()
    )
    upsells_waiting = (
        db.query(Offer)
        .filter(Offer.tenant_id == tenant, Offer.status == OfferStatus.offered)
        .count()
    )
    open_tasks = (
        db.query(Task)
        .filter(Task.tenant_id == tenant, Task.status == TaskStatus.open)
        .count()
    )
    upsell_revenue = (
        db.query(func.coalesce(func.sum(Offer.price), 0.0))
        .filter(Offer.tenant_id == tenant, Offer.status == OfferStatus.accepted)
        .scalar()
        or 0.0
    )
    today_rev = (
        db.query(func.coalesce(func.sum(Reservation.total_amount), 0.0))
        .filter(
            Reservation.tenant_id == tenant,
            Reservation.check_in <= today,
            Reservation.check_out >= today,
            Reservation.status.in_(
                [ReservationStatus.confirmed, ReservationStatus.checked_in]
            ),
        )
        .scalar()
        or 0.0
    )
    repeat_guests = (
        db.query(Guest).filter(Guest.tenant_id == tenant, Guest.stay_count > 1).count()
    )
    avg_spend = (
        db.query(func.coalesce(func.avg(Guest.average_booking), 0.0))
        .filter(Guest.tenant_id == tenant)
        .scalar()
        or 0.0
    )
    total_reviews = db.query(Review).filter(Review.tenant_id == tenant).count()
    reviewed_guests = (
        db.query(Guest).filter(Guest.tenant_id == tenant, Guest.previous_reviews > 0).count()
    )
    total_guests = db.query(Guest).filter(Guest.tenant_id == tenant).count()
    active = (
        db.query(Reservation)
        .filter(
            Reservation.tenant_id == tenant,
            Reservation.status.in_(
                [ReservationStatus.confirmed, ReservationStatus.checked_in]
            ),
        )
        .count()
    )
    rooms = prop.rooms if prop else 40
    occupancy = min(100.0, round((active / rooms) * 100, 1)) if rooms else 0

    return DashboardStats(
        arrivals_today=arrivals,
        departures_today=departures,
        pending_messages=pending_messages,
        negative_reviews=negative_reviews,
        pending_approvals=pending_approvals,
        upsells_waiting=upsells_waiting,
        open_tasks=open_tasks,
        revenue_today=round(float(today_rev) * 0.35 + float(upsell_revenue), 2),
        upsell_revenue=round(float(upsell_revenue), 2),
        repeat_guests=repeat_guests,
        average_spend=round(float(avg_spend), 2),
        review_conversion=round(
            (reviewed_guests / total_guests * 100) if total_guests else 0, 1
        ),
        google_rating=prop.google_rating if prop else 4.5,
        response_time_hours=1.4,
        ai_saved_hours=18.5,
        occupancy_pct=occupancy,
        active_reservations=active,
        total_guests=total_guests,
    )


# ---------- Properties ----------
@router.get("/properties", response_model=list[PropertyOut])
def list_properties(db: Session = Depends(get_db)):
    return db.query(Property).filter(Property.tenant_id == settings.default_tenant_id).all()


# ---------- Guests ----------
@router.get("/guests", response_model=list[GuestOut])
def list_guests(db: Session = Depends(get_db)):
    return (
        db.query(Guest)
        .filter(Guest.tenant_id == settings.default_tenant_id)
        .order_by(Guest.ltv_score.desc())
        .all()
    )


@router.get("/guests/{guest_id}", response_model=GuestOut)
def get_guest(guest_id: str, db: Session = Depends(get_db)):
    guest = db.get(Guest, guest_id)
    if not guest:
        raise HTTPException(404, "Guest not found")
    return guest


# ---------- Reservations ----------
@router.get("/reservations", response_model=list[ReservationOut])
def list_reservations(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Reservation).filter(Reservation.tenant_id == settings.default_tenant_id)
    if status:
        q = q.filter(Reservation.status == status)
    rows = q.order_by(Reservation.check_in.asc()).all()
    out = []
    for r in rows:
        guest = db.get(Guest, r.guest_id)
        item = ReservationOut.model_validate(r)
        item.guest_name = guest.name if guest else None
        item.status = r.status.value if hasattr(r.status, "value") else r.status
        out.append(item)
    return out


@router.post("/reservations", response_model=ReservationOut)
def create_reservation(payload: ReservationCreate, db: Session = Depends(get_db)):
    tenant = settings.default_tenant_id
    prop = db.query(Property).filter(Property.tenant_id == tenant).first()
    if not prop:
        raise HTTPException(400, "No property configured")

    guest = Guest(
        tenant_id=tenant,
        property_id=prop.id,
        name=payload.guest_name,
        email=payload.guest_email,
        phone=payload.guest_phone,
        country=payload.country,
        language=payload.language,
        travel_type=payload.travel_type,
        purpose=payload.purpose,
        children=payload.children,
        communication_preference=payload.communication_preference,
        stay_count=1,
        lifetime_spend=payload.total_amount,
        average_booking=payload.total_amount,
        ltv_score=60.0,
        satisfaction_score=70.0,
    )
    db.add(guest)
    db.flush()

    reservation = Reservation(
        tenant_id=tenant,
        property_id=prop.id,
        guest_id=guest.id,
        source=payload.source,
        status=ReservationStatus.confirmed,
        room_type=payload.room_type,
        check_in=payload.check_in,
        check_out=payload.check_out,
        adults=payload.adults,
        children=payload.children,
        total_amount=payload.total_amount,
        currency=payload.currency,
        special_requests=payload.special_requests,
        external_id=f"MAN-{datetime.utcnow().strftime('%H%M%S')}",
    )
    db.add(reservation)
    db.flush()

    event_bus.publish(
        db,
        tenant,
        "ReservationCreated",
        {
            "reservation_id": reservation.id,
            "guest_id": guest.id,
            "property_id": prop.id,
        },
        source="api",
    )
    event_bus.publish(
        db,
        tenant,
        "GuestProfileCreated",
        {"guest_id": guest.id},
        source="api",
    )
    db.commit()
    db.refresh(reservation)

    out = ReservationOut.model_validate(reservation)
    out.guest_name = guest.name
    out.status = reservation.status.value
    return out


@router.post("/reservations/{reservation_id}/decide", response_model=DecideResult)
def decide_for_reservation(reservation_id: str, db: Session = Depends(get_db)):
    reservation = db.get(Reservation, reservation_id)
    if not reservation:
        raise HTTPException(404, "Reservation not found")
    guest = db.get(Guest, reservation.guest_id)
    property_ = db.get(Property, reservation.property_id)
    decision = ai_orchestrator.decide(db, guest, reservation, property_)
    execution = execute_decision(db, decision, guest, reservation, property_)
    db.commit()
    db.refresh(decision)
    return DecideResult(
        decision=AIDecisionOut.model_validate(decision),
        execution=execution,
    )


@router.post("/reservations/{reservation_id}/checkout")
def checkout_reservation(reservation_id: str, db: Session = Depends(get_db)):
    reservation = db.get(Reservation, reservation_id)
    if not reservation:
        raise HTTPException(404, "Reservation not found")
    reservation.status = ReservationStatus.checked_out
    guest = db.get(Guest, reservation.guest_id)
    property_ = db.get(Property, reservation.property_id)

    event_bus.publish(
        db,
        reservation.tenant_id,
        "GuestCheckedOut",
        {"reservation_id": reservation.id, "guest_id": guest.id},
        source="api",
    )

    decision = AIDecision(
        tenant_id=reservation.tenant_id,
        reservation_id=reservation.id,
        guest_id=guest.id,
        action="ReviewRequest",
        channel=guest.communication_preference,
        language=guest.language,
        timing="8 hours after checkout",
        confidence=0.94,
        reasoning="Guest checked out — schedule review request.",
        raw_output=json.dumps({"action": "ReviewRequest"}),
        validated=True,
    )
    db.add(decision)
    db.flush()
    execute_decision(db, decision, guest, reservation, property_)
    db.commit()
    return {"ok": True, "status": "checked_out"}


# ---------- Messages ----------
@router.get("/messages", response_model=list[MessageOut])
def list_messages(db: Session = Depends(get_db)):
    rows = (
        db.query(Message)
        .filter(Message.tenant_id == settings.default_tenant_id)
        .order_by(Message.created_at.desc())
        .all()
    )
    out = []
    for m in rows:
        guest = db.get(Guest, m.guest_id)
        item = MessageOut.model_validate(m)
        item.guest_name = guest.name if guest else None
        item.channel = m.channel.value if hasattr(m.channel, "value") else m.channel
        item.status = m.status.value if hasattr(m.status, "value") else m.status
        out.append(item)
    return out


@router.post("/messages/{message_id}/send")
def send_message(message_id: str, db: Session = Depends(get_db)):
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(404, "Message not found")
    message.status = MessageStatus.sent
    message.sent_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "status": "sent"}


# ---------- Reviews ----------
@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(db: Session = Depends(get_db)):
    rows = (
        db.query(Review)
        .filter(Review.tenant_id == settings.default_tenant_id)
        .order_by(Review.created_at.desc())
        .all()
    )
    out = []
    for r in rows:
        guest = db.get(Guest, r.guest_id)
        item = ReviewOut.model_validate(r)
        item.guest_name = guest.name if guest else None
        item.sentiment = r.sentiment.value if hasattr(r.sentiment, "value") else r.sentiment
        out.append(item)
    return out


@router.post("/reviews", response_model=ReviewOut)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    guest = db.get(Guest, payload.guest_id)
    if not guest:
        raise HTTPException(404, "Guest not found")
    property_ = db.get(Property, guest.property_id)
    sentiment = (
        ReviewSentiment.negative
        if payload.rating <= 2
        else ReviewSentiment.positive
        if payload.rating >= 4
        else ReviewSentiment.neutral
    )
    review = Review(
        tenant_id=guest.tenant_id,
        property_id=guest.property_id,
        guest_id=guest.id,
        reservation_id=payload.reservation_id,
        platform=payload.platform,
        rating=payload.rating,
        title=payload.title,
        body=payload.body,
        sentiment=sentiment,
        themes=json.dumps(ai_orchestrator.analyze_review_themes(payload.body)),
        ai_draft_response=ai_orchestrator.draft_review_response(
            Review(
                tenant_id=guest.tenant_id,
                property_id=guest.property_id,
                guest_id=guest.id,
                rating=payload.rating,
                body=payload.body,
                sentiment=sentiment,
            ),
            property_,
            guest,
        ),
    )
    db.add(review)
    db.flush()
    if payload.rating <= 2:
        handle_negative_review(db, review, guest, property_)
        event_bus.publish(
            db,
            guest.tenant_id,
            "NegativeReviewReceived",
            {"review_id": review.id, "rating": payload.rating},
            source="api",
        )
    db.commit()
    db.refresh(review)
    out = ReviewOut.model_validate(review)
    out.guest_name = guest.name
    out.sentiment = review.sentiment.value
    return out


@router.post("/reviews/{review_id}/publish-response")
def publish_review_response(review_id: str, db: Session = Depends(get_db)):
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Review not found")
    if not review.ai_draft_response:
        raise HTTPException(400, "No draft response available")
    review.published_response = review.ai_draft_response
    review.responded = True
    db.commit()
    return {"ok": True}


# ---------- Approvals ----------
@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Approval).filter(Approval.tenant_id == settings.default_tenant_id)
    if status:
        q = q.filter(Approval.status == status)
    rows = q.order_by(Approval.created_at.desc()).all()
    out = []
    for a in rows:
        item = ApprovalOut.model_validate(a)
        item.status = a.status.value if hasattr(a.status, "value") else a.status
        out.append(item)
    return out


@router.post("/approvals/{approval_id}", response_model=ApprovalOut)
def act_on_approval(
    approval_id: str, payload: ApprovalAction, db: Session = Depends(get_db)
):
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    if payload.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")

    approval.status = (
        ApprovalStatus.approved if payload.action == "approve" else ApprovalStatus.rejected
    )
    approval.reviewed_by = payload.reviewed_by
    approval.reviewed_at = datetime.utcnow()

    if (
        payload.action == "approve"
        and approval.related_type == "message"
        and approval.related_id
    ):
        message = db.get(Message, approval.related_id)
        if message:
            message.status = MessageStatus.sent
            message.sent_at = datetime.utcnow()
    elif (
        payload.action == "approve"
        and approval.related_type == "review"
        and approval.related_id
    ):
        review = db.get(Review, approval.related_id)
        if review and review.ai_draft_response:
            review.published_response = review.ai_draft_response
            review.responded = True
    elif (
        payload.action == "reject"
        and approval.related_type == "message"
        and approval.related_id
    ):
        message = db.get(Message, approval.related_id)
        if message:
            message.status = MessageStatus.draft

    db.commit()
    db.refresh(approval)
    out = ApprovalOut.model_validate(approval)
    out.status = approval.status.value
    return out


# ---------- Offers / Tasks / Events ----------
@router.get("/offers", response_model=list[OfferOut])
def list_offers(db: Session = Depends(get_db)):
    rows = (
        db.query(Offer)
        .filter(Offer.tenant_id == settings.default_tenant_id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    out = []
    for o in rows:
        res = db.get(Reservation, o.reservation_id)
        guest = db.get(Guest, res.guest_id) if res else None
        item = OfferOut.model_validate(o)
        item.status = o.status.value if hasattr(o.status, "value") else o.status
        item.guest_name = guest.name if guest else None
        out.append(item)
    return out


@router.post("/offers/{offer_id}/accept")
def accept_offer(offer_id: str, db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(404, "Offer not found")
    offer.status = OfferStatus.accepted
    offer.accepted_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "revenue": offer.price}


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    rows = (
        db.query(Task)
        .filter(Task.tenant_id == settings.default_tenant_id)
        .order_by(Task.created_at.desc())
        .all()
    )
    out = []
    for t in rows:
        item = TaskOut.model_validate(t)
        item.status = t.status.value if hasattr(t.status, "value") else t.status
        item.priority = t.priority.value if hasattr(t.priority, "value") else t.priority
        out.append(item)
    return out


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.status = TaskStatus.done
    db.commit()
    return {"ok": True}


@router.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    return (
        db.query(Event)
        .filter(Event.tenant_id == settings.default_tenant_id)
        .order_by(Event.created_at.desc())
        .limit(100)
        .all()
    )


@router.get("/ai-decisions", response_model=list[AIDecisionOut])
def list_decisions(db: Session = Depends(get_db)):
    return (
        db.query(AIDecision)
        .filter(AIDecision.tenant_id == settings.default_tenant_id)
        .order_by(AIDecision.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/workflows", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db)):
    return (
        db.query(Workflow)
        .filter(Workflow.tenant_id == settings.default_tenant_id)
        .all()
    )


@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors(db: Session = Depends(get_db)):
    return (
        db.query(Connector)
        .filter(Connector.tenant_id == settings.default_tenant_id)
        .all()
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db)):
    return (
        db.query(Notification)
        .filter(Notification.tenant_id == settings.default_tenant_id)
        .order_by(Notification.created_at.desc())
        .all()
    )


@router.get("/intelligence", response_model=IntelligenceReport)
def intelligence_report(db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(Review.tenant_id == settings.default_tenant_id).all()
    counts: dict[str, dict] = {}
    for r in reviews:
        themes = json.loads(r.themes or "[]")
        for t in themes:
            entry = counts.setdefault(t, {"mentions": 0, "pos": 0, "neg": 0})
            entry["mentions"] += 1
            if r.rating >= 4:
                entry["pos"] += 1
            elif r.rating <= 2:
                entry["neg"] += 1

    themes_out = []
    for theme, data in sorted(counts.items(), key=lambda x: -x[1]["mentions"]):
        sent = "positive" if data["pos"] >= data["neg"] else "negative"
        if data["pos"] == data["neg"]:
            sent = "neutral"
        themes_out.append(
            IntelligenceTheme(theme=theme, mentions=data["mentions"], sentiment=sent)
        )

    most_praised = next((t.theme for t in themes_out if t.sentiment == "positive"), None)
    main_complaint = next((t.theme for t in themes_out if t.sentiment == "negative"), None)
    return IntelligenceReport(
        themes=themes_out,
        most_praised=most_praised,
        main_complaint=main_complaint,
        total_reviews=len(reviews),
    )


# ---------- PMS Sync / CSV Import ----------
@router.post("/connectors/sync", response_model=SyncResult)
def sync_pms(db: Session = Depends(get_db)):
    """Simulate a Cloudbeds / PMS pull of new reservations."""
    tenant = settings.default_tenant_id
    prop = db.query(Property).filter(Property.tenant_id == tenant).first()
    if not prop:
        raise HTTPException(400, "No property")

    samples = [
        ("Yuki Tanaka", "Japan", "en", "leisure", today_plus(5), today_plus(8), 460),
        ("Carlos Mendoza", "Spain", "es", "family", today_plus(1), today_plus(4), 620),
    ]
    imported = 0
    events = 0
    for name, country, lang, travel, cin, cout, amount in samples:
        existing = db.query(Guest).filter(Guest.name == name, Guest.tenant_id == tenant).first()
        if existing:
            continue
        guest = Guest(
            tenant_id=tenant,
            property_id=prop.id,
            name=name,
            country=country,
            language=lang,
            travel_type=travel,
            children=2 if travel == "family" else 0,
            communication_preference="whatsapp",
            stay_count=1,
            lifetime_spend=amount,
            average_booking=amount,
            ltv_score=58,
            satisfaction_score=70,
            email=f"{name.lower().replace(' ', '.')}@sync.demo",
        )
        db.add(guest)
        db.flush()
        res = Reservation(
            tenant_id=tenant,
            property_id=prop.id,
            guest_id=guest.id,
            external_id=f"CB-SYNC-{datetime.utcnow().strftime('%H%M%S')}-{imported}",
            source="Cloudbeds",
            status=ReservationStatus.confirmed,
            room_type="Deluxe Double",
            check_in=cin,
            check_out=cout,
            total_amount=amount,
            currency="EUR",
        )
        db.add(res)
        db.flush()
        event_bus.publish(
            db,
            tenant,
            "ReservationCreated",
            {
                "reservation_id": res.id,
                "guest_id": guest.id,
                "property_id": prop.id,
            },
            source="cloudbeds",
        )
        imported += 1
        events += 1

    connector = (
        db.query(Connector)
        .filter(Connector.tenant_id == tenant, Connector.provider == "Cloudbeds")
        .first()
    )
    if connector:
        connector.last_sync_at = datetime.utcnow()
        connector.status = "connected"
    db.commit()
    return SyncResult(
        imported=imported,
        events_emitted=events,
        message=f"Synced {imported} reservations from Cloudbeds",
    )


def today_plus(days: int) -> date:
    from datetime import timedelta

    return date.today() + timedelta(days=days)


@router.post("/connectors/import-csv", response_model=SyncResult)
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import reservations from CSV: name,email,country,language,check_in,check_out,amount,room_type"""
    tenant = settings.default_tenant_id
    prop = db.query(Property).filter(Property.tenant_id == tenant).first()
    if not prop:
        raise HTTPException(400, "No property")

    content = (await file.read()).decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    imported = 0
    events = 0
    for row in reader:
        guest = Guest(
            tenant_id=tenant,
            property_id=prop.id,
            name=row.get("name", "Guest"),
            email=row.get("email"),
            country=row.get("country"),
            language=row.get("language", "en"),
            travel_type=row.get("travel_type", "leisure"),
            communication_preference=row.get("channel", "email"),
            stay_count=1,
            lifetime_spend=float(row.get("amount", 200)),
            average_booking=float(row.get("amount", 200)),
            ltv_score=50,
            satisfaction_score=70,
        )
        db.add(guest)
        db.flush()
        res = Reservation(
            tenant_id=tenant,
            property_id=prop.id,
            guest_id=guest.id,
            source="csv",
            status=ReservationStatus.confirmed,
            room_type=row.get("room_type", "Standard"),
            check_in=date.fromisoformat(row["check_in"]),
            check_out=date.fromisoformat(row["check_out"]),
            total_amount=float(row.get("amount", 200)),
            currency=row.get("currency", "EUR"),
            external_id=f"CSV-{imported}",
        )
        db.add(res)
        db.flush()
        event_bus.publish(
            db,
            tenant,
            "ReservationCreated",
            {
                "reservation_id": res.id,
                "guest_id": guest.id,
                "property_id": prop.id,
            },
            source="csv",
        )
        imported += 1
        events += 1
    db.commit()
    return SyncResult(
        imported=imported,
        events_emitted=events,
        message=f"Imported {imported} rows from CSV",
    )
