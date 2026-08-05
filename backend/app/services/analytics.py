from __future__ import annotations

from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import (
    AIDecision,
    Guest,
    Message,
    MessageStatus,
    Offer,
    OfferStatus,
    Reservation,
    Review,
)


class SalesAnalytics(BaseModel):
    """Sales-demo analytics for V1."""

    review_rate: float
    repeat_guests: int
    repeat_guest_rate: float
    revenue_generated: float
    upsell_revenue: float
    room_revenue_active: float
    ai_messages: int
    ai_messages_sent: int
    upsell_conversion: float
    guest_satisfaction: float
    google_rating_proxy: float
    celebrations_enrolled: int
    period_days: int
    generated_at: datetime


def build_sales_analytics(db: Session, tenant_id: str, period_days: int = 30) -> SalesAnalytics:
    since = datetime.utcnow() - timedelta(days=period_days)
    total_guests = db.query(Guest).filter(Guest.tenant_id == tenant_id).count()
    reviewed = (
        db.query(Guest)
        .filter(Guest.tenant_id == tenant_id, Guest.previous_reviews > 0)
        .count()
    )
    repeat = (
        db.query(Guest).filter(Guest.tenant_id == tenant_id, Guest.stay_count > 1).count()
    )
    offered = (
        db.query(Offer).filter(Offer.tenant_id == tenant_id).count()
    )
    accepted = (
        db.query(Offer)
        .filter(
            Offer.tenant_id == tenant_id,
            Offer.status.in_([OfferStatus.accepted]),
        )
        .count()
    )
    upsell_revenue = float(
        db.query(func.coalesce(func.sum(Offer.price), 0))
        .filter(Offer.tenant_id == tenant_id, Offer.status == OfferStatus.accepted)
        .scalar()
        or 0
    )
    today = date.today()
    room_revenue = float(
        db.query(func.coalesce(func.sum(Reservation.total_amount), 0))
        .filter(
            Reservation.tenant_id == tenant_id,
            Reservation.check_in <= today,
            Reservation.check_out >= today,
        )
        .scalar()
        or 0
    )
    ai_messages = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.direction == "outbound",
            Message.created_at >= since,
        )
        .count()
    )
    ai_sent = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.status.in_([MessageStatus.sent, MessageStatus.delivered]),
            Message.created_at >= since,
        )
        .count()
    )
    sat = float(
        db.query(func.coalesce(func.avg(Guest.satisfaction_score), 0))
        .filter(Guest.tenant_id == tenant_id)
        .scalar()
        or 0
    )
    # Proxy google rating from review avg if present
    avg_rating = (
        db.query(func.avg(Review.rating)).filter(Review.tenant_id == tenant_id).scalar()
    )
    google_proxy = float(avg_rating) if avg_rating is not None else 4.5
    enrolled = (
        db.query(Guest)
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.review_reward_unlocked.is_(True),
            Guest.birthday_locked.is_(True),
        )
        .count()
    )
    decisions = (
        db.query(AIDecision)
        .filter(AIDecision.tenant_id == tenant_id, AIDecision.created_at >= since)
        .count()
    )

    return SalesAnalytics(
        review_rate=round((reviewed / total_guests * 100) if total_guests else 0, 1),
        repeat_guests=repeat,
        repeat_guest_rate=round((repeat / total_guests * 100) if total_guests else 0, 1),
        revenue_generated=round(upsell_revenue, 2),
        upsell_revenue=round(upsell_revenue, 2),
        room_revenue_active=round(room_revenue, 2),
        ai_messages=ai_messages + decisions,
        ai_messages_sent=ai_sent,
        upsell_conversion=round((accepted / offered * 100) if offered else 0, 1),
        guest_satisfaction=round(sat, 1),
        google_rating_proxy=round(google_proxy, 2),
        celebrations_enrolled=enrolled,
        period_days=period_days,
        generated_at=datetime.utcnow(),
    )
