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
    ActionEventStatus,
    ActorType,
    Approval,
    ApprovalStatus,
    AuditLog,
    Connector,
    Event,
    EventStatus,
    Guest,
    ImportSession,
    ImportSessionStatus,
    Message,
    MessageStatus,
    Notification,
    MenuItem,
    Offer,
    OfferStatus,
    Property,
    PropertyKnowledgeBase,
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
    CsvRowIssue,
    CsvValidationReport,
    DashboardStats,
    DecideResult,
    EventOut,
    GuestOut,
    ImportSessionDetail,
    ImportSessionListItem,
    ImportSummaryOut,
    IntelligenceReport,
    IntelligenceTheme,
    LoginRequest,
    MenuImportRequest,
    MenuImportResult,
    MenuItemOut,
    MenuItemUpdate,
    MenuValidationReport,
    MessageOut,
    NotificationOut,
    OfferOut,
    PdfImportRequest,
    PdfImportResult,
    PdfValidationReport,
    PropertyKnowledgeBaseOut,
    PropertyKnowledgeBaseUpdate,
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
from app.integrations.pdf_extractor import (
    PdfPasswordProtectedError,
    PdfTooManyPagesError,
    PdfUnreadableError,
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
from app.services.context_builder import ContextBuilder
from app.services.currency import currency_for_country
from app.services.event_bus import event_bus
from app.services.faq_agent import preview_answers
from app.services.guest_intelligence import (
    GuestIntelligence,
    GuestOpportunity,
    build_intelligence,
    list_opportunities,
)
from app.services.hotel_signup import ensure_trial_demo_data
from app.services.import_orchestrator import (
    build_import_summary,
    finish_import_session,
    import_reservation,
    start_import_session,
)
from app.services.menu_importer import menu_importer
from app.services.messaging import deliver_message, process_due_messages
from app.services.action_logger import action_logger
from app.services.pdf_importer import pdf_importer
from app.services.pilot_health import PilotHealthOut, pilot_health
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
    # Normalize "" to None — the unique index treats every NULL as
    # distinct but would reject two properties both stored as "".
    property_.whatsapp_phone_number_id = payload.whatsapp_phone_number_id or None
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


def _knowledge_base_out(kb: PropertyKnowledgeBase | None) -> PropertyKnowledgeBaseOut:
    """Builds the response for both the GET and PATCH knowledge-base
    endpoints — a property with no row yet is a valid, honest empty
    state (never a 404), not a reason to fabricate a row."""
    data = (
        {
            field: getattr(kb, field)
            for field in PropertyKnowledgeBaseOut.model_fields
            if field != "preview"
        }
        if kb is not None
        else {}
    )
    return PropertyKnowledgeBaseOut(**data, preview=preview_answers(kb))


@router.get(
    "/properties/{property_id}/knowledge-base", response_model=PropertyKnowledgeBaseOut
)
def get_property_knowledge_base(
    property_id: str, user: AuthUser, db: Session = Depends(get_db)
) -> PropertyKnowledgeBaseOut:
    get_tenant_entity(db, Property, property_id, user.tenant_id, not_found="Property not found")
    kb = (
        db.query(PropertyKnowledgeBase)
        .filter(PropertyKnowledgeBase.property_id == property_id)
        .first()
    )
    return _knowledge_base_out(kb)


@router.patch(
    "/properties/{property_id}/knowledge-base", response_model=PropertyKnowledgeBaseOut
)
def update_property_knowledge_base(
    property_id: str,
    payload: PropertyKnowledgeBaseUpdate,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> PropertyKnowledgeBaseOut:
    get_tenant_entity(db, Property, property_id, user.tenant_id, not_found="Property not found")
    kb = (
        db.query(PropertyKnowledgeBase)
        .filter(PropertyKnowledgeBase.property_id == property_id)
        .first()
    )
    if kb is None:
        kb = PropertyKnowledgeBase(property_id=property_id, tenant_id=user.tenant_id)
        db.add(kb)

    # Only the fields actually present in the request are touched — a
    # client omitting a field leaves its stored value alone; explicitly
    # sending null clears it (PropertyKnowledgeBaseUpdate's own
    # docstring).
    changed_fields = payload.model_dump(exclude_unset=True)
    for field, value in changed_fields.items():
        setattr(kb, field, value)
    db.flush()

    # The hotel owns the truth, the AI consumes it — a stale cached
    # context is exactly the failure mode ContextBuilder.invalidate_tenant
    # exists to prevent (its own docstring: "anything that writes to
    # PropertyKnowledgeBase ... MUST call this after committing").
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="update_knowledge_base",
        entity_type="property_knowledge_base",
        entity_id=kb.id,
        # Field *names* only, never values — wifi_password is a
        # credential, and several other fields (house_rules,
        # emergency_contacts) are long free text that doesn't belong in
        # an audit blob either. Which facts changed is what staff need
        # to see in an audit trail, not a duplicate copy of the facts
        # themselves (those already live in PropertyKnowledgeBase).
        details={"changed_fields": sorted(changed_fields)},
    )
    db.commit()
    db.refresh(kb)
    ContextBuilder.invalidate_tenant(user.tenant_id)
    return _knowledge_base_out(kb)


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
    session = start_import_session(
        db,
        tenant_id=user.tenant_id,
        source="manual",
        initiated_by=user.email,
        rows_total=1,
    )
    guest, reservation, _ = import_reservation(
        db,
        tenant_id=user.tenant_id,
        property_id=property_.id,
        payload=payload,
        external_id=f"MAN-{uuid.uuid4()}",
        event_source="api",
        import_session=session,
    )
    finish_import_session(db, session)
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
    # PILOT_READINESS.md §5 — `transition()` raises 409 for any task
    # already `done` (TASK_TRANSITIONS[done] = set()), *before* anything
    # below ever runs. That's what makes this idempotent: a repeated
    # completion attempt never reaches the ActionEvent logging code, so
    # it can never produce a second TASK_COMPLETED for the same Task.
    task.status = transition(task.status, TaskStatus.done, TASK_TRANSITIONS, "task")

    # The evidence chain's last step — closes the gap PILOT_READINESS.md
    # §5 found: completion used to update Task.status and stop there,
    # leaving no ActionEvent record that a human ever did the work.
    # Only emitted when this Task actually has a guest to attribute it
    # to (ActionEvent.guest_id is required, non-nullable) — Tasks with
    # no guest origin (negative-review follow-ups, onboarding Tasks)
    # were never part of an ActionEvent chain to begin with and stay
    # outside the Ledger, same as today. `action_logger.log_action`
    # always INSERTs a new row; the ORDER_CONFIRMED/MEMORY_*/ESCALATED
    # events this Task descended from are never read or touched.
    if task.related_type == "guest" and task.related_id:
        action_logger.log_action(
            db,
            tenant_id=user.tenant_id,
            guest_id=task.related_id,
            correlation_id=task.correlation_id,
            intent="task_completion",
            agent=None,
            action_type="TASK_COMPLETED",
            actor=ActorType.staff,
            confidence=None,
            input_summary=f"Staff completed task: {task.title}",
            decision=f"Task {task.id} marked done by {user.email}.",
            status=ActionEventStatus.completed,
            metadata={"task_id": task.id, "completed_by": user.email},
        )

    db.commit()
    return {"ok": True}


@router.get("/pilot-health", response_model=PilotHealthOut)
def get_pilot_health(
    user: AuthUser,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    db: Session = Depends(get_db),
) -> PilotHealthOut:
    """PILOT_READINESS.md §4 — operational visibility for a hotel operator:
    inbound processing failures, translation failures, outbound delivery
    failures (active/exhausted), duplicate webhooks, and stale open Tasks
    over the trailing `hours` window (default 24, capped at a week).
    """
    return pilot_health(db, tenant_id=user.tenant_id, hours=hours)


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


def _csv_row_to_raw(row: dict[str, str | None]) -> dict[str, Any]:
    return {
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


def _validate_csv_row(
    row: dict[str, str | None], line_number: int
) -> tuple[ReservationCreate | None, list[CsvRowIssue], list[CsvRowIssue]]:
    """Validate one CSV row without raising.

    Returns (payload, warnings, errors). payload is None when the row has
    errors and cannot be imported — the caller decides whether to skip it
    or block the whole file, rather than this function deciding for them.
    """
    raw = _csv_row_to_raw(row)
    warnings: list[CsvRowIssue] = []
    if not raw["guest_email"]:
        warnings.append(
            CsvRowIssue(
                line_number=line_number,
                field="email",
                message="No email — this guest can't be matched on repeat visits",
            )
        )
    if not raw["guest_phone"]:
        warnings.append(
            CsvRowIssue(line_number=line_number, field="phone", message="No phone number")
        )
    try:
        payload = ReservationCreate.model_validate(raw)
    except ValidationError as exc:
        errors = [
            CsvRowIssue(
                line_number=line_number,
                field=str(err["loc"][-1]) if err.get("loc") else None,
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return None, warnings, errors
    return payload, warnings, []


def _validate_csv_rows(
    raw_rows: list[dict[str, str | None]],
) -> tuple[list[tuple[int, ReservationCreate]], list[CsvRowIssue], list[CsvRowIssue]]:
    """Validate every row in a parsed CSV. Returns (valid rows with their
    line numbers, all warnings, all errors) — never raises. Also flags
    emails that repeat across multiple rows in the same file.
    """
    valid: list[tuple[int, ReservationCreate]] = []
    warnings: list[CsvRowIssue] = []
    errors: list[CsvRowIssue] = []
    email_lines: dict[str, list[int]] = {}
    for line_number, row in enumerate(raw_rows, start=2):
        payload, row_warnings, row_errors = _validate_csv_row(row, line_number)
        warnings.extend(row_warnings)
        errors.extend(row_errors)
        if payload is not None:
            valid.append((line_number, payload))
            if payload.guest_email:
                email_lines.setdefault(str(payload.guest_email).lower(), []).append(
                    line_number
                )
    for email, lines in email_lines.items():
        if len(lines) > 1:
            warnings.append(
                CsvRowIssue(
                    line_number=lines[0],
                    field="email",
                    message=(
                        f"{email} appears on {len(lines)} rows (lines "
                        f"{', '.join(map(str, lines))}) — will be treated as one "
                        "returning guest"
                    ),
                )
            )
    return valid, warnings, errors


async def _read_csv_rows(file: UploadFile) -> list[dict[str, str | None]]:
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
    return raw_rows


@router.post("/connectors/import-csv/validate", response_model=CsvValidationReport)
async def validate_csv(
    user: ManagerUser,
    file: UploadFile = File(...),
) -> CsvValidationReport:
    """Read-only: validates every row, writes nothing to the database.
    Powers the Import flow's Validate step so hotels see problems before
    anything is imported, instead of finding out mid-import.
    """
    raw_rows = await _read_csv_rows(file)
    valid, warnings, errors = _validate_csv_rows(raw_rows)
    return CsvValidationReport(
        total_rows=len(raw_rows),
        valid_count=len(valid),
        warning_count=len({w.line_number for w in warnings}),
        error_count=len({e.line_number for e in errors}),
        warnings=warnings,
        errors=errors,
    )


@router.post("/connectors/import-csv", response_model=SyncResult)
async def import_csv(
    user: ManagerUser,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> SyncResult:
    raw_rows = await _read_csv_rows(file)
    valid, warnings, errors = _validate_csv_rows(raw_rows)
    property_ = _property_for_tenant(db, user.tenant_id)
    session = start_import_session(
        db,
        tenant_id=user.tenant_id,
        source="csv",
        initiated_by=user.email,
        rows_total=len(raw_rows),
        filename=file.filename,
    )
    for _line_number, payload in valid:
        import_reservation(
            db,
            tenant_id=user.tenant_id,
            property_id=property_.id,
            payload=payload,
            external_id=f"CSV-{uuid.uuid4()}",
            event_source="csv",
            import_session=session,
        )
    error_lines = sorted({issue.line_number for issue in errors})
    session.rows_skipped = len(error_lines)
    if error_lines:
        session.error_summary = (
            f"Skipped {len(error_lines)} row(s) with validation errors: "
            f"lines {', '.join(map(str, error_lines))}"
        )
    if warnings or errors:
        session.validation_issues = json.dumps(
            {
                "warnings": [w.model_dump() for w in warnings],
                "errors": [e.model_dump() for e in errors],
            }
        )
    finish_import_session(db, session)
    imported = session.rows_imported
    emitted = imported
    db.commit()
    return SyncResult(
        imported=imported,
        events_emitted=emitted,
        import_session_id=session.id,
        rows_skipped=session.rows_skipped,
        message=(
            f"Imported {imported} rows from CSV"
            + (
                f", skipped {session.rows_skipped} with errors"
                if session.rows_skipped
                else ""
            )
        ),
    )


@router.post("/connectors/import-pdf/extract", response_model=PdfValidationReport)
async def extract_pdf(
    user: ManagerUser,
    file: UploadFile = File(...),
) -> PdfValidationReport:
    """Read-only: extracts + parses a PDF and returns Ready to Import /
    Needs Review rows for a human to approve or edit. Writes nothing to
    the database and creates no ImportSession — same "preview before
    anything happens" contract as /connectors/import-csv/validate, except
    PDF's preview *is* the review step (PDF_IMPORT.md §7), not a
    precursor to an automatic import.

    The uploaded file is never written to disk and is discarded once this
    request returns — only the extracted, validated data is kept
    (PDF_IMPORT.md §11.3).
    """
    content = await file.read(settings.pdf_max_bytes + 1)
    if len(content) > settings.pdf_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF exceeds {settings.pdf_max_bytes} bytes",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    # Magic-byte check, not a Content-Type check: the header a browser/
    # client sends is trivially spoofable (or absent) and proves nothing;
    # every real PDF starts with the literal bytes "%PDF-" regardless of
    # what the client claims. Fail fast on obviously-wrong files instead
    # of handing them to pdfplumber first.
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This file does not appear to be a PDF",
        )
    try:
        report = pdf_importer.validate(content, filename=file.filename or "upload.pdf")
    except (PdfPasswordProtectedError, PdfUnreadableError, PdfTooManyPagesError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if report.total_reservations > settings.pdf_max_reservations_per_file:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"PDF contains {report.total_reservations} reservations — "
                f"exceeds the {settings.pdf_max_reservations_per_file}-per-file limit"
            ),
        )
    return report


@router.post("/connectors/import-pdf/confirm", response_model=PdfImportResult)
def confirm_pdf_import(
    body: PdfImportRequest,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> PdfImportResult:
    """The one write endpoint in the PDF flow. Only reached after a human
    has approved (and optionally edited) every row on the Review screen —
    PDF never auto-imports, regardless of extraction confidence
    (PDF_IMPORT.md §7). `confirmation_number` is optional per row: when
    absent, identity falls back to a hash of the reservation's own fields
    rather than blocking the import (PDF_IMPORT.md §11.1).
    """
    property_ = _property_for_tenant(db, user.tenant_id)
    session = start_import_session(
        db,
        tenant_id=user.tenant_id,
        source="pdf",
        initiated_by=user.email,
        rows_total=len(body.rows),
        filename=body.filename,
    )
    result = pdf_importer.import_(
        body.rows,
        session,
        db=db,
        tenant_id=user.tenant_id,
        property_id=property_.id,
    )
    duplicates = result["duplicate_confirmation_numbers"]
    if duplicates:
        session.error_summary = (
            f"Skipped {len(duplicates)} already-imported reservation(s): "
            f"{', '.join(duplicates)}"
        )
    finish_import_session(db, session)
    imported_count = session.rows_imported
    db.commit()
    return PdfImportResult(
        import_session_id=session.id,
        imported=imported_count,
        duplicates_skipped=len(duplicates),
        message=(
            f"Imported {imported_count} reservation(s) from PDF"
            + (f", skipped {len(duplicates)} already imported" if duplicates else "")
        ),
    )


@router.post("/connectors/import-menu/extract", response_model=MenuValidationReport)
async def extract_menu(
    user: ManagerUser,
    file: UploadFile = File(...),
) -> MenuValidationReport:
    """Read-only: extracts + parses a menu PDF and returns Ready to
    Import / Needs Review rows for a human to approve or edit. Writes
    nothing to the database and creates no ImportSession — same
    "preview before anything happens" contract as PDF reservation
    import. PDF only for v1 (MENU_ORDERING.md, frozen decision) — Excel/
    CSV follows only if a pilot hotel actually needs it.
    """
    content = await file.read(settings.pdf_max_bytes + 1)
    if len(content) > settings.pdf_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF exceeds {settings.pdf_max_bytes} bytes",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This file does not appear to be a PDF",
        )
    try:
        report = menu_importer.validate(content, filename=file.filename or "menu.pdf")
    except (PdfPasswordProtectedError, PdfUnreadableError, PdfTooManyPagesError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if report.total_items > settings.menu_max_items_per_file:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"PDF contains {report.total_items} items — exceeds the "
                f"{settings.menu_max_items_per_file}-per-file limit"
            ),
        )
    return report


@router.post("/connectors/import-menu/confirm", response_model=MenuImportResult)
def confirm_menu_import(
    body: MenuImportRequest,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> MenuImportResult:
    """The one write endpoint in the menu flow. Only reached after a
    human has approved (and optionally edited) every row on the Review
    screen — a menu item never auto-publishes, regardless of extraction
    confidence (MENU_ORDERING.md's own guardrail, restated here).
    """
    property_ = _property_for_tenant(db, user.tenant_id)
    session = start_import_session(
        db,
        tenant_id=user.tenant_id,
        source="menu",
        initiated_by=user.email,
        rows_total=len(body.rows),
        filename=body.filename,
    )
    menu_importer.import_(
        body.rows,
        session,
        db=db,
        tenant_id=user.tenant_id,
        property_id=property_.id,
    )
    finish_import_session(db, session)
    imported_count = session.rows_imported
    db.commit()
    return MenuImportResult(
        import_session_id=session.id,
        imported=imported_count,
        message=f"Published {imported_count} menu item(s)",
    )


@router.get("/menu-items", response_model=list[MenuItemOut])
def list_menu_items(
    user: AuthUser,
    menu_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[MenuItem]:
    query = db.query(MenuItem).filter(MenuItem.tenant_id == user.tenant_id)
    if menu_name:
        query = query.filter(MenuItem.menu_name == menu_name)
    return query.order_by(MenuItem.menu_name, MenuItem.category, MenuItem.name).all()


@router.patch("/menu-items/{item_id}", response_model=MenuItemOut)
def update_menu_item(
    item_id: str,
    payload: MenuItemUpdate,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> MenuItem:
    """Staff edit price/availability/description/category/dietary tags
    after upload (MENU_ORDERING.md §3.3) — the same tenant-scoped PATCH
    shape `update_property_knowledge_base` already established. Audited
    via the existing AuditLog mechanism, not a new subsystem: this,
    together with `source_import_id`, is what later answers "which
    upload produced this item, and was it subsequently edited by staff"
    without a dedicated menu-versioning table.
    """
    item = get_tenant_entity(db, MenuItem, item_id, user.tenant_id, not_found="Menu item not found")

    changed_fields = payload.model_dump(exclude_unset=True)
    for field, value in changed_fields.items():
        setattr(item, field, value)
    db.flush()

    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="update_menu_item",
        entity_type="menu_item",
        entity_id=item.id,
        details={"changed_fields": sorted(changed_fields)},
    )
    db.commit()
    db.refresh(item)
    return item


@router.get("/import-sessions", response_model=list[ImportSessionListItem])
def list_import_sessions(
    user: AuthUser,
    source: str | None = Query(default=None),
    session_status: str | None = Query(default=None, alias="status"),
    skip: PageSkip = 0,
    limit: PageLimit = 100,
    db: Session = Depends(get_db),
) -> list[ImportSession]:
    query = db.query(ImportSession).filter(ImportSession.tenant_id == user.tenant_id)
    if source:
        query = query.filter(ImportSession.source == source)
    if session_status:
        try:
            normalized_status = ImportSessionStatus(session_status)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid import session status",
            ) from exc
        query = query.filter(ImportSession.status == normalized_status)
    return (
        query.order_by(ImportSession.started_at.desc()).offset(skip).limit(limit).all()
    )


@router.get("/import-sessions/{session_id}", response_model=ImportSessionDetail)
def get_import_session(
    session_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> ImportSessionDetail:
    session = get_tenant_entity(
        db, ImportSession, session_id, user.tenant_id, not_found="Import session not found"
    )
    duration_ms: int | None = None
    if session.completed_at:
        duration_ms = int(
            (session.completed_at - session.started_at).total_seconds() * 1000
        )
    warnings: list[CsvRowIssue] = []
    errors: list[CsvRowIssue] = []
    if session.validation_issues:
        try:
            parsed = json.loads(session.validation_issues)
            warnings = [CsvRowIssue.model_validate(w) for w in parsed.get("warnings", [])]
            errors = [CsvRowIssue.model_validate(e) for e in parsed.get("errors", [])]
        except (json.JSONDecodeError, TypeError):
            pass
    return ImportSessionDetail(
        id=session.id,
        source=session.source,
        status=session.status.value,
        filename=session.filename,
        initiated_by=session.initiated_by,
        started_at=session.started_at,
        completed_at=session.completed_at,
        rows_total=session.rows_total,
        rows_imported=session.rows_imported,
        rows_skipped=session.rows_skipped,
        rows_failed=session.rows_failed,
        duration_ms=duration_ms,
        error_summary=session.error_summary,
        warnings=warnings,
        errors=errors,
    )


@router.get("/import-sessions/{session_id}/summary", response_model=ImportSummaryOut)
def get_import_summary(
    session_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> ImportSummaryOut:
    session = get_tenant_entity(
        db, ImportSession, session_id, user.tenant_id, not_found="Import session not found"
    )
    summary = build_import_summary(db, session)
    return ImportSummaryOut(
        import_session_id=session.id,
        source=session.source,
        status=session.status.value,
        **summary,
    )


@router.post("/import-sources/{source}/early-access")
def request_early_access(
    source: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Records interest in a not-yet-built import source (PDF, email, PMS
    connectors) so demand can be measured later via the audit log — no new
    table, reuses the existing AuditLog exactly like every other action.
    """
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="early_access_request",
        entity_type="import_source",
        entity_id=source,
        details={"source": source},
    )
    db.commit()
    return {"ok": True}


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
