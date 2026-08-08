"""action_event actor field

Revision ID: a3c5e7f9b1d3
Revises: f7a1c3e5b9d7
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d3"
down_revision: Union[str, Sequence[str], None] = "f7a1c3e5b9d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_actor = sa.Enum("AI", "GUEST", "STAFF", "SYSTEM", name="actortype")


def upgrade() -> None:
    _actor.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "action_events",
        sa.Column("actor", _actor, nullable=False, server_default="AI"),
    )
    op.create_index("ix_action_event_actor", "action_events", ["actor"])


def downgrade() -> None:
    op.drop_index("ix_action_event_actor", table_name="action_events")
    op.drop_column("action_events", "actor")
    _actor.drop(op.get_bind(), checkfirst=True)
