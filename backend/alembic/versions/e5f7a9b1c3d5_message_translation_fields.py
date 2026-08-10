"""translation layer: Message.detected_language + normalized_text

Revision ID: e5f7a9b1c3d5
Revises: d9f1b3a5c7e9
Create Date: 2026-08-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f7a9b1c3d5"
down_revision: Union[str, Sequence[str], None] = "d9f1b3a5c7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TRANSLATION_LAYER.md §2 constraint 3 / §4 — deliberately distinct
    # from the existing `language` column (Guest's declared preference,
    # copied at message creation): `detected_language` is the per-message
    # auto-detected language, and `normalized_text` is the internal
    # English representation. `body` (already existing) stays the
    # guest's untouched original text — never overwritten.
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("detected_language", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("normalized_text", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("normalized_text")
        batch_op.drop_column("detected_language")
