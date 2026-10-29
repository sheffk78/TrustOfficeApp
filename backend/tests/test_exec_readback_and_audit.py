"""
Tests for the chat action-stack hardening bundle (council P0, 2026-10-23).

Four defects are locked down here:

  (a) EXEC READ-BACK VERIFICATION — a chat action that reports success but
      wrote no record must be FLIPPED to success=false with the error
      "record not found after write", and a Discord notify_alert must fire
      (loud, at the moment it happens — zero cron). A verified action must
      carry verified=true. An unmapped action type must be reported honestly
      as verification_skipped, never as verified.

  (b) DELETE PROVENANCE — every member-record deletion writes an audit_logs
      row BEFORE the delete commits, carrying actor_user_id, performed_by
      (self or impersonated + the admin id), record_type, record_id,
      deleted_at and a snapshot_summary.

  (c) STREAMING TELEMETRY — the streaming route (the ONLY route members
      use) writes the same chat_telemetry row the non-streaming route
      writes: response_time_s, message_length, intent, has_action_card,
      conversation_id.

  (d) REPLY-LINK COVERAGE — every action type's success reply carries a
      real record link, and every route named in the reply-link map exists
      in frontend/src/App.js. No fabricated routes.

These are true unit tests: mongomock-backed, no live server, no LLM, no
network. The module-level mongomock shim patches motor's client so
``routers.chat``/``routers.minutes`` see an in-memory database.
"""
import os
import sys
import inspect
import asyncio

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_exec_readback_audit")
os.environ.setdefault("JWT_SECRET", "test-secret-for-exec-readback-audit")
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

    def __getitem__(self, name):
        return _AsyncCollection(self._db[name])

    def __getattr__(self, name):
        return _AsyncCollection(self._db[name])

    def get_collection(self, name):
        return _AsyncCollection(self._db[name])

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


@pytest.fixture(scope="module", autouse=True)
def _patch_motor():
    """Patch motor's client factory so the app sees an in-memory mongomock."""
    import mongomock
    from unittest.mock import patch

    client = mongomock.MongoClient()

    class _FakeAsyncIOMotorClient:
        def __init__(self, *args, **kwargs):
            self._client = client

        def __getitem__(self, name):
            return _AsyncDatabase(client[name])

        def __getattr__(self, name):
            return getattr(client, name)

    with patch("motor.motor_asyncio.AsyncIOMotorClient", _FakeAsyncIOMotorClient):
        yield client


# 2026-10-29 incident gate (autouse seal): several tests here deliberately drive
# the read-back MISS / removal-verification failure paths, and prod calls
# notify_alert (late import) on each miss. Tests that assert alert payloads
# stub notify_alert themselves; tests that DON'T previously let the real one
# through — which paged the live #trustoffice-main channel 7 times overnight
# (user_test_harden / dist_still_here fixtures) when the lane ran the suite
# with Railway parity webhook env vars set. Both Discord entry points are now
# sealed for the whole module; teardown fails any test that touched delivery.
@pytest.fixture(autouse=True)
def _seal_discord(monkeypatch):
    import discord_service

    delivered: list[dict] = []

    async def _capture_alert(*a, **k):
        return {"ok": True, "captured": True}

    async def _capture_deliver(*a, **k):
        delivered.append({"args": a, "kwargs": k})
        raise AssertionError(
            "unit test attempted REAL Discord delivery via send_discord_message"
        )

    monkeypatch.setattr(discord_service, "notify_alert", _capture_alert)
    monkeypatch.setattr(discord_service, "send_discord_message", _capture_deliver)
    yield
    assert not delivered, (
        f"{len(delivered)} Discord delivery attempt(s) leaked out of this test: "
        f"{delivered[0].get('kwargs', {}) or delivered[0].get('args')}"
    )


@pytest.fixture
def seeded(_patch_motor):
    """A seeded in-memory DB with a user, a trust and a subscription."""
    import routers.minutes  # noqa: F401  (ensures the app modules import)
    from database import db

    client = _patch_motor
    client.drop_database("test_exec_readback_audit")
    raw = client["test_exec_readback_audit"]

    now = "2026-10-23T00:00:00+00:00"
    raw["users"].insert_one({
        "user_id": "user_test_harden",
        "email": "harden@example.com",
        "name": "Harden Test",
        "is_admin": False,
        "created_at": now,
    })
    raw["subscriptions"].insert_one({
        "user_id": "user_test_harden",
        "plan_type": "trustee",
        "status": "active",
        "current_period_end": "2027-10-23T00:00:00+00:00",
        "is_legacy_price": False,
    })
    raw["trusts"].insert_one({
        "trust_id": "trust_test_harden",
        "user_id": "user_test_harden",
        "name": "Harden Trust",
        "status": "active",
        "created_at": now,
    })
    return db


