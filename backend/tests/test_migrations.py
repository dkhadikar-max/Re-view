"""CI protection for the Alembic migration chain (CTO P1, follow-up to #56).

The #56 outage happened because nothing verified that the deployed
database's schema actually matched what the application code expects.
These tests catch that class of drift *before* a PR merges, rather than
discovering it in production, and exercise the exact same bootstrap
logic `scripts/migrate_and_verify.py` runs on every real deploy (imported
directly, not reimplemented, so the two can't silently diverge).

Why `monkeypatch.setattr(settings, "database_url", ...)`: `alembic/env.py`
deliberately has one source of truth for the connection URL --
`settings.database_url` -- and re-asserts it at import time regardless of
what's set on the `Config` object passed in. That's correct for
production (one URL, no ambiguity about which database a deploy touches)
but means a test can't point Alembic at an isolated scratch database by
setting `Config.set_main_option("sqlalchemy.url", ...)` alone; `settings`
is a module-level singleton, imported by reference, so mutating its
`database_url` attribute in place is what actually reaches env.py.

Known scope limitation, stated plainly rather than glossed over: because
`initial_schema` is an intentionally empty stub (see migrate_and_verify.py's
module docstring) and every environment bootstraps its base tables via
`Base.metadata.create_all()`, a model column added with no migration ever
written for it will NOT be caught by `test_bootstrap_lands_on_head` below
-- create_all() builds straight from the current model, so a freshly
bootstrapped test database can never be "behind" the model that produced
it. What these tests DO guarantee: the bootstrap-and-verify gate itself
works end-to-end without error, and the migration chain has no structural
ambiguity. Catching "existing production table missing a column" (the
actual #56 failure mode) is what `run_migration_gate`'s head-equality
check exists for at deploy time, against the real, already-populated
database -- not something a from-scratch CI database can simulate.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _sqlite_url(db_path: Path) -> str:
    # .as_posix(): a raw Windows backslash path interpolated into a
    # sqlite:/// URL parses inconsistently across SQLAlchemy/Alembic
    # engine construction. Forward slashes are valid and unambiguous in
    # a sqlite URL on every platform.
    return f"sqlite:///{db_path.as_posix()}"


def _alembic_config(db_path: Path) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", _sqlite_url(db_path))
    return cfg


def test_single_migration_head():
    """`scripts/migrate_and_verify.py` refuses to deploy unless the chain
    has exactly one head -- catch a branch here, in CI, not at deploy time."""
    cfg = _alembic_config(BACKEND_DIR / "unused.db")
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, (
        f"Migration chain has {len(heads)} heads (expected 1): {heads}. "
        "Merge the branched history with `alembic merge heads`."
    )


def test_bootstrap_lands_on_head(tmp_path, monkeypatch):
    """Runs the real deploy-time gate (`run_migration_gate`) against a
    brand-new database and asserts it succeeds and lands exactly on the
    migration chain's head -- proves the create_all + stamp/upgrade
    bootstrap this ships with actually works, not just in theory."""
    from app.core.config import settings
    from scripts.migrate_and_verify import run_migration_gate

    db_path = tmp_path / "bootstrap_test.db"
    url = _sqlite_url(db_path)
    monkeypatch.setattr(settings, "database_url", url)
    cfg = _alembic_config(db_path)
    engine = create_engine(url)

    heads = run_migration_gate(cfg, engine)

    expected = set(ScriptDirectory.from_config(cfg).get_heads())
    assert heads == expected


def test_bootstrap_is_idempotent(tmp_path, monkeypatch):
    """Running the gate a second time (every subsequent deploy) must
    also succeed -- the already-stamped `alembic upgrade head` path, not
    just the first-deploy `alembic stamp head` path."""
    from app.core.config import settings
    from scripts.migrate_and_verify import run_migration_gate

    db_path = tmp_path / "bootstrap_idempotent_test.db"
    url = _sqlite_url(db_path)
    monkeypatch.setattr(settings, "database_url", url)
    cfg = _alembic_config(db_path)
    engine = create_engine(url)

    first = run_migration_gate(cfg, engine)
    second = run_migration_gate(cfg, engine)

    assert first == second
