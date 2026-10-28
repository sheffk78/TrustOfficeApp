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


# ==================== checkout-path membership (2026-10-28) ====================
# The pricing-page checkout path may carry a wp_ref for legacy/admin-created
# accounts that pre-date identity stamping. Contracts pinned here:
#   1. normalize_wp_ref only accepts provisioning-ref shapes (WP-XXXXXXXX-XXXX)
#   2. wp_ref_belongs_to_referrer verifies user+ref AGAINST the ledger
#   3. garbage refs never reach the ledger
#   4. CheckoutRequest accepts wp_ref; the guard verifies BEFORE the 403
#   5. guest checkout stays blocked (can't pre-verify without an account)

import re  # noqa: E402

from services.wingpoint_identity import (  # noqa: E402
    normalize_wp_ref,
    wp_ref_belongs_to_referrer,
)


def _make_db_with(doc):
    """Fake db.external_provisions that captures the last find_one query."""

    class ProvisionColl:
        last_query = None
        calls = 0

        async def find_one(self, query, projection=None):
            ProvisionColl.calls += 1
            ProvisionColl.last_query = query
            return doc

    class FakeDB:
        external_provisions = ProvisionColl()

    ProvisionColl.calls = 0
    ProvisionColl.last_query = None
    return FakeDB()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("WP-AB12CD34-5678", "WP-AB12CD34-5678"),        # canonical
        ("  wp-ab12cd34-5678  ", "WP-AB12CD34-5678"),    # trim + case-fold up
        ("WP-ab12CD34-5678", "WP-AB12CD34-5678"),        # mixed case normalized
        ("ref=wp", None),                                # marketing ref is NOT a WP ref
        ("wp", None),
        ("", None),
        (None, None),
        (12345, None),
        ("WP-SHORT-1", None),                            # malformed shape
        ("WP-AB12CD34-56789", None),                     # wrong trailing length
    ],
)
def test_normalize_wp_ref(raw, expected):
    assert normalize_wp_ref(raw) == expected


@pytest.mark.asyncio
async def test_wp_ref_ledger_match_is_user_scoped():
    """A ledger hit only counts when the row belongs to THIS user_id."""
    db = _make_db_with({"_id": "x"})
    assert await wp_ref_belongs_to_referrer(db, "user_abc", "wp-ab12cd34-5678") is True
    q = db.external_provisions.last_query
    assert q["wingpoint_ref"] == "WP-AB12CD34-5678"
    assert q["user_id"] == "user_abc"


@pytest.mark.asyncio
async def test_wp_ref_ledger_mismatch_returns_false():
    db = _make_db_with(None)
    assert await wp_ref_belongs_to_referrer(db, "user_abc", "WP-AB12CD34-5678") is False
    # Even on miss, the probe stayed user-scoped
    assert db.external_provisions.last_query["user_id"] == "user_abc"


@pytest.mark.asyncio
async def test_wp_ref_garbage_never_hits_ledger():
    db = _make_db_with({"_id": "x"})
    assert await wp_ref_belongs_to_referrer(db, "user_abc", "ref=wp") is False
    assert await wp_ref_belongs_to_referrer(db, "", "WP-AB12CD34-5678") is False
    assert await wp_ref_belongs_to_referrer(db, None, "WP-AB12CD34-5678") is False
    assert db.external_provisions.calls == 0, "malformed input must not query the ledger"


def test_checkout_request_carries_wp_ref():
    """CheckoutRequest must accept wp_ref so verified legacy accounts can pass membership."""
    src = (BACKEND / "models.py").read_text()
    m = re.search(r"class CheckoutRequest\(BaseModel\):.*?(?=\nclass )", src, re.DOTALL)
    assert m, "CheckoutRequest class not found"
    assert "wp_ref" in m.group(0), "CheckoutRequest lost the wp_ref field"


def test_checkout_guard_verifies_before_403():
    """The logged-in checkout guard must try ledger verification before rejecting."""
    src = (BACKEND / "routers" / "subscriptions.py").read_text()
    assert "wp_ref_belongs_to_referrer(" in src, "guard does not call wp_ref_belongs_to_referrer"
    # Guard order: doc identity first, ledger probe second, 403 last.
    i_doc = src.find("is_wingpoint_user(user_doc)")
    i_ledger = src.find("wp_ref_belongs_to_referrer(")
    i_403 = src.find("only available to WingPoint customers", i_ledger)
    assert -1 < i_doc < i_ledger < i_403, "guard verification order regressed"


def test_guest_checkout_still_blocks_wingpoint():
    """Guest checkout can't verify membership pre-account — must stay blocked."""
    src = (BACKEND / "routers" / "subscriptions.py").read_text()
    m = re.search(
        r"async def _validate_guest_checkout.*?(?=\nasync def |\nclass |\Z)", src, re.DOTALL
    )
    assert m and "wingpoint" in m.group(0) and "403" in m.group(0), (
        "guest-checkout wingpoint block regressed"
    )