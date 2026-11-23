"""Tests for GET /admin-api/subscriptions/renewals and the invoice.paid webhook fix.

Contract source: Kit/life/brands/TrustOffice/docs/RENEWALS-CARD-DESIGN.md
"""
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_renewals")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-renewals-tests")
os.environ.setdefault("ADMIN_API_KEY", "test-renewals-admin-key")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from database import db as real_db
import routers.admin_api as admin_api
import routers.subscriptions as subscriptions


class FakeCollection:
    """Minimal in-memory MongoDB collection substitute."""

    def __init__(self, docs=None):
        self.docs = docs or {}
        self._seq = 0

    def _next_id(self):
        self._seq += 1
        return f"ren_{self._seq:012x}"

    async def find_one(self, query, projection=None, **kwargs):
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if k == "$or":
                    or_match = False
                    for sub in v:
                        sub_ok = True
                        for sk, sv in sub.items():
                            if doc.get(sk) != sv:
                                sub_ok = False
                                break
                        if sub_ok:
                            or_match = True
                            break
                    if not or_match:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    def find(self, query, projection=None):
        results = []
        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                results.append(dict(doc))
        return FakeCursor(results)

    async def count_documents(self, query):
        return sum(
            1
            for d in self.docs.values()
            if all(d.get(k) == v for k, v in query.items())
        )

    async def insert_one(self, doc):
        _id = doc.get("_id") or self._next_id()
        doc["_id"] = _id
        self.docs[_id] = dict(doc)
        return MagicMock()

    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        if doc is None:
            if upsert:
                new_doc = {}
                for k, v in query.items():
                    new_doc[k] = v
                for k, v in update.get("$set", {}).items():
                    new_doc[k] = v
                for k, v in update.get("$setOnInsert", {}).items():
                    new_doc[k] = v
                self.docs[new_doc.get("_id", self._next_id())] = new_doc
                return MagicMock(upserted_id=new_doc.get("_id"))
            return MagicMock()
        for k, v in update.get("$set", {}).items():
            doc[k] = v
        for k, v in update.get("$setOnInsert", {}).items():
            doc.setdefault(k, v)
        self.docs[doc["_id"]] = dict(doc)
        m = MagicMock()
        m.upserted_id = None
        return m

    def to_list(self, limit):
        return [dict(d) for d in self.docs.values()][:limit]


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    async def to_list(self, limit):
        return self._docs[:limit]


@pytest.fixture
def fake_db(monkeypatch):
    class FakeDB:
        pass

    db = FakeDB()
    db.users = FakeCollection()
    db.subscriptions = FakeCollection()
    db.payment_transactions = FakeCollection()
    db.admin_api_audit = FakeCollection()

    monkeypatch.setattr("database.db", db)
    monkeypatch.setattr(admin_api, "db", db)
    monkeypatch.setattr(subscriptions, "db", db)
    # Stub email_service in subscriptions module so we never send real email.
    monkeypatch.setattr(subscriptions, "email_service", MagicMock(is_configured=False))
    return db


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


def _make_stripe_sub(
    sub_id,
    customer_id,
    status,
    current_period_end=None,
    trial_end=None,
    cancel_at_period_end=False,
    unit_amount=9999,
    customer_email="customer@example.com",
    customer_name="Customer Name",
):
    """Build a Stripe subscription dict with expanded customer."""
    price = {
        "id": f"price_{sub_id}",
        "unit_amount": unit_amount,
        "nickname": "Trustee Monthly",
        "product": {"name": "Trustee"},
    }
    return {
        "id": sub_id,
        "customer": {
            "id": customer_id,
            "email": customer_email,
            "name": customer_name,
        },
        "status": status,
        "current_period_end": int(current_period_end.timestamp()) if current_period_end else None,
        "trial_end": int(trial_end.timestamp()) if trial_end else None,
        "cancel_at_period_end": cancel_at_period_end,
        "items": {"data": [{"price": price}]},
    }


class FakeStripeList:
    def __init__(self, data):
        self._data = data

    def auto_paging_iter(self):
        return iter(self._data)


def _mock_subscription_list(data):
    return patch.object(
        admin_api.stripe.Subscription,
        "list",
        return_value=FakeStripeList(data),
    )


