#!/usr/bin/env python3
"""P3 (2026-10-23): benevolence policy 'declined' state.

A benevolence trust whose trustees deliberately elect NOT to maintain a
written policy had no way to record that decision — the risk engine always
flagged it (high: no doc, medium: draft).

Covers:
  - declined policy -> NO risk finding
  - no policy doc at all -> 'no_benevolence_policy' (high) finding
  - draft policy -> 'policy_not_published' (medium) finding, unchanged
  - decline route upserts the declined marker, preserving an earlier draft
  - undecline route restores 'draft' and clears declined_at
"""
import os
import sys
from datetime import date

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database
import routers.benevolence_policy as benpol
from services.risk_gathering import gather_risk_findings

TODAY = date(2026, 10, 23)

BENEVOLENCE_TRUST = {
    "trust_id": "t1",
    "user_id": "u1",
    "name": "Benevolence Trust",
    "state_code": "DE",
    "benevolence_enabled": True,
}


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    import mongomock_motor
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for mod in (database, benpol):
        monkeypatch.setattr(mod, "db", fresh)
    for c in ("trusts", "benevolence_policies", "benevolence_policy_versions",
              "benevolence_records", "audit_logs"):
        await fresh[c].delete_many({})
    await fresh.trusts.insert_one(dict(BENEVOLENCE_TRUST))
    yield fresh


@pytest.fixture
def owner_user():
    return {"user_id": "u1", "email": "owner@x.com", "name": "Owner", "is_admin": False}


async def _gather(ctx):
    return await gather_risk_findings(
        "t1", dict(BENEVOLENCE_TRUST), ctx, TODAY,
        include_separation_alerts=False, include_upcoming_tax=False,
    )


def _benevolence_findings(risks):
    return [r for r in risks if r["module"] == "benevolence"]


# --- risk gathering behaviour ---

@pytest.mark.asyncio
async def test_declined_policy_produces_no_finding(ctx):
    """A deliberate decision to not maintain a policy is NOT a missing document."""
    await ctx.benevolence_policies.insert_one({
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "current_version_id": None,
        "current_version_label": "declined-20261023",
        "current_version_status": "declined",
        "declined_at": "2026-10-23T00:00:00+00:00",
        "created_at": "2026-10-23T00:00:00+00:00",
    })

    risks = await _gather(ctx)
    ben = _benevolence_findings(risks)

    assert [r["type"] for r in ben] == []
    # And the medium draft finding does not fire either.
    assert "policy_not_published" not in [r["type"] for r in risks]
    assert "no_benevolence_policy" not in [r["type"] for r in risks]


@pytest.mark.asyncio
async def test_no_policy_doc_still_finds_high_finding(ctx):
    """Genuinely no doc at all -> the high finding still fires."""
    risks = await _gather(ctx)
    ben = _benevolence_findings(risks)

    types = [r["type"] for r in ben]
    assert "no_benevolence_policy" in types
    finding = next(r for r in ben if r["type"] == "no_benevolence_policy")
    assert finding["severity"] == "high"
    assert finding["deeplink"] == "/benevolence/policy"


@pytest.mark.asyncio
async def test_draft_policy_medium_finding_unchanged(ctx):
    await ctx.benevolence_policies.insert_one({
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "current_version_id": "benpolv_1",
        "current_version_label": "1.0",
        "current_version_status": "draft",
        "created_at": "2026-10-23T00:00:00+00:00",
    })

    risks = await _gather(ctx)
    ben = _benevolence_findings(risks)

    finding = next(r for r in ben if r["type"] == "policy_not_published")
    assert finding["severity"] == "medium"
    assert "1.0" in finding["detail"]


@pytest.mark.asyncio
async def test_published_policy_no_finding(ctx):
    await ctx.benevolence_policies.insert_one({
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "current_version_id": "benpolv_1",
        "current_version_label": "1.0",
        "current_version_status": "published",
        "created_at": "2026-10-23T00:00:00+00:00",
    })

    risks = await _gather(ctx)
    assert _benevolence_findings(risks) == []


# --- decline route ---

@pytest.mark.asyncio
async def test_decline_creates_policy_doc(ctx, owner_user):
    out = await benpol.decline_benevolence_policy(
        benpol.BenevolencePolicyDecline(trust_id="t1"), user=owner_user
    )

    assert out["status"] == "declined"
    assert out["current_version_label"].startswith("declined-")

    policy = await ctx.benevolence_policies.find_one({"trust_id": "t1", "user_id": "u1"})
    assert policy["current_version_status"] == "declined"
    assert policy["current_version_label"] == out["current_version_label"]
    assert policy["declined_at"] is not None

    # And the risk engine now stays quiet.
    risks = await _gather(ctx)
    assert _benevolence_findings(risks) == []


