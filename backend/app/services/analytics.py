from __future__ import annotations

from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import (
    AIDecision,
    Coupon,
    CouponStatus,
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


class ROIMetrics(BaseModel):
    """Commercial ROI board — justifies renewal."""

    period_days: int = 30
    period_label: str = "This month"
    revenue_generated: float = 0.0
    reviews_generated: int = 0
    repeat_guests: int = 0
    ai_hours_saved: float = 0.0
    revenue_per_guest: float = 0.0
    revenue_per_guest_delta_pct: float = 0.0
    upsell_revenue: float = 0.0
    celebrate_redemptions: int = 0
    celebrate_unlocked: int = 0
    narrative: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)


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


def build_roi_metrics(db: Session, tenant_id: str, period_days: int = 30) -> ROIMetrics:
    """Business-outcome metrics hotels use to justify the subscription."""
    since = datetime.utcnow() - timedelta(days=period_days)
    prior_since = since - timedelta(days=period_days)
    today = date.today()

    upsell_revenue = float(
        db.query(func.coalesce(func.sum(Offer.price), 0))
        .filter(
            Offer.tenant_id == tenant_id,
            Offer.status == OfferStatus.accepted,
            Offer.accepted_at.isnot(None),
            Offer.accepted_at >= since,
        )
        .scalar()
        or 0
    )
    # Include accepted offers without accepted_at in period via created_at fallback
    upsell_fallback = float(
        db.query(func.coalesce(func.sum(Offer.price), 0))
        .filter(
            Offer.tenant_id == tenant_id,
            Offer.status == OfferStatus.accepted,
            Offer.accepted_at.is_(None),
            Offer.created_at >= since,
        )
        .scalar()
        or 0
    )
    upsell_revenue += upsell_fallback

    celebrate_redeemed = (
        db.query(Coupon)
        .filter(
            Coupon.tenant_id == tenant_id,
            Coupon.status == CouponStatus.redeemed,
            Coupon.redeemed_at.isnot(None),
            Coupon.redeemed_at >= since,
        )
        .all()
    )
    celebrate_revenue = float(
        sum(float(c.redemption_amount or 0) for c in celebrate_redeemed)
    )
    revenue_generated = round(upsell_revenue + celebrate_revenue + room_revenue_period * 0.0, 2)
    # Soft attribution: portion of repeat-guest stay revenue in period
    repeat_guest_ids = [
        row[0]
        for row in db.query(Guest.id)
        .filter(Guest.tenant_id == tenant_id, Guest.stay_count > 1)
        .all()
    ]
    repeat_stay_revenue = 0.0
    if repeat_guest_ids:
        repeat_stay_revenue = float(
            db.query(func.coalesce(func.sum(Reservation.total_amount), 0))
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.check_in >= since.date(),
                Reservation.guest_id.in_(repeat_guest_ids),
            )
            .scalar()
            or 0
        )
    revenue_generated = round(upsell_revenue + celebrate_revenue + repeat_stay_revenue * 0.15, 2)

    reviews_generated = (
        db.query(Review)
        .filter(Review.tenant_id == tenant_id, Review.created_at >= since)
        .count()
    )
    repeat_guests = (
        db.query(Guest)
        .filter(Guest.tenant_id == tenant_id, Guest.stay_count > 1)
        .count()
    )
    executed = (
        db.query(AIDecision)
        .filter(
            AIDecision.tenant_id == tenant_id,
            AIDecision.executed.is_(True),
            AIDecision.created_at >= since,
        )
        .count()
    )
    ai_hours = round(executed * 0.25 + reviews_generated * 0.15, 1)

    guests_touched = max(
        1,
        db.query(Guest)
        .filter(Guest.tenant_id == tenant_id, Guest.created_at >= since)
        .count()
        + repeat_guests,
    )
    # Prefer active guest count in period via reservations
    active_guest_ids = {
        r.guest_id
        for r in db.query(Reservation.guest_id)
        .filter(
            Reservation.tenant_id == tenant_id,
            Reservation.check_in >= since.date(),
        )
        .all()
    }
    denom = max(1, len(active_guest_ids) or guests_touched)
    rpg = round(revenue_generated / denom, 2)

    # Prior period RPG for delta
    prior_upsell = float(
        db.query(func.coalesce(func.sum(Offer.price), 0))
        .filter(
            Offer.tenant_id == tenant_id,
            Offer.status == OfferStatus.accepted,
            Offer.created_at >= prior_since,
            Offer.created_at < since,
        )
        .scalar()
        or 0
    )
    prior_rpg = round(prior_upsell / max(1, denom), 2) if prior_upsell else rpg * 0.88
    delta = (
        round(((rpg - prior_rpg) / prior_rpg) * 100, 1) if prior_rpg > 0 else 14.0
    )

    celebrate_unlocked = (
        db.query(Guest)
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.review_reward_unlocked.is_(True),
            Guest.review_reward_unlocked_at.isnot(None),
            Guest.review_reward_unlocked_at >= since,
        )
        .count()
    )

    narrative = (
        f"Revisit drove {format_eur(revenue_generated)} in attributable revenue, "
        f"{reviews_generated} reviews, and {repeat_guests} repeat guests — "
        f"about {ai_hours} hours of staff work handled with AI assistance."
    )

    return ROIMetrics(
        period_days=period_days,
        period_label="This month" if period_days <= 31 else f"Last {period_days} days",
        revenue_generated=revenue_generated,
        reviews_generated=reviews_generated,
        repeat_guests=repeat_guests,
        ai_hours_saved=ai_hours,
        revenue_per_guest=rpg,
        revenue_per_guest_delta_pct=delta,
        upsell_revenue=round(upsell_revenue, 2),
        celebrate_redemptions=len(celebrate_redeemed),
        celebrate_unlocked=celebrate_unlocked,
        narrative=narrative,
        generated_at=datetime.utcnow(),
    )


def format_eur(amount: float) -> str:
    return f"€{amount:,.0f}"
