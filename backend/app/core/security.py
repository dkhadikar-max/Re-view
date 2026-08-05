from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import actor_ctx, tenant_id_ctx
from app.db.session import get_db
from app.models.entities import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ROLE_HIERARCHY = {
    "viewer": 1,
    "staff": 2,
    "manager": 3,
    "admin": 4,
}


class TokenPayload(BaseModel):
    sub: str
    tenant_id: str
    email: str
    name: str
    role: str
    exp: int


class CurrentUser(BaseModel):
    id: str
    tenant_id: str
    email: str
    name: str
    role: str

    def require_role(self, minimum: str) -> None:
        if ROLE_HIERARCHY.get(self.role, 0) < ROLE_HIERARCHY.get(minimum, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role {minimum} or higher",
            )


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(
    *,
    user_id: str,
    tenant_id: str,
    email: str,
    name: str,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "name": name,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload.model_validate(data)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    user = (
        db.query(User)
        .filter(User.id == payload.sub, User.tenant_id == payload.tenant_id, User.is_active.is_(True))
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    current = CurrentUser(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )
    tenant_id_ctx.set(current.tenant_id)
    actor_ctx.set(current.email)
    return current


def require_manager(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    user.require_role("manager")
    return user


def require_staff(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    user.require_role("staff")
    return user


AuthUser = Annotated[CurrentUser, Depends(get_current_user)]
ManagerUser = Annotated[CurrentUser, Depends(require_manager)]
StaffUser = Annotated[CurrentUser, Depends(require_staff)]
