"""Trust Assistant trust-honesty overhaul (Day-0 audit, 2026-11-06).

Covers the council days 1-6 fixes:

  * distribution_minutes now goes through verify_exec_write (it was the one
    card path that skipped the read-back entirely).
  * verify-fail contract: read-back miss -> ONE automatic retry -> still
    missing -> success:false + plain failure; never claim success.
  * review_link for contribute_asset (and generate-minutes) carries the real
    record id, not a literal-string placeholder.
  * READBACK_MAP completeness + trust-scoped read-back for settings_update /
    alert_dismiss.
  * No-fabricated-capability guard: a plain-text vault claim with no
    execution_result is rewritten to the honest form.
  * Alert resolve writes a member-visible activity receipt (audit_logs) and
    client-computed insight resolve persists a durable marker + receipt.
  * document_upload is an honest stub: the receipt says the file is not
    uploaded yet and names the one action left.

True unit tests: mongomock-backed, no live server, no LLM, no network.
"""
import os
import sys
import asyncio
import types

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ta_honesty_days")
os.environ.setdefault("JWT_SECRET", "test-secret-for-ta-honesty-days")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")
os.environ.setdefault("MAILERCLOUD_API_KEY", "")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "")
os.environ.setdefault("POSTMARK_SERVER_TOKEN", "")
os.environ.setdefault("TIDYCAL_API_TOKEN", "")

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --------------------------------------------------------------------------- #
# Async mongomock shim (motor-style API over sync mongomock)
# --------------------------------------------------------------------------- #
class _AsyncCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._cursor)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        items = list(self._cursor)
        return items if length is None else items[:length]

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self


class _AsyncCollection:
    def __init__(self, coll):
        self._c = coll

    async def find_one(self, *args, **kwargs):
        return self._c.find_one(*args, **kwargs)

    def find(self, *args, **kwargs):
        return _AsyncCursor(self._c.find(*args, **kwargs))

    def aggregate(self, *args, **kwargs):
        return _AsyncCursor(self._c.aggregate(*args, **kwargs))

    async def insert_one(self, doc):
        return self._c.insert_one(doc)

    async def insert_many(self, docs):
        return self._c.insert_many(docs)

    async def update_one(self, *args, **kwargs):
        return self._c.update_one(*args, **kwargs)

    async def update_many(self, *args, **kwargs):
        return self._c.update_many(*args, **kwargs)

    async def delete_one(self, *args, **kwargs):
        return self._c.delete_one(*args, **kwargs)

    async def delete_many(self, *args, **kwargs):
        return self._c.delete_many(*args, **kwargs)

    async def count_documents(self, *args, **kwargs):
        return self._c.count_documents(*args, **kwargs)

    async def find_one_and_update(self, *args, **kwargs):
        return self._c.find_one_and_update(*args, **kwargs)

    async def distinct(self, *args, **kwargs):
        return self._c.distinct(*args, **kwargs)

    def create_index(self, *args, **kwargs):
        return self._c.create_index(*args, **kwargs)


class _AsyncDatabase:
    def __init__(self, db):
        self._db = db
        self._cols = {}

    def __getitem__(self, name):
        return self._col(name)

    def __getattr__(self, name):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        return self._col(name)

    def _col(self, name):
        if name not in self._cols:
            self._cols[name] = _AsyncCollection(self._db[name])
        return self._cols[name]

    def get_collection(self, name):
        return self._col(name)

    async def list_collection_names(self):
        return self._db.list_collection_names()


class _AsyncMongoClient:
    def __init__(self, client):
        self._c = client

    def __getitem__(self, name):
        return _AsyncDatabase(self._c[name])

    def __getattr__(self, name):
        return getattr(self._c, name)

    def close(self):
        return self._c.close()


