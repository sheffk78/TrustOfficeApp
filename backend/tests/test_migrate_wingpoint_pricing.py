"""Tests for migrate_wingpoint_pricing.py script.

Pure-unit: mocks Stripe SDK, does NOT hit the network.
"""
import os
import sys
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

# The script lives in backend/scripts/
SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPT_DIR)

import migrate_wingpoint_pricing as mig


# Rebind module constants to test values so we don't depend on the live IDs.
_LEGACY_ANNUAL = "price_legacy_annual"
_LEGACY_MONTHLY = "price_legacy_monthly"
_NEW_ANNUAL = "price_new_annual"
_NEW_MONTHLY = "price_new_monthly"
_OTHER_PRICE = "price_other"


@pytest.fixture(autouse=True)
def _patch_ids(monkeypatch):
    monkeypatch.setattr(mig, "LEGACY_WINGPOINT_ANNUAL", _LEGACY_ANNUAL)
    monkeypatch.setattr(mig, "LEGACY_WINGPOINT_MONTHLY", _LEGACY_MONTHLY)
    monkeypatch.setattr(mig, "NEW_WINGPOINT_ANNUAL", _NEW_ANNUAL)
    monkeypatch.setattr(mig, "NEW_WINGPOINT_MONTHLY", _NEW_MONTHLY)
    monkeypatch.setattr(mig, "LEGACY_TO_NEW", {
        _LEGACY_ANNUAL: _NEW_ANNUAL,
        _LEGACY_MONTHLY: _NEW_MONTHLY,
    })
    monkeypatch.setattr(mig, "_LEGACY_NAMES", {
        _LEGACY_ANNUAL: "legacy_annual",
        _LEGACY_MONTHLY: "legacy_monthly",
    })
    monkeypatch.setattr(mig, "_NEW_NAMES", {
        _NEW_ANNUAL: "new_annual",
        _NEW_MONTHLY: "new_monthly",
    })
    monkeypatch.setattr(mig, "_PRICE_AMOUNTS", {
        _LEGACY_ANNUAL: 1188.0,
        _LEGACY_MONTHLY: 119.0,
        _NEW_ANNUAL: 948.0,
        _NEW_MONTHLY: 99.0,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sub(price_id, sub_id="sub_test", status="active", customer="cus_test",
              current_period_end=None):
    sub = MagicMock()
    sub.to_dict.return_value = {
        "id": sub_id,
        "status": status,
        "customer": customer,
        "current_period_end": current_period_end,
        "items": {"data": [{"price": {"id": price_id}}]},
    }
    return sub


def _make_other_sub(price_id):
    return _make_sub(price_id, sub_id="sub_other", status="active")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_matching_only_legacy_wingpoint(monkeypatch):
    """Only subscriptions with the two legacy WingPoint price IDs are returned."""
    subs = [
        _make_sub(_LEGACY_ANNUAL, sub_id="sub_1"),
        _make_sub(_LEGACY_MONTHLY, sub_id="sub_2"),
        _make_sub(_OTHER_PRICE, sub_id="sub_3"),
    ]

    mock_list = MagicMock()
    mock_list.auto_paging_iter.return_value = subs
    mock_list.has_more = False

    with patch("stripe.Subscription.list", return_value=mock_list):
        rows = list(mig._list_matching_subscriptions())

    assert len(rows) == 2
    ids = {r["subscription_id"] for r in rows}
    assert ids == {"sub_1", "sub_2"}


def test_legacy_to_new_mapping_annual(monkeypatch):
    """Annual legacy price maps to the new annual price."""
    sub = _make_sub(_LEGACY_ANNUAL, sub_id="sub_a")
    mock_list = MagicMock()
    mock_list.auto_paging_iter.return_value = [sub]
    mock_list.has_more = False

    with patch("stripe.Subscription.list", return_value=mock_list):
        rows = list(mig._list_matching_subscriptions())

    assert rows[0]["current_price_id"] == _LEGACY_ANNUAL
    assert rows[0]["proposed_new_price_id"] == _NEW_ANNUAL
    assert rows[0]["current_price_amount"] == 1188.0
    assert rows[0]["proposed_new_price_amount"] == 948.0


def test_legacy_to_new_mapping_monthly(monkeypatch):
    """Monthly legacy price maps to the new monthly price."""
    sub = _make_sub(_LEGACY_MONTHLY, sub_id="sub_m")
    mock_list = MagicMock()
    mock_list.auto_paging_iter.return_value = [sub]
    mock_list.has_more = False

    with patch("stripe.Subscription.list", return_value=mock_list):
        rows = list(mig._list_matching_subscriptions())

    assert rows[0]["current_price_id"] == _LEGACY_MONTHLY
    assert rows[0]["proposed_new_price_id"] == _NEW_MONTHLY
    assert rows[0]["current_price_amount"] == 119.0
    assert rows[0]["proposed_new_price_amount"] == 99.0


def test_update_subscription_calls_modify_correctly(monkeypatch):
    """--apply must call Subscription.modify with proration_behavior='none'."""
    sub_obj = MagicMock()
    sub_obj.__getitem__ = lambda self, k: {"items": {"data": [{"id": "item_1"}]}}[k]
    sub_obj.to_dict.return_value = {
        "id": "sub_upd",
        "items": {"data": [{"id": "item_1"}]},
    }

    retrieve_mock = MagicMock(return_value=sub_obj)
    modify_mock = MagicMock()

    with patch("stripe.Subscription.retrieve", retrieve_mock), \
         patch("stripe.Subscription.modify", modify_mock):
        mig._update_subscription("sub_upd", _NEW_ANNUAL)

    retrieve_mock.assert_called_once_with("sub_upd")
    modify_mock.assert_called_once()
    call_args = modify_mock.call_args
    assert call_args[0][0] == "sub_upd"
    assert call_args[1]["proration_behavior"] == "none"
    assert call_args[1]["items"] == [{"id": "item_1", "price": _NEW_ANNUAL}]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
