"""Lightweight schema patches for environments that use create_all without alembic."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.db.session import engine
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

    if "google_review_url" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE properties ADD COLUMN google_review_url VARCHAR(512)")
            )
        logger.info("Added properties.google_review_url column")

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
