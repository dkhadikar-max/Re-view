"""action events (the Action Ledger)

Revision ID: f7a1c3e5b9d7
Revises: d4e6f8a0b2c4
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a1c3e5b9d7"
down_revision: Union[str, Sequence[str], None] = "d4e6f8a0b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_status = sa.Enum(
    "proposed",
    "accepted",
    "rejected",
    "completed",
    "failed",
    "escalated",
    name="actioneventstatus",
)


def upgrade() -> None:
    op.create_table(
        "action_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column(
            "tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("guest_id", sa.String(length=36), sa.ForeignKey("guests.id"), nullable=False),
        sa.Column(
            "reservation_id",
            sa.String(length=36),
            sa.ForeignKey("reservations.id"),
            nullable=True,
        ),
        sa.Column("conversation_id", sa.String(length=64), nullable=True),
        sa.Column("intent", sa.String(length=32), nullable=False),
        sa.Column("agent", sa.String(length=32), nullable=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("status", _status, nullable=False, server_default="proposed"),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_action_event_tenant_id", "action_events", ["tenant_id"])
    op.create_index("ix_action_event_guest_id", "action_events", ["guest_id"])
    op.create_index("ix_action_event_reservation_id", "action_events", ["reservation_id"])
    op.create_index("ix_action_event_conversation_id", "action_events", ["conversation_id"])
    op.create_index("ix_action_event_created_at", "action_events", ["created_at"])
    op.create_index("ix_action_event_action_type", "action_events", ["action_type"])
    op.create_index("ix_action_event_correlation_id", "action_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_action_event_correlation_id", table_name="action_events")
    op.drop_index("ix_action_event_action_type", table_name="action_events")
    op.drop_index("ix_action_event_created_at", table_name="action_events")
    op.drop_index("ix_action_event_conversation_id", table_name="action_events")
    op.drop_index("ix_action_event_reservation_id", table_name="action_events")
    op.drop_index("ix_action_event_guest_id", table_name="action_events")
    op.drop_index("ix_action_event_tenant_id", table_name="action_events")
    op.drop_table("action_events")
    _status.drop(op.get_bind(), checkfirst=True)
