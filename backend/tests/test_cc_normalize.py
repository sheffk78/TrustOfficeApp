"""Regression tests for CC normalization in notifications.py.

2026-09-15 (Jeff, #trustoffice-main): booking-email CC feature. The
_normalize_cc helper validates + normalizes a comma/semicolon CC list and
raises HTTPException(422) on any invalid address. It must return None for
empty input and a ", "-joined string otherwise.

Mirrors the isolation stub pattern from test_booking_email_endpoints.py so
notifications.py can be imported without APIRouter / env-var requirements.
"""
import sys
import types
import importlib.util
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# ---- Module-level stubs (same shape as the sibling test) ----
_routers_pkg = types.ModuleType("routers")
_routers_pkg.__path__ = [str(BACKEND / "routers")]
sys.modules["routers"] = _routers_pkg

_admin_stub = types.ModuleType("routers.admin")
_admin_stub.require_admin = lambda *a, **k: None
sys.modules["routers.admin"] = _admin_stub

_email_svc_mod = types.ModuleType("email_service")
_email_svc_mod.email_service = types.SimpleNamespace(
    send_email=lambda **kw: {"status": "ok"}
)
sys.modules["email_service"] = _email_svc_mod

_database_mod = types.ModuleType("database")
_database_mod.db = types.SimpleNamespace()
sys.modules["database"] = _database_mod

_deps_mod = types.ModuleType("dependencies")
_deps_mod.get_current_user = lambda *a, **k: None
sys.modules["dependencies"] = _deps_mod

_leads_stub = types.ModuleType("routers.leads")
_leads_stub._log_activity = lambda *a, **k: None
sys.modules["routers.leads"] = _leads_stub

# ---- Load notifications.py with stubs in place ----
_spec = importlib.util.spec_from_file_location(
    "notifications", BACKEND / "routers" / "notifications.py"
)
_notifications = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_notifications)

_normalize_cc = _notifications._normalize_cc
HTTPException = __import__("fastapi").HTTPException


def test_none_returns_none():
    assert _normalize_cc(None) is None


def test_empty_string_returns_none():
    assert _normalize_cc("") is None


def test_whitespace_only_returns_none():
    assert _normalize_cc("   ") is None


def test_single_address_passthrough():
    assert _normalize_cc("a@b.com") == "a@b.com"


def test_mixed_separators_and_whitespace():
    raw = " a@b.com ; c@d.com , e@f.com "
    assert _normalize_cc(raw) == "a@b.com, c@d.com, e@f.com"


def test_semicolon_only_list():
    assert _normalize_cc("x@y.com;z@w.com") == "x@y.com, z@w.com"


def test_invalid_not_an_email_raises_422():
    try:
        _normalize_cc("not-an-email")
    except HTTPException as e:
        assert e.status_code == 422
    else:
        raise AssertionError("expected HTTPException 422 for 'not-an-email'")


def test_invalid_missing_dot_raises_422():
    try:
        _normalize_cc("a@b")
    except HTTPException as e:
        assert e.status_code == 422
    else:
        raise AssertionError("expected HTTPException 422 for 'a@b'")


def test_invalid_embedded_space_raises_422():
    try:
        _normalize_cc("x y@z.com")
    except HTTPException as e:
        assert e.status_code == 422
    else:
        raise AssertionError("expected HTTPException 422 for 'x y@z.com'")


def test_mixed_valid_and_invalid_raises_422():
    try:
        _normalize_cc("good@ok.com; bad@nodot")
    except HTTPException as e:
        assert e.status_code == 422
    else:
        raise AssertionError("expected HTTPException 422 for mixed list")
