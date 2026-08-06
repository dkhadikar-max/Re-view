"""property address and google review url

Revision ID: d1f6b3c4e5a6
Revises: c9e5a1b2d3f4
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1f6b3c4e5a6"
down_revision: Union[str, Sequence[str], None] = "c9e5a1b2d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.add_column(sa.Column("address", sa.String(length=500), nullable=True))
        batch.add_column(
            sa.Column("google_review_url", sa.String(length=512), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("properties") as batch:
        batch.drop_column("google_review_url")
        batch.drop_column("address")