# --------------------------------------------------------------------------- #
# (a) EXEC READ-BACK VERIFICATION
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_readback_miss_flips_success_and_fires_alert(seeded, monkeypatch):
    """A handler that reports success but wrote nothing must be caught.

    This is the Jerel Kratt failure mode: the member was told the draft was
    created, but no record existed. The read-back flips success to false,
    sets error='record not found after write', and fires notify_alert.
    """
    import asyncio as _asyncio
    import exec_hardening
    exec_hardening._MISS_RECHECK_SECONDS = 1  # deterministic strike-2 pacing

    alerts = []

    async def _fake_notify_alert(title, message, color=0, ping_kit=False):
        alerts.append({"title": title, "message": message, "color": color,
                       "ping_kit": ping_kit})
        return {"ok": True}

    import discord_service
    monkeypatch.setattr(discord_service, "notify_alert", _fake_notify_alert)

    result = {
        "success": True,
        "record_id": "minutes_ghost_123",
        "endpoint": "minutes",
    }

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="minutes",
        result=result,
        user_id="user_test_harden",
        trust_id="trust_test_harden",
        action_type="minutes_preview",
    )

    # 2026-10-29 two-strike: strike-1 records the miss but does NOT page.
    assert out["success"] is False, "a missing record must NOT report success"
    assert out["error"] == "record not found after write"
    assert out["verified"] is False
    assert out["readback_missing_collection"] == "minutes_records"
    assert out["readback_missing_key"] == "minutes_ghost_123"
    assert out["readback_missing_at"], "the miss must be timestamped"
    assert out["readback_recheck_pending"] is True, "strike-1 must defer the alert"
    assert alerts == [], "NO alert on strike-1 — a transient miss must not page"

    # Strike 2: the recheck task paces on _MISS_RECHECK_SECONDS (1s in test).
    await _asyncio.sleep(1.6)

    assert len(alerts) == 1, "exactly ONE alert after strike-2 confirm"
    alert = alerts[0]
    assert "read-back MISS" in alert["title"]
    assert "confirmed" in alert["title"]
    assert "minutes_preview" in alert["message"]
    assert "user_test_harden" in alert["message"]
    assert "minutes_ghost_123" in alert["message"]
    assert "confirmed:" in alert["message"]
    assert alert["ping_kit"] is True, "the alert must be loud"


@pytest.mark.asyncio
async def test_readback_transient_miss_recovers_without_alert(seeded, monkeypatch):
    """A record that appears within the recheck window repairs the result.

    The deploy-restart churn false-paged twice at 01:30Z 2026-10-29: the
    write lagged its own read-back. Two-strike: strike-2 finds the record,
    the result flips back to success+verified, NO Discord page.
    """
    import asyncio
    import exec_hardening
    exec_hardening._MISS_RECHECK_SECONDS = 1

    alerts = []

    async def _fake_notify_alert(title, message, color=0, ping_kit=False):
        alerts.append({"title": title})
        return {"ok": True}

    import discord_service
    monkeypatch.setattr(discord_service, "notify_alert", _fake_notify_alert)

    result = {
        "success": True,
        "record_id": "minutes_late_landing",
        "endpoint": "minutes",
    }
    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="minutes",
        result=result,
        user_id="user_test_harden",
        trust_id="trust_test_harden",
        action_type="minutes_preview",
    )
    assert out["success"] is False
    assert out["readback_recheck_pending"] is True

    # The record lands late — inside the recheck window.
    await asyncio.sleep(0.3)
    await seeded.minutes_records.insert_one({
        "minutes_id": "minutes_late_landing",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "status": "draft",
    })

    await asyncio.sleep(1.4)  # strike-2 recheck fires (1s pacing)

    assert out["readback_recovered"] is True
    assert out["success"] is True, "a late-landing record must repair success"
    assert out["verified"] is True
    assert "error" not in out
    assert alerts == [], "a recovered miss must NEVER page"


@pytest.mark.asyncio
async def test_readback_hit_marks_verified(seeded):
    """A record that IS in Mongo must come back verified=true."""
    import exec_hardening

    await seeded.minutes_records.insert_one({
        "minutes_id": "minutes_real_1",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "minutes_type": "quarterly",
        "status": "draft",
    })

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="minutes",
        result={"success": True, "record_id": "minutes_real_1"},
        user_id="user_test_harden",
        trust_id="trust_test_harden",
        action_type="minutes_preview",
    )

    assert out["success"] is True
    assert out["verified"] is True
    assert out["verified_collection"] == "minutes_records"
    assert out["verified_key"] == "minutes_real_1"
    assert "error" not in out


