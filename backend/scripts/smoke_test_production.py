"""Production smoke test (CTO P3, follow-up to #56/#57).

Runs against the live production API and exits non-zero if any check
fails -- CI marks the run failed, which is the trigger for GitHub's own
failure-notification email on a scheduled workflow. Deliberately zero
third-party dependencies (stdlib `urllib` only), so it runs with no
`pip install` step and can't itself break from a dependency issue.

Checks, in order:
  1. GET  /health                -- app + DB reachable at all.
  2. POST /api/auth/login        -- log into a dedicated smoke-test
     account. If it doesn't exist yet (the very first run, ever),
     create it once via /api/demo/hotel-signup instead. One account,
     reused forever -- this does NOT create a new tenant on every run.
  3. GET  /api/dashboard/stats   -- the exact query that broke in #56
     (messages.detected_language).
  4. GET  /api/tasks             -- the exact query that broke in #56
     (tasks.correlation_id).

Config via environment variables (set as GitHub Actions secrets --
SMOKE_EMAIL/SMOKE_PASSWORD are smoke-test-only credentials, not real
user credentials):
  SMOKE_BASE_URL   e.g. https://re-visit-production.up.railway.app
  SMOKE_EMAIL      dedicated smoke-test account email
  SMOKE_PASSWORD   dedicated smoke-test account password
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get(
    "SMOKE_BASE_URL", "https://re-visit-production.up.railway.app"
)
TIMEOUT = 15


def _request(
    method: str, path: str, *, body: dict | None = None, token: str | None = None
) -> tuple[int, dict]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode()
    except urllib.error.URLError as exc:
        print(f"FAIL  request  {method} {path} -- unreachable: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    return status, payload


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}  {detail}", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    email = os.environ["SMOKE_EMAIL"]
    password = os.environ["SMOKE_PASSWORD"]

    status, body = _request("GET", "/health")
    check(
        "health",
        status == 200 and body.get("status") == "ok",
        f"status={status} body={body}",
    )

    status, body = _request(
        "POST", "/api/auth/login", body={"username": email, "password": password}
    )
    if status != 200:
        # First run ever -- the smoke account doesn't exist yet. Create it
        # once via the real trial-signup path (this is also the single
        # heaviest-write endpoint in the app, touching messages/tasks/
        # guests/reservations/offers/reviews -- the best canary for
        # exactly the class of schema drift that caused #56).
        print(f"Smoke account not found (status={status}) -- bootstrapping it via signup.")
        status, body = _request(
            "POST",
            "/api/demo/hotel-signup",
            body={
                "hotel_name": "ReVisit Smoke Test",
                "your_name": "Smoke Test",
                "email": email,
                "password": password,
                "city": "Berlin",
                "country": "Germany",
                "rooms": 10,
            },
        )
        check("signup (bootstrap smoke account)", status == 200, f"status={status} body={body}")
    else:
        check("login", status == 200, f"status={status} body={body}")

    token = body.get("access_token")
    check("access_token present", bool(token))

    status, _ = _request("GET", "/api/dashboard/stats", token=token)
    check("dashboard stats", status == 200, f"status={status}")

    status, _ = _request("GET", "/api/tasks", token=token)
    check("tasks", status == 200, f"status={status}")

    print("All production smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
