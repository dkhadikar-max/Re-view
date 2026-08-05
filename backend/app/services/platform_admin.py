"""Platform owner admin — client signups and cross-tenant analytics."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import (
    Guest,
    Offer,
    OfferStatus,
    Property,
    Reservation,
    Tenant,
    User,
)
from app.services.currency import currency_for_country


class ClientOut(BaseModel):
    tenant_id: str
    hotel_name: str
    plan: str
    is_active: bool
    signed_up_at: datetime
    manager_name: Optional[str] = None
    manager_email: Optional[EmailStr] = None
    manager_role: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    currency: str = "EUR"
    rooms: int = 0
    guest_count: int = 0
    reservation_count: int = 0
    upsell_revenue: float = 0.0
    is_demo: bool = False


class CountryBreakdown(BaseModel):
    country: str
    hotels: int
    currency: str


class PlanBreakdown(BaseModel):
    plan: str
    hotels: int


class RecentSignup(BaseModel):
    tenant_id: str
    hotel_name: str
    manager_email: Optional[str] = None
    country: Optional[str] = None
    currency: str = "EUR"
    signed_up_at: datetime


class PlatformAnalytics(BaseModel):
    total_hotels: int
    trial_hotels: int
    active_hotels: int
    paying_hotels: int
    total_managers: int
    signups_last_7_days: int
    signups_last_30_days: int
    total_guests: int
    total_reservations: int
    total_upsell_revenue: float
    by_plan: list[PlanBreakdown]
    by_country: list[CountryBreakdown]
    recent_signups: list[RecentSignup]
    generated_at: datetime = Field(default_factory=datetime.utcnow)


def _manager_for_tenant(db: Session, tenant_id: str) -> User | None:
    users = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .all()
    )
    if not users:
        return None
    for preferred in ("admin", "manager", "staff", "viewer"):
        hit = next((u for u in users if u.role == preferred), None)
        if hit:
            return hit
    return users[0]


def list_clients(db: Session) -> list[ClientOut]:
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    out: list[ClientOut] = []
    for tenant in tenants:
        prop = db.query(Property).filter(Property.tenant_id == tenant.id).first()
        manager = _manager_for_tenant(db, tenant.id)
        guests = db.query(Guest).filter(Guest.tenant_id == tenant.id).count()
        reservations = (
            db.query(Reservation).filter(Reservation.tenant_id == tenant.id).count()
        )
        upsell = float(
            db.query(func.coalesce(func.sum(Offer.price), 0))
            .filter(
                Offer.tenant_id == tenant.id,
                Offer.status == OfferStatus.accepted,
            )
            .scalar()
            or 0
        )
        currency = (
            (getattr(prop, "currency", None) or "").upper()
            if prop
            else ""
        ) or currency_for_country(prop.country if prop else None)
        out.append(
            ClientOut(
                tenant_id=tenant.id,
                hotel_name=tenant.name,
                plan=tenant.plan,
                is_active=tenant.is_active,
                signed_up_at=tenant.created_at,
                manager_name=manager.name if manager else None,
                manager_email=manager.email if manager else None,
                manager_role=manager.role if manager else None,
                city=prop.city if prop else None,
                country=prop.country if prop else None,
                currency=currency,
                rooms=prop.rooms if prop else 0,
                guest_count=guests,
                reservation_count=reservations,
                upsell_revenue=round(upsell, 2),
                is_demo=tenant.id == "demo-hotel",
            )
        )
    return out


def platform_analytics(db: Session) -> PlatformAnalytics:
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    tenants = db.query(Tenant).all()
    total = len(tenants)
    trial = sum(1 for t in tenants if t.plan == "trial")
    active = sum(1 for t in tenants if t.is_active)
    paying = sum(1 for t in tenants if t.plan in {"starter", "growth", "founding"} and t.id != "demo-hotel")
    managers = (
        db.query(User)
        .filter(User.is_active.is_(True), User.role.in_(["manager", "admin"]))
        .count()
    )
    signups_7 = sum(1 for t in tenants if t.created_at and t.created_at >= week_ago)
    signups_30 = sum(1 for t in tenants if t.created_at and t.created_at >= month_ago)

    plan_counts: dict[str, int] = {}
    for t in tenants:
        plan_counts[t.plan] = plan_counts.get(t.plan, 0) + 1
    by_plan = [
        PlanBreakdown(plan=p, hotels=c)
        for p, c in sorted(plan_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    country_rows = (
        db.query(Property.country, func.count(Property.id))
        .group_by(Property.country)
        .all()
    )
    by_country = [
        CountryBreakdown(
            country=row[0] or "Unknown",
            hotels=row[1],
            currency=currency_for_country(row[0]),
        )
        for row in sorted(country_rows, key=lambda r: (-r[1], r[0] or ""))
    ]

    clients = list_clients(db)
    recent = [
        RecentSignup(
            tenant_id=c.tenant_id,
            hotel_name=c.hotel_name,
            manager_email=str(c.manager_email) if c.manager_email else None,
            country=c.country,
            currency=c.currency,
            signed_up_at=c.signed_up_at,
        )
        for c in clients
        if not c.is_demo
    ][:12]

    return PlatformAnalytics(
        total_hotels=total,
        trial_hotels=trial,
        active_hotels=active,
        paying_hotels=paying,
        total_managers=managers,
        signups_last_7_days=signups_7,
        signups_last_30_days=signups_30,
        total_guests=db.query(Guest).count(),
        total_reservations=db.query(Reservation).count(),
        total_upsell_revenue=round(
            float(
                db.query(func.coalesce(func.sum(Offer.price), 0))
                .filter(Offer.status == OfferStatus.accepted)
                .scalar()
                or 0
            ),
            2,
        ),
        by_plan=by_plan,
        by_country=by_country,
        recent_signups=recent,
        generated_at=now,
    )
