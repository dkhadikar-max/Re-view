"""pilot readiness §5: Task.correlation_id (ties a Task back to the
ActionEvent chain that created it, for TASK_COMPLETED evidence)

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("correlation_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_task_correlation_id", ["correlation_id"])


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_task_correlation_id")
        batch_op.drop_column("correlation_id")
