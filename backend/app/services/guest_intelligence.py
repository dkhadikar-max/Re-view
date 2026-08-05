"""Living Guest Intelligence — computed insights from guest memory."""

from __future__ import annotations

from calendar import month_name
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.entities import (
    Coupon,
    CouponStatus,
    Guest,
    Message,
    Offer,
    OfferStatus,
    Reservation,
    Review,
)
from app.schemas import GuestOut


class TimelineEvent(BaseModel):
    at: date | datetime
    label: str
    kind: str  # stay | review | offer | purchase | message | celebrate | ltv
    amount: float | None = None


class GuestOpportunity(BaseModel):
    guest_id: str
    guest_name: str
    title: str
    reason: str
    action_label: str
    priority: int = 50
    health: str = "neutral"  # loyal | neutral | at_risk


class GuestIntelligence(GuestOut):
    """Guest profile + AI-visible intelligence for the hotel UI."""

    loyalty_label: str = "Guest"
    health: str = "neutral"  # loyal | neutral | at_risk
    health_label: str = "Neutral"
    return_probability: float = 0.0
    upsell_probability: float = 0.0
    review_probability: float = 0.0
    churn_risk: float = 0.0
    preferred_channel: str = "whatsapp"
    preferred_time: str = "6 PM"
    days_since_last_visit: int | None = None
    likely_next_visit: str | None = None
    favorite_wine: str | None = None
    tags: list[str] = Field(default_factory=list)
    remembers: list[str] = Field(default_factory=list)
    ai_summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
    next_best_action: dict[str, Any] | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    avg_rating: float | None = None
    lifetime_value: float = 0.0
    revenue_from_upsells: float = 0.0
    revenue_timeline: list[TimelineEvent] = Field(default_factory=list)



def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _loyalty_label(guest: Guest) -> str:
    if guest.ltv_score >= 85 and guest.stay_count >= 3:
        return "Loyal Guest"
    if guest.ltv_score >= 70:
        return "Valued Guest"
    if guest.complaint_history > 0 or guest.satisfaction_score < 55:
        return "Needs Attention"
    if guest.stay_count <= 1:
        return "New Guest"
    return "Returning Guest"


def _health(guest: Guest, days_since: int | None) -> tuple[str, str]:
    if guest.complaint_history >= 2 or guest.satisfaction_score < 50:
        return "at_risk", "At Risk"
    if days_since is not None and days_since > 180 and guest.stay_count > 0:
        return "at_risk", "At Risk"
    if guest.ltv_score >= 75 and guest.satisfaction_score >= 70:
        return "loyal", "Loyal"
    return "neutral", "Neutral"


def _tags(guest: Guest, days_until_bday: int | None) -> list[str]:
    tags: list[str] = []
    if guest.ltv_score >= 85:
        tags.append("VIP")
    if (guest.travel_type or "").lower() == "luxury":
        tags.append("Luxury")
    if (guest.travel_type or "").lower() == "business":
        tags.append("Business")
    if guest.children > 0 or (guest.travel_type or "").lower() == "family":
        tags.append("Family")
    if guest.dietary_preferences:
        diet = guest.dietary_preferences.strip().title()
        tags.append(diet if len(diet) < 24 else "Dietary Pref")
    if days_until_bday is not None and 0 <= days_until_bday <= 45:
        tags.append("Birthday Soon")
    if float(guest.lifetime_spend or 0) >= 1000:
        tags.append("High Spender")
    if guest.previous_reviews > 0:
        tags.append("Reviewer")
    if guest.communication_preference:
        tags.append(guest.communication_preference.title())
    if guest.stay_count > 1:
        tags.append("Repeat Guest")
    if guest.review_reward_unlocked:
        tags.append("Celebrate")
    return tags[:8]


