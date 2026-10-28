#!/usr/bin/env python3
"""P2 (2026-10-23): 'uninvested_assets' severity graduation for real-asset trusts.

Rule A fired HIGH (-12) for any trust with Schedule A assets and zero tracked
investments. For a trust holding real estate / insurance / vehicles instead of
securities nothing is "uninvested" — the Prudent Investor Rule framing is a
false alarm.

Covers:
  - all-real-estate Schedule A -> 'no_securities_advisory' (low), NO high finding
  - mixed with a financial category -> 'uninvested_assets' (high), unchanged
  - Rule B (cash_heavy_portfolio) is untouched
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
import services.risk_gathering as rg
from services.risk_gathering import gather_risk_findings, compute_risk_penalty

TODAY = date(2026, 10, 23)


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    import mongomock_motor
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for c in ("trusts", "schedule_a_items", "investments", "vault_documents",
              "benevolence_policies", "tax_calendar", "communications",
              "separation_alerts", "benevolence_records"):
        await fresh[c].delete_many({})
    yield fresh


def _asset(category, value=100000.0, status="active"):
    return {
        "trust_id": "t1",
        "status": status,
        "category": category,
        "approximate_value": value,
    }


async def _gather(ctx, trust=None):
    trust = trust or {"trust_id": "t1", "user_id": "u1", "state_code": "DE"}
    return await gather_risk_findings(
        "t1", trust, ctx, TODAY, include_separation_alerts=False, include_upcoming_tax=False
    )


def _investments_findings(risks):
    """Only the investments-module findings (other modules add unrelated risks)."""
    return [r for r in risks if r["module"] == "investments"]


# --- all non-financial Schedule A -> advisory low, no high finding ---

@pytest.mark.asyncio
async def test_all_real_estate_schedule_a_is_advisory_only(ctx):
    """A trust holding only real estate is not 'uninvested'."""
    await ctx.schedule_a_items.insert_many([
        _asset("real_property", 400000.0),
        _asset("real_property", 250000.0),
    ])

    risks = await _gather(ctx)

    types = [r["type"] for r in risks]
    assert "uninvested_assets" not in types
    assert "no_securities_advisory" in types

    advisory = next(r for r in risks if r["type"] == "no_securities_advisory")
    assert advisory["severity"] == "low"
    assert advisory["title"] == "No securities tracked — advisory only"
    assert advisory["action"] == "Document investment approach or add securities (optional)"
    assert advisory["module"] == "investments"
    assert advisory["deeplink"] == "/investments"
    assert "non-securities assets" in advisory["detail"]


@pytest.mark.asyncio
async def test_advisory_finding_penalty_is_low_not_high(ctx):
    await ctx.schedule_a_items.insert_many([
        _asset("real_property", 400000.0),
        _asset("personal_property", 25000.0),
        _asset("other_property", 15000.0),
    ])

    risks = await _gather(ctx)
    inv_risks = _investments_findings(risks)
    assert [r["severity"] for r in inv_risks] == ["low"]

    penalty = compute_risk_penalty(inv_risks)
    assert penalty["breakdown"]["high"]["count"] == 0
    # Low severity = -2 (not -12 for high).
    assert penalty["breakdown"]["low"]["count"] == 1
    assert penalty["total_penalty"] == -2


# --- mixed composition keeps the original high finding ---

@pytest.mark.asyncio
async def test_mixed_financial_and_real_estate_keeps_high_finding(ctx):
    """Any financial-category item keeps the original high-severity finding."""
    await ctx.schedule_a_items.insert_many([
        _asset("real_property", 400000.0),
        _asset("financial_accounts", 120000.0),
    ])

    risks = await _gather(ctx)

    types = [r["type"] for r in risks]
    assert "uninvested_assets" in types
    assert "no_securities_advisory" not in types

    high = next(r for r in risks if r["type"] == "uninvested_assets")
    assert high["severity"] == "high"
    assert high["title"] == "Trust assets may be uninvested"
    assert high["module"] == "investments"
    assert high["deeplink"] == "/investments"

    penalty = compute_risk_penalty(_investments_findings(risks))
    assert penalty["breakdown"]["high"]["count"] == 1
    assert penalty["total_penalty"] == -12


@pytest.mark.asyncio
async def test_financial_only_schedule_a_keeps_high_finding(ctx):
    await ctx.schedule_a_items.insert_many([
        _asset("financial_accounts", 500000.0),
    ])

    risks = await _gather(ctx)
    assert "uninvested_assets" in [r["type"] for r in risks]
    assert "no_securities_advisory" not in [r["type"] for r in risks]


@pytest.mark.asyncio
async def test_business_interest_counts_as_financial(ctx):
    """Business interests are financial holdings — the high finding stays."""
    await ctx.schedule_a_items.insert_many([
        _asset("real_property", 400000.0),
        _asset("business_interests", 90000.0),
    ])

    risks = await _gather(ctx)
    assert "uninvested_assets" in [r["type"] for r in risks]
    assert "no_securities_advisory" not in [r["type"] for r in risks]


# --- Rule B unchanged ---

@pytest.mark.asyncio
async def test_cash_heavy_portfolio_rule_unchanged(ctx):
    """Rule B still fires medium when financial accounts dominate."""
    await ctx.schedule_a_items.insert_many([
        _asset("financial_accounts", 900000.0),
        _asset("real_property", 50000.0),
    ])
    await ctx.investments.insert_one({
        "trust_id": "t1",
        "is_active": True,
        "asset_name": "Brokerage",
        "current_value": 200000.0,
        "cost_basis": 200000.0,
    })

    risks = await _gather(ctx)
    cash = next((r for r in risks if r["type"] == "cash_heavy_portfolio"), None)
    assert cash is not None
    assert cash["severity"] == "medium"


@pytest.mark.asyncio
async def test_no_schedule_a_no_finding(ctx):
    """No assets at all -> neither finding."""
    risks = await _gather(ctx)
    types = [r["type"] for r in risks]
    assert "uninvested_assets" not in types
    assert "no_securities_advisory" not in types


@pytest.mark.asyncio
async def test_zero_value_schedule_a_no_finding(ctx):
    """A Schedule A with no values was already excluded by the value guard."""
    await ctx.schedule_a_items.insert_many([
        _asset("real_property", 0),
    ])

    risks = await _gather(ctx)
    types = [r["type"] for r in risks]
    assert "uninvested_assets" not in types
    assert "no_securities_advisory" not in types


if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__), "-v", "--tb=short"])
