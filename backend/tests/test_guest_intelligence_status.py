"""Guest Intelligence epistemic-status taxonomy — PHASE4_PRODUCT_REVIEW.md
§4/§8 ("act now" scope A).

Unit tests of `build_intelligence`'s new status fields: the shared
`predictions_status` on return/upsell/review/churn, and each Next Best
Action branch's `expected_redemption_status`/`expected_revenue_status`.
Confirms the taxonomy assignment matches the review's own diagnosis —
in particular, the two literal-constant cases (win-back's
`expected_redemption=0.42`, upsell-window's `expected_revenue=95/55`)
are `illustrative`, not `heuristic_estimate`, since they aren't
derived from any formula at all.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import Guest, Property, Reservation, ReservationStatus, Tenant
from app.services.guest_intelligence import (
    STATUS_HEURISTIC_ESTIMATE,
    STATUS_ILLUSTRATIVE,
    build_intelligence,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_guest(db, *, tenant_id, **guest_kwargs):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    guest = Guest(tenant_id=tenant_id, property_id=property_.id, name="Guest", **guest_kwargs)
    db.add(guest)
    db.flush()
    return guest


# -- shared predictions status -------------------------------------------------


def test_predictions_status_is_heuristic_estimate_for_every_guest(db_session):
    """return/upsell/review/churn are all the same hand-tuned formula
    family -- always heuristic_estimate today, regardless of the
    guest's own data, since none of them are calibrated against a real
    outcome."""
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-a")

    intel = build_intelligence(db, guest)

    assert intel.predictions_status == STATUS_HEURISTIC_ESTIMATE


# -- next best action: birthday outreach ---------------------------------------


def test_birthday_outreach_both_numbers_are_heuristic_estimate(db_session):
    today = date.today()
    upcoming_birthday = today + timedelta(days=10)
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-b",
        birthday=date(1990, upcoming_birthday.month, upcoming_birthday.day),
        average_booking=200,
    )

    intel = build_intelligence(db, guest)

    assert intel.next_best_action is not None
    assert intel.next_best_action["title"] == "Birthday outreach"
    assert intel.next_best_action["expected_redemption_status"] == STATUS_HEURISTIC_ESTIMATE
    assert intel.next_best_action["expected_revenue_status"] == STATUS_HEURISTIC_ESTIMATE


# -- next best action: win-back offer -------------------------------------------


def test_winback_redemption_is_illustrative_not_heuristic(db_session):
    """The exact case PHASE4_PRODUCT_REVIEW.md §4 named: expected_redemption
    is a literal 0.42 constant, never derived from churn or any other
    guest data -- must be tagged illustrative, not heuristic_estimate."""
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-c",
        complaint_history=3, satisfaction_score=30,  # drives churn_risk >= 55
        average_booking=250,
    )

    intel = build_intelligence(db, guest)

    assert intel.next_best_action is not None
    assert intel.next_best_action["title"] == "Win-back offer"
    assert intel.next_best_action["expected_redemption"] == 0.42
    assert intel.next_best_action["expected_redemption_status"] == STATUS_ILLUSTRATIVE
    # expected_revenue *is* derived from average_booking -- a real formula,
    # even if not calibrated -- so it gets the weaker (not misleading) tag.
    assert intel.next_best_action["expected_revenue_status"] == STATUS_HEURISTIC_ESTIMATE


# -- next best action: request review -------------------------------------------


def test_request_review_revenue_is_illustrative_zero(db_session):
    db = db_session
    guest = _make_guest(db, tenant_id="hotel-d", previous_reviews=0)
    property_id = guest.property_id
    reservation = Reservation(
        tenant_id="hotel-d",
        property_id=property_id,
        guest_id=guest.id,
        source="manual",
        status=ReservationStatus.checked_out,
        room_type="Standard",
        check_in=date.today() - timedelta(days=10),
        check_out=date.today() - timedelta(days=8),
        adults=1,
        total_amount=150,
        currency="EUR",
    )
    db.add(reservation)
    db.flush()

    intel = build_intelligence(db, guest)

    assert intel.next_best_action is not None
    assert intel.next_best_action["title"] == "Request review"
    assert intel.next_best_action["expected_revenue"] == 0
    assert intel.next_best_action["expected_revenue_status"] == STATUS_ILLUSTRATIVE
    assert intel.next_best_action["expected_redemption_status"] == STATUS_HEURISTIC_ESTIMATE


# -- next best action: upsell window ---------------------------------------------


def test_upsell_window_revenue_is_illustrative_not_heuristic(db_session):
    """expected_revenue here is a hardcoded 95-or-55 picked by a string
    match on the recommendation text, not derived from guest data --
    same "constant dressed as a number" shape as the win-back case."""
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-e",
        upsell_acceptance=0.9, ltv_score=90,  # drives upsell_probability >= 60
        previous_reviews=1,  # skip the "Request review" branch
    )

    intel = build_intelligence(db, guest)

    assert intel.next_best_action is not None
    assert intel.next_best_action["title"] == "Upsell window"
    assert intel.next_best_action["expected_revenue"] in (95, 55)
    assert intel.next_best_action["expected_revenue_status"] == STATUS_ILLUSTRATIVE
    assert intel.next_best_action["expected_redemption_status"] == STATUS_HEURISTIC_ESTIMATE


def test_no_next_best_action_when_no_branch_matches(db_session):
    """A guest matching none of the four NBA conditions gets no card at
    all -- no status fields to check, but confirms build_intelligence
    doesn't crash or fabricate one."""
    db = db_session
    guest = _make_guest(
        db, tenant_id="hotel-f",
        upsell_acceptance=0.0, ltv_score=10, satisfaction_score=90,
        complaint_history=0, previous_reviews=1,
    )

    intel = build_intelligence(db, guest)

    assert intel.next_best_action is None
