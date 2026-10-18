"""
Tests for the TrustOffice internal proactive agent MVP.

Covers:
- Enable/disable gating via internal agent API
- Activity logging to agent_activity
- Deadline window logic with mock clock
- Consent fail-closed behavior (drafts by default, sends only with consent)
"""
import os
import sys
import pytest
import pytest_asyncio
from datetime import date, datetime, timezone, timedelta

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_agent_mvp")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-agent-mvp")
os.environ["INTERNAL_API_KEY"] = "test-internal-api-key"
os.environ["ADMIN_API_KEY"] = "test-internal-api-key"

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
from fastapi.testclient import TestClient
from routers.internal_agent import router as internal_agent_router
from scripts import agent_runner
from agent_mailer import AgentMailer


db = database.db


@pytest_asyncio.fixture
async def clean_db():
    for coll in ("users", "trusts", "deadlines", "health_score_snapshots", "agent_activity", "agent_communications"):
        await db[coll].delete_many({})
    yield
    for coll in ("users", "trusts", "deadlines", "health_score_snapshots", "agent_activity", "agent_communications"):
        await db[coll].delete_many({})


@pytest_asyncio.fixture
async def api_client(clean_db):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(internal_agent_router, prefix="/api/internal/agent")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date(days_offset: int) -> str:
    return (date.today() + timedelta(days=days_offset)).isoformat()


