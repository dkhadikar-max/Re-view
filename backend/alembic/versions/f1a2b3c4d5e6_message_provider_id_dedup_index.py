"""pilot readiness §1: index for provider_message_id dedup lookup

Revision ID: f1a2b3c4d5e6
Revises: e5f7a9b1c3d5
Create Date: 2026-08-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e5f7a9b1c3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PILOT_READINESS.md §1 — supports the (tenant_id, provider_message_id)
    # dedup lookup `ingest_inbound_whatsapp` now runs on every inbound
    # webhook. Not a unique constraint: most rows (outbound messages,
    # any inbound event shape without a provider id) legitimately have
    # a NULL provider_message_id, and the dedup check itself is an
    # application-level query-before-insert, not a DB-enforced
    # constraint — this index exists purely so that query stays fast
    # as message volume grows.
    op.create_index(
        "ix_msg_tenant_provider_message_id",
        "messages",
        ["tenant_id", "provider_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_msg_tenant_provider_message_id", table_name="messages")
