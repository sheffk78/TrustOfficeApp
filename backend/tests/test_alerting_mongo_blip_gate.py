"""Tests for the transient Mongo connection-blip suppression gate.

Background (2026-11-26): background/integration call sites report Mongo
connection errors directly (empty stack, empty URL, no user_id). A transient
blip self-heals in seconds, but the alert fires AFTER recovery — pure noise.

Gate semantics: a server-source Mongo connection alert is suppressed (stored
in error_logs, never pages Discord/Hermes) ONLY when a live ping at report
time proves Mongo is reachable. If the ping FAILS (real outage), the alert
fires unchanged — dedupe already prevents Discord storms.
"""

import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_alert_mongo_blip")
os.environ.setdefault("JWT_SECRET", "test-secret-alert-mongo-blip")
# Prod-like alerting: the test-env gate must NOT mask the blip gate's own
# suppression semantics.
os.environ["ENVIRONMENT"] = "production"
os.environ.pop("HERMES_WEBHOOK_URL", None)

import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database
import error_alerting

db = database.db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    await db.error_logs.delete_many({})
    # Reset the in-process dedupe cache so each test starts from a clean slate
    # (tests share fingerprints like "ConnectionError||" within the 5-min window).
    error_alerting._ALERT_CACHE.clear()
    yield
    await db.error_logs.delete_many({})
    error_alerting._ALERT_CACHE.clear()


@pytest.fixture(autouse=True)
def _restore_ping(monkeypatch):
    """Undo any _mongo_live_ping monkeypatch between tests."""
    yield
    monkeypatch.undo()


# ---------------------------------------------------------------------------
# Predicate unit tests
# ---------------------------------------------------------------------------


def test_is_mongo_connection_alert_matches_conn_fail_types():
    for t in ("ServerSelectionTimeoutError", "AutoReconnect", "ConnectionFailure"):
        assert error_alerting._is_mongo_connection_alert(t, "") is True
    # Generic ConnectionError needs a mongo provenance marker
    assert error_alerting._is_mongo_connection_alert("ConnectionError", "Mongo timeout") is True
    assert error_alerting._is_mongo_connection_alert("ConnectionError", "HTTP connect failed") is False
    assert error_alerting._is_mongo_connection_alert("ValueError", "mongo") is False


# ---------------------------------------------------------------------------
# Live-ping timeout/failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mongo_live_ping_false_when_command_raises(monkeypatch):
    """A failing ping (real outage) must return False so the alert fires."""

    async def _boom(*args, **kwargs):
        raise RuntimeError("no server")

    monkeypatch.setattr(error_alerting.db, "command", _boom)
    assert await error_alerting._mongo_live_ping() is False


@pytest.mark.asyncio
async def test_mongo_live_ping_false_when_command_times_out(monkeypatch):
    """A ping that exceeds the 3s budget must be bounded and return False."""
    import asyncio

    async def _slow(*args, **kwargs):
        await asyncio.sleep(10.0)
        return {"ok": 1.0}

    monkeypatch.setattr(error_alerting.db, "command", _slow)
    assert await error_alerting._mongo_live_ping() is False


@pytest.mark.asyncio
async def test_mongo_live_ping_true_when_reachable(monkeypatch):
    """A healthy ping returns True (mongomock returns {'ok': 1.0})."""
    assert await error_alerting._mongo_live_ping() is True


# ---------------------------------------------------------------------------
# Gate behavior inside report_error()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_error_mongo_ping_ok_suppressed(monkeypatch):
    """ConnectionError + mongo message + ping OK -> no alert, transient marker."""
    called = {"notify": 0, "hermes": 0}

    async def _no_notify(**kwargs):
        called["notify"] += 1
        return True

    async def _no_hermes(payload):
        called["hermes"] += 1
        return True

    async def _ping_ok():
        return True

    monkeypatch.setattr(error_alerting, "notify_alert", _no_notify)
    monkeypatch.setattr(error_alerting, "_trigger_hermes_agent", _no_hermes)
    monkeypatch.setattr(error_alerting, "_mongo_live_ping", _ping_ok)

    result = await error_alerting.report_error(
        source="server",
        error_type="ConnectionError",
        error_message="Mongo connection refused",
    )

    assert result["alerted"] is False
    assert result["duplicate"] is False
    assert result["transient_mongo_blip"] is True
    assert called["notify"] == 0 and called["hermes"] == 0


@pytest.mark.asyncio
async def test_conn_fail_ping_false_alert_fires(monkeypatch):
    """Any conn-fail type with ping False -> alert FIRES (dedupe/webhook path)."""
    called = {"notify": 0, "hermes": 0}

    async def _count_notify(**kwargs):
        called["notify"] += 1
        return True

    async def _yes_hermes(payload):
        called["hermes"] += 1
        return True

    async def _ping_fail():
        return False

    monkeypatch.setattr(error_alerting, "notify_alert", _count_notify)
    monkeypatch.setattr(error_alerting, "_trigger_hermes_agent", _yes_hermes)
    monkeypatch.setattr(error_alerting, "_mongo_live_ping", _ping_fail)

    for t in ("ConnectionError", "ServerSelectionTimeoutError", "AutoReconnect", "ConnectionFailure"):
        result = await error_alerting.report_error(
            source="server",
            error_type=t,
            error_message="Mongo connection lost",
        )
        assert result["alerted"] is True, t
        assert "transient_mongo_blip" not in result, t
    assert called["hermes"] == 4


@pytest.mark.asyncio
async def test_non_mongo_connection_error_ping_ok_still_fires(monkeypatch):
    """A non-mongo ConnectionError with ping OK must NOT be suppressed."""
    called = {"hermes": 0}

    async def _yes_hermes(payload):
        called["hermes"] += 1
        return True

    async def _no_notify(**kwargs):
        return True

    async def _ping_ok():
        return True

    monkeypatch.setattr(error_alerting, "notify_alert", _no_notify)
    monkeypatch.setattr(error_alerting, "_trigger_hermes_agent", _yes_hermes)
    monkeypatch.setattr(error_alerting, "_mongo_live_ping", _ping_ok)

    result = await error_alerting.report_error(
        source="server",
        error_type="ConnectionError",
        error_message="Upstream HTTP connection failed",
    )

    assert result["alerted"] is True
    assert "transient_mongo_blip" not in result
    assert called["hermes"] == 1


@pytest.mark.asyncio
async def test_suppressed_blip_still_stored(monkeypatch):
    """Suppression must not skip storage — the doc is still in error_logs."""
    async def _ping_ok():
        return True

    async def _no_notify(**kwargs):
        return True

    async def _no_hermes(payload):
        return True

    monkeypatch.setattr(error_alerting, "_mongo_live_ping", _ping_ok)
    monkeypatch.setattr(error_alerting, "notify_alert", _no_notify)
    monkeypatch.setattr(error_alerting, "_trigger_hermes_agent", _no_hermes)

    result = await error_alerting.report_error(
        source="server",
        error_type="ConnectionError",
        error_message="Mongo connection refused",
    )
    assert result["transient_mongo_blip"] is True

    doc = await db.error_logs.find_one({})
    assert doc is not None
    assert doc["error_type"] == "ConnectionError"
    assert doc["metadata"]["source"] == "server"
    assert doc["metadata"]["fingerprint"] == result["fingerprint"]