@pytest.fixture(scope="module")
def mongo_client():
    import mongomock
    return mongomock.MongoClient()


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def patched_db(mongo_client, monkeypatch_module):
    """Patch the `db` handle on every module that imported it by name.

    Routers do `from database import db`, so patching database.db alone does
    not reach them. This is the same pattern test_minutes_prefill_and_link.py
    uses, and it avoids the motor-client singleton contamination that breaks
    when two mongomock suites run in one pytest process.
    """
    import database
    import routers.chat
    import routers.minutes
    import routers.alerts
    import routers.governance
    import routers.schedule_a
    import dependencies
    import actions_seed
    import exec_hardening
    import approval_handler
    import utils.audit

    fake = _AsyncDatabase(mongo_client["test_ta_honesty_days"])
    for mod in (
        database, routers.chat, routers.minutes, routers.alerts,
        routers.governance, routers.schedule_a, dependencies, actions_seed,
        exec_hardening, approval_handler, utils.audit,
    ):
        monkeypatch_module.setattr(mod, "db", fake, raising=False)
    return fake


@pytest.fixture(autouse=True)
def _seal_discord(monkeypatch):
    """Never let a read-back miss page a real Discord channel from tests."""
    import discord_service

    async def _capture_alert(*a, **k):
        return {"ok": True, "captured": True}

    async def _capture_deliver(*a, **k):
        raise AssertionError("unit test attempted REAL Discord delivery")

    monkeypatch.setattr(discord_service, "notify_alert", _capture_alert)
    monkeypatch.setattr(discord_service, "send_discord_message", _capture_deliver)


@pytest.fixture
def seeded(patched_db, mongo_client):
    client_db = mongo_client["test_ta_honesty_days"]
    client_db.users.drop()
    client_db.trusts.drop()
    client_db.subscriptions.drop()
    client_db.minutes_records.drop()
    client_db.dismissed_insights.drop()
    client_db.audit_logs.drop()
    client_db.separation_alerts.drop()
    client_db.alert_audit_log.drop()

    now = "2026-11-06T00:00:00+00:00"
    client_db.users.insert_one({
        "user_id": "user_test_honesty",
        "email": "honesty@example.com",
        "name": "Honesty Test",
        "is_admin": False,
        "created_at": now,
    })
    client_db.subscriptions.insert_one({
        "user_id": "user_test_honesty",
        "plan_type": "trustee",
        "status": "active",
        "current_period_end": "2027-11-06T00:00:00+00:00",
        "is_legacy_price": False,
    })
    client_db.trusts.insert_one({
        "trust_id": "trust_test_honesty",
        "user_id": "user_test_honesty",
        "name": "Honesty Trust",
        "status": "active",
        "created_at": now,
    })
    return patched_db


@pytest.fixture(autouse=True)
def _slow_recheck(monkeypatch):
    """Keep the 90s deferred miss-recheck from firing during a test."""
    import exec_hardening
    monkeypatch.setattr(exec_hardening, "_MISS_RECHECK_SECONDS", 9999)


async def _cancel_background_tasks():
    current = asyncio.current_task()
    for task in asyncio.all_tasks():
        if task is not current:
            task.cancel()


# --------------------------------------------------------------------------- #
# 1. distribution_minutes read-back
# --------------------------------------------------------------------------- #
def test_distribution_minutes_has_readback_map_entry():
    from exec_hardening import READBACK_MAP

    assert "distribution_minutes" in READBACK_MAP, (
        "distribution_minutes was the one card path that skipped read-back"
    )
    collection, key_field, _result_key, scope_field = READBACK_MAP["distribution_minutes"]
    assert collection == "minutes_records"
    assert key_field == "minutes_id"
    assert scope_field == "user_id"


