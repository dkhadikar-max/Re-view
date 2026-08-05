"""Public demo onboarding endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.seed import DEMO_EMAIL, DEMO_TENANT
from app.db.session import get_db
from app.models.entities import User
from app.services.demo_onboard import (
    DemoOnboardRequest,
    DemoOnboardResponse,
    build_onboard_response,
    onboard_demo_guest,
)

router = APIRouter(prefix="/demo", tags=["demo-onboarding"])


@router.post("/onboard", response_model=DemoOnboardResponse)
def demo_guest_onboard(
    payload: DemoOnboardRequest,
    db: Session = Depends(get_db),
) -> DemoOnboardResponse:
    """Public: create a rich guest profile in the demo hotel and optionally issue a dashboard session."""
    try:
        guest = onboard_demo_guest(db, payload)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    access_token: str | None = None
    if payload.open_dashboard:
        manager = (
            db.query(User)
            .filter(User.tenant_id == DEMO_TENANT, User.email == DEMO_EMAIL)
            .first()
        )
        if manager:
            access_token = create_access_token(
                user_id=manager.id,
                tenant_id=manager.tenant_id,
                email=manager.email,
                name=manager.name,
                role=manager.role,
            )

    return build_onboard_response(db, guest, access_token=access_token)
