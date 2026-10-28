#!/usr/bin/env python3
"""P1 (2026-10-23): dismissed risk findings must stop penalizing the score.

Before this fix, dismissed_insights only hid governance INSIGHT CARDS — the
scoring pipeline never consulted them, so a user who dismissed a
recommendation still paid the risk penalty for it.

Covers:
  (a) a finding with a matching 'risk:<type>' dismissal is excluded from
      risk_findings and contributes zero penalty
  (b) non-dismissed findings are still penalized
  (c) the dismiss route deletes the risk_findings_cache row for that trust
  (d) the score payload reports the dismissed risk types
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone

import database
import dependencies
import routers.governance as gov
from services.risk_gathering import compute_risk_penalty

NOW = datetime.now(timezone.utc)

HIGH_FINDING = {
    "type": "uninvested_assets",
    "severity": "high",
    "module": "investments",
    "title": "Trust assets may be uninvested",
    "detail": "No investment holdings tracked.",
    "action": "Add investment holdings",
    "deeplink": "/investments",
}

MEDIUM_FINDING = {
    "type": "policy_not_published",
    "severity": "medium",
    "module": "benevolence",
    "title": "Benevolence policy draft not yet published",
    "detail": "Policy version 1.0 is in draft status.",
    "action": "Review and publish the policy draft",
    "deeplink": "/benevolence/policy",
}


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    import mongomock_motor
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for mod in (database, dependencies, gov):
        monkeypatch.setattr(mod, "db", fresh)
    for c in ("trusts", "dismissed_insights", "risk_findings_cache"):
        await fresh[c].delete_many({})
    yield fresh


@pytest.fixture
def owner_user():
    return {"user_id": "u_owner", "email": "owner@x.com", "name": "Owner", "is_admin": False}


def _stub_gather(monkeypatch, findings):
    """Stub the raw risk gather so tests exercise the DISMISSAL filter only."""
    calls = []

    async def fake_gather(trust_id, trust_doc, db, today, **kwargs):
        calls.append(trust_id)
        return [dict(f) for f in findings]

    monkeypatch.setattr(gov, "gather_risk_findings", fake_gather)
    return calls


# --- (a) dismissed finding is excluded and contributes zero penalty ---

@pytest.mark.asyncio
async def test_dismissed_finding_excluded_from_risk_findings(ctx, owner_user, monkeypatch):
    _stub_gather(monkeypatch, [HIGH_FINDING])
    await ctx.dismissed_insights.insert_one({
        "dismiss_id": "dismiss_abc",
        "trust_id": "t1",
        "user_id": "u_owner",
        "criterion_name": "risk:uninvested_assets",
        "dismissed_at": NOW.isoformat(),
    })

    findings, dismissed_types = await gov._gather_risk_findings(
        "t1", {}, NOW, NOW.date(), use_cache=False, user_id="u_owner"
    )

    assert findings == [], "dismissed risk finding must not be returned"
    assert dismissed_types == {"uninvested_assets"}
    # Zero penalty — the whole point of the fix.
    assert compute_risk_penalty(findings)["total_penalty"] == 0


@pytest.mark.asyncio
async def test_dismissed_finding_zero_penalty_in_score(ctx, owner_user, monkeypatch):
    """The penalty math sees no findings at all when the only one is dismissed."""
    _stub_gather(monkeypatch, [HIGH_FINDING])
    await ctx.dismissed_insights.insert_one({
        "dismiss_id": "dismiss_abc",
        "trust_id": "t1",
        "user_id": "u_owner",
        "criterion_name": "risk:uninvested_assets",
        "dismissed_at": NOW.isoformat(),
    })

    findings, _ = await gov._gather_risk_findings(
        "t1", {}, NOW, NOW.date(), use_cache=False, user_id="u_owner"
    )
    penalty = compute_risk_penalty(findings)
    assert penalty["total_penalty"] == 0
    assert penalty["breakdown"]["high"]["count"] == 0


# --- (b) non-dismissed findings still penalized ---

@pytest.mark.asyncio
async def test_non_dismissed_finding_still_penalized(ctx, owner_user, monkeypatch):
    _stub_gather(monkeypatch, [HIGH_FINDING])
    await ctx.dismissed_insights.insert_one({
        "dismiss_id": "dismiss_abc",
        "trust_id": "t1",
        "user_id": "u_owner",
        "criterion_name": "risk:some_other_type",
        "dismissed_at": NOW.isoformat(),
    })

    findings, dismissed_types = await gov._gather_risk_findings(
        "t1", {}, NOW, NOW.date(), use_cache=False, user_id="u_owner"
    )

    assert len(findings) == 1
    assert findings[0]["type"] == "uninvested_assets"
    assert dismissed_types == {"some_other_type"}
    assert compute_risk_penalty(findings)["total_penalty"] == -12


@pytest.mark.asyncio
async def test_partial_dismissal_leaves_other_findings(ctx, owner_user, monkeypatch):
    """Dismissing one type must not silently drop the others."""
    _stub_gather(monkeypatch, [HIGH_FINDING, MEDIUM_FINDING])
    await ctx.dismissed_insights.insert_one({
        "dismiss_id": "dismiss_abc",
        "trust_id": "t1",
        "user_id": "u_owner",
        "criterion_name": "risk:uninvested_assets",
        "dismissed_at": NOW.isoformat(),
    })

    findings, _ = await gov._gather_risk_findings(
        "t1", {}, NOW, NOW.date(), use_cache=False, user_id="u_owner"
    )

    assert [f["type"] for f in findings] == ["policy_not_published"]
    assert compute_risk_penalty(findings)["total_penalty"] == -5


# --- non-'risk:' dismissals never affect penalties ---

@pytest.mark.asyncio
async def test_regular_insight_dismissal_does_not_filter_findings(ctx, owner_user, monkeypatch):
    _stub_gather(monkeypatch, [HIGH_FINDING])
    await ctx.dismissed_insights.insert_one({
        "dismiss_id": "dismiss_abc",
        "trust_id": "t1",
        "user_id": "u_owner",
        "criterion_name": "Quarterly Minutes",
        "dismissed_at": NOW.isoformat(),
    })

    findings, dismissed_types = await gov._gather_risk_findings(
        "t1", {}, NOW, NOW.date(), use_cache=False, user_id="u_owner"
    )

    assert len(findings) == 1
    assert dismissed_types == set()


# --- (c) the dismiss route invalidates the risk findings cache ---

@pytest.mark.asyncio
async def test_dismiss_route_deletes_risk_findings_cache_row(ctx, owner_user):
    await ctx.trusts.insert_one({
        "trust_id": "t1",
        "name": "Test Trust",
        "user_id": "u_owner",
    })
    await ctx.risk_findings_cache.insert_one({
        "trust_id": "t1",
        "findings": [dict(HIGH_FINDING)],
        "cached_at": NOW.isoformat(),
    })

    out = await gov.dismiss_insight(
        gov.DismissedInsightCreate(trust_id="t1", criterion_name="risk:uninvested_assets"),
        user=owner_user,
    )

    assert out["dismissed"] is True
    assert await ctx.risk_findings_cache.find_one({"trust_id": "t1"}) is None
    # The dismissal itself was recorded.
    rec = await ctx.dismissed_insights.find_one({
        "trust_id": "t1", "user_id": "u_owner", "criterion_name": "risk:uninvested_assets",
    })
    assert rec is not None


@pytest.mark.asyncio
async def test_dismiss_route_keeps_cache_for_regular_insight(ctx, owner_user):
    """A non-risk dismissal does not change the penalty math — cache stays."""
    await ctx.trusts.insert_one({
        "trust_id": "t1",
        "name": "Test Trust",
        "user_id": "u_owner",
    })
    await ctx.risk_findings_cache.insert_one({
        "trust_id": "t1",
        "findings": [dict(HIGH_FINDING)],
        "cached_at": NOW.isoformat(),
    })

    await gov.dismiss_insight(
        gov.DismissedInsightCreate(trust_id="t1", criterion_name="Quarterly Minutes"),
        user=owner_user,
    )

    assert await ctx.risk_findings_cache.find_one({"trust_id": "t1"}) is not None


# --- stale cache is bypassed when a dismissal exists ---

@pytest.mark.asyncio
async def test_stale_cache_bypassed_when_dismissal_exists(ctx, owner_user, monkeypatch):
    """A dismissal must take effect immediately, not after the 5-min TTL."""
    calls = _stub_gather(monkeypatch, [HIGH_FINDING])
    # A STALE cached entry that still contains the finding.
    await ctx.risk_findings_cache.insert_one({
        "trust_id": "t1",
        "findings": [dict(HIGH_FINDING)],
        "cached_at": NOW.isoformat(),
    })
    await ctx.dismissed_insights.insert_one({
        "dismiss_id": "dismiss_abc",
        "trust_id": "t1",
        "user_id": "u_owner",
        "criterion_name": "risk:uninvested_assets",
        "dismissed_at": NOW.isoformat(),
    })

    findings, _ = await gov._gather_risk_findings(
        "t1", {}, NOW, NOW.date(), use_cache=True, user_id="u_owner"
    )

    assert calls, "cache must be bypassed so a fresh gather happens"
    assert findings == []


@pytest.mark.asyncio
async def test_cache_used_when_no_dismissal(ctx, owner_user, monkeypatch):
    calls = _stub_gather(monkeypatch, [HIGH_FINDING])
    await ctx.risk_findings_cache.insert_one({
        "trust_id": "t1",
        "findings": [dict(MEDIUM_FINDING)],
        "cached_at": NOW.isoformat(),
    })

    findings, dismissed_types = await gov._gather_risk_findings(
        "t1", {}, NOW, NOW.date(), use_cache=True, user_id="u_owner"
    )

    assert not calls, "cache should be used when there are no dismissals"
    assert [f["type"] for f in findings] == ["policy_not_published"]
    assert dismissed_types == set()


# --- (d) the score payload reports the dismissed risk types ---

@pytest.mark.asyncio
async def test_calculate_health_score_reports_dismissed_risk_types(ctx, owner_user, monkeypatch):
    _stub_gather(monkeypatch, [HIGH_FINDING, MEDIUM_FINDING])
    await ctx.trusts.insert_one({
        "trust_id": "t1",
        "name": "Test Trust",
        "user_id": "u_owner",
        "created_at": NOW.isoformat(),
    })
    await ctx.dismissed_insights.insert_one({
        "dismiss_id": "dismiss_abc",
        "trust_id": "t1",
        "user_id": "u_owner",
        "criterion_name": "risk:uninvested_assets",
        "dismissed_at": NOW.isoformat(),
    })

    async def fake_gather_score_data(trust_id, user_id, use_cache=False):
        findings, dismissed = await gov._gather_risk_findings(
            trust_id, {}, NOW, NOW.date(), use_cache, user_id=user_id
        )
        return {
            "now": NOW,
            "quarterly_minutes": 0,
            "total_tasks": 0,
            "overdue_tasks": 0,
            "comp_plan": None,
            "ytd_total": 0,
            "approved_amount": None,
            "dist_count": 0,
            "benevolence_dists": [],
            "annual_review": None,
            "pending_annual_review": None,
            "trust_created_at": NOW.isoformat(),
            "active_assets": [],
            "twelve_months_ago": NOW,
            "total_txns": 0,
            "classified_txns": 0,
            "active_alert_count": 0,
            "risk_findings": findings,
            "onboarding_state_raw": {},
            "benevolence_enabled": False,
            "dismissed_risk_types": dismissed,
        }

    monkeypatch.setattr(gov, "_gather_score_data", fake_gather_score_data)
    monkeypatch.setattr(gov, "ensure_transaction_review_task", lambda *a, **k: _noop())
    monkeypatch.setattr(gov, "_clear_achieved_dismissals", lambda *a, **k: _noop())

    result = await gov.calculate_health_score("t1", "u_owner", save_snapshot=False)

    assert result["dismissed_risk_types"] == ["uninvested_assets"]
    # The dismissed finding is gone from the payload too.
    assert [f["type"] for f in result["risk_findings"]] == ["policy_not_published"]


async def _noop():
    return None


if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__), "-v", "--tb=short"])
