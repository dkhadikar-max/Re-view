from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.entities import Base


def get_tenant_entity(
    db: Session,
    model: type[Base],
    entity_id: str,
    tenant_id: str,
    *,
    not_found: str = "Resource not found",
):
    obj = (
        db.query(model)
        .filter(model.id == entity_id, model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        .first()
    )
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)
    return obj
