"""One-off cleanup: remove synthetic verification tenants from production.

Deletes every row scoped to each target tenant across all tenant-scoped
tables, using SQLAlchemy's metadata dependency graph (sorted_tables)
reversed so children are always deleted before their parents -- avoids
hand-ordering the ~28 tenant-scoped tables and hitting an FK violation.
Tenants can be targeted by exact tenant_id or by a user's email (resolved
to that user's tenant_id).

Run with DRY_RUN=1 first -- prints row counts per table, deletes nothing.

Usage (from backend/, with DATABASE_URL pointed at the target environment):
    DRY_RUN=1 python scripts/cleanup_test_tenants.py
    python scripts/cleanup_test_tenants.py

Or on Railway, injecting the service's real env:
    railway run --service Re-view -- python scripts/cleanup_test_tenants.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.db.session import engine
from app.models.entities import Base

# Targets created during the Aug 24 2026 renewed-heart production
# verification pass -- not real customer data.
TENANT_IDS = ["verify-test-hotel-9068e8"]
EMAILS_TO_RESOLVE = ["smoke-test@revisit.internal"]

DRY_RUN = os.environ.get("DRY_RUN") == "1"

with engine.begin() as conn:
    tenant_ids = set(TENANT_IDS)
    for email in EMAILS_TO_RESOLVE:
        row = conn.execute(
            text('SELECT tenant_id FROM "users" WHERE lower(email) = lower(:email)'),
            {"email": email},
        ).fetchone()
        if row:
            tenant_ids.add(row[0])
        else:
            print(f"(no user found for {email} -- skipping)")

    if not tenant_ids:
        print("Nothing to delete.")
        raise SystemExit(0)

    print(f"Target tenant_id(s): {sorted(tenant_ids)}\n")

    # Reverse topological order: tables nothing else depends on come out
    # first in metadata.sorted_tables' natural (parent-first) order is
    # wrong for deletion -- we need children first, so reverse it.
    ordered_tables = list(reversed(Base.metadata.sorted_tables))

    total = 0
    for table in ordered_tables:
        if table.name == "tenants" or "tenant_id" not in table.columns:
            continue
        count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{table.name}" WHERE tenant_id = ANY(:tids)'),
            {"tids": list(tenant_ids)},
        ).scalar()
        if count:
            print(f"{table.name}: {count} row(s)")
            total += count
            if not DRY_RUN:
                conn.execute(
                    text(f'DELETE FROM "{table.name}" WHERE tenant_id = ANY(:tids)'),
                    {"tids": list(tenant_ids)},
                )

    tenant_count = conn.execute(
        text('SELECT COUNT(*) FROM "tenants" WHERE id = ANY(:tids)'),
        {"tids": list(tenant_ids)},
    ).scalar()
    if tenant_count:
        print(f"tenants: {tenant_count} row(s)")
        total += tenant_count
        if not DRY_RUN:
            conn.execute(
                text('DELETE FROM "tenants" WHERE id = ANY(:tids)'), {"tids": list(tenant_ids)}
            )

    print(f"\nTotal rows {'that would be ' if DRY_RUN else ''}deleted: {total}")
    if DRY_RUN:
        print("DRY RUN -- no DELETE statements were issued.")
