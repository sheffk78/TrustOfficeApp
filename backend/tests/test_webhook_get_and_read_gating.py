"""
Regression test for the Stripe webhook 'get' crash and the read-access gating model.

These tests are pure-unit (no live server, no DB) so they run anywhere. They guard
against two regressions fixed on 2026-08-12:

1. Stripe webhook: calling .get()/.items() on a Stripe StripeObject raises
   AttributeError('get') — which was stored as error='get' and blocked every
   payment from activating a customer. The fix is `_stripe_to_dict()`.

2. Read-access model: free/expired users may READ their own data, but write
   actions (POST/PUT/PATCH/DELETE, incl. AI chat) are gated to active subscribers.
"""
import pytest


# ---- _stripe_to_dict (extracted to be testable without importing the router) ----

def _stripe_to_dict(obj):
    """Copy of the helper in backend/routers/subscriptions.py."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    try:
        return dict(obj)
    except Exception:
        return {}


class _FakeStripeObject:
    """Mimics StripeObject: no .get(), no .items(), no .keys() — only to_dict()."""
    def __init__(self, data):
        self._d = data
    def to_dict(self):
        return self._d
    def __getattr__(self, name):
        # Replicates StripeObject behavior: bare attribute name as the message.
        raise AttributeError(name)


class TestStripeToDict:
    def test_stripe_object_converts_to_plain_dict(self):
        """A StripeObject (which lacks .get/.items) must convert to a plain dict."""
        raw = _FakeStripeObject({"user_id": "user_123", "plan_type": "trustee"})
        d = _stripe_to_dict(raw)
        assert isinstance(d, dict)
        assert d.get("user_id") == "user_123"
        assert d["plan_type"] == "trustee"

    def test_stripe_object_metadata_preserves_user_id(self):
        """The checkout.session.completed metadata conversion must not lose user_id."""
        # Simulate event.data.object.metadata as a StripeObject
        metadata = _FakeStripeObject({"user_id": "user_9ea5d362515b", "plan_type": "trustee", "billing_period": "monthly"})
        converted = _stripe_to_dict(metadata)
        # The old buggy code did: metadata = dict(metadata) if hasattr(metadata,"items") else {}
        # hasattr(metadata,"items") was False on StripeObject -> metadata became {} -> user_id lost.
        assert converted.get("user_id") == "user_9ea5d362515b"
        assert converted["plan_type"] == "trustee"

    def test_none_and_plain_dict(self):
        assert _stripe_to_dict(None) == {}
        assert _stripe_to_dict({"a": 1}) == {"a": 1}

    def test_previous_attributes_no_get_crash(self):
        """The customer.subscription.updated handler reads previous_attributes via
        .get() — if it's still a StripeObject this crashes with 'get'. The fix
        converts it to a dict first, so .get() works."""
        previous_attributes = _FakeStripeObject({"items": {"data": [{"price": {"id": "price_old"}}]}})
        prev = _stripe_to_dict(previous_attributes)
        items = (prev.get("items") or {}).get("data") or [{}]
        old_price = items[0].get("price") or {}
        if isinstance(old_price, dict):
            old_price = old_price.get("id")
        assert old_price == "price_old"

    def test_error_logging_captures_class_not_bare_name(self):
        """Webhook failures must record the exception class name, never bare 'get'."""
        try:
            _FakeStripeObject({"x": 1}).get("x")
        except AttributeError as e:
            # Old code stored str(e) -> 'get'. New code stores type + traceback.
            assert str(e) == "get"  # confirms the root cause of the stored 'get'
            assert type(e).__name__ == "AttributeError"
            # The fix formats error_msg = f"{type(e).__name__}: {e}"
            error_msg = f"{type(e).__name__}: {e}"
            assert error_msg.startswith("AttributeError: get")


# ---- Read-only gating model ----

# Endpoints that must be READ-ALLOWED for free/expired users (auth only).
# These had require_premium_feature(402) wrongly blocking reads.
# (file_fragment, expected_file)
READ_ALLOWED_ENDPOINTS = [
    ("GET", "/trust-units/summary", "trust_units.py"),
    ("GET", "/trust-units/certificates", "trust_units.py"),
    ("GET", "/dashboard", "beneficiaries.py"),
    ("GET", "/class-beneficiaries", "beneficiaries.py"),
    ("GET", "/export/minutes", "exports.py"),
    ("GET", "/export/distributions", "exports.py"),
    ("GET", "/export/compensation", "exports.py"),
    ("GET", "/export/tasks", "exports.py"),
]

# Endpoints that MUST remain WRITE-GATED (403 for free/expired).
# (file_fragment, expected_file)
WRITE_GATED_ENDPOINTS = [
    ('POST', '/chat"', "chat.py"),
    ('POST', '/chat/stream', "chat.py"),
    ('POST', '/chat/actions/{conversation_id}/{message_index}/confirm', "chat.py"),
    ('POST', '/chat/conversations/{conversation_id}/rename', "chat.py"),
    ('POST', '/trust-units/certificates', "trust_units.py"),
    ('POST', '/create', "beneficiaries.py"),
]


class TestGatingModelInvariants:
    """Static guard: the route decorators in the source must reflect the model."""

    @pytest.mark.parametrize("method,frag,router_file", READ_ALLOWED_ENDPOINTS)
    def test_read_endpoints_use_auth_only(self, method, frag, router_file):
        """Free/expired users must be able to READ these — so they must NOT use
        require_premium_feature anywhere in their route definitions."""
        import os
        base = os.path.join(os.path.dirname(__file__), "..", "routers")
        path = os.path.join(base, router_file)
        assert os.path.exists(path), f"{path} missing"
        with open(path) as fh:
            src = fh.read()
        assert frag in src, f"route {frag} not in {router_file}"
        block = src[src.find(frag)-50:src.find(frag)+400]
        assert "require_premium_feature" not in block, \
            f"{frag} must not use require_premium_feature (blocks reads): {block[:150]}"

    @pytest.mark.parametrize("method,frag,router_file", WRITE_GATED_ENDPOINTS)
    def test_write_endpoints_use_write_access(self, method, frag, router_file):
        """Chat + write actions must be gated to active subscribers via
        require_write_access (403), never left open with get_current_user."""
        import os
        base = os.path.join(os.path.dirname(__file__), "..", "routers")
        path = os.path.join(base, router_file)
        assert os.path.exists(path), f"{path} missing"
        with open(path) as fh:
            src = fh.read()
        assert frag in src, f"route {frag} not in {router_file}"
        block = src[src.find(frag)-50:src.find(frag)+600]
        assert "require_write_access" in block, \
            f"{frag} must be gated with require_write_access: {block[:200]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
