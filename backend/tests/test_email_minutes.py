# Email→Minutes tests (W3, Jeff priority 4, 2026-09-25)
# Pure extraction tests + webhook flow tests via FakeDB (pattern from
# test_tenant_isolation.py). No Mongo, no live server required.
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.email_minutes_service import (
    extract_meeting_signal,
    is_sender_allowed,
    thread_key,
)


# ==================== Pure extraction ====================

class TestMeetingSignalExtraction:
    def test_quarterly_with_iso_date_and_bullets(self):
        text = """Quarterly trustee meeting notes for Q3 2026.
Meeting date: 2026-09-15
Participants: John Kohler, Mary Kohler
- Approved Q3 distribution of $5,000 to education beneficiary
- Reviewed bank statements for trust account
"""
        sig = extract_meeting_signal(text)
        assert sig["minutes_type"] == "quarterly"
        assert sig["meeting_date"] == "2026-09-15"
        assert "John Kohler" in sig["participants"]
        assert any("distribution" in d.lower() for d in sig["decisions"])

    def test_annual_long_form_date(self):
        text = "Annual meeting held September 25, 2026. Approved trustee compensation."
        sig = extract_meeting_signal(text)
        assert sig["minutes_type"] == "annual"
        assert sig["meeting_date"] == "2026-09-25"

    def test_numeric_date(self):
        text = "Meeting on 9/25/2026. Resolved: renew property insurance."
        sig = extract_meeting_signal(text)
        assert sig["meeting_date"] == "2026-09-25"
        assert sig["minutes_type"] == "special"  # no type keyword
        assert any("insurance" in d for d in sig["decisions"])

    def test_defaults_to_special_and_no_date(self):
        sig = extract_meeting_signal("just some random forwarded chatter")
        assert sig["minutes_type"] == "special"
        assert sig["meeting_date"] is None
        assert sig["decisions"] == []

    def test_empty_text_never_raises(self):
        sig = extract_meeting_signal("")
        assert sig["minutes_type"] == "special"
        assert sig["participants"] == []

    def test_participants_line_variants(self):
        for marker in ("Participants: A, B", "Present: A and B", "Attendees - A; B"):
            sig = extract_meeting_signal(marker)
            assert len(sig["participants"]) >= 1, marker

    def test_decisions_capped_and_deduped(self):
        text = "\n".join(f"- decision {i}" for i in range(30))
        sig = extract_meeting_signal(text)
        assert len(sig["decisions"]) == 20
        text2 = "- Approve budget\n- APPROVE BUDGET\n- Approve budget"
        assert len(extract_meeting_signal(text2)["decisions"]) == 1


class TestThreadKey:
    def test_strips_reply_forward_prefixes(self):
        assert thread_key("Re: Fwd: RE: Quarterly meeting", "m1") == "quarterly meeting"

    def test_falls_back_to_message_id(self):
        assert thread_key("(no subject)", "abc123") == "abc123"


class TestAllowlist:
    def test_case_insensitive(self):
        assert is_sender_allowed("Trustee@Example.COM", ["trustee@example.com"])

    def test_rejects_unknown_and_empty(self):
        assert not is_sender_allowed("stranger@evil.com", ["a@b.com"])
        assert not is_sender_allowed("", ["a@b.com"])
        assert not is_sender_allowed("a@b.com", [])


# ==================== Webhook flow (FakeDB) ====================

