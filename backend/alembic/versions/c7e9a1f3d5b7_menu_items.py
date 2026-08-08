"""menu_items table

Revision ID: c7e9a1f3d5b7
Revises: b6d8fac1e4b6
Create Date: 2026-08-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7e9a1f3d5b7"
down_revision: Union[str, Sequence[str], None] = "b6d8fac1e4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "menu_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "property_id", sa.String(length=36), sa.ForeignKey("properties.id"), nullable=False
        ),
        sa.Column("menu_name", sa.String(length=128), nullable=False, server_default="Menu"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="EUR"),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("vegetarian", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("vegan", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gluten_free", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("spicy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "source_import_id",
            sa.String(length=36),
            sa.ForeignKey("import_sessions.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_menu_item_tenant_id", "menu_items", ["tenant_id"])
    op.create_index("ix_menu_item_property_id", "menu_items", ["property_id"])
    op.create_index("ix_menu_item_source_import_id", "menu_items", ["source_import_id"])


def downgrade() -> None:
    op.drop_index("ix_menu_item_source_import_id", table_name="menu_items")
    op.drop_index("ix_menu_item_property_id", table_name="menu_items")
    op.drop_index("ix_menu_item_tenant_id", table_name="menu_items")
    op.drop_table("menu_items")
