"""
Checkout-first registration model tests (2026-09-04).

Model: no free account creation anywhere. Accounts are provisioned ONLY by
the Stripe webhook on checkout.session.completed (guest checkout).

These are pure-unit tests (no live server, no real Stripe, no DB) following
the pattern of test_webhook_get_and_read_gating.py. They validate:

1. /auth/register is a hard stop (410) — no free account door.
2. Google OAuth callback no longer creates user docs.
3. Guest-checkout endpoint validation rules (privileged emails, wingpoint block,
   plan/period validation, duplicate active account guard).
4. Webhook provisioner: user+onboarding+subscription created, idempotent on
   redelivery, privileged emails blocked, active plan stamped.
5. Middleware: never-paid accounts blocked from data reads; churned payers
   keep read access; READ_EXEMPT_PATHS honored; /api/trusts write exemption gone.
"""
import ast
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Static-source guarantees (no imports needed — parse the source directly)
# ---------------------------------------------------------------------------

def _load(path):
    return ast.parse((BACKEND_DIR / path).read_text())


def _fn_src(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment((BACKEND_DIR / "routers/auth.py").read_text(), node) or ""
    return ""


class TestRegisterEndpointDisabled:
    """Door #1: POST /api/auth/register must never create a user."""

    def test_register_is_hard_410_stop(self):
        src = (BACKEND_DIR / "routers/auth.py").read_text()
        # Extract the register function body
        start = src.index('async def register(')
        end = src.index('@router.post("/auth/login")')
        body = src[start:end]
        assert "410" in body, "register must raise HTTPException(status_code=410)"
        assert "db.users.insert_one" not in body, "register must not insert users"
        assert "db.users.update_one" not in body
        assert "insert_one" not in body, "register must not write any collection"

    def test_register_docstring_documents_checkout_first(self):
        src = (BACKEND_DIR / "routers/auth.py").read_text()
        start = src.index('async def register(')
        end = src.index('@router.post("/auth/login")')
        body = src[start:end]
        assert "checkout-first" in body.lower()


class TestGoogleOAuthSignupBlocked:
    """Door #2: Google OAuth must not create accounts."""

    def test_google_callback_has_no_user_insert(self):
        src = (BACKEND_DIR / "routers/auth.py").read_text()
        start = src.index('async def google_callback(')
        # google_callback runs to the next router decorator or EOF
        rest = src[start:]
        next_dec = rest.find('\n@router.')
        body = rest[:next_dec] if next_dec > 0 else rest
        assert "db.users.insert_one" not in body, (
            "google_callback must NOT create users (checkout-first)"
        )
        assert "signup blocked" in body or "signup_disabled" in body, (
            "google_callback must redirect new Google users to pricing"
        )


class TestWingPointProvisionUntouched:
    """Door #3: WingPoint provisioning is intentional and must still work."""

    def test_external_provision_still_creates_users(self):
        src = (BACKEND_DIR / "routers/external.py").read_text()
        assert "db.users.insert_one" in src, "WP provisioning must keep creating provisioned users"
        assert '"created_via": "wingpoint_provision"' in src


# ---------------------------------------------------------------------------
# Guest checkout endpoint validation (logic tests, no Stripe calls)
# ---------------------------------------------------------------------------

class TestGuestCheckoutValidation:
    """Shared validation logic for POST /api/subscription/guest-checkout."""

    @pytest.fixture
    def validate(self):
        """Import the real validator from the router module."""
        import sys
        sys.path.insert(0, str(BACKEND_DIR))
        from routers.subscriptions import _validate_guest_checkout
        return _validate_guest_checkout

    def _req(self, **kw):
        req = MagicMock()
        req.email = kw.get("email", "buyer@example.com")
        req.name = kw.get("name", "Test Buyer")
        req.plan_type = kw.get("plan_type", "trustee")
        return req

    @pytest.mark.asyncio
    async def test_wingpoint_blocked_for_guest(self, validate):
        """WingPoint plan requires a provisioned WP account — guest checkout blocked."""
        from fastapi import HTTPException
        with pytest.raises(Exception) as exc:
            await validate(self._req(plan_type="wingpoint"))
        assert "WingPoint" in str(exc.value)

    @pytest.mark.asyncio
    async def test_privileged_email_blocked(self, validate):
        req = self._req(email="contact@trustoffice.app")
        with pytest.raises(Exception):
            await validate(req)

    @pytest.mark.asyncio
    async def test_invalid_email_blocked(self, validate):
        with pytest.raises(Exception):
            await validate(self._req(email="not-an-email"))

    @pytest.mark.asyncio
    async def test_empty_name_blocked(self, validate):
        with pytest.raises(Exception):
            await validate(self._req(name="  "))

    @pytest.mark.asyncio
    async def test_valid_email_name_pass_through(self, validate):
        email, name = await validate(self._req(email="Buyer@Example.com ", name=" Jane "))
        assert email == "buyer@example.com"
        assert name == "Jane"


# ---------------------------------------------------------------------------
# Webhook provisioner (_provision_guest_account)
# ---------------------------------------------------------------------------

class _FakeCollection:
    """Minimal async mongo collection stand-in."""

    def __init__(self, store):
        self.store = store

    async def find_one(self, query, *a, **kw):
        return self.store.get("find_one_result")

    async def insert_one(self, doc):
        self.store["last_insert"] = doc
        return MagicMock()

    async def update_one(self, query, update, upsert=False):
        self.store["last_update"] = (query, update, upsert)
        return MagicMock()


class _FakeDB:
    def __init__(self):
        self.users = _FakeCollection({})
        self.user_onboarding = _FakeCollection({})
        self.subscriptions = _FakeCollection({})
        self.password_resets = _FakeCollection({})

    def __getitem__(self, name):
        return getattr(self, name, _FakeCollection({}))


def _fake_session(customer="cus_test123", stripe_email=None):
    s = MagicMock()
    s.customer = customer
    s.id = "cs_test_123"
    s.subscription = "sub_test_123"
    # Model real Stripe: customer_details is a StripeObject or None.
    if stripe_email is None:
        s.customer_details = None
    else:
        cd = MagicMock(spec=["to_dict"])
        cd.to_dict.return_value = {"email": stripe_email}
        s.customer_details = cd
    return s


class TestProvisionGuestAccount:
    @pytest.fixture
    def provision(self):
        import sys
        sys.path.insert(0, str(BACKEND_DIR))
        from routers.subscriptions import _provision_guest_account
        return _provision_guest_account

    @pytest.fixture
    def fresh_db(self):
        import routers.subscriptions as subs
        with patch.object(subs, "db", _FakeDB()) as fake:
            yield fake

    @pytest.mark.asyncio
    async def test_creates_user_onboarding_subscription(self, provision, fresh_db):
        metadata = {
            "guest_checkout": "1",
            "guest_email": "newpaid@example.com",
            "guest_name": "New Paid",
            "plan_type": "trustee",
            "billing_period": "monthly",
        }
        uid = await provision(_fake_session(), metadata, "trustee", "monthly")
        assert uid and uid.startswith("user_")
        # user doc written with no password and created_via=guest_checkout
        user_doc = fresh_db.users.store["last_insert"]
        assert user_doc["email"] == "newpaid@example.com"
        assert user_doc["password_hash"] is None
        assert user_doc["created_via"] == "guest_checkout"
        # onboarding doc written
        assert fresh_db.user_onboarding.store["last_insert"]["user_id"] == uid
        # subscription upsert written
        q, upd, upsert = fresh_db.subscriptions.store["last_update"]
        assert q == {"user_id": uid}
        assert upsert is True
        assert upd["$setOnInsert"]["plan_type"] == "trustee"

    @pytest.mark.asyncio
    async def test_idempotent_on_existing_user(self, provision):
        """Webhook redelivery must NOT create a duplicate account."""
        import routers.subscriptions as subs
        fake = _FakeDB()
        fake.users.store["find_one_result"] = {"user_id": "user_existing123", "email": "x"}
        with patch.object(subs, "db", fake):
            uid = await provision(_fake_session(), {
                "guest_checkout": "1", "guest_email": "x@example.com",
                "guest_name": "X", "plan_type": "trustee",
            }, "trustee", "monthly")
        assert uid == "user_existing123", f"must return the EXISTING user_id, got {uid}"
        # no duplicate insert
        assert "last_insert" not in fake.users.store

    @pytest.mark.asyncio
    async def test_privileged_email_blocked_at_provision(self, provision, fresh_db):
        uid = await provision(_fake_session(), {
            "guest_checkout": "1", "guest_email": "contact@trustoffice.app",
            "guest_name": "Admin Impersonator", "plan_type": "trustee",
        }, "trustee", "monthly")
        assert uid is None
        assert "last_insert" not in fresh_db.users.store

    @pytest.mark.asyncio
    async def test_missing_email_returns_none(self, provision, fresh_db):
        uid = await provision(_fake_session(), {"guest_checkout": "1"}, "trustee", "monthly")
        assert uid is None

    @pytest.mark.asyncio
    async def test_stripe_email_mismatch_wins(self, provision, fresh_db):
        """Payer edited their email at Stripe Checkout — provision with the
        Stripe-side email (the one that actually paid), not the modal email."""
        uid = await provision(
            _fake_session(stripe_email="actualpayer@example.com"),
            {"guest_checkout": "1", "guest_email": "modalemail@example.com",
             "guest_name": "Modal Name", "plan_type": "trustee"},
            "trustee", "monthly"
        )
        assert uid and uid.startswith("user_")
        user_doc = fresh_db.users.store["last_insert"]
        assert user_doc["email"] == "actualpayer@example.com"
        assert user_doc["stripe_customer_id"] == "cus_test123"

    @pytest.mark.asyncio
    async def test_user_doc_gets_stripe_customer_id(self, provision, fresh_db):
        """Lifecycle webhooks resolve users by stripe_customer_id on the user doc."""
        uid = await provision(_fake_session(customer="cus_lifecycle"), {
            "guest_checkout": "1", "guest_email": "lifecycle@example.com",
            "guest_name": "L", "plan_type": "trustee",
        }, "trustee", "monthly")
        user_doc = fresh_db.users.store["last_insert"]
        assert user_doc["stripe_customer_id"] == "cus_lifecycle"


class TestWebhookCheckoutCompletedGuest:
    """Behavior tests for the guest branch of _webhook_checkout_session_completed."""

    @pytest.mark.asyncio
    async def test_provision_failure_raises(self):
        """Provisioning failure must propagate (so the webhook dispatcher marks
        the event failed and Stripe retries) — never silently return 'ok'."""
        import routers.subscriptions as subs
        fake = _FakeDB()
        fake.users.store["find_one_result"] = None  # no existing user
        with patch.object(subs, "db", fake), \
             patch.object(subs.db.users, "insert_one", side_effect=RuntimeError("mongo down")):
            with pytest.raises(Exception):
                await subs._provision_guest_account(
                    _fake_session(), {
                        "guest_checkout": "1", "guest_email": "boom@example.com",
                        "guest_name": "B", "plan_type": "trustee",
                    }, "trustee", "monthly"
                )


# ---------------------------------------------------------------------------
# Middleware behavior (parse-based: verifies wiring, not full dispatch)
# ---------------------------------------------------------------------------

class TestMiddlewareCheckoutFirst:

    def test_read_exempt_paths_defined(self):
        src = (BACKEND_DIR / "server.py").read_text()
        assert "READ_EXEMPT_PATHS" in src
        # Auth + subscription state must be readable without payment
        for p in ('"/api/auth/me"', '"/api/subscription"'):
            assert p in src

    def test_trusts_write_exemption_removed(self):
        """First-trust write exemption (the freemium backdoor) is gone."""
        src = (BACKEND_DIR / "server.py").read_text()
        write_block = src[src.index("WRITE_EXEMPT_PATHS = {"):src.index("READ_EXEMPT_PATHS")]
        assert '"/api/trusts"' not in write_block, (
            "/api/trusts must not be write-exempt — unpaid accounts must not create trusts"
        )

    def test_unpaid_get_blocked_with_403_style_response(self):
        src = (BACKEND_DIR / "server.py").read_text()
        mid = src[src.index("class SubscriptionMiddleware"):]
        # The GET gate must check READ_EXEMPT_PATHS or active state
        assert "READ_EXEMPT_PATHS or state.is_active" in mid
        # Churned payers keep read access
        assert "_user_has_payment_history" in mid

    def test_payment_history_checks_both_stripe_sources(self):
        src = (BACKEND_DIR / "server.py").read_text()
        fn = src[src.index("async def _user_has_payment_history"):]
        fn = fn[:fn.find("\nasync def ") if "\nasync def " in fn else fn.find("\nclass ")]
        assert "stripe_subscription_id" in fn
        assert "payment_transactions" in fn


# ---------------------------------------------------------------------------
# Webhook wiring: guest metadata routes to provisioner
# ---------------------------------------------------------------------------

class TestWebhookWiring:
    def test_checkout_completed_handles_guest_metadata(self):
        src = (BACKEND_DIR / "routers/subscriptions.py").read_text()
        start = src.index("async def _webhook_checkout_session_completed")
        body = src[start:start + 4000]
        assert 'guest_checkout' in body, "webhook must branch on guest_checkout metadata"
        assert "_provision_guest_account" in body

    def test_provisioner_exists_and_idempotent(self):
        src = (BACKEND_DIR / "routers/subscriptions.py").read_text()
        fn = src[src.index("async def _provision_guest_account"):]
        fn = fn[:fn.index("\nasync def _send_activation_emails_safe")]
        assert "find_one" in fn  # existing-user check
        assert "users.insert_one" in fn or "users\n" in fn or "db.users.insert_one" in fn
        assert "user_onboarding" in fn
        assert "subscriptions" in fn