"""P4 onboarding audit (CTO P0): activation_events table +
Property.has_real_data

Revision ID: b1c2d3e4f5a6
Revises: d5e6f7a8b9c0
Create Date: 2026-08-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activation_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_activation_tenant_event",
        "activation_events",
        ["tenant_id", "event_type"],
    )
    op.create_index(
        op.f("ix_activation_events_tenant_id"),
        "activation_events",
        ["tenant_id"],
    )

    with op.batch_alter_table("properties") as batch_op:
        batch_op.add_column(
            sa.Column(
                "has_real_data", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("properties") as batch_op:
        batch_op.drop_column("has_real_data")

    op.drop_index(op.f("ix_activation_events_tenant_id"), table_name="activation_events")
    op.drop_index("ix_activation_tenant_event", table_name="activation_events")
    op.drop_table("activation_events")
