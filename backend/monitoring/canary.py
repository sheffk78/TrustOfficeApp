#!/usr/bin/env python3
"""
TrustOffice Synthetic Canary — AI chat response time monitor.

Checks:
  1. GET  /health                         → 200 + {"status":"ok"}
  2. GET  /                               → 200 (frontend)
  3. POST /api/auth/login (or register)   → JWT token
  4. GET  /api/auth/me  (with JWT)        → 200
  5. GET  /api/ai/health (with JWT)        → 200 + providers available
  6. POST /api/ai/chat/stream (SSE)        → measure ttfb + total time

Thresholds:
  - time-to-first-token >  5s → WARNING   (exit 1)
  - time-to-first-token > 10s → CRITICAL   (exit 2)
  - Any endpoint failure            → CRITICAL   (exit 2)
  - AI provider unavailable         → CRITICAL   (exit 2)

Output: one-line status, e.g.
  OK — ttfb: 2.1s, total: 8.3s
  CRITICAL — ttfb: 12.5s, total: 45.2s

Stdlib only (urllib, json, time). No pip dependencies.
"""

import json
import sys
import time
import urllib.request
import urllib.error

# ==================== CONFIGURATION ====================

API_BASE = "https://api.trustoffice.app"
FRONTEND_URL = "https://app.trustoffice.app"

TEST_EMAIL = "monitoring@trustoffice.app"
TEST_PASSWORD = "TrustOfficeCanary2024!"
TEST_NAME = "Monitoring Canary"

# Thresholds (seconds)
TTFB_WARN = 5.0
TTFB_CRITICAL = 10.0

# HTTP timeout for non-streaming requests
HTTP_TIMEOUT = 15

# Test message for chat endpoint
TEST_MESSAGE = "What is a trust?"


# ==================== HTTP HELPERS ====================

DEFAULT_UA = "TrustOfficeCanary/1.0 (synthetic monitoring; +https://trustoffice.app)"


def http_request(method, url, body=None, headers=None, timeout=HTTP_TIMEOUT):
    """Make an HTTP request, return (status_code, response_body_str_or_None, response_headers)."""
    if headers is None:
        headers = {}
    headers.setdefault("User-Agent", DEFAULT_UA)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        status = resp.getcode()
        raw = resp.read()
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = ""
        return status, text, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = ""
        return e.code, text, dict(e.headers) if hasattr(e, "headers") else {}
    except Exception as e:
        return -1, str(e), {}


