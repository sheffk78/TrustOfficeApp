"""Session-1 read-path tests: dashboard members[] extension + legacy GET roster.

Covers the two read surfaces the 2026-10-07 council session-1 scope added:
  1. get_beneficiary_dashboard — each class_beneficiaries row now carries
     members[] (id-keyed derived shares), active_member_count,
     pool_percentage_ppm, share_mode="per_capita_equal". Empty-roster classes
     (Harmony Haven case) render with members=[] and pool intact.
  2. list_class_members on a LEGACY roster — docs predating the feature
     (no member_status / member_order): shares must still derive exactly,
     ordered by confirmed_at then class_member_id.

Real local mongod, dedicated throwaway DB, no transactions, no live server,
no prod URL (conftest gate unaffected). Real Motor binds its client to the
FIRST event loop it awaits on, so the whole module runs on ONE module-scoped
pytest-asyncio loop (repo pattern: tests/test_migrate_class_member_shares.py).
Dashboard rows are ClassBeneficiaryResponse models — attribute access.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["DB_NAME"] = "trustoffice_test_cm_dashboard_s1"
os.environ["JWT_SECRET"] = "test-jwt-dashboard-s1"

# Standalone-only, like the sibling txn suite (test_class_member_mutations.py).
# Motor binds its client to the FIRST loop that awaits; two real-motor suites
# sharing database.db inside one pytest process make the second module's
# module-scoped loop hit closed-loop futures (established 2026-10-07 combined
# run). Run:  TR_CLASS_DASHBOARD_SUITE=1 .venv/bin/python -m pytest tests/test_class_member_dashboard.py
pytestmark = pytest.mark.skipif(
    os.environ.get("TR_CLASS_DASHBOARD_SUITE", "") != "1",
    reason="real-mongo suite sharing database.db — run standalone with TR_CLASS_DASHBOARD_SUITE=1",
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
from fastapi import HTTPException
from routers.beneficiaries import get_beneficiary_dashboard, list_class_members

db = database.db

# motor futures bind to the loop running at first use; with pytest-asyncio's
# default function-scoped loop the SECOND test's loop gets futures created on
# the first test's loop → "Event loop is closed". One module-scoped loop
# keeps the real-motor client coherent (repo pattern:
# tests/test_migrate_class_member_shares.py).
pytestmark = pytest.mark.asyncio(loop_scope="module")

USER = "u_dash_s1"
TRUST = "tr_dash_s1"
NOW = datetime.now(timezone.utc)


def _iso(minutes_ago: int) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def _member(mid, name, minutes_ago, class_id="cb_dash_a", **extra):
    doc = {
        "class_member_id": mid, "class_beneficiary_id": class_id,
        "trust_id": TRUST, "user_id": USER, "name": name,
        "confirmed_by_user_id": USER, "confirmed_at": _iso(minutes_ago),
        "created_at": _iso(minutes_ago),
    }
    doc.update(extra)
    return doc


async def _seed(extra_members=()):
    for coll in ("users", "trusts", "trust_units_settings", "trust_unit_certificates",
                 "trust_unit_transfers", "class_beneficiaries",
                 "class_beneficiary_members", "class_member_events"):
        await db[coll].delete_many({})
    await db.trusts.insert_one({
        "trust_id": TRUST, "user_id": USER, "name": "Session-1 Dash Trust",
        "created_at": _iso(999),
    })
    # class A: 100% pool, legacy members (one deceased); class B: 40% pool, empty roster
    await db.class_beneficiaries.insert_many([
        {"class_beneficiary_id": "cb_dash_a", "trust_id": TRUST, "user_id": USER,
         "class_type": "descendants", "class_type_label": "Descendants",
         "description": "legacy roster class", "percentage": 100.0, "notes": "",
         "distribution_convention": "per_capita", "member_count": 3,
         "created_at": _iso(500)},
        {"class_beneficiary_id": "cb_dash_b", "trust_id": TRUST, "user_id": USER,
         "class_type": "charity", "class_type_label": "Charity",
         "description": "empty-roster class", "percentage": 40.0, "notes": "",
         "distribution_convention": "per_capita", "member_count": 0,
         "created_at": _iso(499)},
    ])
    base_members = [
        _member("cm_leg1", "Alice", 300),
        _member("cm_leg2", "Bob", 200),
        _member("cm_leg3", "Cara", 100, member_status="deceased"),
    ]
    await db.class_beneficiary_members.insert_many([*base_members, *extra_members])
    # a DIFFERENT owner's class must never leak into USER's dashboard
    await db.class_beneficiaries.insert_one({
        "class_beneficiary_id": "cb_other", "trust_id": "tr_other", "user_id": "u_other",
        "class_type": "descendants", "class_type_label": "Descendants",
        "description": "other tenant", "percentage": 90.0, "notes": "",
        "distribution_convention": "per_capita", "member_count": 0,
        "created_at": _iso(400),
    })


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def seeded():
    await _seed()
    yield


class TestDashboardMembersExtension:
    async def test_members_attached_with_exact_shares(self, seeded):
        dash = await get_beneficiary_dashboard(trust_id=TRUST, user={"user_id": USER})
        by_id = {cb.class_beneficiary_id: cb for cb in dash.class_beneficiaries}
        a = by_id["cb_dash_a"]
        assert a.share_mode == "per_capita_equal"
        assert a.pool_percentage_ppm == 1_000_000
        assert a.active_member_count == 2
        ids = [m["class_member_id"] for m in a.members]
        assert ids == ["cm_leg1", "cm_leg2"]  # creation order; deceased absent
        ppms = [m["share_ppm"] for m in a.members]
        assert ppms == [500_000, 500_000]
        assert sum(ppms) == a.pool_percentage_ppm
        assert [m["share_pct"] for m in a.members] == [50.0, 50.0]

    async def test_empty_roster_class_renders_undistributed(self, seeded):
        dash = await get_beneficiary_dashboard(trust_id=TRUST, user={"user_id": USER})
        by_id = {cb.class_beneficiary_id: cb for cb in dash.class_beneficiaries}
        b = by_id["cb_dash_b"]
        assert b.members == []
        assert b.active_member_count == 0
        assert b.pool_percentage_ppm == 400_000  # pool intact, undistributed
        assert b.share_mode == "per_capita_equal"

    async def test_tenant_isolation_on_dashboard(self, seeded):
        dash = await get_beneficiary_dashboard(trust_id=TRUST, user={"user_id": USER})
        ids = {cb.class_beneficiary_id for cb in dash.class_beneficiaries}
        assert "cb_other" not in ids


class TestLegacyRosterGet:
    async def test_legacy_docs_derive_exactly_without_member_fields(self, seeded):
        body = await list_class_members("cb_dash_a", user={"user_id": USER})
        assert body["member_count"] == 3
        assert body["active_member_count"] == 2
        assert body["pool_percentage_ppm"] == 1_000_000
        assert body["sum_check_ppm"] == 1_000_000
        rows = body["per_member_shares"]
        assert [(r["class_member_id"], r["share_ppm"]) for r in rows] == [
            ("cm_leg1", 500_000), ("cm_leg2", 500_000)]
        assert body["per_member_shares"][0]["share_pct"] == 50.0
        # items stay position-aligned for the UI; deceased member shows 0
        by_id = {i["class_member_id"]: i for i in body["items"]}
        assert by_id["cm_leg3"]["member_share_ppm"] == 0
        assert by_id["cm_leg3"]["member_share_percent"] == 0.0
        assert by_id["cm_leg1"]["member_share_ppm"] == 500_000

    async def test_legacy_tie_order_and_exact_split(self, seeded):
        # Additional members with a confirmed_at tie: id breaks it (cm_tie_a
        # before cm_tie_b deterministically). Seeded INSIDE this test so the
        # shared module fixture stays untouched.
        tied = (
            _member("cm_tie_b", "Tie B", 120),
            _member("cm_tie_a", "Tie A", 120),
        )
        await db.class_beneficiary_members.insert_many(tied)
        try:
            body = await list_class_members("cb_dash_a", user={"user_id": USER})
        finally:
            await db.class_beneficiary_members.delete_many(
                {"class_member_id": {"$in": ["cm_tie_a", "cm_tie_b"]}})
        rows = body["per_member_shares"]
        active_ids = [r["class_member_id"] for r in rows]
        assert active_ids == ["cm_leg1", "cm_leg2", "cm_tie_a", "cm_tie_b"]
        ppms = [r["share_ppm"] for r in rows]
        assert sum(ppms) == 1_000_000
        assert max(ppms) - min(ppms) <= 1

    async def test_roster_unknown_class_404(self, seeded):
        with pytest.raises(HTTPException) as exc:
            await list_class_members("cb_missing", user={"user_id": USER})
        assert exc.value.status_code == 404