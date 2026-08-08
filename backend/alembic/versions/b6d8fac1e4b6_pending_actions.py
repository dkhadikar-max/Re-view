"""pending_actions table

Revision ID: b6d8fac1e4b6
Revises: a3c5e7f9b1d3
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6d8fac1e4b6"
down_revision: Union[str, Sequence[str], None] = "a3c5e7f9b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_status = sa.Enum("pending", "resolved", "cancelled", "expired", name="pendingactionstatus")


def upgrade() -> None:
    _status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "pending_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("guest_id", sa.String(length=36), sa.ForeignKey("guests.id"), nullable=False),
        sa.Column(
            "reservation_id",
            sa.String(length=36),
            sa.ForeignKey("reservations.id"),
            nullable=True,
        ),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("origin_action_type", sa.String(length=64), nullable=False),
        sa.Column("origin_intent", sa.String(length=32), nullable=False),
        sa.Column("status", _status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_pending_action_tenant_id", "pending_actions", ["tenant_id"])
    op.create_index("ix_pending_action_guest_id", "pending_actions", ["guest_id"])
    op.create_index("ix_pending_action_correlation_id", "pending_actions", ["correlation_id"])
    op.create_index(
        "ix_pending_action_guest_status", "pending_actions", ["guest_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_pending_action_guest_status", table_name="pending_actions")
    op.drop_index("ix_pending_action_correlation_id", table_name="pending_actions")
    op.drop_index("ix_pending_action_guest_id", table_name="pending_actions")
    op.drop_index("ix_pending_action_tenant_id", table_name="pending_actions")
    op.drop_table("pending_actions")
    _status.drop(op.get_bind(), checkfirst=True)
