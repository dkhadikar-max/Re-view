"""property knowledge base (AI Concierge FAQ Agent data source)

Revision ID: c3d5e7f9a1b2
Revises: b2c4d6e8f0a1
Create Date: 2026-08-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, Sequence[str], None] = "b2c4d6e8f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "property_knowledge_base",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "property_id",
            sa.String(length=36),
            sa.ForeignKey("properties.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("wifi_password", sa.String(length=255), nullable=True),
        sa.Column("breakfast_hours", sa.String(length=255), nullable=True),
        sa.Column("pool_hours", sa.String(length=255), nullable=True),
        sa.Column("gym_hours", sa.String(length=255), nullable=True),
        sa.Column("spa_hours", sa.String(length=255), nullable=True),
        sa.Column("parking_info", sa.Text(), nullable=True),
        sa.Column("checkin_time", sa.String(length=64), nullable=True),
        sa.Column("checkout_time", sa.String(length=64), nullable=True),
        sa.Column("late_checkout_policy", sa.Text(), nullable=True),
        sa.Column("airport_transfer_info", sa.Text(), nullable=True),
        sa.Column("pet_policy", sa.Text(), nullable=True),
        sa.Column("house_rules", sa.Text(), nullable=True),
        sa.Column("policies", sa.Text(), nullable=True),
        sa.Column("restaurants", sa.Text(), nullable=True),
        sa.Column("cafes", sa.Text(), nullable=True),
        sa.Column("nearby_attractions", sa.Text(), nullable=True),
        sa.Column("services", sa.Text(), nullable=True),
        sa.Column("room_service_hours", sa.String(length=255), nullable=True),
        sa.Column("emergency_contacts", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_property_knowledge_base_property_id",
        "property_knowledge_base",
        ["property_id"],
    )
    op.create_index(
        "ix_property_knowledge_base_tenant_id",
        "property_knowledge_base",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_property_knowledge_base_tenant_id", table_name="property_knowledge_base")
    op.drop_index(
        "ix_property_knowledge_base_property_id", table_name="property_knowledge_base"
    )
    op.drop_table("property_knowledge_base")
