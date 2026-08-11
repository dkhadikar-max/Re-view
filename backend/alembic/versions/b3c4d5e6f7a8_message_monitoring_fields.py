"""pilot readiness §4: Message monitoring fields (processing_failed,
failure_reason, duplicate_webhook_count)

Revision ID: b3c4d5e6f7a8
Revises: a9b8c7d6e5f4
Create Date: 2026-08-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "processing_failed", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(sa.Column("failure_reason", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "duplicate_webhook_count", sa.Integer(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("duplicate_webhook_count")
        batch_op.drop_column("failure_reason")
        batch_op.drop_column("processing_failed")
