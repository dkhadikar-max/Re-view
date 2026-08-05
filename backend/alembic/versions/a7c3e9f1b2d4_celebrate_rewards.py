"""celebrate_rewards

Revision ID: a7c3e9f1b2d4
Revises: e161cc9d3830
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c3e9f1b2d4"
down_revision: Union[str, None] = "e161cc9d3830"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("guests") as batch:
        batch.add_column(sa.Column("birthday_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("anniversary_locked", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("birthday_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("anniversary_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("review_reward_unlocked", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("review_reward_unlocked_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("celebrate_dates_confirmed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "celebrate_reward_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("birthday_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("birthday_discount_pct", sa.Float(), nullable=False, server_default="20"),
        sa.Column("birthday_days_before", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("birthday_days_after", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("birthday_min_spend", sa.Numeric(12, 2), nullable=False, server_default="1000"),
        sa.Column("birthday_max_uses_per_year", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("birthday_stackable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("anniversary_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("anniversary_discount_pct", sa.Float(), nullable=False, server_default="15"),
        sa.Column("anniversary_days_before", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("anniversary_days_after", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("anniversary_min_spend", sa.Numeric(12, 2), nullable=False, server_default="2000"),
        sa.Column("anniversary_max_uses_per_year", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("anniversary_stackable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="INR"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_celebrate_config_tenant"),
    )
    op.create_index("ix_celebrate_reward_configs_tenant_id", "celebrate_reward_configs", ["tenant_id"])

    op.create_table(
        "coupons",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("guest_id", sa.String(length=36), sa.ForeignKey("guests.id"), nullable=False),
        sa.Column("offer_type", sa.Enum("birthday", "anniversary", name="celebrateoffertype"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("min_spend", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("status", sa.Enum("active", "redeemed", "expired", "cancelled", name="couponstatus"), nullable=False),
        sa.Column("stackable", sa.Boolean(), nullable=False),
        sa.Column("personalized_perk", sa.String(length=255), nullable=True),
        sa.Column("message_body", sa.Text(), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(), nullable=True),
        sa.Column("redemption_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_coupon_code"),
        sa.CheckConstraint("discount_pct >= 0 AND discount_pct <= 100", name="ck_coupon_pct"),
    )
    op.create_index("ix_coupons_tenant_id", "coupons", ["tenant_id"])
    op.create_index("ix_coupons_guest_id", "coupons", ["guest_id"])
    op.create_index("ix_coupon_guest_type_year", "coupons", ["tenant_id", "guest_id", "offer_type", "year"])

    op.create_table(
        "celebrate_date_audits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("guest_id", sa.String(length=36), sa.ForeignKey("guests.id"), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(length=255), nullable=False),
        sa.Column("changed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_celebrate_date_audits_tenant_id", "celebrate_date_audits", ["tenant_id"])
    op.create_index("ix_celebrate_audit_guest", "celebrate_date_audits", ["tenant_id", "guest_id"])


def downgrade() -> None:
    op.drop_table("celebrate_date_audits")
    op.drop_table("coupons")
    op.drop_table("celebrate_reward_configs")
    with op.batch_alter_table("guests") as batch:
        batch.drop_column("celebrate_dates_confirmed_at")
        batch.drop_column("review_reward_unlocked_at")
        batch.drop_column("review_reward_unlocked")
        batch.drop_column("anniversary_verified")
        batch.drop_column("birthday_verified")
        batch.drop_column("anniversary_locked")
        batch.drop_column("birthday_locked")
