"""Database URL normalization and production storage guards."""

import os

import pytest

from app.core.database_url import (
    database_backend,
    is_ephemeral_sqlite,
    normalize_database_url,
)


def test_normalize_railway_postgres_urls():
    assert normalize_database_url("postgres://u:p@host/db").startswith(
        "postgresql+psycopg://"
    )
    assert normalize_database_url("postgresql://u:p@host/db").startswith(
        "postgresql+psycopg://"
    )
    assert normalize_database_url("postgresql+psycopg2://u:p@host/db").startswith(
        "postgresql+psycopg://"
    )
    assert normalize_database_url("sqlite:///./revisit.db") == "sqlite:///./revisit.db"


def test_ephemeral_detection():
    assert is_ephemeral_sqlite("sqlite:///./revisit.db") is True
    assert is_ephemeral_sqlite("postgresql+psycopg://u:p@h/db") is False
    assert database_backend("postgresql+psycopg://u:p@h/db") == "postgresql"


def test_production_rejects_sqlite_when_required():
    previous = {
        k: os.environ.get(k)
        for k in (
            "ENVIRONMENT",
            "DATABASE_URL",
            "ALLOW_EPHEMERAL_SQLITE",
            "REQUIRE_DURABLE_STORAGE",
            "JWT_SECRET",
        )
    }
    try:
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DATABASE_URL"] = "sqlite:///./revisit.db"
        os.environ["REQUIRE_DURABLE_STORAGE"] = "true"
        os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-characters-long"
        os.environ.pop("ALLOW_EPHEMERAL_SQLITE", None)
        from app.core.config import Settings

        with pytest.raises(ValueError, match="Production cannot use container SQLite"):
            Settings()
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_production_allows_sqlite_with_escape_hatch():
    previous = {
        k: os.environ.get(k)
        for k in (
            "ENVIRONMENT",
            "DATABASE_URL",
            "ALLOW_EPHEMERAL_SQLITE",
            "REQUIRE_DURABLE_STORAGE",
            "JWT_SECRET",
        )
    }
    try:
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DATABASE_URL"] = "sqlite:///./revisit.db"
        os.environ["ALLOW_EPHEMERAL_SQLITE"] = "true"
        os.environ["REQUIRE_DURABLE_STORAGE"] = "true"
        os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-characters-long"
        from app.core.config import Settings

        s = Settings()
        assert s.storage_durable is False
        assert s.allow_ephemeral_sqlite is True
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_admin_analytics_includes_storage(client, auth_header):
    res = client.get("/api/admin/analytics", headers=auth_header)
    assert res.status_code == 200
    body = res.json()
    assert "storage_backend" in body
    assert "storage_durable" in body
    assert body["storage_backend"] == "sqlite"
    assert body["storage_durable"] is False
    assert body["storage_warning"]