async def _seed_customer(user_id: str, agent_enabled: bool = False, agent_consent: bool = False, email: str = None):
    await db.users.insert_one({
        "user_id": user_id,
        "email": email or f"{user_id}@t.test",
        "name": "Test Customer",
        "agent_enabled": agent_enabled,
        "agent_consent": agent_consent,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def _seed_trust(user_id: str, trust_id: str, name: str = "Test Trust"):
    await db.trusts.insert_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def _seed_deadline(trust_id: str, title: str, due_offset: int, status: str = "upcoming"):
    await db.deadlines.insert_one({
        "deadline_id": f"dl_{trust_id}_{title.replace(' ', '_')}",
        "trust_id": trust_id,
        "user_id": "ignored",
        "title": title,
        "due_date": _date(due_offset),
        "status": status,
        "priority": "high",
        "category": "annual_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# API enable/disable + activity logging
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enable_agent_sets_flag_and_logs_activity(api_client, clean_db):
    await _seed_customer("cust_01")
    client = api_client
    res = client.post(
        "/api/internal/agent/enable",
        json={"customer_id": "cust_01"},
        headers={"X-Internal-API-Key": "test-internal-api-key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["customer_id"] == "cust_01"
    assert data["agent_enabled"] is True
    assert data["activity_id"].startswith("agent_act_")

    user = await db.users.find_one({"user_id": "cust_01"}, {"_id": 0})
    assert user["agent_enabled"] is True

    log = await db.agent_activity.find_one({"customer_id": "cust_01", "action": "agent_enabled"}, {"_id": 0})
    assert log is not None
    assert log["payload"]["via"] == "internal_api"


@pytest.mark.asyncio
async def test_disable_agent_sets_flag_and_logs_activity(api_client, clean_db):
    await _seed_customer("cust_02", agent_enabled=True)
    client = api_client
    res = client.post(
        "/api/internal/agent/disable",
        json={"customer_id": "cust_02"},
        headers={"X-Internal-API-Key": "test-internal-api-key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["agent_enabled"] is False

    user = await db.users.find_one({"user_id": "cust_02"}, {"_id": 0})
    assert user["agent_enabled"] is False
    assert await db.agent_activity.count_documents({"customer_id": "cust_02", "action": "agent_disabled"}) == 1


@pytest.mark.asyncio
async def test_activity_endpoint_logs_action(api_client, clean_db):
    await _seed_customer("cust_03")
    client = api_client
    res = client.post(
        "/api/internal/agent/activity",
        json={
            "customer_id": "cust_03",
            "trust_id": "trust_03",
            "action": "deadline_check",
            "payload": {"overdue": 1, "upcoming": 2},
            "run_id": "run_123",
        },
        headers={"X-Internal-API-Key": "test-internal-api-key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "deadline_check"

    log = await db.agent_activity.find_one({"customer_id": "cust_03"}, {"_id": 0})
    assert log["trust_id"] == "trust_03"
    assert log["run_id"] == "run_123"


@pytest.mark.asyncio
async def test_status_endpoint_returns_trust_status(api_client, clean_db):
    await _seed_customer("cust_04", agent_enabled=True, agent_consent=True)
    await _seed_trust("cust_04", "trust_04")
    await _seed_deadline("trust_04", "Annual review", 5)
    await db.health_score_snapshots.insert_one({
        "snapshot_id": "snap_1",
        "trust_id": "trust_04",
        "score_value": 82,
        "color": "green",
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    })

    client = api_client
    res = client.get(
        "/api/internal/agent/status/trust_04",
        headers={"X-Internal-API-Key": "test-internal-api-key"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["trust_id"] == "trust_04"
    assert data["agent_enabled"] is True
    assert data["agent_consent"] is True
    assert data["health_score"]["score"] == 82
    assert data["next_deadline"]["title"] == "Annual review"


@pytest.mark.asyncio
async def test_api_rejects_missing_key(api_client, clean_db):
    res = api_client.post("/api/internal/agent/enable", json={"customer_id": "cust_x"})
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Deadline window logic with mock clock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deadline_buckets_group_by_window(clean_db):
    await _seed_customer("cust_05", agent_enabled=True)
    await _seed_trust("cust_05", "trust_05")

    # Place deadlines at 5, 13, 29, and -2 days relative to today
    await _seed_deadline("trust_05", "Due in 5", 5)
    await _seed_deadline("trust_05", "Due in 13", 13)
    await _seed_deadline("trust_05", "Due in 29", 29)
    await _seed_deadline("trust_05", "Overdue", -2)

    deadlines = await agent_runner._get_deadlines("trust_05")
    overdue, upcoming = agent_runner._deadline_buckets(deadlines)

    assert len(overdue) == 1
    assert overdue[0]["title"] == "Overdue"

    buckets = {w: items for w, items in upcoming}
    assert len(buckets[7]) == 1 and buckets[7][0]["title"] == "Due in 5"
    assert len(buckets[14]) == 1 and buckets[14][0]["title"] == "Due in 13"
    assert len(buckets[30]) == 1 and buckets[30][0]["title"] == "Due in 29"


class _MockClock:
    def __init__(self, fixed_date: date):
        self.fixed_date = fixed_date

    def now(self):
        return datetime.combine(self.fixed_date, datetime.min.time(), tzinfo=timezone.utc)

    def today(self):
        return self.fixed_date


@pytest.mark.asyncio
async def test_daily_run_respects_mock_clock(clean_db):
    await _seed_customer("cust_06", agent_enabled=True)
    await _seed_trust("cust_06", "trust_06")
    # Fixed "today" so the due_date is exactly 7 days out
    fixed = date(2026, 10, 18)
    due = (fixed + timedelta(days=7)).isoformat()
    await db.deadlines.insert_one({
        "deadline_id": "dl_06",
        "trust_id": "trust_06",
        "user_id": "cust_06",
        "title": "Tax deadline",
        "due_date": due,
        "status": "upcoming",
        "priority": "high",
        "category": "tax_filing_1041",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    original_clock = agent_runner._CLOCK
    agent_runner._set_clock(_MockClock(fixed))
    try:
        summary = await agent_runner.run_daily("run_clock", mailer=AgentMailer())
    finally:
        agent_runner._set_clock(original_clock)

    assert summary["customers"] == 1
    assert summary["drafts"] == 1
    assert summary["sent"] == 0


# ---------------------------------------------------------------------------
# Consent fail-closed behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_produces_draft_without_consent(clean_db):
    await _seed_customer("cust_07", agent_enabled=True, agent_consent=False)
    await _seed_trust("cust_07", "trust_07")
    await _seed_deadline("trust_07", "Urgent deadline", 3)

    summary = await agent_runner.run_daily("run_no_consent", mailer=AgentMailer())
    assert summary["drafts"] == 1
    assert summary["sent"] == 0

    comms = await db.agent_communications.find({}).to_list(length=10)
    assert len(comms) == 1
    assert comms[0]["status"] == "draft"


@pytest.mark.asyncio
async def test_run_sends_with_consent_using_mock_mailer(clean_db):
    await _seed_customer("cust_08", agent_enabled=True, agent_consent=True)
    await _seed_trust("cust_08", "trust_08")
    await _seed_deadline("trust_08", "Urgent deadline", 3)

    class _FakeMailer:
        async def send_or_draft(self, **kwargs):
            return {"status": "sent", "message_id": "msg_123"}

    summary = await agent_runner.run_daily("run_with_consent", mailer=_FakeMailer())
    assert summary["sent"] == 1
    assert summary["drafts"] == 0

    comms = await db.agent_communications.find({}).to_list(length=10)
    assert len(comms) == 1
    assert comms[0]["status"] == "sent"
    assert comms[0]["send_result"]["message_id"] == "msg_123"


@pytest.mark.asyncio
async def test_run_no_action_when_agent_disabled(clean_db):
    await _seed_customer("cust_09", agent_enabled=False)
    await _seed_trust("cust_09", "trust_09")
    await _seed_deadline("trust_09", "Urgent deadline", 3)

    summary = await agent_runner.run_daily("run_disabled", mailer=AgentMailer())
    assert summary["customers"] == 0
    assert summary["drafts"] == 0