def http_get(url, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("GET", url, body=None, headers=headers, timeout=timeout)


def http_post(url, body, headers=None, timeout=HTTP_TIMEOUT):
    return http_request("POST", url, body=body, headers=headers, timeout=timeout)


# ==================== SSE STREAMING ====================

def stream_sse(url, body, headers, timeout=30):
    """
    Open a POST connection and read the SSE stream line-by-line.
    Returns:
      ttfb: float or None (time to first SSE event)
      ttft: float or None (time to first 'token' event)
      total: float (total time from request start to stream end)
      events: list of (event_type, data_dict)
      error: str or None
    """
    data = json.dumps(body).encode("utf-8")
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("User-Agent", DEFAULT_UA)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    start = time.monotonic()
    ttfb = None
    ttft = None
    events = []

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        raw = e.read()
        try:
            text = raw.decode("utf-8")
        except Exception:
            text = ""
        return None, None, elapsed, [], f"HTTP {e.code}: {text[:200]}"
    except Exception as e:
        elapsed = time.monotonic() - start
        return None, None, elapsed, [], str(e)

    # Read the stream
    buf = b""
    current_event = None
    try:
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            # Process complete lines
            while b"\n" in buf:
                line_bytes, buf = buf.split(b"\n", 1)
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")

                if line.startswith("event: "):
                    current_event = line[len("event: "):].strip()
                    if ttfb is None:
                        ttfb = time.monotonic() - start
                elif line.startswith("data: "):
                    data_str = line[len("data: "):]
                    try:
                        data_obj = json.loads(data_str)
                    except Exception:
                        data_obj = data_str
                    if current_event:
                        events.append((current_event, data_obj))
                        if ttft is None and current_event == "token":
                            ttft = time.monotonic() - start
                    current_event = None  # reset after data
                elif line == "":
                    # Event boundary
                    current_event = None
                elif line.startswith(":"):
                    # SSE comment / heartbeat — ignore
                    pass
    except Exception as e:
        elapsed = time.monotonic() - start
        return ttfb, ttft, elapsed, events, f"Stream read error: {e}"

    total = time.monotonic() - start

    # Check if we got an error event
    for ev_type, ev_data in events:
        if ev_type == "error":
            msg = ev_data.get("message", "Unknown error") if isinstance(ev_data, dict) else str(ev_data)
            return ttfb, ttft, total, events, f"SSE error event: {msg}"

    return ttfb, ttft, total, events, None


# ==================== AUTHENTICATION ====================

def authenticate():
    """
    Register or login the test user, return JWT token or None.
    """
    # Try login first (account may already exist)
    status, text, _ = http_post(
        f"{API_BASE}/api/auth/login",
        {"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if status == 200:
        try:
            data = json.loads(text)
            token = data.get("token") or data.get("access_token")
            if token:
                return token, "login"
        except Exception:
            pass
    elif status == 401:
        pass  # wrong password — try register

    # Try registering
    status, text, _ = http_post(
        f"{API_BASE}/api/auth/register",
        {"email": TEST_EMAIL, "password": TEST_PASSWORD, "name": TEST_NAME},
    )
    if status == 200:
        # Registration might auto-login or return token — check
        try:
            data = json.loads(text)
            token = data.get("token") or data.get("access_token")
            if token:
                return token, "register"
        except Exception:
            pass
        # Need to login after registration
        status2, text2, _ = http_post(
            f"{API_BASE}/api/auth/login",
            {"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        if status2 == 200:
            try:
                data = json.loads(text2)
                token = data.get("token") or data.get("access_token")
                if token:
                    return token, "register+login"
            except Exception:
                pass
    elif status == 400 and "already registered" in text.lower():
        # Account exists but password doesn't match — can't proceed
        return None, f"email_exists_bad_password (login={status})"

    return None, f"auth_failed (login_status={status}, register_status={status})"


# ==================== TRUST MANAGEMENT ====================

def get_trust_id(token):
    """
    Get an existing trust_id for the user, or create one.
    Returns (trust_id, error_msg).
    """
    headers = {"Authorization": f"Bearer {token}"}

    # Try listing existing trusts
    status, text, _ = http_get(f"{API_BASE}/api/trusts", headers=headers)
    if status == 200:
        try:
            trusts = json.loads(text)
            if isinstance(trusts, list) and len(trusts) > 0:
                return trusts[0].get("trust_id"), None
        except Exception:
            pass
    else:
        return None, f"get_trusts_failed: HTTP {status}"

    # No trust found — create one
    status, text, _ = http_post(
        f"{API_BASE}/api/trusts",
        {"name": "Canary Test Trust", "trust_type": "family"},
        headers=headers,
    )
    if status == 200:
        try:
            trust = json.loads(text)
            return trust.get("trust_id"), None
        except Exception:
            pass
    elif status == 402:
        # Plan limit — try with different approach
        return None, f"create_trust_payment_required: HTTP {status}"

    return None, f"create_trust_failed: HTTP {status}: {text[:200]}"


# ==================== MAIN CHECK ====================

def run_checks():
    """
    Run all checks, return (exit_code, status_line, details_dict).
    """
    errors = []
    warnings = []

    # --- Check 1: Backend /health ---
    status, text, _ = http_get(f"{API_BASE}/health", timeout=10)
    if status != 200:
        errors.append(f"backend_health: HTTP {status}")
    else:
        try:
            data = json.loads(text)
            if data.get("status") != "ok":
                errors.append(f"backend_health: status={data.get('status')}")
        except Exception:
            errors.append("backend_health: invalid JSON")

    # --- Check 2: Frontend / ---
    status, _, _ = http_get(FRONTEND_URL, timeout=10)
    if status != 200:
        errors.append(f"frontend: HTTP {status}")

    # --- Check 3: Authenticate ---
    token, auth_info = authenticate()
    if not token:
        errors.append(f"auth: {auth_info}")
        # Can't continue without auth
        ttfb_str = "N/A"
        total_str = "N/A"
        status_line = f"CRITICAL — ttfb: {ttfb_str}, total: {total_str}"
        if errors:
            status_line += f" [{'; '.join(errors)}]"
        return 2, status_line, {"errors": errors, "warnings": warnings}

    # --- Check 4: GET /api/auth/me ---
    status, text, _ = http_get(
        f"{API_BASE}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        errors.append(f"auth_me: HTTP {status}")

    # --- Check 5: GET /api/ai/health ---
    status, text, _ = http_get(
        f"{API_BASE}/api/ai/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        errors.append(f"ai_health: HTTP {status}")
    else:
        try:
            ai_health = json.loads(text)
            if ai_health.get("ok") is False:
                errors.append("ai_health: providers unavailable")
            else:
                providers = ai_health.get("providers", {})
                any_available = False
                for prov_name, prov_info in providers.items():
                    if isinstance(prov_info, dict):
                        if not prov_info.get("available", False):
                            warnings.append(f"ai_provider_{prov_name}: unavailable")
                        else:
                            any_available = True
                if not any_available:
                    errors.append("ai_health: no providers available")
        except Exception as e:
            errors.append(f"ai_health: parse error: {e}")

    # --- Check 6: Get trust_id ---
    trust_id, trust_err = get_trust_id(token)
    if not trust_id:
        errors.append(f"trust: {trust_err}")
        ttfb_str = "N/A"
        total_str = "N/A"
        status_line = f"CRITICAL — ttfb: {ttfb_str}, total: {total_str}"
        if errors:
            status_line += f" [{'; '.join(errors)}]"
        if warnings:
            status_line += f" [warnings: {'; '.join(warnings)}]"
        return 2, status_line, {"errors": errors, "warnings": warnings}

    # --- Check 7: POST /api/ai/chat/stream (SSE) ---
    ttfb, ttft, total, events, stream_err = stream_sse(
        f"{API_BASE}/api/ai/chat/stream",
        {
            "message": TEST_MESSAGE,
            "trust_id": trust_id,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )

    if stream_err:
        errors.append(f"chat_stream: {stream_err}")
        ttfb_val = ttft if ttft is not None else (ttfb if ttfb is not None else None)
        ttfb_str = f"{ttfb_val:.1f}s" if ttfb_val is not None else "N/A"
        total_str = f"{total:.1f}s" if total else "N/A"
        status_line = f"CRITICAL — ttfb: {ttfb_str}, total: {total_str}"
        if errors:
            status_line += f" [{'; '.join(errors)}]"
        if warnings:
            status_line += f" [warnings: {'; '.join(warnings)}]"
        return 2, status_line, {"errors": errors, "warnings": warnings, "ttfb": ttfb, "ttft": ttft, "total": total}

    # Use time-to-first-token (ttft) as the primary metric, fall back to ttfb
    ttfb_val = ttft if ttft is not None else ttfb
    if ttfb_val is None:
        errors.append("chat_stream: no events received")
        status_line = f"CRITICAL — ttfb: N/A, total: {total:.1f}s"
        if errors:
            status_line += f" [{'; '.join(errors)}]"
        return 2, status_line, {"errors": errors, "warnings": warnings, "ttfb": ttfb, "ttft": ttft, "total": total}

    # Determine exit code based on thresholds
    if ttfb_val > TTFB_CRITICAL:
        errors.append(f"ttfb: {ttfb_val:.1f}s > {TTFB_CRITICAL}s")
        exit_code = 2
        level = "CRITICAL"
    elif ttfb_val > TTFB_WARN:
        warnings.append(f"ttfb: {ttfb_val:.1f}s > {TTFB_WARN}s")
        exit_code = 1
        level = "WARNING"
    else:
        exit_code = 0
        level = "OK"

    # If we have endpoint errors, escalate to critical
    if errors:
        exit_code = 2
        level = "CRITICAL"

    ttfb_str = f"{ttfb_val:.1f}s"
    total_str = f"{total:.1f}s"

    status_line = f"{level} — ttfb: {ttfb_str}, total: {total_str}"
    if errors:
        status_line += f" [{'; '.join(errors)}]"
    if warnings:
        status_line += f" [warnings: {'; '.join(warnings)}]"

    return exit_code, status_line, {
        "errors": errors,
        "warnings": warnings,
        "ttfb": ttfb,
        "ttft": ttft,
        "total": total,
        "events": len(events),
    }


# ==================== ENTRY POINT ====================

def main():
    exit_code, status_line, details = run_checks()
    print(status_line)

    # Print detailed info to stderr for debugging
    if exit_code != 0 or details.get("errors") or details.get("warnings"):
        for e in details.get("errors", []):
            print(f"  ERROR: {e}", file=sys.stderr)
        for w in details.get("warnings", []):
            print(f"  WARN: {w}", file=sys.stderr)
        if details.get("ttfb") is not None:
            print(f"  ttfb(first event): {details['ttfb']:.2f}s", file=sys.stderr)
        if details.get("ttft") is not None:
            print(f"  ttft(first token): {details['ttft']:.2f}s", file=sys.stderr)
        if details.get("total"):
            print(f"  total: {details['total']:.2f}s", file=sys.stderr)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()