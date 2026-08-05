"""Platform owner admin API — signup visibility and client analytics."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.security import PlatformOwner
from app.db.session import get_db
from app.services.passwords import (
    AdminResetPasswordRequest,
    PasswordResetResult,
    admin_reset_password,
)
from app.services.platform_admin import (
    ClientOut,
    PlatformAnalytics,
    list_clients,
    platform_analytics,
)

router = APIRouter(prefix="/admin", tags=["platform-admin"])


@router.get("/clients", response_model=list[ClientOut])
def admin_list_clients(
    _: PlatformOwner,
    db: Session = Depends(get_db),
) -> list[ClientOut]:
    return list_clients(db)


@router.get("/analytics", response_model=PlatformAnalytics)
def admin_platform_analytics(
    _: PlatformOwner,
    db: Session = Depends(get_db),
) -> PlatformAnalytics:
    return platform_analytics(db)


@router.post(
    "/clients/{tenant_id}/reset-password",
    response_model=PasswordResetResult,
)
def admin_reset_client_password(
    tenant_id: str,
    user: PlatformOwner,
    db: Session = Depends(get_db),
    payload: AdminResetPasswordRequest = Body(default_factory=AdminResetPasswordRequest),
) -> PasswordResetResult:
    return admin_reset_password(
        db,
        tenant_id=tenant_id,
        actor_email=user.email,
        new_password=payload.new_password,
    )