@pytest.mark.asyncio
async def test_readback_is_scoped_to_the_acting_member(seeded):
    """A read-back must never match ANOTHER member's record.

    If the scoping were dropped, user A's action could be 'verified' by
    user B's record, which would hide a real write failure.
    """
    import exec_hardening

    # The record exists — but it belongs to a different user.
    await seeded.minutes_records.insert_one({
        "minutes_id": "minutes_other_user",
        "user_id": "user_someone_else",
        "trust_id": "trust_other",
        "status": "draft",
    })

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="minutes",
        result={"success": True, "record_id": "minutes_other_user"},
        user_id="user_test_harden",
        trust_id="trust_test_harden",
        action_type="minutes_preview",
    )

    assert out["success"] is False, "must not verify against another member's record"
    assert out["error"] == "record not found after write"


@pytest.mark.asyncio
async def test_readback_skipped_is_reported_honestly(seeded):
    """An action type with no read-back mapping must NOT claim verified=true."""
    import exec_hardening

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="totally_unknown_type",
        result={"success": True, "record_id": "whatever"},
        user_id="user_test_harden",
        action_type="totally_unknown_type",
    )

    assert out["success"] is True, "the action itself still succeeded"
    assert out["verified"] is False, "an unverified action must not claim verified"
    assert "verification_skipped" in out
    assert "totally_unknown_type" in out["verification_skipped"]


@pytest.mark.asyncio
async def test_failed_action_is_not_read_back(seeded):
    """A failed action needs no read-back — it must not be 'verified'."""
    import exec_hardening

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="minutes",
        result={"success": False, "error": "handler said no"},
        user_id="user_test_harden",
        action_type="minutes_preview",
    )

    assert out["success"] is False
    assert out.get("verified") is None, "a failed action must not be marked verified"
    assert out["error"] == "handler said no"


@pytest.mark.asyncio
async def test_removal_readback_requires_record_to_be_gone(seeded):
    """A removal that reports success but leaves the record live must fail."""
    import exec_hardening

    await seeded.distribution_records.insert_one({
        "distribution_id": "dist_still_here",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "status": "pending",
    })

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="distribution_cancel",
        result={"success": True, "record_id": "dist_still_here"},
        user_id="user_test_harden",
        trust_id="trust_test_harden",
        action_type="distribution_cancel_preview",
    )

    assert out["success"] is False
    assert out["error"] == "record still present after removal"
    assert out["verified"] is False


@pytest.mark.asyncio
async def test_removal_readback_accepts_a_real_soft_delete(seeded):
    """A record deactivated (not deleted) counts as removed.

    Regression guard: an earlier version treated ANY status other than
    'active' as removed, so a distribution left in 'review' or 'pending'
    was wrongly reported as successfully cancelled.
    """
    import exec_hardening

    await seeded.distribution_records.insert_one({
        "distribution_id": "dist_soft_cancelled",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "status": "cancelled",
    })

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="distribution_cancel",
        result={"success": True, "record_id": "dist_soft_cancelled"},
        user_id="user_test_harden",
        trust_id="trust_test_harden",
        action_type="distribution_cancel_preview",
    )

    assert out["success"] is True
    assert out["verified"] is True
    assert out.get("verified_soft_delete") is True


@pytest.mark.asyncio
async def test_removal_readback_passes_when_record_is_gone(seeded):
    """A removal whose record really is gone must verify."""
    import exec_hardening

    out = await exec_hardening.verify_exec_write(
        seeded,
        endpoint_type="distribution_cancel",
        result={"success": True, "record_id": "dist_already_gone"},
        user_id="user_test_harden",
        trust_id="trust_test_harden",
        action_type="distribution_cancel_preview",
    )

    assert out["success"] is True
    assert out["verified"] is True


# --------------------------------------------------------------------------- #
# (b) DELETE PROVENANCE
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_minutes_delete_writes_audit_row_before_delete(seeded):
    """Deleting a draft minutes must leave an audit_logs row behind."""
    from routers.minutes import delete_minutes

    await seeded.minutes_records.insert_one({
        "minutes_id": "minutes_to_delete",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "minutes_type": "quarterly",
        "status": "draft",
        "title": "Q3 Quarterly Meeting",
    })

    out = await delete_minutes(
        "minutes_to_delete",
        request=None,
        user={"user_id": "user_test_harden"},
    )

    assert out.get("message") == "Minutes deleted"

    # The document is gone...
    assert await seeded.minutes_records.find_one(
        {"minutes_id": "minutes_to_delete"}) is None

    # ...but the trail is not.
    audit = await seeded.audit_logs.find_one({"record_id": "minutes_to_delete"})
    assert audit is not None, "a member-record deletion must write an audit row"
    assert audit["record_type"] == "minutes_records"
    assert audit["actor_user_id"] == "user_test_harden"
    assert audit["performed_by"] == "self"
    assert audit["deleted_at"]
    assert audit["snapshot_summary"], "the audit row must summarize what went away"
    assert audit["timestamp"]