@pytest.mark.asyncio
async def test_distribution_minutes_envelope_is_verified(seeded, monkeypatch):
    """The distribution_minutes branch must carry verified:true like the rest."""
    import routers.chat as chat_router

    async def _fake_exec_minutes(mapped_data, trust_id, user_id):
        # Real handler writes a minutes_records row; mirror that here.
        await seeded.minutes_records.insert_one({
            "minutes_id": "min_dm_1",
            "trust_id": trust_id,
            "user_id": user_id,
            "status": "draft",
            "minutes_type": "distribution",
        })
        return {
            "success": True,
            "record_id": "min_dm_1",
            "endpoint": "minutes",
            "status": "draft",
            "review_link": "/minutes/min_dm_1",
        }

    monkeypatch.setattr(chat_router, "_exec_minutes", _fake_exec_minutes)

    result = await chat_router._execute_approved_action(
        action_card={
            "type": "distribution_minutes_preview",
            "data": {"distribution_id": "dist_1"},
        },
        user_id="user_test_honesty",
        trust_id="trust_test_honesty",
    )

    assert result.get("success") is True, result
    assert result.get("verified") is True, result
    # The distribution link is still stamped on the minutes record.
    linked = await seeded.minutes_records.find_one({"minutes_id": "min_dm_1"})
    assert linked.get("distribution_id") == "dist_1"


# --------------------------------------------------------------------------- #
# 2. verify-fail contract: retry once, never claim success
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_readback_miss_retries_once_and_never_claims_success(seeded, monkeypatch):
    import routers.chat as chat_router

    calls = {"count": 0}

    async def _ghost_exec_minutes(mapped_data, trust_id, user_id):
        calls["count"] += 1
        # Reports success but writes NOTHING (the phantom-write failure mode).
        return {
            "success": True,
            "record_id": "min_ghost_1",
            "endpoint": "minutes",
            "status": "draft",
        }

    monkeypatch.setattr(chat_router, "_exec_minutes", _ghost_exec_minutes)

    try:
        result = await chat_router._execute_approved_action(
            action_card={
                "type": "minutes_preview",
                "data": {"minutes_type": "quarterly"},
            },
            user_id="user_test_honesty",
            trust_id="trust_test_honesty",
        )
    finally:
        await _cancel_background_tasks()

    # Exactly one automatic retry of the write.
    assert calls["count"] == 2, f"expected initial write + 1 retry, got {calls['count']}"
    assert result.get("success") is False, "must never claim success on a read-back miss"
    assert result.get("verified") is False
    assert result.get("error") == "record not found after write"
    assert result.get("readback_retry_attempted") is True


@pytest.mark.asyncio
async def test_readback_miss_retry_that_lands_is_verified(seeded, monkeypatch):
    """If the retry's write lands, the envelope is verified (no false failure)."""
    import routers.chat as chat_router

    calls = {"count": 0}

    async def _flaky_exec_minutes(mapped_data, trust_id, user_id):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"success": True, "record_id": "min_flaky_1", "endpoint": "minutes"}
        await seeded.minutes_records.insert_one({
            "minutes_id": "min_flaky_1",
            "trust_id": trust_id,
            "user_id": user_id,
            "status": "draft",
        })
        return {"success": True, "record_id": "min_flaky_1", "endpoint": "minutes", "status": "draft"}

    monkeypatch.setattr(chat_router, "_exec_minutes", _flaky_exec_minutes)

    try:
        result = await chat_router._execute_approved_action(
            action_card={"type": "minutes_preview", "data": {"minutes_type": "quarterly"}},
            user_id="user_test_honesty",
            trust_id="trust_test_honesty",
        )
    finally:
        await _cancel_background_tasks()

    assert calls["count"] == 2
    assert result.get("success") is True, result
    assert result.get("verified") is True, result


