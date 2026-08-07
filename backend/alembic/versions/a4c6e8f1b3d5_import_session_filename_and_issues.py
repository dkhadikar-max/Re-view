"""import session filename and validation issues

Revision ID: a4c6e8f1b3d5
Revises: f3b9d1e2a4c5
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a4c6e8f1b3d5"
down_revision: Union[str, Sequence[str], None] = "f3b9d1e2a4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("import_sessions") as batch:
        batch.add_column(sa.Column("filename", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("validation_issues", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("import_sessions") as batch:
        batch.drop_column("validation_issues")
        batch.drop_column("filename")
