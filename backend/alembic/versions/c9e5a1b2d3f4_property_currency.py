"""property currency from country

Revision ID: c9e5a1b2d3f4
Revises: b8d4f0a2c3e5
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e5a1b2d3f4"
down_revision: Union[str, Sequence[str], None] = "b8d4f0a2c3e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.add_column(
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="EUR")
        )


def downgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.drop_column("currency")
