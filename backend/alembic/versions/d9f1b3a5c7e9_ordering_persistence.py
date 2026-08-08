"""ordering agent persistence layer: PendingAction extension + orders

Revision ID: d9f1b3a5c7e9
Revises: c7e9a1f3d5b7
Create Date: 2026-08-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9f1b3a5c7e9"
down_revision: Union[str, Sequence[str], None] = "c7e9a1f3d5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MENU_ORDERING.md §7.1 — generalized PendingAction extension for
    # multi-turn cart-building, not order-specific.
    with op.batch_alter_table("pending_actions") as batch_op:
        batch_op.alter_column(
            "origin_action_type", existing_type=sa.String(length=64), nullable=True
        )
        batch_op.add_column(sa.Column("origin_agent", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("payload", sa.Text(), nullable=True))

    # MENU_ORDERING.md §6 — durable, confirmed business object. Created
    # only at confirmation; no "pending_confirmation" status of its own.
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "property_id", sa.String(length=36), sa.ForeignKey("properties.id"), nullable=False
        ),
        sa.Column("guest_id", sa.String(length=36), sa.ForeignKey("guests.id"), nullable=False),
        sa.Column(
            "reservation_id",
            sa.String(length=36),
            sa.ForeignKey("reservations.id"),
            nullable=True,
        ),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column(
            "source_menu_import_id",
            sa.String(length=36),
            sa.ForeignKey("import_sessions.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "confirmed",
                "received",
                "preparing",
                "delivered",
                "cancelled",
                name="orderstatus",
            ),
            nullable=False,
            server_default="confirmed",
        ),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="EUR"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_order_tenant_id", "orders", ["tenant_id"])
    op.create_index("ix_order_guest_id", "orders", ["guest_id"])
    op.create_index("ix_order_correlation_id", "orders", ["correlation_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column(
            "menu_item_id", sa.String(length=36), sa.ForeignKey("menu_items.id"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="EUR"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_order_item_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_item_order_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_order_correlation_id", table_name="orders")
    op.drop_index("ix_order_guest_id", table_name="orders")
    op.drop_index("ix_order_tenant_id", table_name="orders")
    op.drop_table("orders")
    op.execute("DROP TYPE IF EXISTS orderstatus")

    with op.batch_alter_table("pending_actions") as batch_op:
        batch_op.drop_column("payload")
        batch_op.drop_column("origin_agent")
        batch_op.alter_column(
            "origin_action_type", existing_type=sa.String(length=64), nullable=False
        )
