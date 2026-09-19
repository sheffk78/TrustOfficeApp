"""Regression tests: demo-health + transaction-classification fixes.

Jeff approved 2026-09-19 (demo account shows critically bad score):
  1. Evergreen demo minutes: _top_up_demo_quarterly_minutes inserts one
     quarterly demo minute for demo trusts with no minutes this quarter;
     never touches non-demo trusts; idempotent within a quarter.
  2. Transaction Classification field fix: scorer counts
     governance_classification (real field, set at create/bulk-classify),
     not the nonexistent "classification" field (bug: 0/10 forever for every
     trust with txns — 1,411 live snapshots, 0 ever earned points).
"""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi")

import routers.governance as _gov_module


@pytest.fixture(autouse=True)
def _restore_governance_stubs():
    """Snapshot routers.governance attributes before each test and restore
    them after. Tests here assign AsyncMock stubs (gov._gather_risk_findings,
    gov.db) directly onto the shared module object; without restoration the
    stubs leak into every later test module in the same pytest run (seen as
    'TypeError: ... got AsyncMock' in test_health_score_v4's source inspect)."""
    snapshot = dict(vars(_gov_module))
    yield
    restored = {}
    for key, value in list(vars(_gov_module).items()):
        if key not in snapshot or snapshot[key] is not value:
            if key.startswith("_") or key in ("db",):
                restored[key] = snapshot.get(key, value)
    for key, value in restored.items():
        setattr(_gov_module, key, value)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_demo_trust(trust_id="trust_demo1", user_id="user_demo"):
    return {"_id": trust_id, "trust_id": trust_id, "user_id": user_id,
            "name": "Demo Trust", "is_demo": True}


def _quarter_start(dt=None):
    from routers.governance import get_quarter_start
    return get_quarter_start(dt or datetime.now(timezone.utc))


def _fake_db():
    db = MagicMock()
    db.trusts = MagicMock()
    db.minutes_records = MagicMock()
    db.transactions = MagicMock()
    db.trusts.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    return db


# --------------------------------------------------------------------------- #
# 1. Evergreen demo minutes
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_topup_inserts_for_demo_trust_without_quarter_minutes():
    from background_tasks import BackgroundTaskRunner
    runner = BackgroundTaskRunner.__new__(BackgroundTaskRunner)
    runner.db = _fake_db()

    demo = {"trust_id": "trust_demo1", "user_id": "user_demo", "name": "Demo Trust"}
    runner.db.trusts.find.return_value.to_list = AsyncMock(return_value=[demo])
    runner.db.minutes_records.count_documents = AsyncMock(return_value=0)
    runner.db.minutes_records.insert_one = AsyncMock()

    inserted = await runner._top_up_demo_quarterly_minutes()

    assert inserted == 1
    runner.db.minutes_records.insert_one.assert_awaited_once()
    doc = runner.db.minutes_records.insert_one.await_args.args[0]
    assert doc["trust_id"] == "trust_demo1"
    assert doc["is_demo"] is True
    assert doc["minutes_type"] == "quarterly"
    # created_at must fall inside the CURRENT quarter (that's the whole point)
    assert doc["created_at"] >= _quarter_start().isoformat()


@pytest.mark.asyncio
async def test_topup_skips_demo_trust_with_quarter_minutes():
    from background_tasks import BackgroundTaskRunner
    runner = BackgroundTaskRunner.__new__(BackgroundTaskRunner)
    runner.db = _fake_db()

    demo = {"trust_id": "trust_demo1", "user_id": "user_demo", "name": "Demo Trust"}
    runner.db.trusts.find.return_value.to_list = AsyncMock(return_value=[demo])
    runner.db.minutes_records.count_documents = AsyncMock(return_value=2)
    runner.db.minutes_records.insert_one = AsyncMock()

    inserted = await runner._top_up_demo_quarterly_minutes()

    assert inserted == 0
    runner.db.minutes_records.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_topup_never_touches_real_trusts():
    from background_tasks import BackgroundTaskRunner
    runner = BackgroundTaskRunner.__new__(BackgroundTaskRunner)
    runner.db = _fake_db()

    # The query itself must filter is_demo=True — verify the filter arg.
    captured = {}

    def _capture_find(filt, *a, **k):
        captured["filter"] = filt
        return MagicMock(to_list=AsyncMock(return_value=[]))

    runner.db.trusts.find = MagicMock(side_effect=_capture_find)
    await runner._top_up_demo_quarterly_minutes()

    assert captured["filter"] == {"is_demo": True}


