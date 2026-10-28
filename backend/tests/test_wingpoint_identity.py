"""Regression tests: WingPoint identity must be one shared expression.

Root cause (2026-10-28): the is_wingpoint check existed as 7 inline copies;
3 of them missed created_via == "wingpoint_connect", so customers created via
the Connect Flow v2 signup saw regular TrustOffice pricing instead of their
WingPoint plan. This file pins the single-source-of-truth contract:
    services/wingpoint_identity.is_wingpoint_user()
"""
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from services.wingpoint_identity import is_wingpoint_user  # noqa: E402

# The stale inline comparison all seven historical copies shared:
_STALE_PATTERN = 'get("source") == "wingpoint"'


@pytest.mark.parametrize(
    "doc,expected",
    [
        # --- wp_ref carries attribution → WingPoint customer
        ({"wp_ref": "WP-AB12CD34-5678"}, True),
        # --- legacy source marking
        ({"source": "wingpoint"}, True),
        # --- provisioned via email/set-password flow
        ({"created_via": "wingpoint_provision"}, True),
        # --- created via Connect Flow v2 signup (the bug that shipped)
        ({"created_via": "wingpoint_connect"}, True),
        # --- negative cases: regular users must NOT match
        ({}, False),
        ({"email": "someone@gmail.com"}, False),
        ({"created_via": "guest_checkout"}, False),
        ({"created_via": "admin_create"}, False),
        ({"created_via": "org_queue_recurrence"}, False),
        ({"source": "google_oauth"}, False),
        ({"wp_ref": ""}, False),
        ({"wp_ref": None}, False),
        # --- combined docs
        ({"wp_ref": None, "created_via": "wingpoint_connect"}, True),
        ({"source": "wingpoint", "created_via": "guest_checkout"}, True),
    ],
)
def test_is_wingpoint_user_truth_table(doc, expected):
    assert is_wingpoint_user(doc) is expected


def test_is_wingpoint_user_none_and_empty():
    assert is_wingpoint_user(None) is False
    assert is_wingpoint_user({}) is False


def test_no_drifting_inline_copies():
    """No router may re-derive the check inline — the exact failure mode that
    hid wingpoint_connect accounts from the pricing surfaces."""
    routers_dir = BACKEND / "routers"
    offenders = []
    for py in sorted(routers_dir.glob("*.py")):
        if py.name == "__init__.py":
            continue
        source = py.read_text()
        if _STALE_PATTERN in source:
            offenders.append(str(py))
    assert not offenders, (
        f"inline is_wingpoint copies reintroduced in: {offenders}. "
        "Call services.wingpoint_identity.is_wingpoint_user() instead."
    )


def test_all_seven_call_sites_import_helper():
    """Each known historical call site must reference the helper."""
    sites = {
        "routers/auth.py": 4,
        "routers/subscriptions.py": 1,
        "routers/totp_2fa.py": 1,
        "routers/wingpoint_connect.py": 1,
        "routers/admin.py": 1,
    }
    for rel, min_uses in sites.items():
        source = (BACKEND / rel).read_text()
        assert (
            "from services.wingpoint_identity import is_wingpoint_user" in source
        ), f"{rel} missing helper import"
        uses = source.count("is_wingpoint_user(")
        assert uses >= min_uses, f"{rel} uses helper {uses}x, expected >= {min_uses}"


def test_services_module_has_no_router_dependencies():
    """The helper must stay dependency-free (pure function, stdlib only)."""
    source = (BACKEND / "services" / "wingpoint_identity.py").read_text()
    for banned in ("from database", "import pymongo", "from routers", "from fastapi"):
        assert banned not in source