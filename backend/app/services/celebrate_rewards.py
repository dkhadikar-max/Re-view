from __future__ import annotations

import logging
import secrets
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    CelebrateDateAudit,
    CelebrateOfferType,
    CelebrateRewardConfig,
    Coupon,
    CouponStatus,
    Guest,
    Message,
    MessageChannel,
    MessageStatus,
    Property,
    Review,
)
from app.services.audit import write_audit

logger = logging.getLogger(__name__)


class CelebrateConfigIn(BaseModel):
    birthday_enabled: bool = True
    birthday_discount_pct: float = Field(default=20.0, ge=0, le=100)
    birthday_days_before: int = Field(default=7, ge=0, le=30)
    birthday_days_after: int = Field(default=7, ge=0, le=30)
    birthday_min_spend: float = Field(default=1000, ge=0)
    birthday_max_uses_per_year: int = Field(default=1, ge=1, le=5)
    birthday_stackable: bool = False
    anniversary_enabled: bool = True
    anniversary_discount_pct: float = Field(default=15.0, ge=0, le=100)
    anniversary_days_before: int = Field(default=3, ge=0, le=30)
    anniversary_days_after: int = Field(default=3, ge=0, le=30)
    anniversary_min_spend: float = Field(default=2000, ge=0)
    anniversary_max_uses_per_year: int = Field(default=1, ge=1, le=5)
    anniversary_stackable: bool = False
    currency: str = Field(default="INR", min_length=3, max_length=3)


class CelebrateDatesIn(BaseModel):
    birthday: date
    anniversary: Optional[date] = None
    confirm: bool = False

    @model_validator(mode="after")
    def validate_dates(self) -> "CelebrateDatesIn":
        if not self.confirm:
            raise ValueError("You must confirm these dates are correct and cannot be changed later")
        today = date.today()
        if self.birthday > today:
            raise ValueError("Birthday cannot be in the future")
        if self.anniversary and self.anniversary > today:
            raise ValueError("Anniversary cannot be in the future")
        # Reasonable bounds
        if self.birthday.year < 1920:
            raise ValueError("Birthday year is invalid")
        return self


class AdminUnlockIn(BaseModel):
    field: str = Field(pattern="^(birthday|anniversary|both)$")
    reason: str = Field(min_length=10, max_length=1000)


def get_or_create_config(db: Session, tenant_id: str) -> CelebrateRewardConfig:
    config = (
        db.query(CelebrateRewardConfig)
        .filter(CelebrateRewardConfig.tenant_id == tenant_id)
        .first()
    )
    if config:
        return config
    config = CelebrateRewardConfig(tenant_id=tenant_id)
    db.add(config)
    db.flush()
    return config


def update_config(
    db: Session, tenant_id: str, payload: CelebrateConfigIn, actor_email: str
) -> CelebrateRewardConfig:
    config = get_or_create_config(db, tenant_id)
    for key, value in payload.model_dump().items():
        setattr(config, key, value if key != "currency" else value.upper())
    config.updated_at = datetime.utcnow()
    write_audit(
        db,
        tenant_id=tenant_id,
        actor=actor_email,
        action="update_celebrate_config",
        entity_type="celebrate_reward_config",
        entity_id=config.id,
        details=payload.model_dump(),
    )
    db.flush()
    return config


def create_guest_celebrate_token(guest: Guest, expires_hours: int = 72) -> str:
    now = datetime.utcnow()
    expire = now + timedelta(hours=expires_hours)
    payload = {
        "sub": guest.id,
        "tenant_id": guest.tenant_id,
        "scope": "celebrate_rewards",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_guest_celebrate_token(token: str) -> dict[str, Any]:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired celebrate link",
        ) from exc
    if data.get("scope") != "celebrate_rewards":
        raise HTTPException(status_code=401, detail="Invalid celebrate token scope")
    return data