# ---------------------------------------------------------------------------
# Tests for /admin-api/subscriptions/renewals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_past_due_outside_window_included(fake_db, now):
    """Past_due rows must appear regardless of window."""
    sub = _make_stripe_sub(
        "sub_pastdue",
        "cus_pastdue",
        "past_due",
        current_period_end=now - timedelta(days=30),
    )
    await fake_db.users.insert_one({
        "user_id": "u_pastdue",
        "email": "pastdue@example.com",
        "name": "Past Due User",
        "stripe_customer_id": "cus_pastdue",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_pastdue",
        "stripe_customer_id": "cus_pastdue",
        "stripe_subscription_id": "sub_pastdue",
        "plan_type": "trustee",
        "billing_period": "monthly",
    })

    with _mock_subscription_list([sub]):
        response = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )

    assert response["source"] == "stripe"
    assert response["error"] is None
    assert len(response["rows"]) == 1
    row = response["rows"][0]
    assert row["status"] == "past_due"
    assert row["user_id"] == "u_pastdue"
    assert row["days_until_due"] <= -30
    assert row["last_event"] == "past_due"


@pytest.mark.asyncio
async def test_renewed_row_from_payment_transactions(fake_db, now):
    """A paid subscription_cycle transaction in the last 14 days yields last_event='renewed'."""
    period_end = now + timedelta(days=30)
    sub = _make_stripe_sub(
        "sub_renewed",
        "cus_renewed",
        "active",
        current_period_end=period_end,
    )
    await fake_db.users.insert_one({
        "user_id": "u_renewed",
        "email": "renewed@example.com",
        "name": "Renewed User",
        "stripe_customer_id": "cus_renewed",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_renewed",
        "stripe_customer_id": "cus_renewed",
        "stripe_subscription_id": "sub_renewed",
        "plan_type": "trustee",
        "billing_period": "monthly",
    })
    await fake_db.payment_transactions.insert_one({
        "user_id": "u_renewed",
        "session_id": "inv_renewed",
        "payment_status": "paid",
        "billing_reason": "subscription_cycle",
        "amount": 99.00,
        "created_at": (now - timedelta(days=2)).isoformat(),
    })

    with _mock_subscription_list([sub]):
        response = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )

    assert response["error"] is None
    rows = response["rows"]
    assert len(rows) == 1
    assert rows[0]["last_event"] == "renewed"
    assert rows[0]["amount_cents"] == 9900


@pytest.mark.asyncio
async def test_cancel_at_period_end_flagged_and_excluded_from_need_action(fake_db, now):
    """Cancel-at-period-end rows are included only in window and flagged."""
    period_end = now + timedelta(days=7)
    sub = _make_stripe_sub(
        "sub_cancel",
        "cus_cancel",
        "active",
        current_period_end=period_end,
        cancel_at_period_end=True,
    )
    await fake_db.users.insert_one({
        "user_id": "u_cancel",
        "email": "cancel@example.com",
        "name": "Cancel User",
        "stripe_customer_id": "cus_cancel",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_cancel",
        "stripe_customer_id": "cus_cancel",
        "stripe_subscription_id": "sub_cancel",
        "plan_type": "estate",
        "billing_period": "annual",
    })

    with _mock_subscription_list([sub]):
        response = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )

    assert response["error"] is None
    rows = response["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["cancel_at_period_end"] is True
    assert row["last_event"] == "cancel_at_period_end"
    # It is in rows (within window) but consumers exclude it from need-action count.

    # Same subscription outside the window should not be a row.
    sub2 = _make_stripe_sub(
        "sub_cancel2",
        "cus_cancel2",
        "active",
        current_period_end=now + timedelta(days=30),
        cancel_at_period_end=True,
    )
    await fake_db.users.insert_one({
        "user_id": "u_cancel2",
        "email": "cancel2@example.com",
        "name": "Cancel User 2",
        "stripe_customer_id": "cus_cancel2",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_cancel2",
        "stripe_customer_id": "cus_cancel2",
        "stripe_subscription_id": "sub_cancel2",
        "plan_type": "estate",
        "billing_period": "annual",
    })

    with _mock_subscription_list([sub2]):
        response2 = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )
    assert len(response2["rows"]) == 0


@pytest.mark.asyncio
async def test_free_and_gifted_excluded(fake_db, now):
    """Free / forever_free / gifted subscriptions are excluded."""
    sub_free = _make_stripe_sub(
        "sub_free",
        "cus_free",
        "active",
        current_period_end=now + timedelta(days=5),
    )
    await fake_db.users.insert_one({
        "user_id": "u_free",
        "email": "free@example.com",
        "name": "Free User",
        "stripe_customer_id": "cus_free",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_free",
        "stripe_customer_id": "cus_free",
        "stripe_subscription_id": "sub_free",
        "plan_type": "forever_free",
        "billing_period": "monthly",
    })

    sub_gifted = _make_stripe_sub(
        "sub_gifted",
        "cus_gifted",
        "active",
        current_period_end=now + timedelta(days=6),
    )
    await fake_db.users.insert_one({
        "user_id": "u_gifted",
        "email": "gifted@example.com",
        "name": "Gifted User",
        "stripe_customer_id": "cus_gifted",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_gifted",
        "stripe_customer_id": "cus_gifted",
        "stripe_subscription_id": "sub_gifted",
        "plan_type": "trustee",
        "billing_period": "monthly",
        "gifted": True,
    })

    with _mock_subscription_list([sub_free, sub_gifted]):
        response = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )
    assert len(response["rows"]) == 0