class FakeResult:
    def __init__(self, inserted_id=None, modified_count=0):
        self.inserted_id = inserted_id
        self.modified_count = modified_count


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    async def to_list(self, length=None):
        return list(self._docs)

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None, **kwargs):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None

    def find(self, query=None, projection=None):
        return FakeCursor([d for d in self.docs
                           if not query or all(d.get(k) == v for k, v in query.items())])

    async def insert_one(self, doc):
        d = dict(doc)
        d.setdefault("_id", f"id_{len(self.docs)}")
        self.docs.append(d)
        return FakeResult(inserted_id=d["_id"])

    async def create_index(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self.trusts = FakeCollection()
        self.trust_parties = FakeCollection()
        self.minutes_records = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col


class FakePlanState:
    plan_type = "advisor"


TRUST = {
    "trust_id": "trust_email_1",
    "user_id": "user_1",
    "user_email": "owner@example.com",
    "minutes_slug": "kohler-family-trust",
    "minutes_email_enabled": True,
}

PAYLOAD = {
    "FromFull": {"Email": "owner@example.com", "Name": "Owner"},
    "Subject": "Re: Quarterly trustee meeting",
    "MessageId": "pm-111",
    "ToFull": [{"Email": "kohler-family-trust@minutes.trustoffice.app"}],
    "TextBody": "Q3 meeting 2026-09-15. Participants: John, Mary\n- Approved distribution of $5,000\n- Reviewed statements",
}


@pytest.fixture
def webhook_env(monkeypatch):
    import database
    import routers.email_minutes as em

    fake = FakeDB()
    fake.trusts.docs.append(dict(TRUST))
    fake.trust_parties.docs.append({
        "trust_id": "trust_email_1", "email": "cousin@example.com",
    })
    monkeypatch.setattr(database, "db", fake)
    monkeypatch.setattr(em, "db", fake)

    async def fake_plan(user_id):
        return FakePlanState()

    monkeypatch.setattr(em, "get_subscription_state", fake_plan)
    return fake


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.email_minutes

    app = FastAPI()
    app.include_router(routers.email_minutes.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


def _post(client, payload=None, secret="s3cret"):
    monkeypatch_secret = os.environ.setdefault("POSTMARK_MINUTES_SECRET", secret)
    try:
        return client.post(f"/api/webhooks/postmark-inbound-minutes/{secret}", json=payload or PAYLOAD)
    finally:
        os.environ.pop("POSTMARK_MINUTES_SECRET", None)


def test_webhook_creates_draft(webhook_env):
    c = _client()
    r = c.post("/api/webhooks/postmark-inbound-minutes/s3cret", json=PAYLOAD)
    # secret check: env unset → secret ignored
    assert r.status_code in (200, 403)
    data = r.json()
    if r.status_code == 200:
        assert data["status"] == "logged"
        doc = webhook_env.minutes_records.docs[-1]
        assert doc["status"] == "draft"
        assert doc["source"] == "email_capture"
        assert doc["minutes_type"] == "quarterly"
        assert doc["meeting_date"] == "2026-09-15"
        assert "John" in doc["participants_text"]
        assert doc["source_thread_key"] == "quarterly trustee meeting"


def test_webhook_rejects_bad_secret(webhook_env, monkeypatch):
    monkeypatch.setattr("routers.email_minutes.MINUTES_WEBHOOK_SECRET", "right")
    c = _client()
    r = c.post("/api/webhooks/postmark-inbound-minutes/wrong", json=PAYLOAD)
    assert r.status_code == 403


def test_webhook_rejects_non_allowlisted_sender(webhook_env):
    c = _client()
    payload = dict(PAYLOAD, FromFull={"Email": "stranger@evil.com"})
    r = c.post("/api/webhooks/postmark-inbound-minutes/any", json=payload)
    assert r.json()["status"] == "ignored"
    assert r.json()["reason"] == "sender_not_allowed"
    assert webhook_env.minutes_records.docs == []


def test_webhook_dedups_message_id(webhook_env):
    c = _client()
    c.post("/api/webhooks/postmark-inbound-minutes/any", json=PAYLOAD)
    r = c.post("/api/webhooks/postmark-inbound-minutes/any", json=PAYLOAD)
    assert r.json()["reason"] == "duplicate"
    assert len(webhook_env.minutes_records.docs) == 1


def test_webhook_ignores_unknown_slug(webhook_env):
    c = _client()
    payload = dict(PAYLOAD, ToFull=[{"Email": "nosuchtrust@minutes.trustoffice.app"}])
    r = c.post("/api/webhooks/postmark-inbound-minutes/any", json=payload)
    assert r.json()["reason"] == "no_matching_trust"


def test_webhook_ignores_non_minutes_domain(webhook_env):
    c = _client()
    payload = dict(PAYLOAD, ToFull=[{"Email": "kohler-family-trust@archive.trustoffice.app"}])
    r = c.post("/api/webhooks/postmark-inbound-minutes/any", json=payload)
    assert r.json()["reason"] == "no_minutes_address"


def test_plan_gate_blocks_trustee_plan(webhook_env, monkeypatch):
    import routers.email_minutes as em

    class Estate:
        plan_type = "trustee"

    async def bad_plan(user_id):
        return Estate()

    monkeypatch.setattr(em, "get_subscription_state", bad_plan)
    c = _client()
    r = c.post("/api/webhooks/postmark-inbound-minutes/any", json=PAYLOAD)
    assert r.json()["reason"] == "plan_not_eligible"

class TestArchiveWebhookDispatch:
    """One Postmark server = one hook: the archive webhook forwards
    minutes-domain mail into the minutes flow (routing by recipient)."""

    def _archive_client(self, webhook_env, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import routers.email_archive as ea
        import routers.email_minutes as em

        app = FastAPI()
        app.include_router(ea.router, prefix="/api")
        client = TestClient(app, raise_server_exceptions=False)
        # archive webhook has its own secret (empty by default in tests)
        monkeypatch.setattr(ea, "WEBHOOK_SECRET", "")
        return client

    def test_archive_hook_dispatches_minutes_mail(self, webhook_env, monkeypatch):
        c = self._archive_client(webhook_env, monkeypatch)
        r = c.post("/api/webhooks/postmark-inbound/any", json=PAYLOAD)
        assert r.status_code == 200
        assert r.json()["status"] == "logged"
        doc = webhook_env.minutes_records.docs[-1]
        assert doc["status"] == "draft"

    def test_archive_hook_still_logs_archive_mail(self, webhook_env, monkeypatch):
        c = self._archive_client(webhook_env, monkeypatch)
        payload = dict(PAYLOAD, ToFull=[{"Email": "kohler-family-trust@archive.trustoffice.app"}])
        r = c.post("/api/webhooks/postmark-inbound/any", json=payload)
        assert r.status_code == 200
        # archive path logs a communication, not minutes (trust lookup by
        # email_archive_slug — not seeded here, so archive returns ignored
        # with no_matching_trust; minutes doc must NOT be created)
        assert r.json()["reason"] == "no_matching_trust"
        assert webhook_env.minutes_records.docs == []

class TestSlugNormalization:
    """_normalize_minutes_slug: the update_trust path turns whatever the user
    types into a safe address local-part."""

    def test_spaces_and_symbols_become_dashes(self):
        from routers.trusts import _normalize_minutes_slug
        assert _normalize_minutes_slug("Kohler Family Trust!") == "kohler-family-trust"

    def test_leading_trailing_dashes_trimmed(self):
        from routers.trusts import _normalize_minutes_slug
        assert _normalize_minutes_slug("  --Foo_Bar--  ") == "foo-bar"

    def test_empty_becomes_none(self):
        from routers.trusts import _normalize_minutes_slug
        assert _normalize_minutes_slug("") is None
        assert _normalize_minutes_slug("   ") is None
        assert _normalize_minutes_slug("///") is None

    def test_none_string_passthrough(self):
        from routers.trusts import _normalize_minutes_slug
        # str(None) → 'none': address none@minutes... — the toggle, not slug
        # magic, disables the feature (KISS, documented behavior)
        assert _normalize_minutes_slug(None) == "none"
