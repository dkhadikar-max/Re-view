from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.security import AuthUser, ManagerUser, StaffUser
from app.db.session import get_db
from app.models.entities import (
    CelebrateDateAudit,
    CelebrateRewardConfig,
    Coupon,
    Guest,
    Property,
    Review,
)
from app.services.celebrate_rewards import (
    AdminUnlockIn,
    CelebrateConfigIn,
    CelebrateDatesIn,
    admin_unlock_dates,
    celebrate_dashboard,
    confirm_and_lock_dates,
    create_guest_celebrate_token,
    decode_guest_celebrate_token,
    get_or_create_config,
    redeem_coupon,
    run_celebrate_campaigns,
    unlock_after_review,
    update_config,
)
from app.services.tenancy import get_tenant_entity

router = APIRouter(prefix="/celebrate", tags=["celebrate-rewards"])


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CelebrateConfigOut(ORMModel):
    id: str
    tenant_id: str
    birthday_enabled: bool
    birthday_discount_pct: float
    birthday_days_before: int
    birthday_days_after: int
    birthday_min_spend: float
    birthday_max_uses_per_year: int
    birthday_stackable: bool
    anniversary_enabled: bool
    anniversary_discount_pct: float
    anniversary_days_before: int
    anniversary_days_after: int
    anniversary_min_spend: float
    anniversary_max_uses_per_year: int
    anniversary_stackable: bool
    currency: str


class CouponOut(ORMModel):
    id: str
    guest_id: str
    offer_type: str
    code: str
    discount_pct: float
    min_spend: float
    currency: str
    year: int
    valid_from: date
    valid_until: date
    status: str
    stackable: bool
    personalized_perk: Optional[str] = None
    redeemed_at: Optional[datetime] = None
    redemption_amount: Optional[float] = None
    guest_name: Optional[str] = None


class CelebrateAuditOut(ORMModel):
    id: str
    guest_id: str
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: str
    reason: Optional[str] = None
    action: str
    created_at: datetime


class GuestCelebrateStatus(BaseModel):
    guest_id: str
    guest_name: str
    property_name: Optional[str] = None
    review_reward_unlocked: bool
    birthday: Optional[date] = None
    anniversary: Optional[date] = None
    birthday_locked: bool
    anniversary_locked: bool
    can_submit_dates: bool
    offers: dict[str, Any]
    tagline: str = "Turn verified reviewers into repeat customers."


class UnlockLinkOut(BaseModel):
    guest_id: str
    token: str
    invite_path: str
    message: str


class RedeemIn(BaseModel):
    amount: float = Field(gt=0)


class DashboardOut(BaseModel):
    guests_enrolled: int
    birthday_this_week: int
    anniversaries_this_month: int
    coupons_redeemed: int
    revenue_generated: float
    repeat_visits: int
    average_spend: float
    estimated_discount_cost: float
    roi: Optional[float] = None
    fraud_alerts: list[dict[str, Any]]
    tagline: str


def _coupon_out(coupon: Coupon, guest_name: Optional[str] = None) -> CouponOut:
    item = CouponOut.model_validate(coupon)
    item.offer_type = coupon.offer_type.value
    item.status = coupon.status.value
    item.min_spend = float(coupon.min_spend)
    item.redemption_amount = (
        float(coupon.redemption_amount) if coupon.redemption_amount is not None else None
    )
    item.guest_name = guest_name
    return item


@router.get("/config", response_model=CelebrateConfigOut)
def get_config(user: AuthUser, db: Session = Depends(get_db)) -> CelebrateRewardConfig:
    return get_or_create_config(db, user.tenant_id)


@router.put("/config", response_model=CelebrateConfigOut)
def put_config(
    payload: CelebrateConfigIn,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> CelebrateRewardConfig:
    config = update_config(db, user.tenant_id, payload, user.email)
    db.commit()
    db.refresh(config)
    return config


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: AuthUser, db: Session = Depends(get_db)) -> DashboardOut:
    return DashboardOut(**celebrate_dashboard(db, user.tenant_id))


@router.get("/coupons", response_model=list[CouponOut])
def list_coupons(user: AuthUser, db: Session = Depends(get_db)) -> list[CouponOut]:
    rows = (
        db.query(Coupon)
        .filter(Coupon.tenant_id == user.tenant_id)
        .order_by(Coupon.created_at.desc())
        .limit(200)
        .all()
    )
    guest_ids = {r.guest_id for r in rows}
    guests = {
        g.id: g.name
        for g in db.query(Guest)
        .filter(Guest.tenant_id == user.tenant_id, Guest.id.in_(guest_ids or {"_"}))
        .all()
    }
    return [_coupon_out(r, guests.get(r.guest_id)) for r in rows]


@router.post("/coupons/{coupon_id}/redeem", response_model=CouponOut)
def redeem(
    coupon_id: str,
    payload: RedeemIn,
    user: ManagerUser,
    db: Session = Depends(get_db),
) -> CouponOut:
    coupon = get_tenant_entity(
        db, Coupon, coupon_id, user.tenant_id, not_found="Coupon not found"
    )
    redeem_coupon(db, coupon, amount=payload.amount, actor=user.email)
    db.commit()
    db.refresh(coupon)
    return _coupon_out(coupon)


