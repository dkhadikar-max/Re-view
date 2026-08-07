from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    AuthUser,
    ManagerUser,
    StaffUser,
    create_access_token,
    is_platform_owner,
    verify_password,
)
from app.db.session import get_db
from app.models.entities import (
    AIDecision,
    Approval,
    ApprovalStatus,
    AuditLog,
    Connector,
    Event,
    EventStatus,
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
    Tenant,
    User,
    Workflow,
)
from app.schemas import (
    AIDecisionOut,
    ApprovalAction,
    ApprovalOut,
    AuditOut,
    ConnectorOut,
    DashboardStats,
    DecideResult,
    EventOut,
    GuestOut,
    IntelligenceReport,
    IntelligenceTheme,
    LoginRequest,
    MessageOut,
    NotificationOut,
    OfferOut,
    PropertyOut,
    PropertyUpdate,
    ReservationCreate,
    ReservationOut,
    ReviewCreate,
    ReviewOut,
    SyncResult,
    TaskOut,
    TokenResponse,
    UserOut,
    WorkerResult,
    WorkflowOut,
)
from app.services.passwords import ChangePasswordRequest
from app.services.ai_orchestrator import (
    ai_orchestrator,
    execute_decision,
    handle_negative_review,
)
from app.services.audit import write_audit
from app.services.celebrate_rewards import run_celebrate_campaigns, unlock_after_review
from app.services.connectors import sync_connector
from app.services.currency import currency_for_country
from app.services.event_bus import event_bus
from app.services.guest_intelligence import (
    GuestIntelligence,
    GuestOpportunity,
    build_intelligence,
    list_opportunities,
)
from app.services.hotel_signup import ensure_trial_demo_data
from app.services.messaging import deliver_message, process_due_messages
from app.services.state_machine import (
    APPROVAL_TRANSITIONS,
    MESSAGE_TRANSITIONS,
    OFFER_TRANSITIONS,
    RESERVATION_TRANSITIONS,
    TASK_TRANSITIONS,
    transition,
)
from app.services.tenancy import get_tenant_entity
from app.services.workflow_engine import process_waiting_workflows

router = APIRouter()

PageSkip = Annotated[int, Query(ge=0)]
PageLimit = Annotated[int, Query(ge=1, le=200)]


class _TenantScopedSession:
    """Session proxy that scopes worker service model queries to one tenant."""

    def __init__(self, db: Session, tenant_id: str) -> None:
        self._db = db
        self._tenant_id = tenant_id

    def query(self, *entities: Any):
        query = self._db.query(*entities)
        if len(entities) == 1 and hasattr(entities[0], "tenant_id"):
            query = query.filter(entities[0].tenant_id == self._tenant_id)
        return query

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)


def _review_out(review: Review, guest_name: str | None = None) -> ReviewOut:
    try:
        themes = json.loads(review.themes or "[]")
    except (json.JSONDecodeError, TypeError):
        themes = []
    if not isinstance(themes, list):
        themes = []
    data = {
        field: getattr(review, field)
        for field in ReviewOut.model_fields
        if hasattr(review, field)
    }
    data["themes"] = [str(theme) for theme in themes]
    data["sentiment"] = (
        review.sentiment.value
        if hasattr(review.sentiment, "value")
        else review.sentiment
    )
    data["guest_name"] = guest_name
    return ReviewOut.model_validate(data)


def _reservation_out(
    reservation: Reservation, guest_name: str | None = None
) -> ReservationOut:
    item = ReservationOut.model_validate(reservation)
    item.status = (
        reservation.status.value
        if hasattr(reservation.status, "value")
        else str(reservation.status)
    )
    item.total_amount = float(reservation.total_amount)
    item.guest_name = guest_name
    return item


def _event_out(event: Event) -> EventOut:
    item = EventOut.model_validate(event)
    item.status = (
        event.status.value if isinstance(event.status, EventStatus) else event.status
    )
    return item


def _property_for_tenant(db: Session, tenant_id: str) -> Property:
    property_ = db.query(Property).filter(Property.tenant_id == tenant_id).first()
    if not property_:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No property configured for tenant",
        )
    return property_


