"""Deploy-time migration gate (CTO P1 decision, follow-up to #56).

Runs before `uvicorn` starts. Exits non-zero -- failing the deploy --
if the database doesn't end up structurally at the migration chain's
head, rather than starting an apparently healthy app against a schema
it silently assumes is current but isn't. That silent-assumption gap is
exactly what caused the #52 crash-loop and the #56 signup/dashboard/
tasks outage: schema_patches.py (the mechanism that historically DID
run on every boot) quietly fell out of sync with newer migrations, and
nothing caught it until production 500s.

## Why this isn't a plain `alembic upgrade head`

`alembic/versions/e161cc9d3830_initial_schema.py` is an intentionally
empty stub (`upgrade()` is just `pass`) -- this codebase has never
actually built its schema by replaying migrations from an empty
database. Every real environment (production, this script now included)
gets its base tables from `Base.metadata.create_all()`
(`AUTO_CREATE_TABLES=true`); migrations have only ever described
*incremental* changes layered on top of that. Replaying the full chain
against a database that already has these tables/columns (which is
every environment that has ever existed, including production today)
fails immediately with "table/column already exists" -- confirmed
locally against a genuinely empty scratch DB before this script shipped.

So the bootstrap logic below mirrors what has actually always happened:

  1. `Base.metadata.create_all()` -- idempotent, lays down anything
     wholly missing with the *current* model shape. No-op for tables
     that already exist (this is the same limitation schema_patches.py
     exists to cover, and still runs after this script, unchanged).
  2. If `alembic_version` has no stamped revision yet (true for every
     environment before this PR, including production): `alembic stamp
     head` rather than `upgrade head` -- the DB is already at head-
     equivalent structure (via create_all + schema_patches.py), so
     stamping records that instead of trying to replay history that
     would conflict with tables/columns already there.
  3. If already stamped (every deploy *after* the first one this ships
     on): `alembic upgrade head` normally. From this point on, a new
     migration added in a future PR runs for real, against a database
     that genuinely doesn't have that column yet -- this is what makes
     Alembic the actual source of truth going forward.
  4. Verify the database's current head(s) match the migration chain's
     expected head(s). Fail loud if not.

schema_patches.py is intentionally left running (from main.py's
lifespan, after this script succeeds) as a safety net for a few more
deploys -- see the PR that introduced this file. Retiring it is a
separate, later change.

Run as a module, from the backend working directory (Docker CMD does
this): `python -m scripts.migrate_and_verify`. Must be `-m`, not
`python scripts/migrate_and_verify.py` -- the latter puts `scripts/`
itself on `sys.path[0]` instead of the backend root, so `app` isn't
importable (confirmed locally: `ModuleNotFoundError: No module named
'app'`, which would have failed shut on every single deploy).
"""

from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine


class MigrationGateError(Exception):
    """Raised when the deploy-time migration gate can't verify the
    database is at the migration chain's head. The caller (main(), or a
    test) is responsible for turning this into a failure."""


def run_migration_gate(cfg: Config, engine: Engine) -> set[str]:
    """Run the bootstrap-aware migration gate against `engine`. Returns
    the verified current head(s) on success; raises MigrationGateError
    on any failure. Shared by `main()` and the CI tests in
    tests/test_migrations.py so the two can never silently diverge.
    """
    script = ScriptDirectory.from_config(cfg)
    expected_heads = set(script.get_heads())
    if len(expected_heads) != 1:
        raise MigrationGateError(
            f"migration chain has {len(expected_heads)} heads (expected "
            f"exactly 1): {sorted(expected_heads)}. A branched migration "
            "history must be merged (`alembic merge heads`) before this "
            "can deploy safely."
        )

    # Step 1 -- see module docstring. Idempotent; matches what
    # AUTO_CREATE_TABLES=true has always done in every real environment.
    from app.db.session import Base

    Base.metadata.create_all(bind=engine)

    # Step 2/3 -- bootstrap (stamp) an unstamped-but-already-populated
    # database instead of replaying history that would conflict with it;
    # upgrade normally once a stamp already exists.
    insp = inspect(engine)
    already_stamped = insp.has_table("alembic_version")
    try:
        if already_stamped:
            command.upgrade(cfg, "head")
        else:
            command.stamp(cfg, "head")
    except Exception as exc:  # noqa: BLE001 -- any failure here must fail the deploy
        raise MigrationGateError(f"alembic bootstrap failed: {exc}") from exc

    # Step 4 -- verify.
    with engine.connect() as conn:
        current_heads = set(MigrationContext.configure(conn).get_current_heads())

    if current_heads != expected_heads:
        raise MigrationGateError(
            f"database is at {sorted(current_heads)}, expected "
            f"{sorted(expected_heads)} after bootstrap -- refusing to "
            "start the app against a schema that isn't at the migration "
            "chain's head."
        )

    return current_heads


def main() -> int:
    cfg = Config("alembic.ini")

    from app.db.session import engine

    try:
        heads = run_migration_gate(cfg, engine)
    except MigrationGateError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    print(f"Schema verified at head: {sorted(heads)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
