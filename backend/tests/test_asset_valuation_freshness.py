"""Regression tests: asset valuation freshness fix (2026-09-25).

Root cause being guarded: last_valued_date was absent from the product, so the
health score judged asset freshness by date_conveyed forever — an asset conveyed
years ago was permanently 'stale' with no UI remedy.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)


def _data(assets, trust_created=None):
    return {
        "now": NOW,
        "twelve_months_ago": NOW - timedelta(days=365),
        "trust_created_at": trust_created,
        "active_assets": assets,
    }


def _asset(conveyed="2020-01-15", valued=None):
    a = {"description": "House", "date_conveyed": conveyed}
    if valued:
        a["last_valued_date"] = valued
    return a


# --- _is_asset_stale: last_valued_date must win over date_conveyed ---

def test_asset_valued_recently_is_fresh_despite_old_conveyance():
    from routers.governance import _is_asset_stale
    # conveyed 2020, valued last month → FRESH (this was the bug: scored stale)
    a = _asset(conveyed="2020-01-15", valued="2026-08-01")
    assert _is_asset_stale(a, NOW - timedelta(days=365)) is False


def test_asset_valued_long_ago_is_stale():
    from routers.governance import _is_asset_stale
    a = _asset(conveyed="2020-01-15", valued="2024-06-01")
    assert _is_asset_stale(a, NOW - timedelta(days=365)) is True


def test_asset_without_any_date_is_stale():
    from routers.governance import _is_asset_stale
    assert _is_asset_stale({"description": "mystery"}, NOW - timedelta(days=365)) is True


def test_legacy_asset_falls_back_to_conveyance_date():
    from routers.governance import _is_asset_stale
    # no last_valued_date (legacy item) → conveyance date governs, as before
    a = _asset(conveyed="2020-01-15")
    assert _is_asset_stale(a, NOW - timedelta(days=365)) is True


# --- criterion: new-trust grace ---

def test_new_trust_assets_get_grace_not_penalty():
    from routers.governance import _compute_asset_valuation_criterion
    trust_created = (NOW - timedelta(days=30)).isoformat()
    assets = [_asset(conveyed="2020-01-15")]  # would be stale for an old trust
    criterion, points = _compute_asset_valuation_criterion(
        _data(assets, trust_created=trust_created)
    )
    assert criterion.no_data is True
    assert criterion.points == 15
    assert criterion.achieved is True


def test_old_trust_with_stale_assets_still_scored_down():
    from routers.governance import _compute_asset_valuation_criterion
    trust_created = (NOW - timedelta(days=400)).isoformat()
    assets = [_asset(conveyed="2020-01-15")]  # stale, no remedy recorded
    criterion, points = _compute_asset_valuation_criterion(
        _data(assets, trust_created=trust_created)
    )
    assert criterion.no_data is False
    assert criterion.points < 15


def test_old_trust_with_recent_valuation_scores_full():
    from routers.governance import _compute_asset_valuation_criterion
    trust_created = (NOW - timedelta(days=400)).isoformat()
    assets = [_asset(conveyed="2020-01-15", valued="2026-08-01")]
    criterion, points = _compute_asset_valuation_criterion(
        _data(assets, trust_created=trust_created)
    )
    assert criterion.points == 15
    assert criterion.achieved is True


def test_no_assets_stays_no_data():
    from routers.governance import _compute_asset_valuation_criterion
    criterion, points = _compute_asset_valuation_criterion(
        _data([], trust_created=(NOW - timedelta(days=400)).isoformat())
    )
    assert criterion.no_data is True
    assert points == 0


# --- schedule_a models accept the new field ---

def test_schedule_a_create_accepts_last_valued_date():
    from models import ScheduleAItemCreate
    item = ScheduleAItemCreate(
        trust_id="trust_x", category="real_property", description="House",
        date_conveyed="2020-01-15", last_valued_date="2026-08-01",
    )
    assert item.last_valued_date == "2026-08-01"


def test_schedule_a_update_accepts_last_valued_date():
    from models import ScheduleAItemUpdate
    upd = ScheduleAItemUpdate(last_valued_date="2026-09-25")
    assert upd.last_valued_date == "2026-09-25"