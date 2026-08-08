"""property services and packages (Revenue Agent config source of truth)

Revision ID: d4e6f8a0b2c4
Revises: c3d5e7f9a1b2
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e6f8a0b2c4"
down_revision: Union[str, Sequence[str], None] = "c3d5e7f9a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "property_services",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "property_id", sa.String(length=36), sa.ForeignKey("properties.id"), nullable=False
        ),
        sa.Column("service_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="EUR"),
        sa.Column(
            "complimentary", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_property_services_property_id", "property_services", ["property_id"]
    )
    op.create_index("ix_property_services_tenant_id", "property_services", ["tenant_id"])

    op.create_table(
        "property_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "property_id", sa.String(length=36), sa.ForeignKey("properties.id"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occasions", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="EUR"),
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_property_packages_property_id", "property_packages", ["property_id"]
    )
    op.create_index("ix_property_packages_tenant_id", "property_packages", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_property_packages_tenant_id", table_name="property_packages")
    op.drop_index("ix_property_packages_property_id", table_name="property_packages")
    op.drop_table("property_packages")
    op.drop_index("ix_property_services_tenant_id", table_name="property_services")
    op.drop_index("ix_property_services_property_id", table_name="property_services")
    op.drop_table("property_services")
