"""Public hotel trial signup — for hotels who want to explore Revisit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.hotel_signup import (
    HotelSignupRequest,
    HotelSignupResponse,
    signup_hotel,
)

router = APIRouter(prefix="/demo", tags=["hotel-trial"])


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
