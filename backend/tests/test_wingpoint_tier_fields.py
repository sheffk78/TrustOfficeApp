"""Red-first regression tests for WingPoint plan_tier / governance_financed fields.

Bug (2026-11-23): WingPoint sends plan_tier="wingpoint" and
governance_financed=true, but WingPointProvisionRequest did not declare those
fields, so Pydantic silently discarded them. _resolve_suggested_plan then fell
back to package-based mapping, producing the wrong tier for WP-paid customers.

This file pins the contract:
  1. WingPointProvisionRequest accepts and preserves plan_tier + governance_financed.
  2. _resolve_suggested_plan prefers plan_tier when present.
  3. The full provision path passes plan_tier into _determine_recommended_action.
  4. Idempotent replay + race-complete responses also read plan_tier from payload.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_tier_fields_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-tier-fields")

from routers import external as external_module
from routers.external import (
    WingPointProvisionRequest,
    _resolve_suggested_plan,
)

pytestmark = pytest.mark.asyncio(loop_scope="module")


# ==================== UNIT: model accepts new fields ====================


def _base_request_kwargs(extra=None):
    base = {
        "email": "darla.jo@example.com",
        "wingpoint_ref": "WP-20261123-SIM01",
        "trust_name": "Whitlock Family Trust",
        "jurisdiction": "TX",
        "role_for_trust": "trustee",
        "entity_type": "irrevocable_trust",
        "trust_type": "FAMILY_TRUST",
    }
    if extra:
        base.update(extra)
    return base


def test_request_accepts_plan_tier_and_governance_financed():
    req = WingPointProvisionRequest(**_base_request_kwargs({
        "plan_tier": "wingpoint",
        "governance_financed": True,
        "source_package": "single_trust",
    }))
    assert req.plan_tier == "wingpoint"
    assert req.governance_financed is True
    dumped = req.model_dump()
    assert dumped["plan_tier"] == "wingpoint"
    assert dumped["governance_financed"] is True


def test_request_defaults_governance_financed_false_and_plan_tier_none():
    req = WingPointProvisionRequest(**_base_request_kwargs())
    assert req.plan_tier is None
    assert req.governance_financed is False


def test_invalid_plan_tier_rejected():
    with pytest.raises(Exception):
        WingPointProvisionRequest(**_base_request_kwargs({"plan_tier": "enterprise"}))


# ==================== UNIT: tier-suggestion logic ====================

def _sub_state(plan_type="none", legacy_trust_limit=None):
    return SimpleNamespace(
        plan_type=plan_type,
        legacy_trust_limit=legacy_trust_limit,
        is_active=False,
        cancel_at_period_end=False,
    )


def test_resolve_suggested_plan_prefers_explicit_plan_tier():
    sub = _sub_state(plan_type="none")
    # Without plan_tier, single_trust maps to trustee.
    assert _resolve_suggested_plan("single_trust", 1, "none", sub) == "trustee"
    # With plan_tier wingpoint, it must win regardless of package.
    assert _resolve_suggested_plan("single_trust", 1, "none", sub, plan_tier="wingpoint") == "wingpoint"


def test_resolve_suggested_plan_honors_downgrade_guard():
    """A legacy user with 10 trusts must not be downgraded by an explicit tier."""
    sub = _sub_state(plan_type="annual", legacy_trust_limit=10)
    assert _resolve_suggested_plan("single_trust", 1, "annual", sub, plan_tier="trustee") == "advisor"


def test_resolve_suggested_plan_falls_back_without_plan_tier_or_package():
    sub = _sub_state(plan_type="none")
    assert _resolve_suggested_plan(None, 1, "none", sub) == "trustee"
    assert _resolve_suggested_plan(None, 3, "none", sub) == "estate"
    assert _resolve_suggested_plan(None, 9, "none", sub) == "advisor"


# ==================== INTEGRATION: determine_recommended_action passes tier through ====================

class FakeSubState:
    def __init__(self, plan_type="none", legacy_trust_limit=None, is_active=False, cancel_at_period_end=False):
        self.plan_type = plan_type
        self.legacy_trust_limit = legacy_trust_limit
        self.is_active = is_active
        self.cancel_at_period_end = cancel_at_period_end


async def test_determine_recommended_action_uses_plan_tier():
    user_id = "user_tier_test_001"

    class FakeColl:
        def __init__(self, count=1):
            self._count = count
        async def count_documents(self, _filter):
            return self._count
        async def find_one(self, query, projection=None):
            return None

    class FakeDB:
        trusts = FakeColl(count=1)
        users = FakeColl()
        subscriptions = FakeColl()

    real_db = external_module.db
    real_get_subscription_state = external_module.get_subscription_state
    try:
        external_module.db = FakeDB()
        external_module.get_subscription_state = AsyncMock(return_value=FakeSubState(plan_type="none"))
        rec = await external_module._determine_recommended_action(
            user_id=user_id,
            is_new_user=True,
            source_package="single_trust",
            coupon_code=None,
            frontend_url="https://app.trustoffice.app",
            plan_tier="wingpoint",
        )
        assert rec["suggested_plan"] == "wingpoint"
        assert rec["suggested_plan_name"] == "WingPoint Annual"
    finally:
        external_module.db = real_db
        external_module.get_subscription_state = real_get_subscription_state


# ==================== INTEGRATION: idempotent replay reads plan_tier ====================

async def test_idempotent_replay_reads_plan_tier_from_payload():
    existing = {
        "user_id": "user_replay_001",
        "wingpoint_ref": "WP-REPLAY-001",
        "request_payload": {
            "source_package": "single_trust",
            "coupon_code": None,
            "plan_tier": "wingpoint",
        },
    }

    class FakeColl:
        async def count_documents(self, _filter):
            return 1
        async def find_one(self, query, projection=None):
            return None

    class FakeDB:
        trusts = FakeColl()
        users = FakeColl()
        subscriptions = FakeColl()

    real_db = external_module.db
    real_get_subscription_state = external_module.get_subscription_state
    try:
        external_module.db = FakeDB()
        external_module.get_subscription_state = AsyncMock(return_value=FakeSubState(plan_type="none"))
        result = await external_module._handle_idempotent_replay(existing)
        assert result["recommended_action"]["suggested_plan"] == "wingpoint"
    finally:
        external_module.db = real_db
        external_module.get_subscription_state = real_get_subscription_state


# ==================== INTEGRATION: race-complete response reads plan_tier ====================

async def test_race_complete_response_reads_plan_tier_from_payload():
    existing = {
        "user_id": "user_race_001",
        "wingpoint_ref": "WP-RACE-001",
        "request_payload": {
            "source_package": "estate_bundle",
            "coupon_code": None,
            "plan_tier": "wingpoint",
        },
    }

    class FakeColl:
        async def count_documents(self, _filter):
            return 1
        async def find_one(self, query, projection=None):
            return None

    class FakeDB:
        trusts = FakeColl()
        users = FakeColl()
        subscriptions = FakeColl()

    real_db = external_module.db
    real_get_subscription_state = external_module.get_subscription_state
    try:
        external_module.db = FakeDB()
        external_module.get_subscription_state = AsyncMock(return_value=FakeSubState(plan_type="none"))
        result = await external_module._build_race_complete_response(existing)
        assert result["recommended_action"]["suggested_plan"] == "wingpoint"
    finally:
        external_module.db = real_db
        external_module.get_subscription_state = real_get_subscription_state


# ==================== WIRING: full provision path passes plan_tier ====================

async def test_provision_endpoint_passes_plan_tier_to_recommended_action(monkeypatch):
    """The endpoint calls _determine_recommended_action with request.plan_tier."""
    captured = {}

    async def fake_determine(user_id, is_new_user, source_package, coupon_code, frontend_url, plan_tier=None):
        captured["plan_tier"] = plan_tier
        return {
            "action": "set_password",
            "redirect_url": None,
            "message": "Check your email",
            "suggested_plan": plan_tier or "trustee",
            "suggested_plan_name": "WingPoint Annual",
            "needs_upgrade": False,
            "requires_payment": True,
        }

    monkeypatch.setattr(external_module, "_determine_recommended_action", fake_determine)
    monkeypatch.setattr(external_module, "check_rate_limit", AsyncMock())

    # Make dry_run call our fake so the endpoint reaches the real smart-routing block.
    real_handle_dry_run = external_module._handle_dry_run

    async def fake_dry_run(request):
        captured["dry_run_plan_tier"] = request.plan_tier
        # Avoid touching the real DB inside _handle_dry_run; return a minimal stub.
        return {
            "status": "dry_run",
            "plan_tier_seen": request.plan_tier,
            "governance_financed_seen": request.governance_financed,
        }

    monkeypatch.setattr(external_module, "_handle_dry_run", fake_dry_run)

    partner = {"partner_id": "wingpoint"}

    req = WingPointProvisionRequest(**_base_request_kwargs({
        "plan_tier": "wingpoint",
        "governance_financed": True,
        "dry_run": True,
    }))

    result = await external_module.provision_trustoffice(req, partner=partner)
    assert result["status"] == "dry_run"
    assert captured.get("dry_run_plan_tier") == "wingpoint"
    assert result.get("governance_financed_seen") is True