# --------------------------------------------------------------------------- #
# 3. review_link literal-string bug
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_contribute_asset_review_link_uses_real_minutes_id(seeded, monkeypatch):
    """The 10/28 placeholder leak: review_link must carry the created id."""
    import routers.schedule_a as schedule_a_router
    import routers.minutes as minutes_router
    import dependencies
    from action_layer import ActionContext
    from actions_seed import _chat_contribute_asset

    async def _fake_create_asset(item, user):
        return types.SimpleNamespace(item_id="sa_real_1")

    async def _fake_create_minutes(minutes, background_tasks, user):
        return types.SimpleNamespace(minutes_id="min_real_123")

    async def _fake_update_asset(item_id, update, user):
        return None

    async def _fake_onboarding(user_id, trust_id):
        return None

    monkeypatch.setattr(schedule_a_router, "create_schedule_a_item", _fake_create_asset)
    monkeypatch.setattr(schedule_a_router, "update_schedule_a_item", _fake_update_asset)
    monkeypatch.setattr(minutes_router, "create_minutes", _fake_create_minutes)
    monkeypatch.setattr(dependencies, "auto_update_onboarding", _fake_onboarding)

    ctx = ActionContext(
        user_id="user_test_honesty",
        trust_id="trust_test_honesty",
        user={"user_id": "user_test_honesty"},
        surface="chat",
    )
    result = await _chat_contribute_asset(
        {
            "description": "Family home",
            "category": "real_property",
            "approximate_value": 500000,
            "date_conveyed": "2026-01-01",
        },
        ctx,
    )

    assert result.get("success") is True, result
    assert result["review_link"] == "/minutes/min_real_123", result
    assert "minutes_result.minutes_id" not in result["review_link"]


@pytest.mark.asyncio
async def test_chat_exec_contribute_asset_review_link_uses_real_id(seeded, monkeypatch):
    """The card-path handler (routers/chat.py) had the same literal bug."""
    import routers.chat as chat_router
    import routers.schedule_a as schedule_a_router
    import routers.minutes as minutes_router
    import dependencies

    async def _fake_create_asset(item, user):
        return types.SimpleNamespace(item_id="sa_chat_1")

    async def _fake_create_minutes(minutes, background_tasks, user):
        return types.SimpleNamespace(minutes_id="min_chat_123")

    async def _fake_update_asset(item_id, update, user):
        return None

    async def _fake_onboarding(user_id, trust_id):
        return None

    monkeypatch.setattr(schedule_a_router, "create_schedule_a_item", _fake_create_asset)
    monkeypatch.setattr(schedule_a_router, "update_schedule_a_item", _fake_update_asset)
    monkeypatch.setattr(minutes_router, "create_minutes", _fake_create_minutes)
    monkeypatch.setattr(dependencies, "auto_update_onboarding", _fake_onboarding)

    result = await chat_router._exec_contribute_asset(
        {
            "description": "Family home",
            "category": "real_property",
            "approximate_value": 500000,
            "date_conveyed": "2026-01-01",
        },
        "trust_test_honesty",
        "user_test_honesty",
    )
    assert result.get("success") is True, result
    assert result["review_link"] == "/minutes/min_chat_123", result


def test_generate_minutes_review_link_is_not_a_literal_placeholder():
    """Source invariant: the old f"/minutes/result.minutes_id" bug is gone
    from BOTH parallel execution systems (actions_seed + chat card path)."""
    from pathlib import Path

    base = Path(os.path.join(os.path.dirname(__file__), ".."))
    for rel in ("actions_seed.py", "routers/chat.py"):
        source = (base / rel).read_text()
        assert 'f"/minutes/result.minutes_id"' not in source, rel
        assert 'f"/minutes/minutes_result.minutes_id"' not in source, rel

    actions = (base / "actions_seed.py").read_text()
    assert 'f"/minutes/{minutes_result.minutes_id}"' in actions
    assert 'f"/minutes/{result.minutes_id}"' in actions

    chat_src = (base / "routers/chat.py").read_text()
    assert 'f"/minutes/{minutes_result.minutes_id}"' in chat_src


def test_no_literal_review_link_placeholders_remain():
    """No member-facing review_link may be a literal-string placeholder.

    The same class of bug existed in the AI/dashboard surfaces (ai.py,
    governance.py); this locks all of them down.
    """
    from pathlib import Path

    base = Path(os.path.join(os.path.dirname(__file__), ".."))
    offenders = [
        'f"/minutes/existing[\'minutes_id\']"',
        'f"/minutes/minutes_id"',
        'f"/minutes/pending_draft[\'minutes_id\']"',
        'f"/minutes/result.minutes_id"',
        'f"/minutes/minutes_result.minutes_id"',
    ]
    for rel in ("actions_seed.py", "routers/chat.py", "routers/ai.py", "routers/governance.py"):
        source = (base / rel).read_text()
        for bad in offenders:
            assert bad not in source, f"{rel} still has a literal review_link: {bad}"