def _remembers(guest: Guest, last_res: Reservation | None) -> list[str]:
    items: list[str] = []
    if guest.preferred_room:
        items.append(guest.preferred_room)
    elif last_res:
        items.append(last_res.room_type)
    if guest.dietary_preferences:
        items.append(guest.dietary_preferences.title())
    if guest.pets:
        items.append("Travels with pets")
    if last_res and last_res.special_requests:
        for part in str(last_res.special_requests).split(","):
            part = part.strip()
            if part:
                items.append(part[:60])
    if guest.notes:
        for line in guest.notes.splitlines():
            line = line.strip()
            if line.startswith("Remembers:"):
                items.append(line.replace("Remembers:", "").strip()[:60])
            elif "sparkling" in line.lower():
                items.append("Sparkling water")
            elif "no feather" in line.lower():
                items.append("No feather pillows")
            elif "late checkout" in line.lower():
                items.append("Late checkout")
    # Defaults that feel human for high-LTV guests without notes
    if guest.ltv_score >= 80 and "Late checkout" not in " ".join(items):
        items.append("Late checkout preferred")
    return list(dict.fromkeys([i for i in items if i]))[:8]


def _days_until_anniversary(d: date | None, today: date) -> int | None:
    if not d:
        return None
    nxt = date(today.year, d.month, d.day)
    if nxt < today:
        nxt = date(today.year + 1, d.month, d.day)
    return (nxt - today).days


