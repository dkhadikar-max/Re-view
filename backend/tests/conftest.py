from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Configure test env before app import
os.environ["ENVIRONMENT"] = "test"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-characters-long"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["OWNER_EMAIL"] = "dkhadikar@gmail.com"
os.environ["OWNER_PASSWORD"] = "test-owner-password"

from app.core.config import get_settings

get_settings.cache_clear()

from app.core.security import hash_password  # noqa: E402
from app.db.seed import DEMO_EMAIL, DEMO_PASSWORD, DEMO_TENANT, register_handlers, seed_database  # noqa: E402
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import User  # noqa: E402


@pytest.fixture()
def db_engine():
    """The engine+sessionmaker backing `client` — factored out so `db`
    (below) can hand tests a session against the exact same database
    `client`'s HTTP requests read/write, rather than an isolated
    in-memory sqlite of its own. Needed for tests that set up state via
    a service function directly (matching every other test in this
    suite) and then exercise an endpoint through the real API boundary
    (PILOT_READINESS.md §5 check 8) against that same state.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    register_handlers()
    db = TestingSessionLocal()
    seed_database(db)
    db.close()
    yield engine, TestingSessionLocal
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_engine):
    engine, TestingSessionLocal = db_engine

    def _get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db(db_engine):
    """A session against `client`'s own database — same `engine`
    (StaticPool: one shared connection), so a commit made here is
    immediately visible to `client`'s next HTTP request and vice versa.
    Requesting both `client` and `db` in the same test reuses one
    `db_engine` instance (function-scoped fixture caching), not two
    separate databases.
    """
    _, TestingSessionLocal = db_engine
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def auth_header(client: TestClient):
    res = client.post(
        "/api/auth/login",
        data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