@router.get("/audits", response_model=list[CelebrateAuditOut])
def list_audits(
    user: ManagerUser, db: Session = Depends(get_db)
) -> list[CelebrateDateAudit]:
    return (
        db.query(CelebrateDateAudit)
        .filter(CelebrateDateAudit.tenant_id == user.tenant_id)
        .order_by(CelebrateDateAudit.created_at.desc())
        .limit(200)
        .all()
    )


@router.post("/guests/{guest_id}/invite", response_model=UnlockLinkOut)
def create_invite(
    guest_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> UnlockLinkOut:
    guest = get_tenant_entity(
        db, Guest, guest_id, user.tenant_id, not_found="Guest not found"
    )
    if not guest.review_reward_unlocked:
        raise HTTPException(
            status_code=409,
            detail="Guest has not unlocked Celebrate Rewards yet (needs a verified review)",
        )
    token = create_guest_celebrate_token(guest)
    return UnlockLinkOut(
        guest_id=guest.id,
        token=token,
        invite_path=f"/celebrate/{token}",
        message="Share this link so the guest can lock birthday & anniversary dates.",
    )


@router.post("/guests/{guest_id}/unlock-from-review/{review_id}")
def unlock_from_review(
    guest_id: str,
    review_id: str,
    user: StaffUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    guest = get_tenant_entity(
        db, Guest, guest_id, user.tenant_id, not_found="Guest not found"
    )
    review = get_tenant_entity(
        db, Review, review_id, user.tenant_id, not_found="Review not found"
    )
    if review.guest_id != guest.id:
        raise HTTPException(status_code=422, detail="Review does not belong to guest")
    unlock_after_review(db, review, guest, actor=user.email)
    token = create_guest_celebrate_token(guest)
    db.commit()
    return {
        "unlocked": True,
        "invite_path": f"/celebrate/{token}",
        "token": token,
        "note": "Rewards participation (leaving a review), not the star rating.",
    }


@router.post("/guests/{guest_id}/admin-unlock")
def admin_unlock(
    guest_id: str,
    payload: AdminUnlockIn,
    user: AuthUser,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user.require_role("admin")
    guest = get_tenant_entity(
        db, Guest, guest_id, user.tenant_id, not_found="Guest not found"
    )
    admin_unlock_dates(
        db,
        guest,
        payload,
        actor_email=user.email,
        actor_user_id=user.id,
    )
    db.commit()
    return {
        "ok": True,
        "birthday_locked": guest.birthday_locked,
        "anniversary_locked": guest.anniversary_locked,
    }


@router.post("/campaigns/run")
def run_campaigns(user: ManagerUser, db: Session = Depends(get_db)) -> dict[str, int]:
    result = run_celebrate_campaigns(db, user.tenant_id)
    db.commit()
    return result


@router.get("/public/{token}", response_model=GuestCelebrateStatus)
def public_status(token: str, db: Session = Depends(get_db)) -> GuestCelebrateStatus:
    data = decode_guest_celebrate_token(token)
    guest = (
        db.query(Guest)
        .filter(Guest.id == data["sub"], Guest.tenant_id == data["tenant_id"])
        .first()
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    config = get_or_create_config(db, guest.tenant_id)
    prop = db.get(Property, guest.property_id)
    return GuestCelebrateStatus(
        guest_id=guest.id,
        guest_name=guest.name,
        property_name=prop.name if prop else None,
        review_reward_unlocked=guest.review_reward_unlocked,
        birthday=guest.birthday,
        anniversary=guest.anniversary,
        birthday_locked=guest.birthday_locked,
        anniversary_locked=guest.anniversary_locked,
        can_submit_dates=bool(
            guest.review_reward_unlocked
            and not guest.birthday_locked
            and not guest.anniversary_locked
        ),
        offers={
            "birthday": {
                "enabled": config.birthday_enabled,
                "discount_pct": config.birthday_discount_pct,
                "window": (
                    f"{config.birthday_days_before} days before / "
                    f"{config.birthday_days_after} after"
                ),
                "min_spend": float(config.birthday_min_spend),
            },
            "anniversary": {
                "enabled": config.anniversary_enabled,
                "discount_pct": config.anniversary_discount_pct,
                "window": (
                    f"{config.anniversary_days_before} days before / "
                    f"{config.anniversary_days_after} after"
                ),
                "min_spend": float(config.anniversary_min_spend),
            },
        },
    )


@router.post("/public/{token}/dates")
def public_submit_dates(
    token: str,
    payload: CelebrateDatesIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    data = decode_guest_celebrate_token(token)
    guest = (
        db.query(Guest)
        .filter(Guest.id == data["sub"], Guest.tenant_id == data["tenant_id"])
        .first()
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    result = confirm_and_lock_dates(
        db, guest, payload, actor=guest.email or guest.name
    )
    db.commit()
    return {
        **result,
        "message": "Profile updated. Birthday and anniversary locked. Coupons created.",
    }
