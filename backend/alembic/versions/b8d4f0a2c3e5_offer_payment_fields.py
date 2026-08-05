"""offer payment link fields

Revision ID: b8d4f0a2c3e5
Revises: a7c3e9f1b2d4
Create Date: 2026-08-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d4f0a2c3e5"
down_revision: Union[str, Sequence[str], None] = "a7c3e9f1b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("offers") as batch:
        batch.add_column(sa.Column("payment_link_url", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("payment_session_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("offers") as batch:
        batch.drop_column("paid_at")
        batch.drop_column("payment_session_id")
        batch.drop_column("payment_link_url")