# --------------------------------------------------------------------------- #
# 4. READBACK_MAP completeness + trust scoping
# --------------------------------------------------------------------------- #
def test_readback_map_covers_every_action_execution_map_type():
    from exec_hardening import READBACK_MAP, REMOVAL_MAP
    from routers.chat import ACTION_EXECUTION_MAP

    endpoint_types = {mapping["endpoint_type"] for mapping in ACTION_EXECUTION_MAP.values()}
    covered = set(READBACK_MAP.keys()) | set(REMOVAL_MAP.keys())
    missing = endpoint_types - covered
    assert not missing, f"endpoint types with no read-back entry: {sorted(missing)}"


def test_settings_update_and_alert_dismiss_are_trust_scoped():
    from exec_hardening import READBACK_MAP

    assert READBACK_MAP["settings_update"][3] == "trust_id"
    assert READBACK_MAP["alert_dismiss"][3] == "trust_id"


@pytest.mark.asyncio
async def test_trust_scoped_readback_uses_trust_id(seeded):
    """A trust-scoped record must be found by trust_id, not the acting user."""
    from exec_hardening import verify_exec_write

    await seeded.trusts.update_one(
        {"trust_id": "trust_test_honesty"},
        {"$set": {"name": "Renamed Trust"}},
    )
    result = {
        "success": True,
        "record_id": "trust_test_honesty",
        "endpoint": "trusts",
    }
    out = await verify_exec_write(
        seeded,
        endpoint_type="settings_update",
        result=result,
        user_id="user_test_honesty",
        trust_id="trust_test_honesty",
        action_type="settings_update_preview",
    )
    assert out.get("verified") is True, out


@pytest.mark.asyncio
async def test_alert_dismiss_readback_uses_trust_scope(seeded):
    """alert_dismiss reports a criterion (no record_id); the read-back must
    find the dismissed_insights marker by trust_id, not the acting user."""
    from exec_hardening import verify_exec_write

    await seeded.dismissed_insights.insert_one({
        "criterion_name": "risk:missing_document",
        "trust_id": "trust_test_honesty",
        "user_id": "user_test_honesty",
    })
    result = {
        "success": True,
        "criterion": "risk:missing_document",
        "endpoint": "insights",
    }
    out = await verify_exec_write(
        seeded,
        endpoint_type="alert_dismiss",
        result=result,
        user_id="user_test_honesty",
        trust_id="trust_test_honesty",
    )
    assert out.get("verified") is True, out


# --------------------------------------------------------------------------- #
# 5. No-fabricated-capability guard
# --------------------------------------------------------------------------- #
def test_capability_guard_flags_text_only_vault_claim():
    from capability_guard import apply_capability_guard, capability_claim_detected

    text = "I've moved the Schedule A to the vault."
    assert capability_claim_detected(text) is True
    rewritten, flagged = apply_capability_guard(text)
    assert flagged is True
    assert "can't move files into the Vault" in rewritten
    assert "/schedule-a" in rewritten
    assert "Nothing was changed" in rewritten


def test_capability_guard_allows_claim_when_action_executed():
    from capability_guard import apply_capability_guard

    text = "Done - the vault document record is created: /vault."
    rewritten, flagged = apply_capability_guard(
        text, {"success": True, "record_id": "doc_1"}
    )
    assert flagged is False
    assert rewritten == text


def test_capability_guard_ignores_honest_guidance():
    from capability_guard import capability_claim_detected

    assert capability_claim_detected("Upload it in the Vault page to finish.") is False
    assert capability_claim_detected("The Vault shows uploaded documents.") is False
    assert capability_claim_detected("I've prepared a document upload card for you.") is False


