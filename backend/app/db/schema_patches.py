"""Lightweight schema patches for environments that use create_all without alembic."""

from __future__ import annotations

import logging

from sqlalchemy import Enum, inspect, text

from app.db.session import engine
from app.models.entities import WhatsAppConnectionStatus
from app.services.currency import currency_for_country

logger = logging.getLogger(__name__)


def ensure_schema_patches() -> None:
    """Add missing columns used by newer app versions (idempotent)."""
    insp = inspect(engine)
    if "properties" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("properties")}
    if "currency" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE properties ADD COLUMN currency VARCHAR(8) "
                    "NOT NULL DEFAULT 'EUR'"
                )
            )
        logger.info("Added properties.currency column")

    if "address" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE properties ADD COLUMN address VARCHAR(500)"))
        logger.info("Added properties.address column")

    if "whatsapp_phone_number_id" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE properties ADD COLUMN whatsapp_phone_number_id VARCHAR(64)"
                )
            )
            # A separate CREATE UNIQUE INDEX (not an inline ALTER TABLE ...
            # ADD CONSTRAINT) because SQLite can't add a UNIQUE constraint
            # to an existing table via ALTER TABLE — a unique index is the
            # one syntax that works identically on both SQLite and Postgres.
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_properties_whatsapp_phone_number_id "
                    "ON properties (whatsapp_phone_number_id)"
                )
            )
        logger.info("Added properties.whatsapp_phone_number_id column")

    if "google_review_url" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE properties ADD COLUMN google_review_url VARCHAR(512)")
            )
        logger.info("Added properties.google_review_url column")

    if "whatsapp_connection_status" not in cols:
        # Same SQLAlchemy type the model declares (Property.whatsapp_connection_status
        # = Enum(WhatsAppConnectionStatus)) so the Postgres enum type this creates —
        # name, member set — is identical to what Alembic migration d5e6f7a8b9c0
        # creates. `.create(checkfirst=True)` is a no-op on SQLite (no native enum
        # type there) and idempotent on Postgres, so it's safe to call unconditionally.
        status_type = Enum(WhatsAppConnectionStatus)
        with engine.begin() as conn:
            status_type.create(conn, checkfirst=True)
            column_type = "VARCHAR(20)" if engine.dialect.name != "postgresql" else "whatsappconnectionstatus"
            conn.execute(
                text(
                    f"ALTER TABLE properties ADD COLUMN whatsapp_connection_status "
                    f"{column_type} NOT NULL DEFAULT 'not_connected'"
                )
            )
            # Backfill: any property that already has a phone_number_id was
            # already connected before this column existed. Mirrors the
            # Alembic migration's own backfill for the deploy path that
            # actually runs (this patcher, not `alembic upgrade`).
            conn.execute(
                text(
                    "UPDATE properties SET whatsapp_connection_status = 'connected' "
                    "WHERE whatsapp_phone_number_id IS NOT NULL"
                )
            )
        logger.info("Added properties.whatsapp_connection_status column")

    if "reservations" in insp.get_table_names():
        res_cols = {c["name"] for c in insp.get_columns("reservations")}
        if "import_session_id" not in res_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE reservations ADD COLUMN import_session_id VARCHAR(36)"
                    )
                )
            logger.info("Added reservations.import_session_id column")

    if "import_sessions" in insp.get_table_names():
        session_cols = {c["name"] for c in insp.get_columns("import_sessions")}
        if "rows_skipped" not in session_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE import_sessions ADD COLUMN rows_skipped "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
            logger.info("Added import_sessions.rows_skipped column")
        if "filename" not in session_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE import_sessions ADD COLUMN filename VARCHAR(255)")
                )
            logger.info("Added import_sessions.filename column")
        if "validation_issues" not in session_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE import_sessions ADD COLUMN validation_issues TEXT")
                )
            logger.info("Added import_sessions.validation_issues column")

    if "messages" in insp.get_table_names():
        msg_cols = {c["name"] for c in insp.get_columns("messages")}
        # Translation Layer (TRANSLATION_LAYER.md) — mirrors Alembic
        # migration e5f7a9b1c3d5, the deploy path that doesn't actually
        # run.
        if "detected_language" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE messages ADD COLUMN detected_language VARCHAR(32)")
                )
            logger.info("Added messages.detected_language column")
        if "normalized_text" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE messages ADD COLUMN normalized_text TEXT"))
            logger.info("Added messages.normalized_text column")

        # PILOT_READINESS.md §2 — mirrors Alembic migration a9b8c7d6e5f4.
        if "retry_count" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE messages ADD COLUMN retry_count INTEGER "
                        "NOT NULL DEFAULT 0"
                    )
                )
            logger.info("Added messages.retry_count column")

        # PILOT_READINESS.md §4 — mirrors Alembic migration b3c4d5e6f7a8.
        if "processing_failed" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE messages ADD COLUMN processing_failed BOOLEAN "
                        "NOT NULL DEFAULT FALSE"
                    )
                )
            logger.info("Added messages.processing_failed column")
        if "failure_reason" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE messages ADD COLUMN failure_reason VARCHAR(64)")
                )
            logger.info("Added messages.failure_reason column")
        if "duplicate_webhook_count" not in msg_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE messages ADD COLUMN duplicate_webhook_count "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )
            logger.info("Added messages.duplicate_webhook_count column")

        # PILOT_READINESS.md §1 — mirrors Alembic migration f1a2b3c4d5e6.
        # provider_message_id itself predates this patcher; only the
        # index was ever missing.
        msg_indexes = {ix["name"] for ix in insp.get_indexes("messages")}
        if "ix_msg_tenant_provider_message_id" not in msg_indexes:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_msg_tenant_provider_message_id "
                        "ON messages (tenant_id, provider_message_id)"
                    )
                )
            logger.info("Added ix_msg_tenant_provider_message_id index")

    if "tasks" in insp.get_table_names():
        task_cols = {c["name"] for c in insp.get_columns("tasks")}
        # PILOT_READINESS.md §5 — mirrors Alembic migration c4d5e6f7a8b9.
        if "correlation_id" not in task_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN correlation_id VARCHAR(36)")
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_task_correlation_id "
                        "ON tasks (correlation_id)"
                    )
                )
            logger.info("Added tasks.correlation_id column")

    # Backfill from country when still on the default and country implies otherwise
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, country, currency FROM properties")).fetchall()
        for row in rows:
            prop_id, country, currency = row[0], row[1], row[2]
            expected = currency_for_country(country)
            if currency and currency.upper() == expected:
                continue
            # Only auto-fix when currency is missing/default EUR but country maps elsewhere
            if (not currency or currency.upper() == "EUR") and expected != "EUR":
                conn.execute(
                    text("UPDATE properties SET currency = :cur WHERE id = :id"),
                    {"cur": expected, "id": prop_id},
                )
