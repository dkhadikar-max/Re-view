"""import sessions

Revision ID: e2a7c8d9f0b1
Revises: d1f6b3c4e5a6
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2a7c8d9f0b1"
down_revision: Union[str, Sequence[str], None] = "d1f6b3c4e5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), index=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "completed_with_errors",
                "failed",
                name="importsessionstatus",
            ),
            nullable=False,
            server_default="running",
        ),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initiated_by", sa.String(length=255), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_import_session_tenant_source",
        "import_sessions",
        ["tenant_id", "source"],
    )

    with op.batch_alter_table("reservations") as batch:
        batch.add_column(
            sa.Column("import_session_id", sa.String(length=36), nullable=True)
        )
        batch.create_foreign_key(
            "fk_reservations_import_session",
            "import_sessions",
            ["import_session_id"],
            ["id"],
        )
        batch.create_index(
            "ix_reservations_import_session_id", ["import_session_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("reservations") as batch:
        batch.drop_index("ix_reservations_import_session_id")
        batch.drop_constraint("fk_reservations_import_session", type_="foreignkey")
        batch.drop_column("import_session_id")

    op.drop_index("ix_import_session_tenant_source", table_name="import_sessions")
    op.drop_table("import_sessions")
