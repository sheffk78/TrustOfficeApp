"""
Tests for security event logging + anomaly alerting.

Pure-unit tests (no live server, no real DB, no real Discord). The database
and discord_service modules are monkeypatched so the service layer can be
exercised in isolation. Guards the contract from the security council decision:

  1. record_security_event writes the expected doc shape to security_events.
  2. The 5th failed login for the same user/email within 15 min fires an alert.
  3. Dedupe suppresses a second alert for the same (rule, user) within 30 min.
  4. A DB write failure does NOT raise (logging must never break a request).

Run only this file:
    python -m pytest backend/tests/test_security_events.py -v
"""
import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# `database.py` reads MONGO_URL/DB_NAME at import time; provide dummies so the
# module imports without a live Mongo. Tests then monkeypatch `database.db`.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")

# Make `backend/` importable as a package root for the service module.
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import services.security_events as se  # noqa: E402  (needs BACKEND_DIR on path first)


def _make_fake_db(collection=None):
    """Build a fake `database.db` whose security_events.insert_one is AsyncMock.

    collection: an object exposing count_documents / insert_one as coroutines.
    """
    if collection is None:
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(return_value=0)
    db = MagicMock()
    db.security_events = collection
    return db


@pytest.fixture(autouse=True)
def _clear_dedup_cache():
    """Ensure the in-memory alert dedup cache starts empty for every test."""
    se._ALERT_CACHE.clear()
    yield
    se._ALERT_CACHE.clear()


# ---------------------------------------------------------------------------
# 1. record_security_event writes the expected doc shape
# ---------------------------------------------------------------------------

