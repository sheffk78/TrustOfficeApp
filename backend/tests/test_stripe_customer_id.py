# Regression test: "Revenue" admin screen crashed with
#   TypeError: unhashable type: 'Customer'
# when Stripe returned an expanded Customer object for invoice.customer
# (the /admin/revenue endpoint queries with expand=["data.customer"]).
#
# The fix: routers.admin._stripe_customer_id and routers.stats._stripe_customer_id
# normalize invoice.customer to a plain string ID (or None) so it can be added
# to the customer_ids set without raising.

import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import pytest

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(BACKEND))


class _FakeCustomerObject:
    """Mimics an expanded Stripe Customer object (has .id, .name, .email)."""
    def __init__(self, cid="cus_123"):
        self.id = cid
        self.name = "Jane Doe"
        self.email = "jane@example.com"


class _FakeInvoice:
    def __init__(self, customer):
        self.customer = customer


def test_admin_customer_id_string():
    from routers import admin
    inv = _FakeInvoice("cus_abc")
    assert admin._stripe_customer_id(inv) == "cus_abc"


def test_admin_customer_id_expanded_object():
    from routers import admin
    # This is the case that previously raised TypeError: unhashable type
    inv = _FakeInvoice(_FakeCustomerObject("cus_456"))
    # Must resolve to the string ID, NOT raise
    cid = admin._stripe_customer_id(inv)
    assert cid == "cus_456"
    # And it must be hashable so the set add never fails
    s = set()
    s.add(cid)  # would have raised before the fix


def test_admin_customer_id_none():
    from routers import admin
    assert admin._stripe_customer_id(_FakeInvoice(None)) is None


def test_stats_customer_id_expanded_object():
    from routers import stats
    inv = _FakeInvoice(_FakeCustomerObject("cus_789"))
    cid = stats._stripe_customer_id(inv)
    assert cid == "cus_789"
    s = set()
    s.add(cid)  # regression guard


def test_stats_customer_id_string():
    from routers import stats
    assert stats._stripe_customer_id(_FakeInvoice("cus_str")) == "cus_str"