async def _login_payload(request: Request) -> LoginRequest:
    content_type = request.headers.get("content-type", "").lower()
    try:
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            form = await request.form()
            raw = {"username": form.get("username"), "password": form.get("password")}
        else:
            raw = await request.json()
        return LoginRequest.model_validate(raw)
    except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid username and password are required",
        ) from exc


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    payload: Annotated[LoginRequest, Depends(_login_payload)],
    db: Session = Depends(get_db),
) -> TokenResponse:
    email = str(payload.username).lower().strip()
    password = payload.password

    # Email is only unique per-tenant in the schema; the same address can exist on
    # demo-hotel (owner) and a trial tenant. Match the password against every
    # active candidate so trial re-login is not blocked by the owner row.
    candidates = (
        db.query(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .filter(
            func.lower(User.email) == email,
            User.is_active.is_(True),
            Tenant.is_active.is_(True),
        )
        .order_by(User.created_at.asc())
        .all()
    )
    user = next(
        (c for c in candidates if verify_password(password, c.password_hash)),
        None,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Trial workspaces always show demo data so hotels understand how Revisit works
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant and tenant.plan == "trial":
        if ensure_trial_demo_data(db, tenant.id):
            db.commit()

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=_user_out(user),
    )


@router.get("/auth/me", response_model=UserOut)
def auth_me(user: AuthUser) -> UserOut:
    return UserOut(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_platform_admin=is_platform_owner(user),
    )


@router.post("/auth/change-password")
def auth_change_password(
    payload: ChangePasswordRequest,
    user: AuthUser,
    db: Session = Depends(get_db),
):
    from app.services.passwords import change_password

    row = (
        db.query(User)
        .filter(User.id == user.id, User.tenant_id == user.tenant_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return change_password(
        db,
        user=row,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )


def _user_out(user: User) -> UserOut:
    from app.core.security import CurrentUser

    current = CurrentUser(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )
    return UserOut(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_platform_admin=is_platform_owner(current),
    )


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(user: AuthUser, db: Session = Depends(get_db)) -> DashboardStats:
    tenant_id = user.tenant_id
    today = date.today()
    property_ = db.query(Property).filter(Property.tenant_id == tenant_id).first()

    arrivals = (
        db.query(Reservation)
        .filter(
            Reservation.tenant_id == tenant_id,
            Reservation.check_in == today,
            Reservation.status != ReservationStatus.cancelled,
        )
        .count()
    )
    departures = (
        db.query(Reservation)
        .filter(
            Reservation.tenant_id == tenant_id,
            Reservation.check_out == today,
            Reservation.status != ReservationStatus.cancelled,
        )
        .count()
    )
    pending_messages = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.status.in_(
                [
                    MessageStatus.queued,
                    MessageStatus.pending_approval,
                    MessageStatus.draft,
                ]
            ),
        )
        .count()
    )
    negative_reviews = (
        db.query(Review)
        .filter(
            Review.tenant_id == tenant_id,
            Review.rating <= 2,
            Review.responded.is_(False),
        )
        .count()
    )
    pending_approvals = (
        db.query(Approval)
        .filter(
            Approval.tenant_id == tenant_id,
            Approval.status == ApprovalStatus.pending,
        )
        .count()
    )
    upsells_waiting = (
        db.query(Offer)
        .filter(Offer.tenant_id == tenant_id, Offer.status == OfferStatus.offered)
        .count()
    )
    open_tasks = (
        db.query(Task)
        .filter(Task.tenant_id == tenant_id, Task.status == TaskStatus.open)
        .count()
    )
    upsell_revenue = (
        db.query(func.coalesce(func.sum(Offer.price), 0))
        .filter(Offer.tenant_id == tenant_id, Offer.status == OfferStatus.accepted)
        .scalar()
        or 0
    )
    revenue_today = (
        db.query(func.coalesce(func.sum(Reservation.total_amount), 0))
        .filter(
            Reservation.tenant_id == tenant_id,
            Reservation.check_in <= today,
            Reservation.check_out >= today,
            Reservation.status.in_(
                [ReservationStatus.confirmed, ReservationStatus.checked_in]
            ),
        )
        .scalar()
        or 0
    )
    repeat_guests = (
        db.query(Guest)
        .filter(Guest.tenant_id == tenant_id, Guest.stay_count > 1)
        .count()
    )
    average_spend = (
        db.query(func.coalesce(func.avg(Guest.average_booking), 0))
        .filter(Guest.tenant_id == tenant_id)
        .scalar()
        or 0
    )
    reviewed_guests = (
        db.query(Guest)
        .filter(Guest.tenant_id == tenant_id, Guest.previous_reviews > 0)
        .count()
    )
    total_guests = db.query(Guest).filter(Guest.tenant_id == tenant_id).count()
    active = (
        db.query(Reservation)
        .filter(
            Reservation.tenant_id == tenant_id,
            Reservation.check_in <= today,
            Reservation.check_out >= today,
            Reservation.status.in_(
                [ReservationStatus.confirmed, ReservationStatus.checked_in]
            ),
        )
        .count()
    )
    sent_messages = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.status.in_([MessageStatus.sent, MessageStatus.delivered]),
            Message.sent_at.isnot(None),
        )
        .all()
    )
    response_samples = [
        max(0.0, (message.sent_at - message.created_at).total_seconds() / 3600)
        for message in sent_messages
        if message.sent_at and message.created_at
    ]
    response_time = (
        sum(response_samples) / len(response_samples) if response_samples else 1.4
    )
    executed_decisions = (
        db.query(AIDecision)
        .filter(AIDecision.tenant_id == tenant_id, AIDecision.executed.is_(True))
        .count()
    )
    rooms = property_.rooms if property_ else 0
    currency = (
        (getattr(property_, "currency", None) or "").upper()
        if property_
        else ""
    ) or (
        currency_for_country(property_.country) if property_ else "EUR"
    )

    return DashboardStats(
        arrivals_today=arrivals,
        departures_today=departures,
        pending_messages=pending_messages,
        negative_reviews=negative_reviews,
        pending_approvals=pending_approvals,
        upsells_waiting=upsells_waiting,
        open_tasks=open_tasks,
        revenue_today=round(float(revenue_today), 2),
        upsell_revenue=round(float(upsell_revenue), 2),
        repeat_guests=repeat_guests,
        average_spend=round(float(average_spend), 2),
        review_conversion=round(
            reviewed_guests / total_guests * 100 if total_guests else 0, 1
        ),
        google_rating=float(property_.google_rating) if property_ else 0.0,
        response_time_hours=round(response_time, 2),
        ai_saved_hours=round(executed_decisions * 0.25, 2),
        occupancy_pct=round(min(100.0, active / rooms * 100), 1) if rooms else 0.0,
        active_reservations=active,
        total_guests=total_guests,
        currency=currency,
    )


