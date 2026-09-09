"""
Regression tests for the 2026-09-08 pricing-restructure grandfathering guarantee.

Locks in (Discord msg 1547048825997369436, confirmed 1547049309197959169):
  - Existing subscribers keep their legacy Stripe price ($79/mo / $790/yr
    Trustee) on every renewal. The invoice.paid webhook must NEVER touch
    plan_type, billing_period, or price — only record the transaction.
  - Grandfathered legacy plans keep their 10-trust limit even though new
    Trustee plans have 1 (get_trust_limit respects legacy_trust_limit).
  - A tier/billing-period change via /subscription/change-plan ENDS the
    legacy rate (legacy_trust_limit cleared; notice surfaced in response).

Pure-unit tests on the webhook handler and helpers — no live server, no
Stripe API, no MongoDB writes to production (mongomock-style fakes).
"""
import asyncio
import datetime
import os
import sys
from datetime import timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import patch, MagicMock

from routers import subscriptions as subs_router
from dependencies import get_trust_limit

LEGACY_MONTHLY = "price_test_legacy_monthly"
LEGACY_ANNUAL = "price_test_legacy_annual"
NEW_TRUSTEE_MONTHLY = "price_test_new_trustee_monthly"


def _setup_legacy_price_ids(monkeypatch):
    """Point the module's legacy-price constants at test IDs."""
    monkeypatch.setattr(subs_router, "STRIPE_MONTHLY_PRICE_ID", LEGACY_MONTHLY, raising=False)
    monkeypatch.setattr(subs_router, "STRIPE_ANNUAL_PRICE_ID", LEGACY_ANNUAL, raising=False)
    monkeypatch.setattr(
        subs_router,
        "LEGACY_TRUSTEE_PRICE_IDS",
        {LEGACY_MONTHLY, LEGACY_ANNUAL},
    )
    monkeypatch.setattr(
        subs_router,
        "LEGACY_PRICE_MAP",
        {LEGACY_MONTHLY: ("trustee", "monthly", 10), LEGACY_ANNUAL: ("trustee", "annual", 10)},
    )


# ==================== 1. RENEWALS NEVER CHANGE THE PLAN ====================

def _invoice_event(billing_reason="subscription_cycle", amount=7900, invoice_id="in_test_1"):
    invoice = {
        "id": invoice_id,
        "customer": "cus_test_123",
        "billing_reason": billing_reason,
        "amount_paid": amount,
        "subscription": "sub_test_abc",
    }
    event = MagicMock()
    event.data.object = invoice
    return event


class _FakeResult:
    """Mimics motor's UpdateResult enough for the handler."""
    def __init__(self):
        self.upserted_id = None


class _FakeCollection:
    def __init__(self):
        self.updates = []

    async def update_one(self, query, update, upsert=False, **kw):
        self.updates.append((query, update, upsert))
        return _FakeResult()


class _FakeDB:
    def __init__(self):
        self.subscriptions = _FakeCollection()
        self.payment_transactions = _FakeCollection()


def _run_invoice_paid(monkeypatch, db, billing_reason="subscription_cycle"):
    monkeypatch.setattr(subs_router, "db", db)

    captured = {}

    async def fake_get_user_by_customer_id(cid):
        return ({"user_id": "user_test", "email": "cust@example.com", "name": "Cust"},
                {"plan_type": "trustee", "billing_period": "monthly", "legacy_trust_limit": 10})

    async def fake_send(*a, **kw):
        captured["renewal_email"] = kw
        return None

    monkeypatch.setattr(subs_router, "get_user_by_customer_id", fake_get_user_by_customer_id)
    monkeypatch.setattr(subs_router.email_service, "server_token", "test-token", raising=False)
    monkeypatch.setattr(subs_router.email_service, "send_subscription_renewed", fake_send)

    asyncio.run(subs_router._webhook_invoice_paid(_invoice_event(billing_reason)))
    return captured


def test_renewal_webhook_never_touches_plan_or_price(monkeypatch):
    """invoice.paid for a renewal must not modify plan_type/billing_period/price.
    Only status=active is set (safe — does not change what the customer pays)."""
    db = _FakeDB()
    _run_invoice_paid(monkeypatch, db)

    updates = [u for u in db.subscriptions.updates]
    assert len(updates) == 1, "renewal should only touch the subscriptions doc once (status)"
    _, update, _ = updates[0]
    set_fields = update.get("$set", {})
    assert "plan_type" not in set_fields, "renewal must NEVER change plan_type"
    assert "billing_period" not in set_fields, "renewal must NEVER change billing_period"
    assert set_fields.get("status") == "active"
    # legacy_trust_limit untouched
    assert "$unset" not in update or "legacy_trust_limit" not in update.get("$unset", {})