@pytest.mark.asyncio
async def test_unresolved_user_row_emitted(fake_db, now):
    """Stripe subscriptions with no DB user are still emitted, marked unresolved, using Stripe email."""
    sub = _make_stripe_sub(
        "sub_unres",
        "cus_unres",
        "active",
        current_period_end=now + timedelta(days=3),
        customer_email="stripeonly@example.com",
        customer_name="Stripe Only",
    )

    with _mock_subscription_list([sub]):
        response = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )

    assert response["error"] is None
    rows = response["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["unresolved"] is True
    assert row["email"] == "stripeonly@example.com"
    assert row["name"] == "Stripe Only"


@pytest.mark.asyncio
async def test_beyond_window_count(fake_db, now):
    """Active subscriptions with period_end > +14d are counted, not rowed."""
    sub = _make_stripe_sub(
        "sub_beyond",
        "cus_beyond",
        "active",
        current_period_end=now + timedelta(days=60),
    )
    await fake_db.users.insert_one({
        "user_id": "u_beyond",
        "email": "beyond@example.com",
        "name": "Beyond User",
        "stripe_customer_id": "cus_beyond",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_beyond",
        "stripe_customer_id": "cus_beyond",
        "stripe_subscription_id": "sub_beyond",
        "plan_type": "trustee",
        "billing_period": "monthly",
    })

    with _mock_subscription_list([sub]):
        response = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )

    assert len(response["rows"]) == 0
    assert response["beyond_window_count"] == 1


@pytest.mark.asyncio
async def test_trialing_in_window_uses_trial_end(fake_db, now):
    """Trialing rows key on trial_end_date and are included when within window."""
    sub = _make_stripe_sub(
        "sub_trial",
        "cus_trial",
        "trialing",
        current_period_end=now + timedelta(days=5),
        trial_end=now + timedelta(days=10),
    )
    await fake_db.users.insert_one({
        "user_id": "u_trial",
        "email": "trial@example.com",
        "name": "Trial User",
        "stripe_customer_id": "cus_trial",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_trial",
        "stripe_customer_id": "cus_trial",
        "stripe_subscription_id": "sub_trial",
        "plan_type": "trustee",
        "billing_period": "monthly",
    })

    with _mock_subscription_list([sub]):
        response = await admin_api.get_subscriptions_renewals(
            request=MagicMock(client=MagicMock(host="127.0.0.1")),
            api_key="test-renewals-admin-key",
        )

    rows = response["rows"]
    assert len(rows) == 1
    assert rows[0]["status"] == "trialing"
    assert rows[0]["days_until_due"] in (9, 10)
    assert rows[0]["last_event"] == "trials_soon"


# ---------------------------------------------------------------------------
# Webhook fix tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_invoice_paid_persists_current_period_end(fake_db, now):
    """_webhook_invoice_paid must persist current_period_end from Stripe subscription."""
    await fake_db.users.insert_one({
        "user_id": "u_web",
        "email": "web@example.com",
        "name": "Webhook User",
        "stripe_customer_id": "cus_web",
    })
    await fake_db.subscriptions.insert_one({
        "user_id": "u_web",
        "stripe_customer_id": "cus_web",
        "stripe_subscription_id": "sub_web",
        "plan_type": "trustee",
        "billing_period": "monthly",
        "status": "past_due",
    })

    period_end = now + timedelta(days=30)

    class FakeStripeSub:
        current_period_end = int(period_end.timestamp())
        id = "sub_web"

    class FakeInvoice:
        class data:
            object = {
                "id": "inv_web",
                "customer": "cus_web",
                "billing_reason": "subscription_cycle",
                "amount_paid": 9900,
                "subscription": "sub_web",
            }

    class FakeEvent:
        class data:
            object = FakeInvoice.data.object

    with patch.object(subscriptions.stripe.Subscription, "retrieve", return_value=FakeStripeSub()):
        await subscriptions._webhook_invoice_paid(FakeEvent())

    updated = await fake_db.subscriptions.find_one({"user_id": "u_web"})
    assert updated["status"] == "active"
    stored_cpe = updated.get("current_period_end")
    assert stored_cpe is not None
    stored_dt = datetime.fromisoformat(stored_cpe)
    assert abs((stored_dt - period_end).total_seconds()) < 2
