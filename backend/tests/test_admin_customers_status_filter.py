"""Regression: admin customer list — subscription-status filter must apply BEFORE
pagination.

2026-09-15 (Jeff): switching the status filter in admin → customers only filtered
the ~20 rows on the current page instead of the full customer base. Root cause:
list_customers() paginated users first, then applied the status filter in Python
inside _enrich_customers() over just that page. Status lives on the
subscriptions collection, so it now resolves matching user_ids in Mongo and
constrains users.user_id BEFORE skip/limit — total and every page reflect the
real filtered set.

Runs fully in-process against mongomock; no live server, no prod writes.
(Also protected by tests/conftest.py: blocked entirely if a prod URL is set.)
"""
import importlib.util
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_fix_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

# Route database.py's Motor client to mongomock (in-process) BEFORE import.
import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import database
from routers.admin import list_customers

db = database.db

TOTAL_USERS = 25
PAGE = 20
ACTIVE_IDS = [f"user_{i:02d}" for i in range(6)]  # 0-5 active, 6-10 trialing,
# 11-12 canceled, 13-24 no subscription doc


def _seeded_call(**kwargs):
    """Seed fresh data and issue the call on ONE event loop (mongomock binds per-loop)."""
    import asyncio

    async def _run():
        await db.users.delete_many({})
        await db.subscriptions.delete_many({})
        users, subs = [], []
        for i in range(TOTAL_USERS):
            uid = f"user_{i:02d}"
            users.append({
                "user_id": uid,
                "email": f"{uid}@example.com",
                "name": f"User {i:02d}",
                "is_admin": False,
                "is_stats_user": False,
                "is_leads_user": False,
                "created_at": f"2026-08-{(i % 28) + 1:02d}T10:00:00Z",
            })
            if i <= 5:
                status = "active"
            elif i <= 10:
                status = "trialing"
            elif i <= 12:
                status = "canceled"
            else:
                continue  # no subscription doc
            subs.append({"user_id": uid, "plan_type": "trustee", "status": status})
        await db.users.insert_many(users)
        await db.subscriptions.insert_many(subs)
        return await list_customers(
            search=kwargs.get("search"), status=kwargs.get("status"),
            is_admin_filter=None, sort_by="created_at", sort_order="desc",
            page=kwargs.get("page", 1), limit=PAGE, admin={"user_id": "admin"},
        )

    return asyncio.run(_run())


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mongomock_motor") is None,
    reason="mongomock_motor not installed",
)


class TestStatusFilterBeforePagination:

    def test_no_filter_baseline(self):
        r = _seeded_call()
        assert r["total"] == TOTAL_USERS
        assert len(r["customers"]) == PAGE

    def test_active_total_and_rows(self):
        """THE bug: total must be ALL active customers (6), not page-size matches."""
        r = _seeded_call(status="active")
        assert r["total"] == len(ACTIVE_IDS)
        assert all(c["subscription_status"] == "active" for c in r["customers"])

    def test_active_page2_empty(self):
        """All 6 actives fit on page 1 — page 2 must exist but be empty."""
        r = _seeded_call(status="active", page=2)
        assert r["total"] == len(ACTIVE_IDS)
        assert r["customers"] == []

    def test_trialing_total(self):
        r = _seeded_call(status="trialing")
        assert r["total"] == 5

    def test_search_plus_status(self):
        """'2' matches user_02, user_12, user_20-24; only user_02 is active."""
        r = _seeded_call(status="active", search="2")
        assert r["total"] == 1
        assert r["customers"][0]["user_id"] == "user_02"

    def test_active_row_set(self):
        """Old code returned only user_05 (sole active in newest 20)."""
        r = _seeded_call(status="active")
        assert {c["user_id"] for c in r["customers"]} == set(ACTIVE_IDS)