@pytest.mark.asyncio
async def test_decline_preserves_existing_draft_fields(ctx, owner_user):
    """Declining must not destroy an earlier draft's data."""
    await ctx.benevolence_policies.insert_one({
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "current_version_id": "benpolv_1",
        "current_version_label": "1.0",
        "current_version_status": "draft",
        "created_at": "2026-10-23T00:00:00+00:00",
    })
    await ctx.benevolence_policy_versions.insert_one({
        "policy_version_id": "benpolv_1",
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "version_number": 1,
        "version_label": "1.0",
        "status": "draft",
        "charitable_class": "Local charities",
    })

    await benpol.decline_benevolence_policy(
        benpol.BenevolencePolicyDecline(trust_id="t1"), user=owner_user
    )

    policy = await ctx.benevolence_policies.find_one({"trust_id": "t1", "user_id": "u1"})
    assert policy["current_version_status"] == "declined"
    # The draft version pointer and the version doc survive.
    assert policy["current_version_id"] == "benpolv_1"
    version = await ctx.benevolence_policy_versions.find_one({"policy_version_id": "benpolv_1"})
    assert version["charitable_class"] == "Local charities"
    assert version["status"] == "draft"


@pytest.mark.asyncio
async def test_decline_requires_benevolence_mode(ctx, owner_user):
    await ctx.trusts.update_one(
        {"trust_id": "t1"}, {"$set": {"benevolence_enabled": False}}
    )
    with pytest.raises(Exception) as exc:
        await benpol.decline_benevolence_policy(
            benpol.BenevolencePolicyDecline(trust_id="t1"), user=owner_user
        )
    assert getattr(exc.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_decline_requires_ownership(ctx):
    other = {"user_id": "someone_else", "email": "x@x.com", "name": "X", "is_admin": False}
    with pytest.raises(Exception) as exc:
        await benpol.decline_benevolence_policy(
            benpol.BenevolencePolicyDecline(trust_id="t1"), user=other
        )
    assert getattr(exc.value, "status_code", None) == 404


# --- undecline route ---

@pytest.mark.asyncio
async def test_undecline_restores_draft(ctx, owner_user):
    await ctx.benevolence_policies.insert_one({
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "current_version_id": "benpolv_1",
        "current_version_label": "declined-20261023",
        "current_version_status": "declined",
        "declined_at": "2026-10-23T00:00:00+00:00",
        "created_at": "2026-10-23T00:00:00+00:00",
    })
    await ctx.benevolence_policy_versions.insert_one({
        "policy_version_id": "benpolv_1",
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "version_number": 1,
        "version_label": "1.0",
        "status": "draft",
    })

    out = await benpol.undecline_benevolence_policy(
        benpol.BenevolencePolicyDecline(trust_id="t1"), user=owner_user
    )

    assert out["status"] == "draft"
    policy = await ctx.benevolence_policies.find_one({"trust_id": "t1", "user_id": "u1"})
    assert policy["current_version_status"] == "draft"
    assert policy["current_version_id"] == "benpolv_1"
    assert policy["current_version_label"] == "1.0"
    assert policy["declined_at"] is None

    # The medium draft finding comes back.
    risks = await _gather(ctx)
    assert "policy_not_published" in [r["type"] for r in _benevolence_findings(risks)]


@pytest.mark.asyncio
async def test_undecline_without_prior_draft_clears_marker(ctx, owner_user):
    await ctx.benevolence_policies.insert_one({
        "policy_id": "benpol_1",
        "trust_id": "t1",
        "user_id": "u1",
        "current_version_id": None,
        "current_version_label": "declined-20261023",
        "current_version_status": "declined",
        "declined_at": "2026-10-23T00:00:00+00:00",
        "created_at": "2026-10-23T00:00:00+00:00",
    })

    out = await benpol.undecline_benevolence_policy(
        benpol.BenevolencePolicyDecline(trust_id="t1"), user=owner_user
    )

    assert out["status"] == "draft"
    policy = await ctx.benevolence_policies.find_one({"trust_id": "t1", "user_id": "u1"})
    assert policy["current_version_status"] == "draft"
    assert policy["declined_at"] is None


@pytest.mark.asyncio
async def test_undecline_without_decline_404(ctx, owner_user):
    with pytest.raises(Exception) as exc:
        await benpol.undecline_benevolence_policy(
            benpol.BenevolencePolicyDecline(trust_id="t1"), user=owner_user
        )
    assert getattr(exc.value, "status_code", None) == 404


if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__), "-v", "--tb=short"])