def build_intelligence(db: Session, guest: Guest) -> GuestIntelligence:
    today = date.today()
    reservations = (
        db.query(Reservation)
        .filter(Reservation.guest_id == guest.id)
        .order_by(Reservation.check_in.desc())
        .all()
    )
    reviews = (
        db.query(Review)
        .filter(Review.guest_id == guest.id)
        .order_by(Review.created_at.desc())
        .all()
    )
    offers = (
        db.query(Offer)
        .join(Reservation, Offer.reservation_id == Reservation.id)
        .filter(Reservation.guest_id == guest.id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    messages = (
        db.query(Message)
        .filter(Message.guest_id == guest.id)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )

    last_res = reservations[0] if reservations else None
    days_since = (today - last_res.check_out).days if last_res else None
    days_bday = _days_until_anniversary(guest.birthday, today)
    days_ann = _days_until_anniversary(guest.anniversary, today)

    return_p = _clamp(
        40
        + guest.stay_count * 8
        + guest.ltv_score * 0.35
        + guest.satisfaction_score * 0.2
        - (min(days_since or 0, 365) * 0.08)
        - guest.complaint_history * 12
    )
    upsell_p = _clamp(
        25 + float(guest.upsell_acceptance or 0) * 55 + guest.ltv_score * 0.25
    )
    review_p = _clamp(
        30
        + guest.previous_reviews * 15
        + guest.satisfaction_score * 0.4
        + (20 if guest.review_reward_unlocked else 0)
    )
    churn = _clamp(
        100
        - return_p
        + guest.complaint_history * 10
        + (15 if (days_since or 0) > 120 else 0)
    )

    health, health_label = _health(guest, days_since)
    loyalty = _loyalty_label(guest)

    likely_next = None
    if guest.birthday:
        likely_next = month_name[guest.birthday.month]
    elif last_res:
        likely_next = month_name[((last_res.check_in.month + 5 - 1) % 12) + 1]

    wine = None
    if guest.notes:
        for line in guest.notes.splitlines():
            if line.lower().startswith("favorite wine:"):
                wine = line.split(":", 1)[1].strip() or None
                break
    if not wine and (guest.travel_type or "").lower() == "luxury":
        wine = "Sauvignon Blanc"
    elif not wine and (guest.country or "").lower() in {"france", "fr"}:
        wine = "Champagne"

    avg_rating = None
    if reviews:
        avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1)

    # Timeline + Revenue Timeline
    timeline: list[TimelineEvent] = []
    revenue_timeline: list[TimelineEvent] = []
    upsell_total = 0.0

    for r in reversed(reservations[-6:]):
        amt = float(r.total_amount or 0)
        ev = TimelineEvent(
            at=r.check_in,
            label=f"Stayed · {r.room_type}",
            kind="stay",
            amount=amt,
        )
        timeline.append(ev)
        revenue_timeline.append(ev)
    for rev in reversed(reviews[-4:]):
        timeline.append(
            TimelineEvent(
                at=rev.created_at,
                label=f"{rev.rating}★ review",
                kind="review",
            )
        )
        revenue_timeline.append(
            TimelineEvent(
                at=rev.created_at,
                label=f"{rev.rating}★ review left",
                kind="review",
            )
        )
    for o in reversed([x for x in offers if x.status == OfferStatus.accepted][-4:]):
        amt = float(o.price or 0)
        upsell_total += amt
        ev = TimelineEvent(
            at=o.accepted_at or o.created_at,
            label=f"Purchased {o.name}",
            kind="purchase",
            amount=amt,
        )
        timeline.append(ev)
        revenue_timeline.append(ev)
    if guest.review_reward_unlocked_at:
        unlock_ev = TimelineEvent(
            at=guest.review_reward_unlocked_at,
            label="Celebrate reward unlocked",
            kind="celebrate",
        )
        timeline.append(unlock_ev)
        revenue_timeline.append(unlock_ev)

    coupons = (
        db.query(Coupon)
        .filter(Coupon.guest_id == guest.id)
        .order_by(Coupon.created_at.asc())
        .all()
    )
    for c in coupons:
        revenue_timeline.append(
            TimelineEvent(
                at=c.created_at,
                label=f"{c.offer_type.value.title()} offer created",
                kind="offer",
            )
        )
        if c.status == CouponStatus.redeemed and c.redeemed_at:
            revenue_timeline.append(
                TimelineEvent(
                    at=c.redeemed_at,
                    label=f"{c.offer_type.value.title()} redeemed",
                    kind="celebrate",
                    amount=float(c.redemption_amount or 0) or None,
                )
            )

    lifetime_value = float(guest.lifetime_spend or 0) + upsell_total
    revenue_timeline.append(
        TimelineEvent(
            at=datetime.utcnow(),
            label=f"Lifetime value €{lifetime_value:,.0f}",
            kind="ltv",
            amount=lifetime_value,
        )
    )

    def _sort_key(e: TimelineEvent):
        return (
            e.at
            if isinstance(e.at, datetime)
            else datetime.combine(e.at, datetime.min.time())
        )

    timeline.sort(key=_sort_key)
    revenue_timeline.sort(key=_sort_key)

    lang = (guest.language or "en").lower()
    lang_label = {
        "en": "English",
        "de": "German",
        "fr": "French",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "nl": "Dutch",
    }.get(lang, lang.upper())

    travel = (guest.travel_type or "leisure").lower()
    channel = guest.communication_preference or "whatsapp"

    room_pref = guest.preferred_room or (last_res.room_type if last_res else None)
    summary_bits = [
        f"{guest.name.split()[0]} is a {loyalty.lower()}.",
        (
            f"Usually books {travel} stays in {room_pref} rooms."
            if room_pref
            else f"Usually books {travel} stays."
        ),
        f"Prefers {channel} and responds in {lang_label}.",
    ]
    if days_since is not None:
        summary_bits.append(f"Last visit {days_since} days ago.")
    if likely_next:
        summary_bits.append(f"Likely to revisit in {likely_next}.")
    if guest.dietary_preferences:
        summary_bits.append(f"Dietary: {guest.dietary_preferences}.")

    recs: list[str] = []
    if travel == "luxury" or guest.ltv_score >= 80:
        recs.append("Spa package instead of a blanket discount")
    if guest.children > 0:
        recs.append("Family dinner or baby cot if travelling with children")
    if channel == "whatsapp":
        recs.append("Reach out on WhatsApp around 6 PM")
    if days_bday is not None and days_bday <= 30:
        recs.append("Send birthday celebrate offer")
    if not recs:
        recs.append("Personalized welcome with room preference noted")

    # Next best action
    nba: dict[str, Any] | None = None
    if days_bday is not None and days_bday <= 21:
        nba = {
            "title": "Birthday outreach",
            "detail": f"Birthday in {days_bday} days · {guest.stay_count} stays · avg {float(guest.average_booking or 0):.0f}",
            "recommendation": "Send complimentary dessert or celebrate reward",
            "expected_redemption": round(min(0.85, 0.45 + guest.upsell_acceptance * 0.4), 2),
            "expected_revenue": round(float(guest.average_booking or 120) * 0.18, 0),
            "action_label": "Send reward",
        }
    elif churn >= 55:
        nba = {
            "title": "Win-back offer",
            "detail": f"Churn risk {churn:.0f}% · last visit {days_since or '—'} days ago",
            "recommendation": "Offer 15% package or suite upgrade incentive",
            "expected_redemption": 0.42,
            "expected_revenue": round(float(guest.average_booking or 200) * 0.2, 0),
            "action_label": "Create offer",
        }
    elif guest.previous_reviews == 0 and last_res and last_res.check_out <= today:
        nba = {
            "title": "Request review",
            "detail": "No review yet after stay",
            "recommendation": "Generate review request message",
            "expected_redemption": round(review_p / 100, 2),
            "expected_revenue": 0,
            "action_label": "Generate message",
        }
    elif upsell_p >= 60:
        nba = {
            "title": "Upsell window",
            "detail": f"Upsell probability {upsell_p:.0f}%",
            "recommendation": recs[0] if recs else "Offer late checkout",
            "expected_redemption": round(upsell_p / 100 * 0.7, 2),
            "expected_revenue": 95 if "Spa" in (recs[0] if recs else "") else 55,
            "action_label": "Draft upsell",
        }

    base = GuestOut.model_validate(guest)
    return GuestIntelligence(
        **base.model_dump(),
        loyalty_label=loyalty,
        health=health,
        health_label=health_label,
        return_probability=round(return_p, 1),
        upsell_probability=round(upsell_p, 1),
        review_probability=round(review_p, 1),
        churn_risk=round(churn, 1),
        preferred_channel=channel,
        preferred_time="6 PM",
        days_since_last_visit=days_since,
        likely_next_visit=likely_next,
        favorite_wine=wine,
        tags=_tags(guest, days_bday),
        remembers=_remembers(guest, last_res),
        ai_summary=" ".join(summary_bits),
        recommendations=recs,
        next_best_action=nba,
        timeline=timeline[-10:],
        avg_rating=avg_rating,
        lifetime_value=round(lifetime_value, 2),
        revenue_from_upsells=round(upsell_total, 2),
        revenue_timeline=revenue_timeline[-12:],
    )


def list_opportunities(db: Session, tenant_id: str, limit: int = 8) -> list[GuestOpportunity]:
    guests = (
        db.query(Guest)
        .filter(Guest.tenant_id == tenant_id)
        .order_by(Guest.ltv_score.desc())
        .limit(80)
        .all()
    )
    today = date.today()
    opps: list[GuestOpportunity] = []
    for g in guests:
        intel = build_intelligence(db, g)
        if intel.next_best_action:
            nba = intel.next_best_action
            opps.append(
                GuestOpportunity(
                    guest_id=g.id,
                    guest_name=g.name,
                    title=nba.get("title") or "Opportunity",
                    reason=nba.get("detail") or "",
                    action_label=nba.get("action_label") or "Act",
                    priority=int(100 - intel.churn_risk + intel.ltv_score * 0.2),
                    health=intel.health,
                )
            )
        days_bday = _days_until_anniversary(g.birthday, today)
        if days_bday is not None and days_bday <= 14:
            opps.append(
                GuestOpportunity(
                    guest_id=g.id,
                    guest_name=g.name,
                    title=f"Birthday in {days_bday} days",
                    reason="Celebrate reward window",
                    action_label="Send reward",
                    priority=95,
                    health=intel.health,
                )
            )
    # de-dupe by guest+title
    seen: set[str] = set()
    unique: list[GuestOpportunity] = []
    for o in sorted(opps, key=lambda x: -x.priority):
        key = f"{o.guest_id}:{o.title}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(o)
        if len(unique) >= limit:
            break
    return unique
