#!/usr/bin/env python3
"""
TrustOffice Health Monitor — runs every 15 minutes via cron.

Checks:
  1. API health endpoint (https://api.trustoffice.app/health)
  2. Frontend load (https://app.trustoffice.app)
  3. Key API endpoints return 401 (auth enforced)
  4. Admin API stats/summary (if key available)

If any check fails, prints an alert to stdout (cron delivers to Discord).
If all pass, prints a silent OK (cron suppresses on no change).

Exit 0 = healthy, Exit 1 = unhealthy.
"""

import requests
import os
import sys
import json
from datetime import datetime

API_BASE = "https://api.trustoffice.app"
APP_URL = "https://app.trustoffice.app"

# Admin API key
ADMIN_API_KEY = ""
_key_path = os.path.expanduser("~/.hermes/secrets/trustoffice-admin-api.key")
if os.path.exists(_key_path):
    with open(_key_path) as f:
        ADMIN_API_KEY = f.read().strip()

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"✅ {name}")
    else:
        print(f"❌ {name} — {detail}")
        failures.append(name)


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"TrustOffice Health Check — {now}")

    # 1. API health
    try:
        r = requests.get(f"{API_BASE}/health", timeout=10)
        data = r.json() if r.status_code == 200 else {}
        check("API /health", r.status_code == 200 and data.get("db") == "connected",
              f"status={r.status_code}, body={r.text[:100]}")
    except Exception as e:
        check("API /health", False, str(e))

    # 2. Frontend
    try:
        r = requests.get(APP_URL, timeout=10)
        check("Frontend app.trustoffice.app", r.status_code == 200,
              f"status={r.status_code}")
    except Exception as e:
        check("Frontend app.trustoffice.app", False, str(e))

    # 3. Auth enforcement on key endpoints
    protected_endpoints = [
        "/api/trusts",
        "/api/calendar/events",
        "/api/minutes",
        "/api/beneficiaries",
        "/api/distributions",
        "/api/audit-logs",
    ]
    for ep in protected_endpoints:
        try:
            r = requests.get(f"{API_BASE}{ep}", timeout=10)
            check(f"Auth: {ep}", r.status_code in (401, 403, 422),
                  f"status={r.status_code} (should be 401/403)")
        except Exception as e:
            check(f"Auth: {ep}", False, str(e))

    # 4. Admin API (if key available)
    if ADMIN_API_KEY:
        try:
            r = requests.get(
                f"{API_BASE}/api/admin-api/users?limit=1",
                headers={"X-Admin-API-Key": ADMIN_API_KEY},
                timeout=10,
            )
            check("Admin API /users", r.status_code == 200,
                  f"status={r.status_code}")
        except Exception as e:
            check("Admin API /users", False, str(e))

        # Stats summary (known to 500 due to Stripe bug — track as warning, not failure)
        try:
            r = requests.get(
                f"{API_BASE}/api/admin-api/stats/summary",
                headers={"X-Admin-API-Key": ADMIN_API_KEY},
                timeout=15,
            )
            if r.status_code == 500:
                print(f"⚠️  Admin API /stats/summary — 500 (known Stripe revenue bug)")
            else:
                check("Admin API /stats/summary", r.status_code == 200,
                      f"status={r.status_code}")
        except Exception as e:
            check("Admin API /stats/summary", False, str(e))

    # Summary
    print("")
    if failures:
        print(f"🔴 {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    else:
        print("🟢 All checks passed")
        sys.exit(0)


if __name__ == "__main__":
    main()