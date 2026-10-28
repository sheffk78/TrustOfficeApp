"""
WingPoint Connect Flow v2 — backend tests.

Spec: Kit/life/brands/TrustOffice/specs/2026-10-22-connect-flow-v2.md

Covers:
  1. Branch resolution: no account / never-activated / activated.
  2. The enumeration guardrail: the scoped endpoint requires a valid WP
     connect context (wp_ref + app_id + WingPoint redirect_url) and there is
     no generic public email-existence API.
  3. The account-claim flow: code request, code verify, password set on the
     EXISTING account (never a second account).
  4. Signup branch: account created bound to the WP email + wp_ref, trust
     re-linked, session issued.
  5. Rate limiting.
  6. Member emails are never written to app logs.

The suite uses a self-contained in-memory fake of the `db` object so it runs
without a live MongoDB (same pattern as test_lead_attribution.py).
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_connect_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-connect-flow")


# ==================== IN-MEMORY FAKE DB ====================

class FakeCollection:
    """Minimal in-memory MongoDB collection substitute.

    Documents are stored under a stable key so an update_one() that changes a
    field (e.g. re-pointing a trust's user_id) does NOT orphan the original
    document — the same doc is mutated in place under its original key.
    """

    def __init__(self):
        self.docs = {}
        self._seq = 0

    def _next_id(self):
        self._seq += 1
        return f"id_{self._seq:012x}"

    def _key_for(self, doc):
        return (
            doc.get("email")
            or doc.get("bucket")
            or doc.get("trust_id")
            or doc.get("user_id")
            or doc.get("_id")
            or self._next_id()
        )

    async def find_one(self, query, projection=None):
        for key, doc in self.docs.items():
            if all(doc.get(k) == v for k, v in query.items() if k not in ("$or", "$in")):
                return dict(doc)
        return None

    async def insert_one(self, doc):
        doc = dict(doc)
        key = self._key_for(doc)
        doc["_id"] = key
        self.docs[key] = doc
        return MagicMock()

    async def update_one(self, query, update, upsert=False):
        matched_key = None
        for key, doc in self.docs.items():
            if all(doc.get(k) == v for k, v in query.items() if k not in ("$or", "$in")):
                matched_key = key
                break

        if matched_key is None:
            if not upsert:
                return MagicMock(modified_count=0)
            doc = dict(query)
            key = self._key_for(doc)
            doc["_id"] = key
            self.docs[key] = doc
            matched_key = key

        doc = self.docs[matched_key]
        for k, v in (update.get("$set") or {}).items():
            doc[k] = v
        for k, v in (update.get("$setOnInsert") or {}).items():
            doc.setdefault(k, v)
        for k, v in (update.get("$inc") or {}).items():
            doc[k] = (doc.get(k) or 0) + v
        return MagicMock(modified_count=1)

    async def delete_one(self, query):
        for key, doc in list(self.docs.items()):
            if all(doc.get(k) == v for k, v in query.items() if k not in ("$or", "$in")):
                self.docs.pop(key, None)
                return MagicMock()
        return MagicMock()

    async def count_documents(self, query=None):
        return len(self.docs)


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()
        self.subscriptions = FakeCollection()
        self.user_onboarding = FakeCollection()
        self.trusts = FakeCollection()
        self.password_resets = FakeCollection()
        self.wingpoint_connect_codes = FakeCollection()
        self.wingpoint_connect_rate_limits = FakeCollection()
        self.audit_logs = FakeCollection()
        self.refresh_tokens = FakeCollection()
        self.partner_api_keys = FakeCollection()


@pytest.fixture
def fake_db(monkeypatch):
    """Install an in-memory fake DB into the wingpoint_connect router."""
    import routers.wingpoint_connect as wc

    db = FakeDB()
    monkeypatch.setattr(wc, "db", db)

    # Neutralize side-effecting collaborators.
    monkeypatch.setattr(wc, "log_audit_event", AsyncMock())
    monkeypatch.setattr(wc, "create_refresh_token_record", AsyncMock(return_value="refresh-raw"))
    monkeypatch.setattr(wc, "email_service", MagicMock(
        is_configured=True,
        send_wingpoint_connect_code_email=AsyncMock(return_value={"status": "sent"}),
    ))
    return db



# ==================== HELPERS ====================

VALID_REDIRECT = "https://wingpointtrust.com/trustoffice/callback?app_id=app_abc123"


def _ctx(email="member@example.com", wp_ref="WP-20260904-2517", app_id="app_abc123"):
    return {
        "wp_ref": wp_ref,
        "app_id": app_id,
        "email": email,
        "redirect_url": VALID_REDIRECT,
    }


def _request(client="203.0.113.9"):
    return SimpleNamespace(
        client=SimpleNamespace(host=client),
        headers={},
    )


def _run(coro):
    """Run a coroutine on a fresh event loop.

    A dedicated loop per call keeps these tests independent of whatever
    event-loop state the rest of the suite leaves behind (several other
    test modules close the shared loop).
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_user(db, email, password_hash=None, **extra):
    doc = {
        "user_id": f"user_{email}",
        "email": email,
        "name": "Test Member",
        "password_hash": password_hash,
        "created_at": "2026-10-01T00:00:00Z",
    }
    doc.update(extra)
    _run(db.users.insert_one(doc))
    return doc


def _hash(pw="Sup3rSecret!23"):
    from dependencies import hash_password
    return hash_password(pw)


# ==================== 1. BRANCH RESOLUTION ====================

class TestBranchResolution:
    """The three branches resolve off the member's email at connect entry."""

    def test_no_account_resolves_to_new(self, fake_db):
        import routers.wingpoint_connect as wc

        result = _run(wc.resolve_connect_state(
            wc.ResolveRequest(**_ctx()),
            request=_request(),
            _rl=None,
        ))
        assert result["state"] == "new"
        assert result["email_locked"] is True
        assert result["verification_required"] is False

    def test_resolve_does_not_echo_the_member_email(self, fake_db):
        """Prefill is UI-only — the server never reflects the email back."""
        import routers.wingpoint_connect as wc

        result = _run(wc.resolve_connect_state(
            wc.ResolveRequest(**_ctx()),
            request=_request(),
            _rl=None,
        ))
        assert "member@example.com" not in str(result)
        assert "prefill_email" not in result
        assert "email" not in result

    def test_never_activated_account_resolves_to_needs_activation(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None,
                   created_via="wingpoint_provision", source="wingpoint",
                   wp_ref="WP-20260904-2517")

        result = _run(wc.resolve_connect_state(
            wc.ResolveRequest(**_ctx()),
            request=_request(),
            _rl=None,
        ))
        assert result["state"] == "needs_activation"
        assert result["verification_required"] is True
        assert result["email_locked"] is True

    def test_wingpoint_provisioned_user_shape_detected(self, fake_db):
        """The real WP-provisioned user document (see routers/external.py
        _create_new_user) has NO password_hash key at all — the member was
        provisioned but never registered. That is John's state."""
        import routers.wingpoint_connect as wc

        _run(fake_db.users.insert_one({
            "user_id": "user_abc123",
            "email": "member@example.com",
            "name": "John Matthews",
            "is_admin": False,
            "created_at": "2026-10-01T00:00:00Z",
            "created_via": "wingpoint_provision",
            "source": "wingpoint",
            "wp_ref": "WP-20260904-2517",
        }))

        result = _run(wc.resolve_connect_state(
            wc.ResolveRequest(**_ctx()),
            request=_request(),
            _rl=None,
        ))
        assert result["state"] == "needs_activation"

    def test_activated_account_resolves_to_activated(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=_hash())

        result = _run(wc.resolve_connect_state(
            wc.ResolveRequest(**_ctx()),
            request=_request(),
            _rl=None,
        ))
        assert result["state"] == "activated"
        assert result["verification_required"] is False

    def test_email_lookup_is_case_insensitive(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=_hash())

        result = _run(wc.resolve_connect_state(
            wc.ResolveRequest(**_ctx(email="MEMBER@Example.COM")),
            request=_request(),
            _rl=None,
        ))
        assert result["state"] == "activated"

    def test_resolve_never_returns_a_second_account(self, fake_db):
        """Resolution is read-only — it must not create a user document."""
        import routers.wingpoint_connect as wc

        _run(wc.resolve_connect_state(
            wc.ResolveRequest(**_ctx()),
            request=_request(),
            _rl=None,
        ))
        assert len(fake_db.users.docs) == 0


# ==================== 2. ENUMERATION GUARDRAIL ====================

class TestEnumerationGuardrail:
    """The lookup is SCOPED — no generic public email-existence API."""

    def test_missing_wp_ref_is_rejected(self, fake_db):
        import routers.wingpoint_connect as wc

        ctx = _ctx()
        ctx["wp_ref"] = ""
        with pytest.raises(Exception) as exc:
            _run(wc.resolve_connect_state(
                wc.ResolveRequest(**ctx), request=_request(), _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400

    def test_missing_app_id_is_rejected(self, fake_db):
        import routers.wingpoint_connect as wc

        ctx = _ctx()
        ctx["app_id"] = ""
        ctx["redirect_url"] = "https://wingpointtrust.com/trustoffice/callback"
        with pytest.raises(Exception) as exc:
            _run(wc.resolve_connect_state(
                wc.ResolveRequest(**ctx), request=_request(), _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400

    def test_app_id_can_be_derived_from_the_redirect_url(self, fake_db):
        import routers.wingpoint_connect as wc

        ctx = _ctx()
        ctx["app_id"] = ""
        result = _run(wc.resolve_connect_state(
            wc.ResolveRequest(**ctx), request=_request(), _rl=None,
        ))
        assert result["app_id"] == "app_abc123"

    def test_non_wingpoint_redirect_is_rejected(self, fake_db):
        import routers.wingpoint_connect as wc

        ctx = _ctx()
        ctx["redirect_url"] = "https://evil.example.com/steal?app_id=app_abc123"
        with pytest.raises(Exception) as exc:
            _run(wc.resolve_connect_state(
                wc.ResolveRequest(**ctx), request=_request(), _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400

    def test_missing_redirect_url_is_rejected(self, fake_db):
        import routers.wingpoint_connect as wc

        ctx = _ctx()
        ctx["redirect_url"] = None
        with pytest.raises(Exception) as exc:
            _run(wc.resolve_connect_state(
                wc.ResolveRequest(**ctx), request=_request(), _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400

    def test_no_generic_public_email_lookup_endpoint_exists(self):
        """Static guard: the only email-existence endpoint is the scoped one.

        There must be NO public route that answers 'does this email exist'
        without a WP connect context.
        """
        source = (BACKEND_DIR / "routers" / "wingpoint_connect.py").read_text()
        # Every endpoint that reads the users collection by email must first
        # validate the connect context.
        assert source.count("_validate_connect_context(") >= 3
        # The scoped router exposes no GET endpoint (all are POST + context).
        assert '@router.get(' not in source

    def test_rate_limit_trips_on_repeated_resolves(self, fake_db):
        import routers.wingpoint_connect as wc

        # The per-email bucket allows 5 per 10 minutes.
        for _ in range(5):
            _run(wc.resolve_connect_state(
                wc.ResolveRequest(**_ctx()), request=_request(), _rl=None,
            ))
        with pytest.raises(Exception) as exc:
            _run(wc.resolve_connect_state(
                wc.ResolveRequest(**_ctx()), request=_request(), _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 429


# ==================== 3. ACCOUNT CLAIM (NEVER-ACTIVATED) ====================

class TestAccountClaim:
    """Provisioned-but-never-activated claims the EXISTING account."""

    def test_request_code_sends_for_unactivated_account(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None,
                   created_via="wingpoint_provision")

        result = _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx()),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        assert result["sent"] is True
        assert fake_db.wingpoint_connect_codes.docs  # a code was stored
        wc.email_service.send_wingpoint_connect_code_email.assert_called_once()

    def test_request_code_response_is_constant_for_unknown_email(self, fake_db):
        """No enumeration surface — the response is identical either way."""
        import routers.wingpoint_connect as wc

        known = _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx(email="known@example.com")),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        unknown = _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx(email="unknown@example.com")),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        assert known == unknown
        # And no code was stored for the unknown email.
        assert "unknown@example.com" not in fake_db.wingpoint_connect_codes.docs

    def test_request_code_not_sent_for_activated_account(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=_hash())

        _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx()),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        wc.email_service.send_wingpoint_connect_code_email.assert_not_called()

    def test_verify_claim_sets_password_on_the_existing_account(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None,
                   created_via="wingpoint_provision", source="wingpoint",
                   wp_ref="WP-20260904-2517")

        _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx()),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        code = wc.email_service.send_wingpoint_connect_code_email.call_args.kwargs["code"]

        result = _run(wc.verify_claim_code(
            wc.ClaimVerifyRequest(**_ctx(), code=code, new_password="BrandNewPass1"),
            request=_request(),
            response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        assert result["token"]
        assert result["user"]["email"] == "member@example.com"

        # The password landed on the EXISTING account.
        stored = _run(fake_db.users.find_one({"user_id": "user_member@example.com"}))
        assert stored["password_hash"]
        assert stored["password_hash"] != "BrandNewPass1"  # hashed
        from dependencies import verify_password
        assert verify_password("BrandNewPass1", stored["password_hash"])
        assert stored["activated_via"] == "wingpoint_connect_claim"

    def test_claim_never_creates_a_second_account(self, fake_db):
        """A provisioned member must not spawn a duplicate account."""
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None,
                   created_via="wingpoint_provision")

        _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx()),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        code = wc.email_service.send_wingpoint_connect_code_email.call_args.kwargs["code"]

        _run(wc.verify_claim_code(
            wc.ClaimVerifyRequest(**_ctx(), code=code, new_password="BrandNewPass1"),
            request=_request(),
            response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        assert len(fake_db.users.docs) == 1

    def test_wrong_code_is_rejected(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None)
        _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx()),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))

        with pytest.raises(Exception) as exc:
            _run(wc.verify_claim_code(
                wc.ClaimVerifyRequest(**_ctx(), code="000000", new_password="BrandNewPass1"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400
        # Password was NOT set.
        stored = _run(fake_db.users.find_one({"user_id": "user_member@example.com"}))
        assert not stored.get("password_hash")

    def test_weak_password_is_rejected(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None)
        with pytest.raises(Exception) as exc:
            _run(wc.verify_claim_code(
                wc.ClaimVerifyRequest(**_ctx(), code="123456", new_password="short"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400

    def test_claim_on_already_activated_account_conflicts(self, fake_db):
        """A claim must never overwrite an existing password."""
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=_hash("OrigPass123"))

        with pytest.raises(Exception) as exc:
            _run(wc.verify_claim_code(
                wc.ClaimVerifyRequest(**_ctx(), code="123456", new_password="BrandNewPass1"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 409

    def test_code_is_single_use(self, fake_db):
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None)
        _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx()),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        code = wc.email_service.send_wingpoint_connect_code_email.call_args.kwargs["code"]

        _run(wc.verify_claim_code(
            wc.ClaimVerifyRequest(**_ctx(), code=code, new_password="BrandNewPass1"),
            request=_request(),
            response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        with pytest.raises(Exception) as exc:
            _run(wc.verify_claim_code(
                wc.ClaimVerifyRequest(**_ctx(), code=code, new_password="AnotherPass2"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) in (400, 409)

    def test_code_attempts_are_capped(self, fake_db):
        """Brute-forcing the 6-digit code is bounded."""
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None)
        _run(wc.request_claim_code(
            wc.ClaimCodeRequest(**_ctx()),
            request=_request(),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))

        for _ in range(wc.CLAIM_CODE_MAX_ATTEMPTS + 1):
            try:
                _run(wc.verify_claim_code(
                    wc.ClaimVerifyRequest(**_ctx(), code="111111", new_password="BrandNewPass1"),
                    request=_request(),
                    response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                    background_tasks=MagicMock(add_task=MagicMock()),
                    _rl=None,
                ))
            except Exception:
                pass

        stored = _run(fake_db.users.find_one({"user_id": "user_member@example.com"}))
        assert not stored.get("password_hash")


# ==================== 4. SIGNUP BRANCH (NO ACCOUNT) ====================

class TestConnectSignup:
    """The no-account branch creates the account and hands off to payment."""

    def test_signup_creates_account_bound_to_wp_email(self, fake_db):
        import routers.wingpoint_connect as wc

        result = _run(wc.connect_signup(
            wc.SignupRequest(**_ctx(), name="John Matthews", password="BrandNewPass1"),
            request=_request(),
            response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        assert result["token"]
        assert result["user"]["email"] == "member@example.com"

        stored = _run(fake_db.users.find_one({"email": "member@example.com"}))
        assert stored["wp_ref"] == "WP-20260904-2517"
        assert stored["source"] == "wingpoint"
        assert stored["created_via"] == "wingpoint_connect"
        from dependencies import verify_password
        assert verify_password("BrandNewPass1", stored["password_hash"])

    def test_signup_creates_a_subscription_record_without_a_plan(self, fake_db):
        import routers.wingpoint_connect as wc

        result = _run(wc.connect_signup(
            wc.SignupRequest(**_ctx(), name="John", password="BrandNewPass1"),
            request=_request(),
            response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        sub = _run(fake_db.subscriptions.find_one({"user_id": result["user"]["user_id"]}))
        assert sub is not None
        assert sub["plan_type"] == "none"
        assert sub["wingpoint_ref"] == "WP-20260904-2517"

    def test_signup_attaches_the_provisioned_trust(self, fake_db):
        """A trust already carrying this wp_ref is re-linked to the account."""
        import routers.wingpoint_connect as wc

        _run(fake_db.trusts.insert_one({
            "trust_id": "trust_abc",
            "user_id": "user_someone_else",
            "wingpoint_ref": "WP-20260904-2517",
            "name": "Lookout Point 5B Ministries",
        }))

        result = _run(wc.connect_signup(
            wc.SignupRequest(**_ctx(), name="John", password="BrandNewPass1"),
            request=_request(),
            response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
            background_tasks=MagicMock(add_task=MagicMock()),
            _rl=None,
        ))
        trust = _run(fake_db.trusts.find_one({"trust_id": "trust_abc"}))
        assert trust["user_id"] == result["user"]["user_id"]

    def test_signup_refuses_when_an_account_already_exists(self, fake_db):
        """Never create a second account for the same email."""
        import routers.wingpoint_connect as wc

        _make_user(fake_db, "member@example.com", password_hash=None)

        with pytest.raises(Exception) as exc:
            _run(wc.connect_signup(
                wc.SignupRequest(**_ctx(), name="John", password="BrandNewPass1"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 409
        assert len(fake_db.users.docs) == 1

    def test_signup_rejects_weak_password(self, fake_db):
        import routers.wingpoint_connect as wc

        with pytest.raises(Exception) as exc:
            _run(wc.connect_signup(
                wc.SignupRequest(**_ctx(), name="John", password="abc"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400
        assert len(fake_db.users.docs) == 0

    def test_signup_requires_a_valid_connect_context(self, fake_db):
        import routers.wingpoint_connect as wc

        ctx = _ctx()
        ctx["redirect_url"] = "https://not-wingpoint.com/cb?app_id=app_abc123"
        with pytest.raises(Exception) as exc:
            _run(wc.connect_signup(
                wc.SignupRequest(**ctx, name="John", password="BrandNewPass1"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert getattr(exc.value, "status_code", None) == 400


# ==================== 5. LOG HYGIENE ====================

class TestLogHygiene:
    """Member emails are never written to app logs."""

    def test_email_fingerprint_is_stable_and_non_reversible(self):
        import routers.wingpoint_connect as wc

        fp1 = wc._email_fingerprint("member@example.com")
        fp2 = wc._email_fingerprint("MEMBER@example.com")
        assert fp1 == fp2
        assert "member@example.com" not in fp1
        assert len(fp1) == 24

    def test_log_safe_representation_never_contains_the_address(self):
        import routers.wingpoint_connect as wc

        safe = wc._normalize_email_for_log("member@example.com")
        assert "member@example.com" not in safe
        assert safe.startswith("fp:")

    def test_resolve_logs_no_raw_email(self, fake_db, caplog):
        import logging

        import routers.wingpoint_connect as wc

        with caplog.at_level(logging.INFO, logger="routers.wingpoint_connect"):
            _run(wc.resolve_connect_state(
                wc.ResolveRequest(**_ctx()),
                request=_request(),
                _rl=None,
            ))
        assert "member@example.com" not in caplog.text
        assert "fp:" in caplog.text

    def test_claim_logs_no_raw_email(self, fake_db, caplog):
        import logging

        import routers.wingpoint_connect as wc

        with caplog.at_level(logging.INFO, logger="routers.wingpoint_connect"):
            _run(wc.request_claim_code(
                wc.ClaimCodeRequest(**_ctx()),
                request=_request(),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert "member@example.com" not in caplog.text

    def test_signup_logs_no_raw_email(self, fake_db, caplog):
        import logging

        import routers.wingpoint_connect as wc

        with caplog.at_level(logging.INFO, logger="routers.wingpoint_connect"):
            _run(wc.connect_signup(
                wc.SignupRequest(**_ctx(), name="John", password="BrandNewPass1"),
                request=_request(),
                response=MagicMock(set_cookie=MagicMock(), delete_cookie=MagicMock()),
                background_tasks=MagicMock(add_task=MagicMock()),
                _rl=None,
            ))
        assert "member@example.com" not in caplog.text


# ==================== 6. WIRING ====================

class TestRouterWiring:
    """The router is mounted and the paywall does not block the flow."""

    def test_router_is_mounted_in_server(self):
        source = (BACKEND_DIR / "server.py").read_text()
        assert "from routers.wingpoint_connect import router as wingpoint_connect_router" in source
        assert 'app.include_router(wingpoint_connect_router, prefix="/api")' in source

    def test_connect_endpoints_are_paywall_write_exempt(self):
        """The flow runs before a subscription exists — never-paid members
        must be able to reach these endpoints."""
        source = (BACKEND_DIR / "server.py").read_text()
        for path in (
            "/api/wingpoint-connect/resolve",
            "/api/wingpoint-connect/claim/request-code",
            "/api/wingpoint-connect/claim/verify",
            "/api/wingpoint-connect/signup",
        ):
            assert path in source, f"{path} must be in the paywall exempt list"

    def test_email_template_and_service_method_exist(self):
        from email_templates import TEMPLATES, render_template

        assert "wingpoint_connect_code" in TEMPLATES
        rendered = render_template("wingpoint_connect_code", {"user_name": "John", "code": "123456"})
        assert rendered["subject"]
        assert "123456" in rendered["html"]
        assert "123456" in rendered["text"]

        from email_service import EmailService
        assert hasattr(EmailService, "send_wingpoint_connect_code_email")