@pytest.mark.asyncio
async def test_delete_audit_records_impersonation_attribution(seeded):
    """A delete performed by an admin must be attributed to that admin."""
    from routers.minutes import delete_minutes

    await seeded.minutes_records.insert_one({
        "minutes_id": "minutes_impersonated_delete",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "status": "draft",
    })
    # The admin_audit_log row written when the impersonation started.
    await seeded.admin_audit_log.insert_one({
        "action": "impersonate_user",
        "admin_user_id": "user_admin_boss",
        "target_user_id": "user_test_harden",
        "timestamp": "2026-10-23T10:00:00+00:00",
    })

    await delete_minutes(
        "minutes_impersonated_delete",
        request=None,
        user={"user_id": "user_test_harden"},
    )

    audit = await seeded.audit_logs.find_one(
        {"record_id": "minutes_impersonated_delete"})
    assert audit is not None
    assert audit["performed_by"] == "impersonated"
    assert audit["impersonated_by_admin_id"] == "user_admin_boss"
    assert audit["details"]["impersonated_by_admin_id"] == "user_admin_boss"
    # The member's own id is still recorded — the record was still theirs.
    assert audit["actor_user_id"] == "user_test_harden"


@pytest.mark.asyncio
async def test_chat_conversation_delete_writes_audit_row(seeded):
    """Conversation deletes were completely unlogged — now they are audited."""
    from routers.chat import delete_conversation

    await seeded.chat_conversations.insert_one({
        "conversation_id": "conv_to_delete",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "title": "Quarterly minutes chat",
        "message_count": 4,
        "messages": [
            {"role": "user", "content": "log our quarterly minutes"},
            {"role": "assistant", "content": "Done."},
        ],
    })

    out = await delete_conversation(
        "conv_to_delete",
        request=None,
        user={"user_id": "user_test_harden"},
    )
    assert out.get("message") == "Conversation deleted"

    audit = await seeded.audit_logs.find_one({"record_id": "conv_to_delete"})
    assert audit is not None, "a conversation deletion must write an audit row"
    assert audit["record_type"] == "chat_conversations"
    assert audit["actor_user_id"] == "user_test_harden"
    assert audit["deleted_at"]


@pytest.mark.asyncio
async def test_audit_write_failure_blocks_the_delete(seeded, monkeypatch):
    """An unaudited delete must not happen: a failed audit write RAISES."""
    from routers.minutes import delete_minutes
    import exec_hardening

    await seeded.minutes_records.insert_one({
        "minutes_id": "minutes_audit_fails",
        "user_id": "user_test_harden",
        "trust_id": "trust_test_harden",
        "status": "draft",
    })

    async def _boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(exec_hardening, "audit_member_deletion", _boom)
    # The router imports the symbol lazily inside the function, so patch
    # the module attribute it will resolve.
    monkeypatch.setattr("routers.minutes.audit_member_deletion", _boom,
                        raising=False)

    with pytest.raises(RuntimeError):
        await delete_minutes(
            "minutes_audit_fails",
            request=None,
            user={"user_id": "user_test_harden"},
        )

    # The record must SURVIVE — the delete did not proceed.
    rec = await seeded.minutes_records.find_one(
        {"minutes_id": "minutes_audit_fails"})
    assert rec is not None, "a delete whose audit row failed must not commit"


# --------------------------------------------------------------------------- #
# (c) STREAMING TELEMETRY
# --------------------------------------------------------------------------- #
def test_streaming_route_writes_telemetry():
    """The streaming route must insert the same telemetry the batch route does.

    This is a STRUCTURAL assertion on purpose: the streaming route is the
    only route members use, and until this bundle it wrote NO telemetry at
    all, so every member turn was invisible to the measurement framework.
    """
    from routers import chat as chat_router

    src = inspect.getsource(chat_router._chat_stream_generator)
    assert "chat_telemetry" in src, (
        "the streaming route must write a chat_telemetry row"
    )
    assert "response_time_s" in src
    assert "message_length" in src
    assert "has_action_card" in src
    assert "conversation_id" in src
    # The failure path must be loud, not silent.
    assert "logger.warning" in src, (
        "a failed telemetry write must log at WARNING, not debug"
    )


