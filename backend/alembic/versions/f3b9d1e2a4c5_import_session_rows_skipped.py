"""import session rows_skipped

Revision ID: f3b9d1e2a4c5
Revises: e2a7c8d9f0b1
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3b9d1e2a4c5"
down_revision: Union[str, Sequence[str], None] = "e2a7c8d9f0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("import_sessions") as batch:
        batch.add_column(
            sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("import_sessions") as batch:
        batch.drop_column("rows_skipped")