class TestRecordSecurityEvent:
    def test_event_recorded_with_expected_shape(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        db = _make_fake_db(collection)

        with patch("database.db", db):
            asyncio.run(
                se.record_security_event(
                    "user_123",
                    "login_failed",
                    ip="1.2.3.4",
                    user_agent="curl/8",
                    details={"email": "a@b.com"},
                )
            )

        assert collection.insert_one.await_count == 1
        doc = collection.insert_one.call_args.args[0]
        assert doc["user_id"] == "user_123"
        assert doc["event_type"] == "login_failed"
        assert doc["ip"] == "1.2.3.4"
        assert doc["user_agent"] == "curl/8"
        assert doc["details"] == {"email": "a@b.com"}
        # ts must be a UTC ISO timestamp
        ts = datetime.fromisoformat(doc["ts"].replace("Z", "+00:00"))
        assert ts.tzinfo is not None

    def test_event_recorded_with_none_user_and_no_details(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        db = _make_fake_db(collection)

        with patch("database.db", db):
            asyncio.run(se.record_security_event(None, "logout"))

        doc = collection.insert_one.call_args.args[0]
        assert doc["user_id"] is None
        assert doc["details"] == {}


# ---------------------------------------------------------------------------
# 2. 5th failed login fires an alert
# ---------------------------------------------------------------------------

class TestFailedLoginAlert:
    def test_fifth_failed_login_fires_alert(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        # In production the call site records the event FIRST, so by the time we
        # count, 5 failures exist. We mirror that post-insert state here.
        collection.count_documents = AsyncMock(return_value=5)
        db = _make_fake_db(collection)

        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(
                se.check_security_alert("login_failed", user_id="user_x", email="x@y.com")
            )

        assert result["alerted"] is True
        assert result["count"] == 5
        assert notify.await_count == 1

    def test_fourth_failed_login_does_not_fire(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(return_value=3)
        db = _make_fake_db(collection)

        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(
                se.check_security_alert("login_failed", user_id="user_x", email="x@y.com")
            )

        assert result["alerted"] is False
        assert notify.await_count == 0

    def test_alert_uses_email_when_no_user_id(self):
        """login_failed for an unknown email has no user_id; dedup/query key on email."""
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(return_value=5)  # >= threshold
        db = _make_fake_db(collection)

        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(
                se.check_security_alert("login_failed", email="unknown@y.com")
            )

        assert result["alerted"] is True
        # count_documents must have queried on details.email for no-user_id case
        q = collection.count_documents.call_args.args[0]
        assert q["details.email"] == "unknown@y.com"
        assert notify.await_count == 1


# ---------------------------------------------------------------------------
# 3. Dedupe suppresses within 30 min
# ---------------------------------------------------------------------------

class TestDedupe:
    def test_second_alert_suppressed_within_window(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(return_value=10)  # way over threshold
        db = _make_fake_db(collection)

        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            first = asyncio.run(
                se.check_security_alert("login_failed", user_id="user_d")
            )
            second = asyncio.run(
                se.check_security_alert("login_failed", user_id="user_d")
            )

        assert first["alerted"] is True
        assert second["alerted"] is False
        assert second["duplicate"] is True
        assert notify.await_count == 1

    def test_alert_fires_again_after_window(self, monkeypatch):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(return_value=10)
        db = _make_fake_db(collection)

        # Force the clock forward >30 min for the second call.
        fake_time = {"t": 1_000_000.0}

        def fake_now():
            return fake_time["t"]

        monkeypatch.setattr(se.time, "time", fake_now)

        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            first = asyncio.run(
                se.check_security_alert("login_failed", user_id="user_d2")
            )
            fake_time["t"] += 31 * 60  # advance 31 minutes
            second = asyncio.run(
                se.check_security_alert("login_failed", user_id="user_d2")
            )

        assert first["alerted"] is True
        assert second["alerted"] is True
        assert notify.await_count == 2


# ---------------------------------------------------------------------------
# 4. DB failure does not raise
# ---------------------------------------------------------------------------

class TestDBFailureSafe:
    def test_insert_failure_is_swallowed(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock(side_effect=RuntimeError("mongo down"))
        db = _make_fake_db(collection)

        # Should NOT raise.
        with patch("database.db", db):
            asyncio.run(se.record_security_event("u", "login_failed"))

    def test_count_failure_is_swallowed_and_no_alert(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(side_effect=RuntimeError("mongo down"))
        db = _make_fake_db(collection)

        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            # Should NOT raise even though counting blew up.
            result = asyncio.run(
                se.check_security_alert("login_failed", user_id="u")
            )

        assert result["alerted"] is False
        assert notify.await_count == 0

    def test_notify_failure_is_swallowed(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(return_value=10)
        db = _make_fake_db(collection)

        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock(side_effect=RuntimeError("discord down"))
        ):
            # Should NOT raise even though Discord send blew up.
            result = asyncio.run(
                se.check_security_alert("login_failed", user_id="u")
            )

        assert result["alerted"] is False


# ---------------------------------------------------------------------------
# 5. Other rules behave as specified
# ---------------------------------------------------------------------------

class TestOtherRules:
    def test_admin_impersonation_always_alerts(self):
        with patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(
                se.alert_security_event(
                    "admin_impersonation",
                    user_id="admin_1",
                    details={"target_user_id": "u2"},
                )
            )
        assert result["alerted"] is True
        assert notify.await_count == 1

    def test_refresh_reuse_always_alerts(self):
        with patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(
                se.alert_security_event("refresh_reuse_detected", user_id="u")
            )
        assert result["alerted"] is True
        assert notify.await_count == 1

    def test_bulk_export_over_50_alerts(self):
        with patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(
                se.alert_security_event("bulk_export", user_id="u", count=120)
            )
        assert result["alerted"] is True
        assert notify.await_count == 1

    def test_bulk_export_under_50_no_alert(self):
        with patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(
                se.alert_security_event("bulk_export", user_id="u", count=10)
            )
        assert result["alerted"] is False
        assert notify.await_count == 0

    def test_vault_download_over_20_alerts(self):
        collection = MagicMock()
        collection.insert_one = AsyncMock()
        collection.count_documents = AsyncMock(return_value=25)
        db = _make_fake_db(collection)
        with patch("database.db", db), patch(
            "services.security_events.notify_alert", new=AsyncMock()
        ) as notify:
            result = asyncio.run(se.check_security_alert("vault_download", user_id="u"))
        assert result["alerted"] is True
        assert notify.await_count == 1
