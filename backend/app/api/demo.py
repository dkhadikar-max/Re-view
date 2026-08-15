"""Public hotel trial signup — for hotels who want to explore Revisit."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.activation import log_event
from app.services.hotel_signup import (
    HotelSignupRequest,
    HotelSignupResponse,
    signup_hotel,
)

router = APIRouter(prefix="/demo", tags=["hotel-trial"])


class PreSignupEvent(BaseModel):
    # Literal, not `str` -- this endpoint is unauthenticated (fires from
    # the public /onboard page before an account exists), so the allowed
    # event_type set is deliberately closed rather than open text.
    event_type: Literal["signup_started"]


@router.post("/activation-event")
def record_pre_signup_event(
    payload: PreSignupEvent, db: Session = Depends(get_db)
) -> dict[str, bool]:
    """P4 onboarding audit (CTO P0) — the one funnel event with no tenant
    yet (a page view, not an account action). Every event after this one
    is logged server-side, tenant-scoped, at its own real call site.

    Returns 200 with a minimal body rather than 204 -- the frontend's
    shared proxy (src/app/api/[...path]/route.ts) constructs
    `new NextResponse(body, { status })` unconditionally, which the Fetch
    spec (correctly) rejects for a 204/205/304 carrying a non-null body.
    Confirmed locally. Avoiding 204 here sidesteps that pre-existing proxy
    bug without touching shared code, out of scope for this change.
    """
    log_event(db, tenant_id=None, event_type=payload.event_type)
    db.commit()
    return {"ok": True}


@router.post("/hotel-signup", response_model=HotelSignupResponse)
@router.post("/onboard", response_model=HotelSignupResponse, include_in_schema=False)
def hotel_trial_signup(
    payload: HotelSignupRequest,
    db: Session = Depends(get_db),
) -> HotelSignupResponse:
    """Create a trial hotel account (tenant + manager + property) and return a login session."""
    try:
        return signup_hotel(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
