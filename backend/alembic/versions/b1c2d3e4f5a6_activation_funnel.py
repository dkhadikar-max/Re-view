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
    # CTO P0 (code-review follow-up): UNIQUE, not a plain index. The
    # "first X" event types are meant to be written at most once per
    # tenant (log_event_once()'s whole contract) -- a plain index only
    # speeds up the check, it doesn't stop two concurrent requests from
    # both passing the check before either commits. This constraint is
    # the actual enforcement; log_event_once()'s SELECT-then-INSERT is
    # just an optimization to usually avoid hitting it.
    op.create_index(
        "ix_activation_tenant_event",
        "activation_events",
        ["tenant_id", "event_type"],
        unique=True,
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

    # CTO P0 (code-review follow-up) — a hotel that already imported real
    # guests before this column existed must not be misclassified as
    # "Sample workspace" the moment it's added. seed_trial_demo_data()
    # always gives every seeded demo guest an email ending in ".demo";
    # every real import path never produces that suffix, and a real guest
    # imported with no email at all (NULL) is still real, not demo.
    op.execute(
        "UPDATE properties SET has_real_data = TRUE WHERE id IN ("
        "SELECT DISTINCT property_id FROM guests "
        "WHERE email IS NULL OR email NOT LIKE '%.demo'"
        ")"
    )


def downgrade() -> None:
    with op.batch_alter_table("properties") as batch_op:
        batch_op.drop_column("has_real_data")

    op.drop_index(op.f("ix_activation_events_tenant_id"), table_name="activation_events")
    op.drop_index("ix_activation_tenant_event", table_name="activation_events")
    op.drop_table("activation_events")
