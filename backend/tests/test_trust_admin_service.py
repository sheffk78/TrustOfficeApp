"""Unit tests for Trust Administrative Services invite clock + entitlement.

Pure unit: exercises backend/trust_admin_service.py directly with injected
dates. No DB, no network, no production contact (see tests/conftest.py gate).
"""
import os
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trust_admin_service import (  # noqa: E402
    add_months,
    compute_quarter_end,
    days_past_quarter,
    invite_due,
    new_gift_entitlement,
    resolve_entitlement,
)


# ==================== add_months ====================

class TestAddMonths:
    def test_basic(self):
        assert add_months(date(2026, 7, 23), 3) == date(2026, 10, 23)

    def test_clamp_month_end(self):
        assert add_months(date(2026, 1, 31), 3) == date(2026, 4, 30)

    def test_clamp_feb_leap(self):
        assert add_months(date(2025, 11, 30), 3) == date(2026, 2, 28)

    def test_year_rollover(self):
        assert add_months(date(2026, 11, 6), 3) == date(2027, 2, 6)


# ==================== quarter clock ====================

class TestQuarterClock:
    def test_quarter_end(self):
        assert compute_quarter_end("2026-07-13T21:38:21.367313+00:00") == date(2026, 10, 13)

    def test_days_remaining(self):
        # Aug 6 + 3 months = Nov 6; Sep 12 is 55 days before that.
        assert days_past_quarter("2026-08-06", now=date(2026, 9, 12)) == -55

    def test_exactly_three_months_is_due(self):
        assert days_past_quarter("2026-06-12", now=date(2026, 9, 12)) == 0
        assert invite_due("2026-06-12", now=date(2026, 9, 12)) is True

    def test_day_before_not_due(self):
        assert invite_due("2026-06-13", now=date(2026, 9, 12)) is False

    def test_no_trust_yet_no_clock(self):
        assert days_past_quarter(None, now=date(2026, 9, 12)) is None
        assert invite_due(None, now=date(2026, 9, 12)) is False

    def test_timezone_normalized_to_utc(self):
        # Denver evening (MDT, UTC-6) belongs to the NEXT UTC day (Sep 13).
        # Quarter therefore ends Dec 13 UTC, and that day the invite is due.
        dt = datetime(2026, 9, 12, 22, 0, tzinfo=timezone(timedelta(hours=-6)))
        assert days_past_quarter(dt.isoformat(), now=date(2026, 12, 13)) == 0


# ==================== entitlement ====================

class TestResolveEntitlement:
    def test_no_subscription(self):
        r = resolve_entitlement(None)
        assert r == {"entitled": False, "source": "none", "status": "none",
                     "quarter_ends": None, "days_past": None}

    def test_purchased_active(self):
        sub = {"trust_admin_service": {"status": "active", "source": "purchased"}}
        assert resolve_entitlement(sub)["entitled"] is True
        assert resolve_entitlement(sub)["source"] == "purchased"

    def test_purchased_cancelled(self):
        sub = {"trust_admin_service": {"status": "cancelled", "source": "purchased"}}
        r = resolve_entitlement(sub)
        assert r["entitled"] is False and r["status"] == "cancelled"

    def test_gifted_within_quarter(self):
        sub = {
            "trust_admin_service": {"source": "gifted", "status": "active"},
            "_first_trust_created_at": "2026-07-23T18:58:20.111060+00:00",
        }
        r = resolve_entitlement(sub, now=date(2026, 10, 1))
        assert r["entitled"] is True
        assert r["quarter_ends"] == "2026-10-23"

    def test_gifted_expired(self):
        sub = {
            "trust_admin_service": {"source": "gifted", "status": "active"},
            "_first_trust_created_at": "2026-05-10T03:29:14.069531+00:00",
        }
        r = resolve_entitlement(sub, now=date(2026, 9, 12))
        assert r["entitled"] is False
        assert r["status"] == "expired"
        assert r["days_past"] == 33

    def test_gifted_no_trust_yet_quarter_not_started(self):
        sub = {"trust_admin_service": {"source": "gifted", "status": "active"}}
        r = resolve_entitlement(sub, now=date(2026, 9, 12))
        assert r["entitled"] is True  # quarter has not started; still entitled
        assert r["quarter_ends"] is None

    def test_gift_with_backdated_trust_corrects_clock(self):
        """Back-dated import (document import) must move the clock, not break it."""
        sub = {
            "trust_admin_service": {"source": "gifted", "status": "active"},
            "_first_trust_created_at": "2026-04-01T00:00:00+00:00",
        }
        r = resolve_entitlement(sub, now=date(2026, 9, 12))
        assert r["status"] == "expired"

    def test_real_cohort_dates(self):
        """The five real cohort members from the 2026-09-12 cohort analysis."""
        cohort = [
            ("user_5c853559b1e8", "2026-07-23T18:58:20.111060+00:00"),  # Kratt
            ("user_9ea5d362515b", "2026-07-13T21:38:21.367313+00:00"),  # Bartlett
            ("user_2891b4cddd89", "2026-08-17T18:13:40.653985+00:00"),  # Roufs
            ("user_9b0ddd056877", "2026-07-14T04:02:39.955882+00:00"),  # Tudsbury
            ("user_5cef08a205c7", "2026-08-06T20:43:30.432214+00:00"),  # Barlow
        ]
        expected_quarter_ends = {
            "user_5c853559b1e8": "2026-10-23",   # Kratt
            "user_9ea5d362515b": "2026-10-13",   # Bartlett
            "user_2891b4cddd89": "2026-11-17",   # Roufs
            "user_9b0ddd056877": "2026-10-14",   # Tudsbury
            "user_5cef08a205c7": "2026-11-06",   # Barlow
        }
        today = date(2026, 9, 12)
        for uid, anchor in cohort:
            past = days_past_quarter(anchor, now=today)
            assert past is not None and past < 0, f"{uid}: quarter already elapsed?!"
        # Exact quarter ends for every cohort member
        for uid, anchor in cohort:
            assert compute_quarter_end(anchor).isoformat() == expected_quarter_ends[uid]


# ==================== gift doc shape ====================

class TestGiftDoc:
    def test_new_gift_entitlement_shape(self):
        doc = new_gift_entitlement(granted_by="admin@trustoffice.app", note="FTD client")
        assert doc["status"] == "active"
        assert doc["source"] == "gifted"
        assert doc["gift_type"] == "free_quarter"
        assert "granted_at" in doc
        assert "quarter_ends_at" not in doc  # derived, never stored