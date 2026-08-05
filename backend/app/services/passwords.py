"""Password change and admin reset — always hashed; never store plaintext."""

from __future__ import annotations

import secrets
import string

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.entities import User
from app.services.audit import write_audit


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AdminResetPasswordRequest(BaseModel):
    """Optional custom password; if omitted a temporary one is generated."""

    new_password: str | None = Field(default=None, min_length=8, max_length=128)


class PasswordResetResult(BaseModel):
    message: str
    email: str
    temporary_password: str | None = None
    """Present only for admin-generated resets — show once, then discard."""


def _generate_temporary_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    # Ensure mix of classes for basic strength
    parts = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    parts += [secrets.choice(alphabet) for _ in range(max(0, length - len(parts)))]
    secrets.SystemRandom().shuffle(parts)
    return "".join(parts)


def change_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> PasswordResetResult:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password",
        )
    user.password_hash = hash_password(new_password)
    write_audit(
        db,
        tenant_id=user.tenant_id,
        actor=user.email,
        action="change_password",
        entity_type="user",
        entity_id=user.id,
        details={"email": user.email},
    )
    db.commit()
    return PasswordResetResult(
        message="Password updated. Use your new password next time you sign in.",
        email=user.email,
    )


def admin_reset_password(
    db: Session,
    *,
    tenant_id: str,
    actor_email: str,
    new_password: str | None = None,
) -> PasswordResetResult:
    user = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.is_active.is_(True))
        .order_by(User.created_at.asc())
        .all()
    )
    # Prefer manager/admin contact
    target = None
    for preferred in ("admin", "manager", "staff", "viewer"):
        target = next((u for u in user if u.role == preferred), None)
        if target:
            break
    if not target and user:
        target = user[0]
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active user found for this hotel",
        )

    temporary = new_password or _generate_temporary_password()
    target.password_hash = hash_password(temporary)
    write_audit(
        db,
        tenant_id=tenant_id,
        actor=actor_email,
        action="admin_reset_password",
        entity_type="user",
        entity_id=target.id,
        details={"email": target.email, "generated": new_password is None},
    )
    db.commit()
    return PasswordResetResult(
        message=(
            "Password reset and stored as a secure hash. "
            "Copy the temporary password now — it will not be shown again."
        ),
        email=target.email,
        temporary_password=temporary if new_password is None else temporary,
    )
