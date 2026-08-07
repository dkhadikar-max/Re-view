"""property whatsapp phone_number_id (multi-tenant WhatsApp routing)

Revision ID: b2c4d6e8f0a1
Revises: a4c6e8f1b3d5
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, Sequence[str], None] = "a4c6e8f1b3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.add_column(
            sa.Column("whatsapp_phone_number_id", sa.String(length=64), nullable=True)
        )
        batch.create_unique_constraint(
            "uq_properties_whatsapp_phone_number_id", ["whatsapp_phone_number_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.drop_constraint(
            "uq_properties_whatsapp_phone_number_id", type_="unique"
        )
        batch.drop_column("whatsapp_phone_number_id")
