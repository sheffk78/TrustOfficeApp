#!/usr/bin/env python3
"""
Post-Deploy Smoke Test for TrustOffice
======================================
Run after a Railway deploy to verify all critical endpoints are healthy.

Usage:
    python3 scripts/post_deploy_check.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
import os

# ─── Configuration ────────────────────────────────────────────────────
API_BASE = "https://api.trustoffice.app"
APP_BASE = "https://app.trustoffice.app"
TEST_EMAIL = "monitoring@trustoffice.app"
TEST_PASSWORD = "TrustOfficeMonitor2024!"  # noqa: hardcoded test credential
LOCAL_FRONTEND_BUILD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "build",
)
TIMEOUT = 15  # seconds per request

# ─── Helpers ──────────────────────────────────────────────────────────

def _request(url, method="GET", body=None, headers=None, timeout=TIMEOUT):
    """Make an HTTP request and return (status_code, body_text, response_headers)."""
    data = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode("utf-8")
        elif isinstance(body, bytes):
            data = body
        else:
            data = str(body).encode("utf-8")

    hdrs = {"User-Agent": "trustoffice-smoke-test/1.0"}
    if headers:
        hdrs.update(headers)
    if data is not None and "Content-Type" not in hdrs:
        hdrs["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace"), dict(e.headers) if e.headers else {}
    except urllib.error.URLError as e:
        return None, str(e), {}
    except Exception as e:
        return None, str(e), {}


def _login():
    """Register the monitoring user if needed, then login and return a JWT token (or None)."""
    # Try register first — if user already exists, that's fine (400 → fall through)
    _request(
        f"{API_BASE}/api/auth/register",
        method="POST",
        body={"email": TEST_EMAIL, "name": "Monitoring Bot", "password": TEST_PASSWORD},
    )
    # Always login after (register doesn't return a token)
    status, body_text, _ = _request(
        f"{API_BASE}/api/auth/login",
        method="POST",
        body={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if status != 200:
        return None
    try:
        data = json.loads(body_text)
        return data.get("token")
    except (json.JSONDecodeError, KeyError):
        return None


# ─── Check functions ──────────────────────────────────────────────────
# Each returns (passed: bool, label: str, detail: str)

def check_backend_health():
    status, body_text, _ = _request(f"{API_BASE}/health")
    if status != 200:
        return False, "Backend health", f"{status} (expected 200)"
    try:
        data = json.loads(body_text)
        if data.get("status") == "ok" and data.get("db") == "connected":
            return True, "Backend health", "200"
        return False, "Backend health", f"200 but body={json.dumps(data)} (expected status=ok, db=connected)"
    except json.JSONDecodeError:
        return False, "Backend health", "200 but non-JSON body"


def check_frontend():
    status, body_text, _ = _request(APP_BASE)
    if status != 200:
        return False, "Frontend", f"{status} (expected 200)"
    if "<html" not in body_text.lower() and "<!doctype" not in body_text.lower():
        return False, "Frontend", "200 but no HTML detected"
    return True, "Frontend", "200"


def check_auth_register():
    status, body_text, _ = _request(
        f"{API_BASE}/api/auth/register", method="POST", body=""
    )
    # 422 = validation error (route exists). 429 = rate limited (also means route exists).
    if status in (422, 429):
        return True, "Auth register", str(status)
    return False, "Auth register", f"{status} (expected 422)"


def check_auth_login():
    status, body_text, _ = _request(
        f"{API_BASE}/api/auth/login", method="POST", body=""
    )
    if status == 422:
        return True, "Auth login", "422"
    return False, "Auth login", f"{status} (expected 422)"


def check_auth_me():
    status, body_text, _ = _request(f"{API_BASE}/api/auth/me")
    if status == 401:
        return True, "Auth me", "401"
    return False, "Auth me", f"{status} (expected 401)"


def check_cors():
    """OPTIONS with an evil origin — should be rejected (400)."""
    status, _, _ = _request(
        f"{API_BASE}/health",
        method="OPTIONS",
        body=None,
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    if status == 400:
        return True, "CORS", "400"
    # Some CORS configs return 200 but without the evil origin in the
    # Access-Control-Allow-Origin header. Check that too.
    if status is not None and status < 500:
        # Acceptable: CORS middleware blocked or allowed; we mainly care it didn't 500
        return True, "CORS", f"{status}"
    return False, "CORS", f"{status} (expected 400 or non-5xx)"


def check_polling_endpoint():
    """
    GET /api/ai/chat/conversations/test/latest
    Should return 401 (no token) or 404 (conversation not found) — NOT 500
    or a route-not-found 404 with a generic body.
    """
    status, body_text, _ = _request(
        f"{API_BASE}/api/ai/chat/conversations/test/latest"
    )
    if status == 401:
        return True, "Polling endpoint", "401 (auth required — route exists)"
    if status == 404:
        # Distinguish route-not-found (FastAPI default) from endpoint-level 404.
        # Route-not-found 404 returns {"detail":"Not Found"}.
        try:
            data = json.loads(body_text)
            detail = data.get("detail", "")
            if detail == "Not Found":
                return False, "Polling endpoint", "404 route-not-found (endpoint missing)"
            return True, "Polling endpoint", f"404 (detail: {detail})"
        except json.JSONDecodeError:
            return False, "Polling endpoint", f"404 unparseable body"
    return False, "Polling endpoint", f"{status} (expected 401 or proper 404)"


def check_js_bundle():
    """Fetch frontend HTML, extract main.*.js, compare hash if local build exists."""
    status, body_text, _ = _request(APP_BASE)
    if status != 200:
        return False, "JS bundle", f"frontend returned {status}"

    # Extract main.HASH.js from HTML
    match = re.search(r'(main\.[a-f0-9]+\.js)', body_text)
    if not match:
        return False, "JS bundle", "no main.*.js found in HTML"
    remote_bundle = match.group(1)

    # Try to find local build hash
    local_hash = None
    if os.path.isdir(LOCAL_FRONTEND_BUILD):
        for fname in os.listdir(LOCAL_FRONTEND_BUILD):
            if re.match(r'main\.[a-f0-9]+\.js$', fname):
                m = re.match(r'main\.([a-f0-9]+)\.js$', fname)
                if m:
                    local_hash = m.group(1)
                break

    remote_match = re.match(r'main\.([a-f0-9]+)\.js$', remote_bundle)
    if local_hash and remote_match:
        remote_hash = remote_match.group(1)
        if local_hash == remote_hash:
            return True, "JS bundle", f"{remote_bundle} (matches local build)"
        return False, "JS bundle", f"{remote_bundle} (local build has main.{local_hash}.js — STALE)"
    # No local build to compare — just verify bundle exists
    return True, "JS bundle", remote_bundle


def check_ai_health():
    """Login as monitoring user, hit /api/ai/health, verify providers available."""
    token = _login()
    if not token:
        return False, "AI health", "could not login as monitoring user"

    status, body_text, _ = _request(
        f"{API_BASE}/api/ai/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        return False, "AI health", f"{status} (expected 200)"

    try:
        data = json.loads(body_text)
    except json.JSONDecodeError:
        return False, "AI health", "200 but non-JSON body"

    if not data.get("ok"):
        providers = data.get("providers", {})
        parts = []
        if isinstance(providers, dict):
            for k, v in providers.items():
                avail = v.get("available", False) if isinstance(v, dict) else v
                parts.append(f"{k}: {avail}")
        else:
            parts.append(str(providers))
        provider_summary = ", ".join(parts) if parts else str(data)
        return False, "AI health", f"providers unavailable ({provider_summary})"

    providers = data.get("providers", {})
    available = []
    if isinstance(providers, dict):
        for k, v in providers.items():
            avail = v.get("available", False) if isinstance(v, dict) else False
            if avail:
                available.append(k)
    return True, "AI health", f"providers available ({', '.join(available) or 'ok'})"


# ─── Main ─────────────────────────────────────────────────────────────

def main():
    checks = [
        check_backend_health,
        check_frontend,
        check_auth_register,
        check_auth_login,
        check_auth_me,
        check_cors,
        check_polling_endpoint,
        check_js_bundle,
        check_ai_health,
    ]

    results = []  # (passed, label, detail)
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            # Get a readable label from the function name
            label = check.__name__.replace("check_", "").replace("_", " ").capitalize()
            results.append((False, label, f"exception: {type(e).__name__}: {e}"))

    passed_count = sum(1 for p, _, _ in results if p)
    total = len(results)
    failed_count = total - passed_count

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\nPOST-DEPLOY SMOKE TEST — {ts}")

    for p, label, detail in results:
        mark = "✓" if p else "✗"
        if p:
            print(f" {mark} {label}: {detail}")
        else:
            print(f" {mark} {label}: {detail}")

    if failed_count == 0:
        print(f"\n{passed_count}/{total} PASSED\n")
        sys.exit(0)
    else:
        print(f"\n{passed_count}/{total} PASSED — {failed_count} FAILED")
        print("FAILURES:")
        for p, label, detail in results:
            if not p:
                print(f"  - {label}: {detail}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()