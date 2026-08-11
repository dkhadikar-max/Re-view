"""WHATSAPP_PLATFORM_ARCHITECTURE.md sec 3: Property.whatsapp_connection_status

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_status = sa.Enum("not_connected", "connected", name="whatsappconnectionstatus")

properties = sa.table(
    "properties",
    sa.column("whatsapp_phone_number_id", sa.String),
    sa.column("whatsapp_connection_status", sa.String),
)


def upgrade() -> None:
    _status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "properties",
        sa.Column(
            "whatsapp_connection_status",
            _status,
            nullable=False,
            server_default="not_connected",
        ),
    )
    # Backfill: any property that already has a phone_number_id was
    # already connected before this column existed.
    op.execute(
        properties.update()
        .where(properties.c.whatsapp_phone_number_id.isnot(None))
        .values(whatsapp_connection_status="connected")
    )


def downgrade() -> None:
    op.drop_column("properties", "whatsapp_connection_status")
    _status.drop(op.get_bind(), checkfirst=True)
