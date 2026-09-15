# ==================== 6. Refresh cookie path (2026-09-15 regression) ====================
# Root cause of "logged out every ~30 minutes": refresh_token cookie was set with
# path="/auth" but the endpoint is mounted at /api/auth/refresh — the browser never
# sent the cookie back, so silent renewal 401'd and every user was hard-logged-out
# at access-token expiry. Cookie path MUST be "/api/auth" (the mounted prefix).

# Reuse the in-process FastAPI harness from the session-manager suite
# (FakeDB + TestClient wired to routers.auth under /api).
from test_session_manager import fake_db, client_a  # noqa: F401

import pytest


@pytest.fixture
def https_client_a(fake_db):
    """client_a over https — httpx TestClient refuses to send secure=True
    cookies over http://, which would falsely fail the refresh roundtrip."""
    import test_session_manager as tsm
    client = tsm._make_client(fake_db, "user_a", "a@trustoffice.app")
    client.base_url = "https://testserver"
    return client


def _cookie_sets(resp, name):
    """All set-cookie headers for a cookie name as (path, max_age) tuples."""
    import http.cookies
    out = []
    for raw in resp.headers.get_list("set-cookie"):
        c = http.cookies.SimpleCookie()
        c.load(raw)
        if name in c:
            m = c[name]
            out.append((m.get("path"), m.get("max-age")))
    return out


def test_login_sets_refresh_cookie_at_api_auth_path(https_client_a):
    """/api/auth/login must scope refresh_token to /api/auth (browser sends it back)."""
    resp = https_client_a.post(
        "/api/auth/login",
        json={"email": "a@trustoffice.app", "password": "CurrentPass123"},
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0 Safari/537.36"},
    )
    assert resp.status_code == 200, resp.text
    sets = _cookie_sets(resp, "refresh_token")
    assert sets, "login must set refresh_token cookie"
    paths = {p for (p, _ma) in sets}
    assert "/api/auth" in paths, f"refresh_token cookie must be scoped to /api/auth, got {paths}"


def test_full_refresh_roundtrip(https_client_a, fake_db):
    """Login -> expire access token -> refresh -> new access token works.

    Simulates the 30-minute kickout scenario: access token expired, refresh
    cookie must reach /api/auth/refresh and rotate into a fresh session.
    """
    import jwt as pyjwt
    import dependencies

    login = https_client_a.post(
        "/api/auth/login",
        json={"email": "a@trustoffice.app", "password": "CurrentPass123"},
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0 Safari/537.36"},
    )
    assert login.status_code == 200, login.text

    # Expire the access-token cookie in the client's jar (30-min kickout moment).
    https_client_a.cookies.set("session_token", "expired-garbage", path="/")

    r = https_client_a.post("/api/auth/refresh")
    assert r.status_code == 200, f"refresh must succeed with cookie present: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("token"), "refresh must mint a new access token"
    payload = pyjwt.decode(body["token"], dependencies.JWT_SECRET or "x", algorithms=[dependencies.JWT_ALGORITHM])
    assert payload["user_id"] == "user_a"
    assert payload["type"] == "access"

    # New refresh cookie must be set at the endpoint path (rotation).
    sets = _cookie_sets(r, "refresh_token")
    assert sets and "/api/auth" in {p for (p, _ma) in sets}

    # Rotation: exactly one live refresh token left for the user.
    live = [d for d in fake_db.refresh_tokens.docs if d.get("revoked") is False]
    assert len(live) == 1, f"expected exactly 1 live refresh token after rotation, got {len(live)}"


def test_refresh_without_cookie_rejected(https_client_a):
    """No refresh cookie -> 401 (endpoint contract unchanged)."""
    https_client_a.post(
        "/api/auth/login",
        json={"email": "a@trustoffice.app", "password": "CurrentPass123"},
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0 Safari/537.36"},
    )
    https_client_a.cookies.clear()
    r = https_client_a.post("/api/auth/refresh")
    assert r.status_code == 401


def test_logout_clears_refresh_cookie(https_client_a):
    """Logout must clear refresh_token at the new path (and the legacy one)."""
    https_client_a.post(
        "/api/auth/login",
        json={"email": "a@trustoffice.app", "password": "CurrentPass123"},
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0 Safari/537.36"},
    )
    r = https_client_a.post("/api/auth/logout")
    assert r.status_code == 200, r.text
    dels = []
    for raw in r.headers.get_list("set-cookie"):
        import http.cookies
        c = http.cookies.SimpleCookie()
        c.load(raw)
        if c.get("refresh_token") is not None and c["refresh_token"].value == "":
            dels.append(c["refresh_token"].get("path"))
    assert "/api/auth" in dels, f"logout must clear refresh_token at /api/auth, cleared {dels}"
    assert "/auth" in dels, f"logout must also clear legacy-path cookie, cleared {dels}"