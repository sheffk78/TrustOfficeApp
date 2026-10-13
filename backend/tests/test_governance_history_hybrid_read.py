#!/usr/bin/env python3
"""Regression: /governance/{trust_id}/history must read BOTH snapshot shapes.

Schema v3 (2026-10-13) stores score as `score_value` with `calculated_at`;
legacy rows store `score` (or `total_score`) with `created_at`. The history
endpoint previously did a bare `snap["score_value"]` read and 500'd
(KeyError) on any trust whose newest snapshot was legacy-shaped. Mirrors the
hybrid reads already shipped in defense_summary / org_queue / org_search.
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

db = database.db

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    import mongomock_motor
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for mod in (database, dependencies, gov):
        monkeypatch.setattr(mod, "db", fresh)
    globals()["db"] = fresh
    for c in ("trusts", "users", "health_score_snapshots", "subscriptions", "feature_access"):
        await db[c].delete_many({})

    async def fake_access(user_id, feature):
        return True

    monkeypatch.setattr(gov, "check_feature_access", fake_access)
    yield


@pytest.fixture
def owner_user():
    return {"user_id": "u_owner", "email": "owner@x.com", "name": "Owner", "is_admin": False}


async def _seed_trust():
    await db.trusts.insert_one({
        "trust_id": "t_hist",
        "name": "History Trust",
        "user_id": "u_owner",
    })


@pytest.mark.asyncio
async def test_legacy_snapshot_shape_returns_history(ctx, owner_user):
    """Newest snapshot in v2 shape (score/created_at) must not 500 (KeyError)."""
    await _seed_trust()
    await db.health_score_snapshots.insert_one({
        "trust_id": "t_hist",
        "user_id": "u_owner",
        "score": 84,
        "created_at": NOW.isoformat(),
    })
    out = await gov.get_governance_history("t_hist", days=30, user=owner_user)
    assert out["history"] == [{"date": NOW.isoformat()[:10], "score": 84, "color": None}]
    assert out["current_score"] == 84


@pytest.mark.asyncio
async def test_v3_snapshot_shape_returns_history(ctx, owner_user):
    """Native v3 rows (score_value/calculated_at) keep working."""
    await _seed_trust()
    await db.health_score_snapshots.insert_one({
        "trust_id": "t_hist",
        "user_id": "u_owner",
        "score_value": 91,
        "calculated_at": NOW.isoformat(),
        "color": "good",
    })
    out = await gov.get_governance_history("t_hist", days=30, user=owner_user)
    assert out["history"] == [{"date": NOW.isoformat()[:10], "score": 91, "color": "good"}]
    assert out["current_score"] == 91


@pytest.mark.asyncio
async def test_mixed_shapes_merge_on_same_date(ctx, owner_user):
    """A legacy row and a v3 row on the same date collapse to the first (newest) score."""
    await _seed_trust()
    await db.health_score_snapshots.insert_many([
        {  # newest (v3) — sorted first by calculated_at desc
            "trust_id": "t_hist",
            "user_id": "u_owner",
            "score_value": 77,
            "calculated_at": NOW.isoformat(),
            "color": "warn",
        },
        {  # older legacy row — different date
            "trust_id": "t_hist",
            "user_id": "u_owner",
            "score": 65,
            "created_at": "2026-10-01T00:00:00+00:00",
        },
    ])
    out = await gov.get_governance_history("t_hist", days=30, user=owner_user)
    dates = {h["date"]: h["score"] for h in out["history"]}
    assert dates[NOW.isoformat()[:10]] == 77
    assert dates["2026-10-01"] == 65
    assert out["current_score"] == 77


@pytest.mark.asyncio
async def test_total_score_fallback(ctx, owner_user):
    """Even older rows carrying only total_score still resolve."""
    await _seed_trust()
    await db.health_score_snapshots.insert_one({
        "trust_id": "t_hist",
        "user_id": "u_owner",
        "total_score": 58,
        "created_at": NOW.isoformat(),
    })
    out = await gov.get_governance_history("t_hist", days=30, user=owner_user)
    assert out["current_score"] == 58