@pytest.mark.asyncio
async def test_streaming_telemetry_row_shape_matches_batch_route():
    """The streaming insert must carry the same fields as the batch insert."""
    from routers import chat as chat_router

    batch_src = inspect.getsource(chat_router.chat)
    stream_src = inspect.getsource(chat_router._chat_stream_generator)

    fields = [
        "response_time_s",
        "message_length",
        "intent",
        "has_action_card",
        "conversation_id",
        "user_id",
        "trust_id",
        "timestamp",
    ]
    for f in fields:
        assert f in batch_src, f"batch route lost field {f}"
        assert f in stream_src, f"streaming route missing field {f}"


# --------------------------------------------------------------------------- #
# (d) REPLY-LINK COVERAGE
# --------------------------------------------------------------------------- #
def test_every_reply_link_route_exists_in_the_frontend():
    """No fabricated routes: every route in the map must be served by App.js."""
    from approval_handler import REPLY_LINK_ROUTES

    app_js = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "src", "App.js"
    )
    with open(app_js, "r", encoding="utf-8") as f:
        frontend = f.read()

    for endpoint_type, template in REPLY_LINK_ROUTES.items():
        route = template.split("?")[0].rstrip("/") or "/"
        # "/minutes/{id}" -> "/minutes/:minutesId"
        if "{id}" in route:
            prefix = route.split("{id}")[0].rstrip("/")
            assert f'path="{prefix}/:minutesId"' in frontend or \
                   f'path="{prefix}/:' in frontend, (
                f"{endpoint_type} -> {template}: no matching frontend route"
            )
        else:
            assert f'path="{route}"' in frontend, (
                f"{endpoint_type} -> {template}: no matching frontend route"
            )


def test_minutes_reply_link_is_not_the_dead_edit_route():
    """/minutes/{id}/edit does not exist — the link must be /minutes/{id}."""
    from approval_handler import REPLY_LINK_ROUTES, build_record_link

    assert REPLY_LINK_ROUTES["minutes"] == "/minutes/{id}"
    assert "/edit" not in REPLY_LINK_ROUTES["minutes"]

    link = build_record_link("minutes", {"record_id": "min_abc123"})
    assert link == "/minutes/min_abc123"
    assert "/edit" not in link


def test_reply_link_covers_every_action_type():
    """Every action type must produce a link or a plain-language reference."""
    from approval_handler import REPLY_LINK_ROUTES, build_record_link

    action_types = [
        "minutes", "contribute_asset", "distribution", "distribution_cancel",
        "asset", "asset_update", "beneficiary", "beneficiary_update",
        "beneficiary_removal", "send_certificate", "class_beneficiary",
        "class_beneficiary_removal", "document_upload", "compensation_plan",
        "compensation_payment", "investment", "task", "transaction", "entity",
        "settings_update", "alert_dismiss",
    ]

    for endpoint_type in action_types:
        assert endpoint_type in REPLY_LINK_ROUTES, (
            f"{endpoint_type} has no reply-link route"
        )
        link = build_record_link(endpoint_type, {"record_id": "rec_123"})
        assert link, f"{endpoint_type} produced no link"
        # Either a real route (starts with /) or a plain reference — never a
        # fabricated URL.
        if link.startswith("/"):
            assert link.count("/") >= 1
        else:
            assert "rec_123" in link, (
                f"{endpoint_type} named the record but lost the id: {link!r}"
            )


def test_action_type_without_route_is_named_plainly():
    """A record type with no member-facing route must be named, not faked."""
    from approval_handler import build_record_link

    link = build_record_link("some_unrouted_type", {"record_id": "abc123"})
    assert not link.startswith("/"), "must not fabricate a route"
    assert "abc123" in link


def test_success_message_carries_the_link():
    """The member's confirmation must end with where the record went."""
    from approval_handler import build_success_message

    text = build_success_message(
        "quarterly minutes",
        {"record_id": "min_xyz789", "endpoint_type": "minutes"},
        "minutes",
    )
    assert "/minutes/min_xyz789" in text, text
    assert "Done" in text


def test_success_message_surfaces_the_caveat():
    """A substituted minutes type must be visible to the member."""
    from approval_handler import build_success_message

    text = build_success_message(
        "minutes",
        {
            "record_id": "min_xyz789",
            "endpoint_type": "minutes",
            "caveat": "Minutes type 'Quarterly Review' was saved as 'quarterly'.",
        },
        "minutes",
    )
    assert "Quarterly Review" in text, text
    assert "/minutes/min_xyz789" in text
