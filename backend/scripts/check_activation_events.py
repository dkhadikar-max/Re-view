"""Read-only diagnostic: confirm the activation funnel actually recorded
events for a tenant, before that tenant's data is deleted by
cleanup_test_tenants.py. Prints rows only -- no writes.

Usage:
    railway run --service Re-view -- python scripts/check_activation_events.py verify-test-hotel-9068e8
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.db.session import engine

tenant_id = sys.argv[1] if len(sys.argv) > 1 else "verify-test-hotel-9068e8"

with engine.connect() as conn:
    rows = conn.execute(
        text(
            "SELECT event_type, created_at FROM activation_events "
            "WHERE tenant_id = :tid ORDER BY created_at"
        ),
        {"tid": tenant_id},
    ).fetchall()

if not rows:
    print(f"No activation_events rows found for tenant_id={tenant_id}")
else:
    print(f"activation_events for tenant_id={tenant_id}:")
    for event_type, created_at in rows:
        print(f"  {created_at}  {event_type}")