@pytest.mark.asyncio
async def test_topup_swallows_per_trust_errors():
    from background_tasks import BackgroundTaskRunner
    runner = BackgroundTaskRunner.__new__(BackgroundTaskRunner)
    runner.db = _fake_db()

    demos = [{"trust_id": f"trust_d{i}", "user_id": "u", "name": "D"} for i in range(2)]
    runner.db.trusts.find.return_value.to_list = AsyncMock(return_value=demos)
    runner.db.minutes_records.count_documents = AsyncMock(side_effect=RuntimeError("boom"))
    runner.db.minutes_records.insert_one = AsyncMock()

    inserted = await runner._top_up_demo_quarterly_minutes()
    assert inserted == 0  # errors swallowed, sweep continues


# --------------------------------------------------------------------------- #
# 2. Transaction classification field fix
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_scorer_counts_governance_classification():
    """_gather_score_data must classify via governance_classification (the real
    field), not 'classification' (never exists — the bug)."""
    import routers.governance as gov

    db = MagicMock()
    db.governance_tasks.find_one = AsyncMock(return_value=None)
    db.trusts.find_one = AsyncMock(return_value={"trust_id": "t", "user_id": "u",
                                                 "created_at": "2026-01-01",
                                                 "tax_year_end_month": 12,
                                                 "tax_year_end_day": 31,
                                                 "benevolence_enabled": False,
                                                 "jurisdiction": "DE"})
    db.schedule_a_items.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=[])))

    seen_filters = []

    async def txn_count(filt, *a, **k):
        seen_filters.append(filt)
        if "classification" in filt and "governance_classification" not in filt:
            raise AssertionError("scorer queried nonexistent 'classification' field")
        if "governance_classification" in filt:
            return 0
        return 0  # total_txns = 0 → classification query never runs

    db.transactions.count_documents = AsyncMock(side_effect=txn_count)

    # Generic async stubs for every other awaited collection call
    for coll in ("governance_tasks", "separation_alerts", "entities",
                 "vault_documents", "user_onboarding", "trust_unit_certificates",
                 "compensation_plans", "distribution_records", "benevolence_records",
                 "minutes_records", "minutes_templates", "tax_calendar",
                 "compensation_payments"):
        m = getattr(db, coll, None)
        if m is None:
            continue
        if hasattr(m, "count_documents"):
            m.count_documents = AsyncMock(return_value=0)
        if hasattr(m, "find_one"):
            m.find_one = AsyncMock(return_value=None)
        if hasattr(m, "find"):
            m.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))

    gov.db = db
    gov._gather_risk_findings = AsyncMock(return_value=[])

    data = await gov._gather_score_data("t", "u", use_cache=False)
    # No txns → criterion is no_data; assert the gather ran and the txn block
    # did not query the dead field (side_effect would have raised).
    assert data["total_txns"] == 0
    assert data["classified_txns"] == 0


@pytest.mark.asyncio
async def test_scorer_uses_real_field_with_txns():
    """With txns present, classification counting must hit governance_classification."""
    import routers.governance as gov

    db = MagicMock()
    db.governance_tasks.find_one = AsyncMock(return_value=None)
    db.trusts.find_one = AsyncMock(return_value={"trust_id": "t", "user_id": "u",
                                                 "created_at": "2026-01-01",
                                                 "tax_year_end_month": 12,
                                                 "tax_year_end_day": 31,
                                                 "benevolence_enabled": False,
                                                 "jurisdiction": "DE"})
    db.schedule_a_items.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=[])))

    calls = []

    async def txn_count(filt, *a, **k):
        calls.append(filt)
        if "classification" in filt and "governance_classification" not in filt:
            raise AssertionError("scorer queried nonexistent 'classification' field")
        if "governance_classification" in filt:
            return 5
        return 7  # total_txns

    db.transactions.count_documents = AsyncMock(side_effect=txn_count)
    for coll in ("governance_tasks", "separation_alerts", "entities",
                 "vault_documents", "user_onboarding", "trust_unit_certificates",
                 "compensation_plans", "distribution_records", "benevolence_records",
                 "minutes_records", "minutes_templates", "tax_calendar",
                 "compensation_payments"):
        m = getattr(db, coll, None)
        if m is None:
            continue
        if hasattr(m, "count_documents"):
            m.count_documents = AsyncMock(return_value=0)
        if hasattr(m, "find_one"):
            m.find_one = AsyncMock(return_value=None)
        if hasattr(m, "find"):
            m.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    db.risk_findings_cache = MagicMock()

    gov.db = db
    # _gather_risk_findings is heavy — stub it
    gov._gather_risk_findings = AsyncMock(return_value=[])

    data = await gov._gather_score_data("t", "u", use_cache=False)
    assert data["total_txns"] == 7
    assert data["classified_txns"] == 5
    assert any("governance_classification" in c for c in calls)