# --------------------------------------------------------------------------- #
# 6. Honest receipts
# --------------------------------------------------------------------------- #
def test_document_upload_receipt_is_honest_stub():
    from approval_handler import build_success_message

    text = build_success_message(
        "vault document",
        {
            "success": True,
            "record_id": "doc_1",
            "endpoint_type": "document_upload",
            "pending_upload": True,
            "note": "Upload the file in the Vault page to finish.",
        },
        "document_upload",
    )
    assert "not uploaded yet" in text
    assert "Upload the file in the Vault page" in text
    assert not text.startswith("Done"), "a stub must not read as 'Done'"


def test_success_message_receipt_is_first_sentence():
    """Contract Rule 5: type - saved-as - working link in the first sentence."""
    from approval_handler import build_success_message

    text = build_success_message(
        "quarterly minutes",
        {"success": True, "record_id": "min_xyz789", "endpoint_type": "minutes", "status": "draft"},
        "minutes",
    )
    first_sentence = text.split(". ")[0]
    assert "quarterly minutes" in first_sentence
    assert "saved as a draft" in first_sentence
    assert "/minutes/min_xyz789" in first_sentence


def test_failure_message_is_plain_and_never_claims_success():
    from approval_handler import build_failure_message

    text = build_failure_message({"success": False, "error": "record not found after write"})
    assert "I couldn't complete that" in text
    assert "nothing was saved" in text
    assert "record not found after write" not in text
    assert "success" not in text.lower()


# --------------------------------------------------------------------------- #
# 7. Alert resolve + insight resolve receipts
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_alert_resolve_writes_member_visible_receipt(seeded):
    from models import AlertResolveRequest
    from routers.alerts import resolve_alert

    await seeded.separation_alerts.insert_one({
        "alert_id": "alert_1",
        "trust_id": "trust_test_honesty",
        "user_id": "user_test_honesty",
        "entity_id": "entity_1",
        "alert_type": "commingling",
        "severity": "red",
        "title": "Possible commingling",
        "description": "test",
        "status": "active",
        "created_at": "2026-11-06T00:00:00+00:00",
    })

    out = await resolve_alert(
        alert_id="alert_1",
        req=AlertResolveRequest(resolution_type="reviewed_no_issue", resolution_note="looked into it"),
        user={"user_id": "user_test_honesty"},
    )

    assert out.status == "resolved"
    assert out.resolution_type == "reviewed_no_issue"

    receipt = await seeded.audit_logs.find_one({"action": "alert_resolved"})
    assert receipt is not None, "resolve must write a member-visible activity receipt"
    assert receipt["user_id"] == "user_test_honesty"
    assert receipt["entity_id"] == "alert_1"
    assert receipt["details"]["resolution_type"] == "reviewed_no_issue"
    assert receipt["details"]["action_taken"] == "no action \u2014 marked reviewed"
    assert receipt["details"]["resolved_by"] == "user_test_honesty"


@pytest.mark.asyncio
async def test_insight_resolve_persists_marker_and_receipt(seeded):
    from models import InsightResolveRequest
    from routers.governance import resolve_insight

    out = await resolve_insight(
        req=InsightResolveRequest(
            trust_id="trust_test_honesty",
            criterion_name="risk:missing_document",
            alert_title="Schedule A (Assets) not found in Document Vault",
        ),
        user={"user_id": "user_test_honesty"},
    )

    assert out["resolved"] is True
    assert out["receipt"] == "resolved \u2014 reviewed, no action taken"

    marker = await seeded.dismissed_insights.find_one({
        "trust_id": "trust_test_honesty",
        "criterion_name": "risk:missing_document",
    })
    assert marker is not None, "resolve must persist a durable marker"
    assert marker["resolution_kind"] == "resolved_reviewed"
    assert marker["action_taken"] == "no action \u2014 marked reviewed"
    assert marker["resolved_by"] == "user_test_honesty"

    receipt = await seeded.audit_logs.find_one({"action": "insight_resolved"})
    assert receipt is not None
    assert receipt["details"]["criterion_name"] == "risk:missing_document"
    assert receipt["details"]["action_taken"] == "no action \u2014 marked reviewed"