@router.get("/properties", response_model=list[PropertyOut])
def list_properties(user: AuthUser, db: Session = Depends(get_db)) -> list[Property]:
    return db.query(Property).filter(Property.tenant_id == user.tenant_id).all()


@router.patch("/properties/{property_id}", response_model=PropertyOut)
def update_property(
    property_id: str,
    payload: PropertyUpdate,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> Property:
    property_ = get_tenant_entity(
        db, Property, property_id, user.tenant_id, not_found="Property not found"
    )
    property_.name = payload.name.strip()
    property_.city = payload.city.strip()
    property_.country = payload.country.strip()
    property_.currency = payload.currency
    property_.timezone = payload.timezone.strip()
    property_.rooms = payload.rooms
    property_.brand_voice = payload.brand_voice.strip()
    property_.address = payload.address
    property_.google_review_url = payload.google_review_url
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="update_property",
        entity_type="property",
        entity_id=property_.id,
        details={"name": property_.name, "city": property_.city, "country": property_.country},
    )
    db.commit()
    db.refresh(property_)
    return property_


@router.get("/guests", response_model=list[GuestIntelligence])
def list_guests(
    user: AuthUser,
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    q: str | None = Query(default=None, description="Search name, email, tags"),
    min_spend: float | None = Query(default=None, ge=0),
    min_stays: int | None = Query(default=None, ge=0),
    birthday_month: bool = Query(default=False),
    inactive_days: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> list[GuestIntelligence]:
    rows = (
        db.query(Guest)
        .filter(Guest.tenant_id == user.tenant_id)
        .order_by(Guest.ltv_score.desc())
        .all()
    )
    today = date.today()
    enriched = [build_intelligence(db, g) for g in rows]
    if q:
        needle = q.lower()
        enriched = [
            g
            for g in enriched
            if needle in g.name.lower()
            or needle in (g.email or "").lower()
            or any(needle in t.lower() for t in g.tags)
            or needle in (g.ai_summary or "").lower()
        ]
    if min_spend is not None:
        enriched = [g for g in enriched if float(g.lifetime_spend) >= min_spend]
    if min_stays is not None:
        enriched = [g for g in enriched if g.stay_count >= min_stays]
    if birthday_month:
        enriched = [
            g
            for g in enriched
            if g.birthday and g.birthday.month == today.month
        ]
    if inactive_days is not None:
        enriched = [
            g
            for g in enriched
            if g.days_since_last_visit is not None
            and g.days_since_last_visit >= inactive_days
        ]
    return enriched[skip : skip + limit]


@router.get("/guests/opportunities", response_model=list[GuestOpportunity])
def guest_opportunities(
    user: AuthUser,
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
) -> list[GuestOpportunity]:
    return list_opportunities(db, user.tenant_id, limit=limit)


@router.get("/guests/{guest_id}", response_model=GuestIntelligence)
def get_guest(
    guest_id: str, user: AuthUser, db: Session = Depends(get_db)
) -> GuestIntelligence:
    guest = get_tenant_entity(
        db, Guest, guest_id, user.tenant_id, not_found="Guest not found"
    )
    return build_intelligence(db, guest)


@router.get("/reservations", response_model=list[ReservationOut])
def list_reservations(
    user: AuthUser,
    reservation_status: str | None = Query(default=None, alias="status"),
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[ReservationOut]:
    query = db.query(Reservation).filter(Reservation.tenant_id == user.tenant_id)
    if reservation_status:
        try:
            normalized_status = ReservationStatus(reservation_status)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid reservation status",
            ) from exc
        query = query.filter(Reservation.status == normalized_status)
    rows = query.order_by(Reservation.check_in.asc()).offset(skip).limit(limit).all()
    guest_ids = {row.guest_id for row in rows}
    guests = {
        guest.id: guest.name
        for guest in db.query(Guest)
        .filter(Guest.tenant_id == user.tenant_id, Guest.id.in_(guest_ids))
        .all()
    }
    return [_reservation_out(row, guests.get(row.guest_id)) for row in rows]


@router.post(
    "/reservations",
    response_model=ReservationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reservation(
    payload: ReservationCreate,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> ReservationOut:
    property_ = _property_for_tenant(db, user.tenant_id)
    guest = Guest(
        tenant_id=user.tenant_id,
        property_id=property_.id,
        name=payload.guest_name,
        email=str(payload.guest_email) if payload.guest_email else None,
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
        tenant_id=user.tenant_id,
        property_id=property_.id,
        guest_id=guest.id,
        external_id=f"MAN-{uuid.uuid4()}",
        source=payload.source,
        status=ReservationStatus.confirmed,
        room_type=payload.room_type,
        check_in=payload.check_in,
        check_out=payload.check_out,
        adults=payload.adults,
        children=payload.children,
        total_amount=payload.total_amount,
        currency=payload.currency.upper(),
        special_requests=payload.special_requests,
    )
    db.add(reservation)
    db.flush()
    event_bus.publish_and_process(
        db,
        user.tenant_id,
        "GuestProfileCreated",
        {"guest_id": guest.id, "property_id": property_.id},
        source="api",
        idempotency_key=f"GuestProfileCreated:{guest.id}",
    )
    event_bus.publish_and_process(
        db,
        user.tenant_id,
        "ReservationCreated",
        {
            "reservation_id": reservation.id,
            "guest_id": guest.id,
            "property_id": property_.id,
        },
        source="api",
        idempotency_key=f"ReservationCreated:{reservation.id}",
    )
    db.commit()
    db.refresh(reservation)
    return _reservation_out(reservation, guest.name)


@router.post("/reservations/{reservation_id}/decide", response_model=DecideResult)
def decide_for_reservation(
    reservation_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> DecideResult:
    reservation = get_tenant_entity(
        db,
        Reservation,
        reservation_id,
        user.tenant_id,
        not_found="Reservation not found",
    )
    guest = get_tenant_entity(
        db, Guest, reservation.guest_id, user.tenant_id, not_found="Guest not found"
    )
    property_ = get_tenant_entity(
        db,
        Property,
        reservation.property_id,
        user.tenant_id,
        not_found="Property not found",
    )
    decision = ai_orchestrator.decide(db, guest, reservation, property_)
    execution = execute_decision(db, decision, guest, reservation, property_)
    db.commit()
    db.refresh(decision)
    return DecideResult(
        decision=AIDecisionOut.model_validate(decision), execution=execution
    )


@router.post("/reservations/{reservation_id}/checkout")
def checkout_reservation(
    reservation_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    reservation = get_tenant_entity(
        db,
        Reservation,
        reservation_id,
        user.tenant_id,
        not_found="Reservation not found",
    )
    reservation.status = transition(
        reservation.status,
        ReservationStatus.checked_out,
        RESERVATION_TRANSITIONS,
        "reservation",
    )
    event_bus.publish_and_process(
        db,
        user.tenant_id,
        "GuestCheckedOut",
        {"reservation_id": reservation.id, "guest_id": reservation.guest_id},
        source="api",
        idempotency_key=f"GuestCheckedOut:{reservation.id}",
    )
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="checkout",
        entity_type="reservation",
        entity_id=reservation.id,
        details={"status": ReservationStatus.checked_out.value},
    )
    db.commit()
    return {"ok": True, "status": ReservationStatus.checked_out.value}


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    user: AuthUser,
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    rows = (
        db.query(Message)
        .filter(Message.tenant_id == user.tenant_id)
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    guest_ids = {row.guest_id for row in rows}
    guests = {
        guest.id: guest.name
        for guest in db.query(Guest)
        .filter(Guest.tenant_id == user.tenant_id, Guest.id.in_(guest_ids))
        .all()
    }
    output: list[MessageOut] = []
    for row in rows:
        item = MessageOut.model_validate(row)
        item.channel = (
            row.channel.value if hasattr(row.channel, "value") else row.channel
        )
        item.status = row.status.value if hasattr(row.status, "value") else row.status
        item.guest_name = guests.get(row.guest_id)
        output.append(item)
    return output


@router.post("/messages/{message_id}/send")
def send_message(
    message_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    message = get_tenant_entity(
        db, Message, message_id, user.tenant_id, not_found="Message not found"
    )
    if message.status == MessageStatus.pending_approval:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Message requires approval before it can be sent",
        )
    if message.status != MessageStatus.queued:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only queued messages can be sent",
        )
    deliver_message(db, message)
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="send",
        entity_type="message",
        entity_id=message.id,
        details={"channel": message.channel.value},
    )
    db.commit()
    return {"ok": True, "status": MessageStatus.sent.value}


@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(
    user: AuthUser,
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[ReviewOut]:
    rows = (
        db.query(Review)
        .filter(Review.tenant_id == user.tenant_id)
        .order_by(Review.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    guest_ids = {row.guest_id for row in rows}
    guests = {
        guest.id: guest.name
        for guest in db.query(Guest)
        .filter(Guest.tenant_id == user.tenant_id, Guest.id.in_(guest_ids))
        .all()
    }
    return [_review_out(row, guests.get(row.guest_id)) for row in rows]


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: ReviewCreate,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> ReviewOut:
    guest = get_tenant_entity(
        db, Guest, payload.guest_id, user.tenant_id, not_found="Guest not found"
    )
    property_ = get_tenant_entity(
        db,
        Property,
        guest.property_id,
        user.tenant_id,
        not_found="Property not found",
    )
    if payload.reservation_id:
        reservation = get_tenant_entity(
            db,
            Reservation,
            payload.reservation_id,
            user.tenant_id,
            not_found="Reservation not found",
        )
        if reservation.guest_id != guest.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reservation does not belong to guest",
            )
    sentiment = (
        ReviewSentiment.negative
        if payload.rating <= 2
        else ReviewSentiment.positive
        if payload.rating >= 4
        else ReviewSentiment.neutral
    )
    review = Review(
        tenant_id=user.tenant_id,
        property_id=property_.id,
        guest_id=guest.id,
        reservation_id=payload.reservation_id,
        platform=payload.platform,
        rating=payload.rating,
        title=payload.title,
        body=payload.body,
        sentiment=sentiment,
        themes=json.dumps(ai_orchestrator.analyze_review_themes(payload.body)),
    )
    db.add(review)
    db.flush()
    # Celebrate Rewards: unlock for participation (any verified review), not rating
    unlock_after_review(db, review, guest, actor=user.email)
    if payload.rating <= 2:
        event_bus.publish_and_process(
            db,
            user.tenant_id,
            "NegativeReviewReceived",
            {"review_id": review.id, "rating": payload.rating},
            source="api",
            idempotency_key=f"NegativeReviewReceived:{review.id}",
        )
        # Keep direct route use safe when event handlers were not registered.
        if not review.ai_draft_response:
            handle_negative_review(db, review, guest, property_)
    else:
        review.ai_draft_response = ai_orchestrator.draft_review_response(
            review, property_, guest
        )
    db.commit()
    db.refresh(review)
    return _review_out(review, guest.name)


def _publish_review(
    db: Session, review: Review, *, user: Any, audit_action: str = "publish_response"
) -> None:
    if not review.ai_draft_response:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No draft response available",
        )
    review.published_response = review.ai_draft_response
    review.responded = True
    # Official Google Business Profile publish when configured (never scrape)
    if (review.platform or "").lower() == "google":
        from app.integrations.google_reviews import google_reviews_client

        google_reviews_client.publish_reply(
            review_name=review.id,
            comment=review.ai_draft_response,
        )
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action=audit_action,
        entity_type="review",
        entity_id=review.id,
        details={"rating": review.rating, "platform": review.platform},
    )


@router.post("/reviews/{review_id}/publish-response")
def publish_review_response(
    review_id: str,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    review = get_tenant_entity(
        db, Review, review_id, user.tenant_id, not_found="Review not found"
    )
    if review.rating <= 3:
        approved = (
            db.query(Approval)
            .filter(
                Approval.tenant_id == user.tenant_id,
                Approval.related_type == "review",
                Approval.related_id == review.id,
                Approval.status == ApprovalStatus.approved,
            )
            .first()
        )
        if not approved:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="An approved review response approval is required",
            )
    _publish_review(db, review, user=user)
    db.commit()
    return {"ok": True}


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(
    user: AuthUser,
    approval_status: str | None = Query(default=None, alias="status"),
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[ApprovalOut]:
    query = db.query(Approval).filter(Approval.tenant_id == user.tenant_id)
    if approval_status:
        try:
            normalized_status = ApprovalStatus(approval_status)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid approval status",
            ) from exc
        query = query.filter(Approval.status == normalized_status)
    rows = query.order_by(Approval.created_at.desc()).offset(skip).limit(limit).all()
    output: list[ApprovalOut] = []
    for row in rows:
        item = ApprovalOut.model_validate(row)
        item.status = row.status.value if hasattr(row.status, "value") else row.status
        output.append(item)
    return output


@router.post("/approvals/{approval_id}", response_model=ApprovalOut)
def act_on_approval(
    approval_id: str,
    payload: ApprovalAction,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> ApprovalOut:
    approval = get_tenant_entity(
        db, Approval, approval_id, user.tenant_id, not_found="Approval not found"
    )
    target = (
        ApprovalStatus.approved
        if payload.action == "approve"
        else ApprovalStatus.rejected
    )
    approval.status = transition(
        approval.status, target, APPROVAL_TRANSITIONS, "approval"
    )
    approval.reviewed_by = user.name
    approval.reviewed_by_user_id = user.id
    approval.reviewed_at = datetime.utcnow()

    if approval.related_type == "message" and approval.related_id:
        message = get_tenant_entity(
            db,
            Message,
            approval.related_id,
            user.tenant_id,
            not_found="Related message not found",
        )
        message_target = (
            MessageStatus.queued
            if target == ApprovalStatus.approved
            else MessageStatus.draft
        )
        message.status = transition(
            message.status, message_target, MESSAGE_TRANSITIONS, "message"
        )
    elif (
        target == ApprovalStatus.approved
        and approval.related_type == "review"
        and approval.related_id
    ):
        review = get_tenant_entity(
            db,
            Review,
            approval.related_id,
            user.tenant_id,
            not_found="Related review not found",
        )
        _publish_review(db, review, user=user, audit_action="approval_publish_response")

    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action=payload.action,
        entity_type="approval",
        entity_id=approval.id,
        details={
            "related_type": approval.related_type,
            "related_id": approval.related_id,
        },
    )
    db.commit()
    db.refresh(approval)
    item = ApprovalOut.model_validate(approval)
    item.status = approval.status.value
    return item


@router.get("/offers", response_model=list[OfferOut])
def list_offers(
    user: AuthUser,
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[OfferOut]:
    rows = (
        db.query(Offer)
        .filter(Offer.tenant_id == user.tenant_id)
        .order_by(Offer.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    reservation_ids = {row.reservation_id for row in rows}
    reservations = {
        row.id: row.guest_id
        for row in db.query(Reservation)
        .filter(
            Reservation.tenant_id == user.tenant_id,
            Reservation.id.in_(reservation_ids),
        )
        .all()
    }
    guest_ids = set(reservations.values())
    guests = {
        row.id: row.name
        for row in db.query(Guest)
        .filter(Guest.tenant_id == user.tenant_id, Guest.id.in_(guest_ids))
        .all()
    }
    output: list[OfferOut] = []
    for row in rows:
        item = OfferOut.model_validate(row)
        item.status = row.status.value if hasattr(row.status, "value") else row.status
        item.price = float(row.price)
        item.guest_name = guests.get(reservations.get(row.reservation_id, ""))
        output.append(item)
    return output


@router.post("/offers/{offer_id}/accept")
def accept_offer(
    offer_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    offer = get_tenant_entity(
        db, Offer, offer_id, user.tenant_id, not_found="Offer not found"
    )
    if offer.status == OfferStatus.accepted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Offer has already been accepted",
        )
    offer.status = transition(
        offer.status, OfferStatus.accepted, OFFER_TRANSITIONS, "offer"
    )
    offer.accepted_at = datetime.utcnow()
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="accept",
        entity_type="offer",
        entity_id=offer.id,
        details={"revenue": float(offer.price)},
    )
    db.commit()
    return {"ok": True, "revenue": float(offer.price)}


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    user: AuthUser,
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[TaskOut]:
    rows = (
        db.query(Task)
        .filter(Task.tenant_id == user.tenant_id)
        .order_by(Task.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    output: list[TaskOut] = []
    for row in rows:
        item = TaskOut.model_validate(row)
        item.status = row.status.value if hasattr(row.status, "value") else row.status
        item.priority = (
            row.priority.value if hasattr(row.priority, "value") else row.priority
        )
        output.append(item)
    return output


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    task = get_tenant_entity(
        db, Task, task_id, user.tenant_id, not_found="Task not found"
    )
    task.status = transition(task.status, TaskStatus.done, TASK_TRANSITIONS, "task")
    db.commit()
    return {"ok": True}


@router.get("/events", response_model=list[EventOut])
def list_events(
    user: AuthUser,
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[EventOut]:
    rows = (
        db.query(Event)
        .filter(Event.tenant_id == user.tenant_id)
        .order_by(Event.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_event_out(row) for row in rows]


@router.get("/ai-decisions", response_model=list[AIDecisionOut])
def list_decisions(user: AuthUser, db: Session = Depends(get_db)) -> list[AIDecision]:
    return (
        db.query(AIDecision)
        .filter(AIDecision.tenant_id == user.tenant_id)
        .order_by(AIDecision.created_at.desc())
        .limit(100)
        .all()
    )


@router.get("/workflows", response_model=list[WorkflowOut])
def list_workflows(user: AuthUser, db: Session = Depends(get_db)) -> list[Workflow]:
    return (
        db.query(Workflow)
        .filter(Workflow.tenant_id == user.tenant_id)
        .order_by(Workflow.created_at.desc())
        .all()
    )


@router.get("/connectors", response_model=list[ConnectorOut])
def list_connectors(user: AuthUser, db: Session = Depends(get_db)) -> list[Connector]:
    return (
        db.query(Connector)
        .filter(Connector.tenant_id == user.tenant_id)
        .order_by(Connector.created_at.desc())
        .all()
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    user: AuthUser, db: Session = Depends(get_db)
) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.tenant_id == user.tenant_id)
        .order_by(Notification.created_at.desc())
        .all()
    )


@router.get("/intelligence", response_model=IntelligenceReport)
def intelligence_report(
    user: AuthUser, db: Session = Depends(get_db)
) -> IntelligenceReport:
    reviews = db.query(Review).filter(Review.tenant_id == user.tenant_id).all()
    counts: dict[str, dict[str, int]] = {}
    for review in reviews:
        try:
            themes = json.loads(review.themes or "[]")
        except (json.JSONDecodeError, TypeError):
            themes = []
        if not isinstance(themes, list):
            continue
        for raw_theme in themes:
            theme = str(raw_theme)
            entry = counts.setdefault(
                theme, {"mentions": 0, "positive": 0, "negative": 0}
            )
            entry["mentions"] += 1
            if review.rating >= 4:
                entry["positive"] += 1
            elif review.rating <= 2:
                entry["negative"] += 1
    themes_out: list[IntelligenceTheme] = []
    for theme, values in sorted(
        counts.items(), key=lambda item: (-item[1]["mentions"], item[0])
    ):
        sentiment = (
            "positive"
            if values["positive"] > values["negative"]
            else "negative"
            if values["negative"] > values["positive"]
            else "neutral"
        )
        themes_out.append(
            IntelligenceTheme(
                theme=theme,
                mentions=values["mentions"],
                sentiment=sentiment,
            )
        )
    return IntelligenceReport(
        themes=themes_out,
        most_praised=next(
            (theme.theme for theme in themes_out if theme.sentiment == "positive"),
            None,
        ),
        main_complaint=next(
            (theme.theme for theme in themes_out if theme.sentiment == "negative"),
            None,
        ),
        total_reviews=len(reviews),
    )


@router.post("/connectors/sync", response_model=SyncResult)
def sync_pms(user: ManagerUser, db: Session = Depends(get_db)) -> SyncResult:
    try:
        result = sync_connector(db, user.tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="sync",
        entity_type="connector",
        entity_id="Cloudbeds",
        details=result,
    )
    db.commit()
    return SyncResult(
        imported=result["imported"],
        events_emitted=result["events_emitted"],
        message=f"Synced {result['imported']} reservations from Cloudbeds",
    )


def _csv_payload(row: dict[str, str | None], line_number: int) -> ReservationCreate:
    raw = {
        "guest_name": (row.get("name") or "").strip(),
        "guest_email": (row.get("email") or "").strip() or None,
        "guest_phone": (row.get("phone") or "").strip() or None,
        "country": (row.get("country") or "").strip() or None,
        "language": (row.get("language") or "en").strip(),
        "travel_type": (row.get("travel_type") or "leisure").strip().lower(),
        "purpose": (row.get("purpose") or "").strip() or None,
        "children": row.get("children") or 0,
        "source": "csv",
        "room_type": (row.get("room_type") or "Standard").strip(),
        "check_in": row.get("check_in"),
        "check_out": row.get("check_out"),
        "adults": row.get("adults") or 2,
        "total_amount": row.get("amount") or 0,
        "currency": (row.get("currency") or "EUR").strip().upper(),
        "special_requests": (row.get("special_requests") or "").strip() or None,
        "communication_preference": (row.get("channel") or "email").strip().lower(),
    }
    try:
        return ReservationCreate.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"Invalid CSV row {line_number}",
                "errors": exc.errors(),
            },
        ) from exc


@router.post("/connectors/import-csv", response_model=SyncResult)
async def import_csv(
    user: ManagerUser,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SyncResult:
    content = await file.read(settings.csv_max_bytes + 1)
    if len(content) > settings.csv_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"CSV exceeds {settings.csv_max_bytes} bytes",
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV must be UTF-8 encoded",
        ) from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "check_in", "check_out", "amount"}
    headers = set(reader.fieldnames or [])
    if not required.issubset(headers):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"CSV is missing required columns: {sorted(required - headers)}",
        )
    raw_rows = list(reader)
    if len(raw_rows) > settings.csv_max_rows:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"CSV exceeds {settings.csv_max_rows} rows",
        )
    if not raw_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV contains no data rows",
        )
    payloads = [
        _csv_payload(row, line_number)
        for line_number, row in enumerate(raw_rows, start=2)
    ]
    property_ = _property_for_tenant(db, user.tenant_id)
    imported = 0
    emitted = 0
    for payload in payloads:
        guest = None
        if payload.guest_email:
            guest = (
                db.query(Guest)
                .filter(
                    Guest.tenant_id == user.tenant_id,
                    func.lower(Guest.email) == str(payload.guest_email).lower(),
                )
                .first()
            )
        if guest is None:
            guest = Guest(
                tenant_id=user.tenant_id,
                property_id=property_.id,
                name=payload.guest_name,
                email=str(payload.guest_email) if payload.guest_email else None,
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
                ltv_score=50,
                satisfaction_score=70,
            )
            db.add(guest)
            db.flush()
        else:
            previous_stays = guest.stay_count
            guest.name = payload.guest_name
            guest.phone = payload.guest_phone or guest.phone
            guest.country = payload.country or guest.country
            guest.language = payload.language
            guest.travel_type = payload.travel_type
            guest.communication_preference = payload.communication_preference
            guest.stay_count = previous_stays + 1
            guest.lifetime_spend = float(guest.lifetime_spend) + payload.total_amount
            guest.average_booking = float(guest.lifetime_spend) / guest.stay_count
        reservation = Reservation(
            tenant_id=user.tenant_id,
            property_id=property_.id,
            guest_id=guest.id,
            external_id=f"CSV-{uuid.uuid4()}",
            source="csv",
            status=ReservationStatus.confirmed,
            room_type=payload.room_type,
            check_in=payload.check_in,
            check_out=payload.check_out,
            adults=payload.adults,
            children=payload.children,
            total_amount=payload.total_amount,
            currency=payload.currency.upper(),
            special_requests=payload.special_requests,
        )
        db.add(reservation)
        db.flush()
        event_bus.publish_and_process(
            db,
            user.tenant_id,
            "ReservationCreated",
            {
                "reservation_id": reservation.id,
                "guest_id": guest.id,
                "property_id": property_.id,
            },
            source="csv",
            idempotency_key=f"ReservationCreated:csv:{reservation.external_id}",
        )
        imported += 1
        emitted += 1
    db.commit()
    return SyncResult(
        imported=imported,
        events_emitted=emitted,
        message=f"Imported {imported} rows from CSV",
    )


@router.post("/workers/tick", response_model=WorkerResult)
def worker_tick(user: ManagerUser, db: Session = Depends(get_db)) -> WorkerResult:
    scoped_db = _TenantScopedSession(db, user.tenant_id)
    events_processed = event_bus.process_pending(scoped_db)  # type: ignore[arg-type]
    messages_delivered = process_due_messages(scoped_db)  # type: ignore[arg-type]
    workflows_advanced = process_waiting_workflows(scoped_db)  # type: ignore[arg-type]
    celebrate = run_celebrate_campaigns(db, user.tenant_id)
    db.commit()
    return WorkerResult(
        events_processed=events_processed,
        messages_delivered=messages_delivered,
        workflows_advanced=workflows_advanced,
        celebrate_campaigns=celebrate,
    )


@router.get("/audit-logs", response_model=list[AuditOut])
def list_audit_logs(
    user: ManagerUser,
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == user.tenant_id)
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