def unlock_after_review(
    db: Session, review: Review, guest: Guest, actor: str = "system"
) -> Guest:
    """Reward participation (leaving a review), not the star rating."""
    if guest.review_reward_unlocked:
        return guest
    guest.review_reward_unlocked = True
    guest.review_reward_unlocked_at = datetime.utcnow()
    guest.previous_reviews = (guest.previous_reviews or 0) + 1
    db.add(
        CelebrateDateAudit(
            tenant_id=guest.tenant_id,
            guest_id=guest.id,
            field_name="review_reward_unlocked",
            old_value="false",
            new_value="true",
            changed_by=actor,
            action="unlock_reward",
            reason=f"Review verified ({review.platform} {review.rating}★) — participation reward",
        )
    )
    write_audit(
        db,
        tenant_id=guest.tenant_id,
        actor=actor,
        action="celebrate_reward_unlocked",
        entity_type="guest",
        entity_id=guest.id,
        details={"review_id": review.id, "rating": review.rating},
    )
    db.flush()
    return guest


def _coupon_code(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def _occurrence_this_year(base: date, year: int) -> date:
    day = base.day
    month = base.month
    # Handle Feb 29
    last_day = monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _window(base: date, year: int, days_before: int, days_after: int) -> tuple[date, date]:
    occ = _occurrence_this_year(base, year)
    return occ - timedelta(days=days_before), occ + timedelta(days=days_after)


def suggest_personalized_perk(guest: Guest) -> Optional[str]:
    """Smart suggestion based on guest memory signals."""
    spend = float(guest.average_booking or guest.lifetime_spend or 0)
    stays = guest.stay_count or 0
    if stays >= 4 and spend >= 4000:
        return "Complimentary Wine"
    if guest.travel_type == "luxury" or spend >= 3000:
        return "Complimentary Dessert"
    if guest.children and guest.children > 0:
        return "Kids Dessert Free"
    return None


def generate_celebration_message(
    guest: Guest,
    property_: Property,
    offer_type: CelebrateOfferType,
    discount_pct: float,
    code: str,
    perk: Optional[str],
) -> str:
    first = guest.name.split()[0]
    if offer_type == CelebrateOfferType.birthday:
        body = (
            f"Happy Birthday {first}!\n\n"
            f"Celebrate with us at {property_.name}. "
            f"Enjoy {discount_pct:.0f}% off this week "
            f"(code {code})."
        )
        if perk:
            body += f" Plus: {perk}."
        body += "\n\nReserve your table — we'd love to see you."
        return body
    body = (
        f"Happy Anniversary!\n\n"
        f"We'd love to celebrate with you again at {property_.name}. "
        f"Here's {discount_pct:.0f}% off"
    )
    if perk:
        body += f" and {perk}"
    body += f" (code {code}).\n\n— {property_.name}"
    return body


def confirm_and_lock_dates(
    db: Session,
    guest: Guest,
    payload: CelebrateDatesIn,
    *,
    actor: str = "guest",
) -> dict[str, Any]:
    if not guest.review_reward_unlocked:
        raise HTTPException(
            status_code=403,
            detail="Celebrate Rewards unlock after a verified review",
        )
    if guest.birthday_locked or guest.anniversary_locked:
        raise HTTPException(
            status_code=409,
            detail="Dates are already locked and cannot be changed",
        )

    guest.birthday = payload.birthday
    guest.anniversary = payload.anniversary
    guest.birthday_locked = True
    guest.birthday_verified = True
    if payload.anniversary:
        guest.anniversary_locked = True
        guest.anniversary_verified = True
    guest.celebrate_dates_confirmed_at = datetime.utcnow()

    db.add(
        CelebrateDateAudit(
            tenant_id=guest.tenant_id,
            guest_id=guest.id,
            field_name="birthday",
            old_value=None,
            new_value=payload.birthday.isoformat(),
            changed_by=actor,
            action="lock",
            reason="Guest confirmed immutable celebration dates",
        )
    )
    if payload.anniversary:
        db.add(
            CelebrateDateAudit(
                tenant_id=guest.tenant_id,
                guest_id=guest.id,
                field_name="anniversary",
                old_value=None,
                new_value=payload.anniversary.isoformat(),
                changed_by=actor,
                action="lock",
                reason="Guest confirmed immutable celebration dates",
            )
        )

    coupons = ensure_upcoming_coupons(db, guest)
    db.flush()
    return {
        "guest_id": guest.id,
        "birthday_locked": guest.birthday_locked,
        "anniversary_locked": guest.anniversary_locked,
        "coupons_created": [c.code for c in coupons],
    }


def ensure_upcoming_coupons(db: Session, guest: Guest) -> list[Coupon]:
    config = get_or_create_config(db, guest.tenant_id)
    property_ = db.get(Property, guest.property_id)
    created: list[Coupon] = []
    year = date.today().year
    perk = suggest_personalized_perk(guest)

    specs = []
    if config.birthday_enabled and guest.birthday and guest.birthday_locked:
        specs.append(
            (
                CelebrateOfferType.birthday,
                guest.birthday,
                config.birthday_discount_pct,
                config.birthday_days_before,
                config.birthday_days_after,
                float(config.birthday_min_spend),
                config.birthday_stackable,
                config.birthday_max_uses_per_year,
                "BDAY",
            )
        )
    if config.anniversary_enabled and guest.anniversary and guest.anniversary_locked:
        specs.append(
            (
                CelebrateOfferType.anniversary,
                guest.anniversary,
                config.anniversary_discount_pct,
                config.anniversary_days_before,
                config.anniversary_days_after,
                float(config.anniversary_min_spend),
                config.anniversary_stackable,
                config.anniversary_max_uses_per_year,
                "ANNV",
            )
        )

    for (
        offer_type,
        base_date,
        pct,
        before,
        after,
        min_spend,
        stackable,
        max_uses,
        prefix,
    ) in specs:
        existing_count = (
            db.query(Coupon)
            .filter(
                Coupon.tenant_id == guest.tenant_id,
                Coupon.guest_id == guest.id,
                Coupon.offer_type == offer_type,
                Coupon.year == year,
                Coupon.status != CouponStatus.cancelled,
            )
            .count()
        )
        if existing_count >= max_uses:
            continue
        valid_from, valid_until = _window(base_date, year, before, after)
        # If window already passed this year, schedule next year
        if valid_until < date.today():
            year_use = year + 1
            existing_next = (
                db.query(Coupon)
                .filter(
                    Coupon.tenant_id == guest.tenant_id,
                    Coupon.guest_id == guest.id,
                    Coupon.offer_type == offer_type,
                    Coupon.year == year_use,
                    Coupon.status != CouponStatus.cancelled,
                )
                .count()
            )
            if existing_next >= max_uses:
                continue
            valid_from, valid_until = _window(base_date, year_use, before, after)
            year_use_final = year_use
        else:
            year_use_final = year

        code = _coupon_code(prefix)
        message = (
            generate_celebration_message(
                guest, property_, offer_type, pct, code, perk
            )
            if property_
            else None
        )
        coupon = Coupon(
            tenant_id=guest.tenant_id,
            guest_id=guest.id,
            offer_type=offer_type,
            code=code,
            discount_pct=pct,
            min_spend=min_spend,
            currency=config.currency,
            year=year_use_final,
            valid_from=valid_from,
            valid_until=valid_until,
            status=CouponStatus.active,
            stackable=stackable,
            personalized_perk=perk,
            message_body=message,
        )
        db.add(coupon)
        created.append(coupon)
    db.flush()
    return created


def admin_unlock_dates(
    db: Session,
    guest: Guest,
    payload: AdminUnlockIn,
    *,
    actor_email: str,
    actor_user_id: str,
) -> Guest:
    fields = (
        ["birthday", "anniversary"]
        if payload.field == "both"
        else [payload.field]
    )
    for field in fields:
        locked_attr = f"{field}_locked"
        verified_attr = f"{field}_verified"
        old_locked = getattr(guest, locked_attr)
        old_value = getattr(guest, field)
        setattr(guest, locked_attr, False)
        setattr(guest, verified_attr, False)
        db.add(
            CelebrateDateAudit(
                tenant_id=guest.tenant_id,
                guest_id=guest.id,
                field_name=field,
                old_value=str(old_value) if old_value else None,
                new_value="UNLOCKED",
                changed_by=actor_email,
                changed_by_user_id=actor_user_id,
                reason=payload.reason,
                action="unlock",
            )
        )
        write_audit(
            db,
            tenant_id=guest.tenant_id,
            actor=actor_email,
            action="celebrate_date_unlock",
            entity_type="guest",
            entity_id=guest.id,
            details={
                "field": field,
                "was_locked": old_locked,
                "reason": payload.reason,
            },
        )
    db.flush()
    return guest


def redeem_coupon(
    db: Session,
    coupon: Coupon,
    *,
    amount: float,
    actor: str,
) -> Coupon:
    if coupon.status != CouponStatus.active:
        raise HTTPException(status_code=409, detail=f"Coupon is {coupon.status.value}")
    today = date.today()
    if today < coupon.valid_from or today > coupon.valid_until:
        coupon.status = CouponStatus.expired
        db.flush()
        raise HTTPException(status_code=409, detail="Coupon is outside its validity window")
    if amount < float(coupon.min_spend):
        raise HTTPException(
            status_code=422,
            detail=f"Minimum spend is {coupon.min_spend} {coupon.currency}",
        )
    # One redemption per calendar year already enforced at generation; mark redeemed
    coupon.status = CouponStatus.redeemed
    coupon.redeemed_at = datetime.utcnow()
    coupon.redemption_amount = amount
    write_audit(
        db,
        tenant_id=coupon.tenant_id,
        actor=actor,
        action="coupon_redeemed",
        entity_type="coupon",
        entity_id=coupon.id,
        details={"amount": amount, "code": coupon.code},
    )
    db.flush()
    return coupon


def run_celebrate_campaigns(db: Session, tenant_id: str) -> dict[str, int]:
    """Nightly-style job: find upcoming birthdays/anniversaries and queue messages."""
    config = get_or_create_config(db, tenant_id)
    today = date.today()
    queued = 0
    coupons_made = 0

    guests = (
        db.query(Guest)
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.review_reward_unlocked.is_(True),
            or_(Guest.birthday_locked.is_(True), Guest.anniversary_locked.is_(True)),
        )
        .all()
    )
    for guest in guests:
        new_coupons = ensure_upcoming_coupons(db, guest)
        coupons_made += len(new_coupons)
        property_ = db.get(Property, guest.property_id)
        if not property_:
            continue
        active = (
            db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.guest_id == guest.id,
                Coupon.status == CouponStatus.active,
                Coupon.valid_from <= today + timedelta(days=7),
                Coupon.valid_until >= today,
            )
            .all()
        )
        for coupon in active:
            # Only queue once when inside send window (7 days before valid_from or during)
            send_from = coupon.valid_from - timedelta(days=1)
            if not (send_from <= today <= coupon.valid_until):
                continue
            already = (
                db.query(Message)
                .filter(
                    Message.tenant_id == tenant_id,
                    Message.guest_id == guest.id,
                    Message.message_type == f"celebrate_{coupon.offer_type.value}",
                    Message.subject.contains(coupon.code),
                )
                .first()
            )
            if already:
                continue
            channel = MessageChannel(
                guest.communication_preference
                if guest.communication_preference in {"whatsapp", "email", "sms"}
                else "email"
            )
            body = coupon.message_body or generate_celebration_message(
                guest,
                property_,
                coupon.offer_type,
                coupon.discount_pct,
                coupon.code,
                coupon.personalized_perk,
            )
            db.add(
                Message(
                    tenant_id=tenant_id,
                    guest_id=guest.id,
                    channel=channel,
                    language=guest.language or "en",
                    subject=f"Celebrate Rewards · {coupon.code}",
                    body=body,
                    status=MessageStatus.queued,
                    message_type=f"celebrate_{coupon.offer_type.value}",
                    confidence=0.95,
                    scheduled_at=datetime.utcnow(),
                )
            )
            queued += 1
    # Expire outdated coupons
    expired = (
        db.query(Coupon)
        .filter(
            Coupon.tenant_id == tenant_id,
            Coupon.status == CouponStatus.active,
            Coupon.valid_until < today,
        )
        .all()
    )
    for c in expired:
        c.status = CouponStatus.expired
    db.flush()
    return {
        "messages_queued": queued,
        "coupons_ensured": coupons_made,
        "coupons_expired": len(expired),
    }


