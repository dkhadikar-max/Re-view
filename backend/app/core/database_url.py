"""Database URL helpers — Railway Postgres + ephemeral SQLite detection."""

from __future__ import annotations


def normalize_database_url(url: str) -> str:
    """Normalize DATABASE_URL for SQLAlchemy + psycopg.

    Railway / Heroku often inject `postgres://` or `postgresql://`.
    This project depends on `psycopg` (v3), so we need
    `postgresql+psycopg://`.
    """
    raw = (url or "").strip()
    if not raw:
        return "sqlite:///./revisit.db"

    # postgres://user:pass@host/db  →  postgresql+psycopg://...
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://") :]
    if raw.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + raw[len("postgresql+psycopg2://") :]
    return raw


def database_backend(url: str) -> str:
    u = (url or "").lower()
    if u.startswith("sqlite"):
        return "sqlite"
    if "postgresql" in u or u.startswith("postgres"):
        return "postgresql"
    return "other"


def is_ephemeral_sqlite(url: str) -> bool:
    """True when the URL points at container-local SQLite (lost on redeploy)."""
    return database_backend(url) == "sqlite"