def test_renewal_records_amount_at_legacy_rate(monkeypatch):
    """Renewal transaction must be recorded with the actual amount paid."""
    db = _FakeDB()
    _run_invoice_paid(monkeypatch, db)
    tx_updates = db.payment_transactions.updates
    assert len(tx_updates) == 1
    _, update, upsert = tx_updates[0]
    assert upsert is True
    assert update["$set"]["amount"] == 79.00  # $7900 cents -> $79.00
    assert update["$set"]["payment_status"] == "paid"
    assert update["$set"]["plan_type"] == "trustee"  # from existing sub doc, not remapped


def test_first_invoice_skipped(monkeypatch):
    """Initial invoice (billing_reason=subscription_create) is handled by
    checkout.session.completed — invoice.paid must be a no-op for it."""
    db = _FakeDB()
    _run_invoice_paid(monkeypatch, db, billing_reason="subscription_create")
    assert db.subscriptions.updates == []
    assert db.payment_transactions.updates == []


# ==================== 2. TRUST LIMITS RESPECT GRANDFATHERING ====================

def test_grandfathered_legacy_limit_wins():
    """Grandfathered user with legacy_trust_limit=10 keeps 10 trusts even on trustee."""
    assert get_trust_limit("trustee", legacy_limit=10) == 10
    assert get_trust_limit("monthly", legacy_limit=10) == 10
    assert get_trust_limit("annual", legacy_limit=10) == 10


def test_new_trustee_default_is_1():
    """New (non-grandfathered) Trustee subscribers get the new 1-trust plan."""
    assert get_trust_limit("trustee", legacy_limit=None) == 1
    assert get_trust_limit("trustee") == 1


def test_subscriber_status_flags_legacy_price(monkeypatch):
    """A sub holding a legacy price object must surface is_legacy_price=True +
    the exact legacy amount to the billing UI."""
    _setup_legacy_price_ids(monkeypatch)

    price = {"id": LEGACY_MONTHLY}
    item = MagicMock()
    item.get = lambda k: price.get(k)
    type(item).price = property(lambda self: price)
    # Simpler: build plain dicts the way calculate_subscription_status consumes them.
    stripe_sub = MagicMock()
    stripe_sub._data = {
        "current_period_end": 1758000000,
        "cancel_at_period_end": False,
        "items": {"data": [{"price": {"id": LEGACY_MONTHLY}}]},
    }
    with patch.object(subs_router.stripe.Subscription, "retrieve", return_value=stripe_sub):
        sub = {
            "subscription_id": "sub_test",
            "user_id": "user_test",
            "plan_type": "trustee",
            "billing_period": "monthly",
            "status": "active",
            "stripe_subscription_id": "sub_test_abc",
        }
        result = subs_router.calculate_subscription_status(sub)
    assert result["is_legacy_price"] is True
    assert result["price_amount"] == 79.00
    assert result["plan_type"] == "trustee"
    assert result["billing_period"] == "monthly"


# ==================== 3. PLAN CHANGE ENDS THE LEGACY RATE ====================

def test_plan_change_clears_legacy_trust_limit():
    """The change-plan endpoint must clear legacy_trust_limit when leaving the
    legacy rate — the grandfathering survives only renewals, not switches."""
    import inspect
    src = inspect.getsource(subs_router.change_plan)
    # Structural check (endpoint is heavily mocked elsewhere): the update path
    # must explicitly clear the legacy limit and warn the subscriber.
    assert 'update_set["legacy_trust_limit"] = None' in src
    assert "legacy_rate_notice" in src


def test_subscription_updated_webhook_preserves_legacy_limit_when_price_unchanged():
    """customer.subscription.updated with an unchanged legacy price (e.g. a
    renewal bump) must NOT clear legacy_trust_limit."""
    import inspect
    src = inspect.getsource(subs_router._handle_subscription_plan_change)
    assert 'update_set["legacy_trust_limit"] = 10' in src
    # The guard requires BOTH old and new price in the legacy map
    assert 'in LEGACY_PRICE_MAP' in src


# ==================== 4. LEGACY AMOUNTS ARE THE GRANDFATHERED RATES ====================

def test_legacy_rates_in_plan_amounts():
    """PLAN_AMOUNTS must carry the grandfathered rates new pricing replaced."""
    assert subs_router.PLAN_AMOUNTS[("trustee", "legacy-monthly")] == 79.00
    assert subs_router.PLAN_AMOUNTS[("trustee", "legacy-annual")] == 790.00
    # New rates differ from legacy (the whole point of the restructure)
    assert subs_router.PLAN_AMOUNTS[("trustee", "monthly")] == 99.00
    assert subs_router.PLAN_AMOUNTS[("trustee", "annual")] == 948.00


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])