def detect_fraud_signals(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    # Duplicate phones across guests
    dup_phones = (
        db.query(Guest.phone, func.count(Guest.id))
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.phone.isnot(None),
            Guest.phone != "",
        )
        .group_by(Guest.phone)
        .having(func.count(Guest.id) > 1)
        .all()
    )
    for phone, count in dup_phones:
        alerts.append(
            {
                "type": "duplicate_phone",
                "phone": phone,
                "guest_count": count,
                "severity": "high",
            }
        )
    return alerts


def celebrate_dashboard(db: Session, tenant_id: str) -> dict[str, Any]:
    today = date.today()
    week_end = today + timedelta(days=7)
    month_end = today + timedelta(days=31)

    enrolled = (
        db.query(Guest)
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.review_reward_unlocked.is_(True),
            Guest.birthday_locked.is_(True),
        )
        .count()
    )

    # Birthday this week: month/day within next 7 days
    birthday_guests = (
        db.query(Guest)
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.birthday_locked.is_(True),
            Guest.birthday.isnot(None),
        )
        .all()
    )
    birthday_this_week = 0
    for g in birthday_guests:
        assert g.birthday
        occ = _occurrence_this_year(g.birthday, today.year)
        if occ < today:
            occ = _occurrence_this_year(g.birthday, today.year + 1)
        if today <= occ <= week_end:
            birthday_this_week += 1

    anniversary_guests = (
        db.query(Guest)
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.anniversary_locked.is_(True),
            Guest.anniversary.isnot(None),
        )
        .all()
    )
    anniversaries_this_month = 0
    for g in anniversary_guests:
        assert g.anniversary
        occ = _occurrence_this_year(g.anniversary, today.year)
        if occ < today:
            occ = _occurrence_this_year(g.anniversary, today.year + 1)
        if today <= occ <= month_end:
            anniversaries_this_month += 1

    redeemed = (
        db.query(Coupon)
        .filter(Coupon.tenant_id == tenant_id, Coupon.status == CouponStatus.redeemed)
        .all()
    )
    revenue = sum(float(c.redemption_amount or 0) for c in redeemed)
    # Rough ROI: assume discount cost ~ avg discount * revenue share
    discount_cost = sum(
        float(c.redemption_amount or 0) * (c.discount_pct / 100.0) for c in redeemed
    )
    repeat_visits = (
        db.query(Guest)
        .filter(
            Guest.tenant_id == tenant_id,
            Guest.review_reward_unlocked.is_(True),
            Guest.stay_count > 1,
        )
        .count()
    )
    avg_spend = (
        db.query(func.coalesce(func.avg(Guest.average_booking), 0))
        .filter(Guest.tenant_id == tenant_id, Guest.review_reward_unlocked.is_(True))
        .scalar()
        or 0
    )

    return {
        "guests_enrolled": enrolled,
        "birthday_this_week": birthday_this_week,
        "anniversaries_this_month": anniversaries_this_month,
        "coupons_redeemed": len(redeemed),
        "revenue_generated": round(float(revenue), 2),
        "repeat_visits": repeat_visits,
        "average_spend": round(float(avg_spend), 2),
        "estimated_discount_cost": round(float(discount_cost), 2),
        "roi": round((float(revenue) - float(discount_cost)) / float(discount_cost), 2)
        if discount_cost > 0
        else None,
        "fraud_alerts": detect_fraud_signals(db, tenant_id),
        "tagline": "Turn verified reviewers into repeat customers.",
    }
