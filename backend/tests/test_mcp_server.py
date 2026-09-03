"""
Unit tests for the TrustOffice MCP server tool layer.

Exercises the MCP tool layer against a mocked Admin API (AdminAPIClient is
replaced with an in-memory fake backed by dicts, so no MongoDB connection is
required). Also covers auth, rate limiting, idempotency, audit logging
(mocked collection), and the Phase 1 write-op stubs.

Run: cd backend && python -m pytest tests/test_mcp_server.py -v
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend dir is importable regardless of pytest rootdir
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mcp_server.server import MCPServer, TOOL_DEFINITIONS, PROTOCOL_VERSION
from mcp_server.auth import validate_api_key, check_rate_limit, reset_rate_limits, ADMIN_API_KEY
from mcp_server.admin_client import AdminAPIClient, _days_remaining
from mcp_server import audit as audit_module


TEST_API_KEY = "test-admin-api-key-12345"


# ==================== MOCK ADMIN API CLIENT ====================

class MockAdminAPIClient:
    """
    In-memory fake of the AdminAPIClient — simulates the Admin API layer
    (MongoDB-backed) without requiring a database connection.
    """

    def __init__(self):
        self.users = {
            "user_001": {
                "user_id": "user_001",
                "email": "kenneth@example.com",
                "name": "Kenneth Test",
            },
        }
        self.trusts = {
            "trust_001": {
                "trust_id": "trust_001",
                "user_id": "user_001",
                "name": "Family Trust",
                "trust_type": "family",
                "jurisdiction": "UT",
                "state_code": "UT",
                "role": "Trustee",
                "trustees": [{"name": "Kenneth Test", "role": "Trustee"}],
                "start_date": "2025-01-15",
                "ein": "87-1234567",
                "is_fiscal_year": False,
                "created_at": "2025-01-15T00:00:00Z",
            },
            "trust_002": {
                "trust_id": "trust_002",
                "user_id": "user_002",  # owned by a DIFFERENT user
                "name": "Other User Trust",
                "trust_type": "family",
            },
        }
        self.health_snapshots = {
            "trust_001": [
                {
                    "trust_id": "trust_001",
                    "user_id": "user_001",
                    "health_score": 85,
                    "criteria": [
                        {"criterion": "Quarterly Minutes", "status": "pass"},
                        {"criterion": "Task Compliance", "status": "pass"},
                    ],
                    "calculated_at": "2026-08-01T00:00:00Z",
                },
                {
                    "trust_id": "trust_001",
                    "user_id": "user_001",
                    "health_score": 80,
                    "criteria": [],
                    "calculated_at": "2026-07-01T00:00:00Z",
                },
            ],
        }
        self.tax_calendar = {
            "trust_001": [
                {
                    "entry_id": "tc_001",
                    "trust_id": "trust_001",
                    "tax_year": 2026,
                    "due_date": (date.today() + timedelta(days=12)).isoformat(),
                    "filing_status": "pending",
                    "form": "Form 1041 Q3",
                },
                {
                    "entry_id": "tc_002",
                    "trust_id": "trust_001",
                    "tax_year": 2026,
                    "due_date": (date.today() - timedelta(days=5)).isoformat(),
                    "filing_status": "pending",
                    "form": "Form 1041 ES",
                },
                {
                    "entry_id": "tc_003",
                    "trust_id": "trust_001",
                    "tax_year": 2026,
                    "due_date": (date.today() - timedelta(days=30)).isoformat(),
                    "filing_status": "filed",
                    "form": "Form 1041 Q2",
                },
            ],
        }
        self.governance_tasks = {
            "trust_001": [
                {
                    "task_id": "task_001",
                    "trust_id": "trust_001",
                    "user_id": "user_001",
                    "title": "Quarterly minutes Q3",
                    "completed": False,
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                },
                {
                    "task_id": "task_002",
                    "trust_id": "trust_001",
                    "user_id": "user_001",
                    "title": "Annual review",
                    "completed": True,
                    "due_date": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                },
                {
                    "task_id": "task_003",
                    "trust_id": "trust_001",
                    "user_id": "user_001",
                    "title": "Asset valuation update",
                    "completed": False,
                    "due_date": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                },
            ],
        }

    # ---- Read operations (mirror AdminAPIClient logic) ----

    async def get_user_trusts(self, user_id: str) -> Dict[str, Any]:
        user = self.users.get(user_id)
        if not user:
            return {"error": "User not found", "status": 404}
        trusts = [t for t in self.trusts.values() if t["user_id"] == user_id]
        return {
            "user_id": user_id,
            "email": user.get("email"),
            "name": user.get("name"),
            "trust_count": len(trusts),
            "trusts": trusts,
        }

    async def get_trust_state(self, user_id: str, trust_id: str) -> Dict[str, Any]:
        trust = self.trusts.get(trust_id)
        if not trust or trust["user_id"] != user_id:
            return {"error": "Trust not found", "status": 404}
        return {k: v for k, v in trust.items() if k != "user_id"} | {"user_id": user_id}

    async def get_governance_health(self, user_id: str, trust_id: str) -> Dict[str, Any]:
        trust = self.trusts.get(trust_id)
        if not trust or trust["user_id"] != user_id:
            return {"error": "Trust not found", "status": 404}
        snaps = self.health_snapshots.get(trust_id, [])
        if not snaps:
            return {
                "trust_id": trust_id,
                "trust_name": trust.get("name"),
                "health_score": None,
                "criteria": [],
                "calculated_at": None,
                "message": "No health score snapshot available.",
            }
        latest = snaps[0]
        return {
            "trust_id": trust_id,
            "trust_name": trust.get("name"),
            "health_score": latest["health_score"],
            "criteria": latest["criteria"],
            "calculated_at": latest["calculated_at"],
        }

    async def get_tax_calendar(self, user_id: str, trust_id: str, tax_year=None) -> Dict[str, Any]:
        trust = self.trusts.get(trust_id)
        if not trust or trust["user_id"] != user_id:
            return {"error": "Trust not found", "status": 404}
        year = tax_year or date.today().year
        raw = [e for e in self.tax_calendar.get(trust_id, []) if e["tax_year"] == year]
        raw.sort(key=lambda e: e["due_date"])
        entries = []
        for doc in raw:
            days = _days_remaining(doc["due_date"])
            entries.append({**doc, "days_remaining": days, "is_overdue": days < 0})
        filed = sum(1 for e in entries if e["filing_status"] in ("filed", "not_required"))
        pending = sum(1 for e in entries if e["filing_status"] == "pending")
        overdue = sum(1 for e in entries if e["is_overdue"] and e["filing_status"] == "pending")
        return {
            "trust_id": trust_id,
            "trust_name": trust.get("name"),
            "tax_year": year,
            "total_entries": len(entries),
            "filed_count": filed,
            "pending_count": pending,
            "overdue_count": overdue,
            "entries": entries,
        }

    async def get_task_list(self, user_id: str, trust_id: str, status=None) -> Dict[str, Any]:
        trust = self.trusts.get(trust_id)
        if not trust or trust["user_id"] != user_id:
            return {"error": "Trust not found", "status": 404}
        tasks = [t for t in self.governance_tasks.get(trust_id, []) if t["user_id"] == user_id]
        now_iso = datetime.now(timezone.utc).isoformat()
        if status == "completed":
            tasks = [t for t in tasks if t["completed"]]
        elif status == "pending":
            tasks = [t for t in tasks if not t["completed"]]
        elif status == "overdue":
            tasks = [t for t in tasks if not t["completed"] and t["due_date"] < now_iso]
        tasks.sort(key=lambda t: t["due_date"])
        completed_count = sum(1 for t in tasks if t["completed"])
        return {
            "trust_id": trust_id,
            "trust_name": trust.get("name"),
            "total_tasks": len(tasks),
            "completed_count": completed_count,
            "pending_count": len(tasks) - completed_count,
            "tasks": tasks,
        }

    # ---- Write operations (stubs, same as real client) ----

    async def submit_trust_update(self, user_id, trust_id, updates):
        return {"error": "Write operations not available in Phase 1", "status": 501,
                "tool": "submit_trust_update", "phase": "Phase 2 (planned)"}

    async def submit_asset_values(self, user_id, trust_id, asset_values):
        return {"error": "Write operations not available in Phase 1", "status": 501,
                "tool": "submit_asset_values", "phase": "Phase 2 (planned)"}

    async def complete_task(self, user_id, trust_id, task_id):
        return {"error": "Write operations not available in Phase 1", "status": 501,
                "tool": "complete_task", "phase": "Phase 2 (planned)"}

    async def submit_minutes_draft(self, user_id, trust_id, minutes_data):
        return {"error": "Write operations not available in Phase 1", "status": 501,
                "tool": "submit_minutes_draft", "phase": "Phase 2 (planned)"}

    async def update_beneficiary(self, user_id, trust_id, beneficiary_id, updates):
        return {"error": "Write operations not available in Phase 1", "status": 501,
                "tool": "update_beneficiary", "phase": "Phase 2 (planned)"}


# ==================== FIXTURES ====================

@pytest.fixture
def mock_client():
    return MockAdminAPIClient()


@pytest.fixture
def server(mock_client):
    """MCP server with mocked client, valid key, clean rate limits."""
    reset_rate_limits()
    with patch.dict(os.environ, {"ADMIN_API_KEY": TEST_API_KEY}):
        # Reload auth module so ADMIN_API_KEY picks up the patched env
        import importlib
        import mcp_server.auth as auth
        importlib.reload(auth)
        import mcp_server.server as srv
        importlib.reload(srv)
        s = srv.MCPServer(api_key=TEST_API_KEY, client=mock_client)
        yield s
    reset_rate_limits()


# ==================== AUTH TESTS ====================

class TestAuth:
    def test_valid_api_key(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": TEST_API_KEY}):
            import importlib
            import mcp_server.auth as auth
            importlib.reload(auth)
            valid, err = auth.validate_api_key(TEST_API_KEY)
            assert valid is True
            assert err == ""

    def test_invalid_api_key(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": TEST_API_KEY}):
            import importlib
            import mcp_server.auth as auth
            importlib.reload(auth)
            valid, err = auth.validate_api_key("wrong-key")
            assert valid is False
            assert "Invalid API key" in err

    def test_missing_api_key(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": TEST_API_KEY}):
            import importlib
            import mcp_server.auth as auth
            importlib.reload(auth)
            valid, err = auth.validate_api_key(None)
            assert valid is False
            assert "Missing API key" in err

    def test_unconfigured_key_rejected(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": ""}):
            import importlib
            import mcp_server.auth as auth
            importlib.reload(auth)
            valid, err = auth.validate_api_key(TEST_API_KEY)
            assert valid is False
            assert "not configured" in err
            importlib.reload(auth)  # restore


# ==================== RATE LIMIT TESTS ====================

class TestRateLimit:
    def test_under_limit(self):
        reset_rate_limits()
        for _ in range(59):
            exceeded, retry = check_rate_limit("test_session")
            assert not exceeded
        reset_rate_limits()

    def test_at_limit(self):
        reset_rate_limits()
        for _ in range(60):
            exceeded, _ = check_rate_limit("test_session")
            assert not exceeded
        exceeded, retry_after = check_rate_limit("test_session")
        assert exceeded is True
        assert retry_after >= 1
        reset_rate_limits()

    def test_isolated_identifiers(self):
        reset_rate_limits()
        for _ in range(60):
            check_rate_limit("session_a")
        exceeded_a, _ = check_rate_limit("session_a")
        assert exceeded_a is True
        exceeded_b, _ = check_rate_limit("session_b")
        assert exceeded_b is False
        reset_rate_limits()


# ==================== TOOL DISPATCH TESTS ====================

class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_list_tools_returns_definitions(self, server):
        tools = server.list_tools()
        assert len(tools) == 10  # 5 read + 5 stubbed write
        read_tools = [t for t in tools if t.get("readOnly")]
        assert len(read_tools) == 5
        write_tools = [t for t in tools if not t.get("readOnly")]
        assert len(write_tools) == 5

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_404(self, server):
        result = await server.call_tool("nonexistent_tool", {})
        assert result["status"] == 404
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_auth_rejected(self, mock_client):
        reset_rate_limits()
        bad_server = MCPServer(api_key="wrong-key", client=mock_client)
        result = await bad_server.call_tool("list_user_trusts", {"user_id": "user_001"})
        assert result["status"] == 401

    @pytest.mark.asyncio
    async def test_missing_auth_rejected(self, mock_client):
        reset_rate_limits()
        no_key_server = MCPServer(api_key=None, client=mock_client)
        # Ensure env var doesn't provide a fallback
        with patch.dict(os.environ, {"ADMIN_API_KEY": ""}):
            result = await no_key_server.call_tool("list_user_trusts", {"user_id": "user_001"})
            assert result["status"] == 401
        reset_rate_limits()


# ==================== READ-ONLY TOOL TESTS (mocked Admin API) ====================

class TestReadOnlyTools:
    @pytest.mark.asyncio
    async def test_list_user_trusts(self, server):
        result = await server.call_tool("list_user_trusts", {"user_id": "user_001"})
        assert "error" not in result
        assert result["trust_count"] == 1
        assert result["trusts"][0]["trust_id"] == "trust_001"
        assert result["email"] == "kenneth@example.com"

    @pytest.mark.asyncio
    async def test_list_user_trusts_unknown_user(self, server):
        result = await server.call_tool("list_user_trusts", {"user_id": "user_ghost"})
        assert result["status"] == 404
        assert "User not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_trust_state(self, server):
        result = await server.call_tool(
            "get_trust_state", {"user_id": "user_001", "trust_id": "trust_001"}
        )
        assert "error" not in result
        assert result["name"] == "Family Trust"
        assert result["trust_type"] == "family"
        assert result["jurisdiction"] == "UT"
        assert result["ein"] == "87-1234567"

    @pytest.mark.asyncio
    async def test_get_trust_state_cross_user_denied(self, server):
        """Security: a user must not read another user's trust."""
        result = await server.call_tool(
            "get_trust_state", {"user_id": "user_001", "trust_id": "trust_002"}
        )
        assert result["status"] == 404
        assert "Trust not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_governance_health_with_snapshot(self, server):
        result = await server.call_tool(
            "get_governance_health", {"user_id": "user_001", "trust_id": "trust_001"}
        )
        assert "error" not in result
        assert result["health_score"] == 85  # latest snapshot
        assert len(result["criteria"]) == 2
        assert result["calculated_at"] is not None

    @pytest.mark.asyncio
    async def test_get_governance_health_no_snapshot(self, server):
        result = await server.call_tool(
            "get_governance_health", {"user_id": "user_001", "trust_id": "trust_nonexistent"}
        )
        assert result["status"] == 404

    @pytest.mark.asyncio
    async def test_get_tax_calendar_current_year(self, server):
        result = await server.call_tool(
            "get_tax_calendar", {"user_id": "user_001", "trust_id": "trust_001"}
        )
        assert "error" not in result
        assert result["total_entries"] == 3
        assert result["pending_count"] == 2
        assert result["filed_count"] == 1
        assert result["overdue_count"] == 1  # tc_002 is overdue+pending
        # Entries sorted ascending by due_date
        dates = [e["due_date"] for e in result["entries"]]
        assert dates == sorted(dates)
        # Overdue entry has negative days_remaining
        # (tc_002 overdue+pending, tc_003 overdue but already filed)
        overdue_entries = [e for e in result["entries"] if e["is_overdue"]]
        assert len(overdue_entries) == 2
        assert overdue_entries[0]["days_remaining"] < 0
        # Only pending+overdue counts toward overdue_count
        overdue_pending = [e for e in result["entries"] if e["is_overdue"] and e["filing_status"] == "pending"]
        assert len(overdue_pending) == 1
        assert overdue_pending[0]["days_remaining"] < 0

    @pytest.mark.asyncio
    async def test_get_tax_calendar_explicit_year(self, server):
        result = await server.call_tool(
            "get_tax_calendar",
            {"user_id": "user_001", "trust_id": "trust_001", "tax_year": 2030},
        )
        assert result["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_get_task_list_all(self, server):
        result = await server.call_tool(
            "get_task_list", {"user_id": "user_001", "trust_id": "trust_001"}
        )
        assert "error" not in result
        assert result["total_tasks"] == 3
        assert result["completed_count"] == 1
        assert result["pending_count"] == 2

    @pytest.mark.asyncio
    async def test_get_task_list_pending_filter(self, server):
        result = await server.call_tool(
            "get_task_list",
            {"user_id": "user_001", "trust_id": "trust_001", "status": "pending"},
        )
        assert result["total_tasks"] == 2
        assert all(not t["completed"] for t in result["tasks"])

    @pytest.mark.asyncio
    async def test_get_task_list_completed_filter(self, server):
        result = await server.call_tool(
            "get_task_list",
            {"user_id": "user_001", "trust_id": "trust_001", "status": "completed"},
        )
        assert result["total_tasks"] == 1
        assert result["tasks"][0]["task_id"] == "task_002"

    @pytest.mark.asyncio
    async def test_get_task_list_overdue_filter(self, server):
        result = await server.call_tool(
            "get_task_list",
            {"user_id": "user_001", "trust_id": "trust_001", "status": "overdue"},
        )
        # task_003 is incomplete and past due
        assert result["total_tasks"] == 1
        assert result["tasks"][0]["task_id"] == "task_003"


# ==================== STUBBED WRITE-OP TESTS ====================

class TestStubbedWriteOps:
    @pytest.mark.asyncio
    async def test_submit_trust_update_stubbed(self, server):
        result = await server.call_tool(
            "submit_trust_update",
            {"user_id": "user_001", "trust_id": "trust_001", "updates": {"name": "New Name"}},
        )
        assert result["status"] == 501
        assert "Write operations not available in Phase 1" in result["error"]
        assert result["tool"] == "submit_trust_update"

    @pytest.mark.asyncio
    async def test_submit_asset_values_stubbed(self, server):
        result = await server.call_tool(
            "submit_asset_values",
            {"user_id": "user_001", "trust_id": "trust_001", "asset_values": []},
        )
        assert result["status"] == 501

    @pytest.mark.asyncio
    async def test_complete_task_stubbed(self, server):
        result = await server.call_tool(
            "complete_task",
            {"user_id": "user_001", "trust_id": "trust_001", "task_id": "task_001"},
        )
        assert result["status"] == 501

    @pytest.mark.asyncio
    async def test_submit_minutes_draft_stubbed(self, server):
        result = await server.call_tool(
            "submit_minutes_draft",
            {"user_id": "user_001", "trust_id": "trust_001", "minutes_data": {}},
        )
        assert result["status"] == 501

    @pytest.mark.asyncio
    async def test_update_beneficiary_stubbed(self, server):
        result = await server.call_tool(
            "update_beneficiary",
            {"user_id": "user_001", "trust_id": "trust_001", "beneficiary_id": "bene_001", "updates": {}},
        )
        assert result["status"] == 501


# ==================== IDEMPOTENCY TESTS ====================

class TestIdempotency:
    @pytest.mark.asyncio
    async def test_same_key_returns_cached_result(self, server):
        args = {"user_id": "user_001", "trust_id": "trust_001"}
        first = await server.call_tool("get_trust_state", args, idempotency_key="idem_abc123")
        second = await server.call_tool("get_trust_state", args, idempotency_key="idem_abc123")
        assert second.get("idempotent_replay") is True
        assert first["name"] == second["name"]

    @pytest.mark.asyncio
    async def test_idempotency_scoped_per_user(self, server):
        """Same idempotency key for a different user scope = new request."""
        first = await server.call_tool(
            "get_trust_state",
            {"user_id": "user_001", "trust_id": "trust_001"},
            idempotency_key="idem_scope",
        )
        # Different user scope → treated as new request (and user_002's trust is not user_001's)
        second = await server.call_tool(
            "get_trust_state",
            {"user_id": "user_002", "trust_id": "trust_002"},
            idempotency_key="idem_scope",
        )
        assert "idempotent_replay" not in second

    @pytest.mark.asyncio
    async def test_no_key_no_cache(self, server):
        args = {"user_id": "user_001", "trust_id": "trust_001"}
        first = await server.call_tool("get_trust_state", args)
        second = await server.call_tool("get_trust_state", args)
        assert "idempotent_replay" not in second


# ==================== AUDIT LOGGING TESTS ====================

class TestAuditLogging:
    @pytest.mark.asyncio
    async def test_tool_call_writes_audit_entry(self, server):
        inserted = []

        async def fake_insert_one(doc):
            inserted.append(doc)

        with patch.object(audit_module.db, "admin_api_audit") as mock_coll:
            mock_coll.insert_one = AsyncMock(side_effect=fake_insert_one)
            await server.call_tool(
                "get_trust_state", {"user_id": "user_001", "trust_id": "trust_001"}
            )

        assert len(inserted) == 1
        entry = inserted[0]
        assert entry["action"] == "mcp_get_trust_state"
        assert entry["source"] == "mcp"
        assert entry["protocol_version"] == "1.0"
        assert entry["user_id"] == "user_001"
        assert entry["details"]["tool_name"] == "get_trust_state"

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_break_tool(self, server):
        async def failing_insert(doc):
            raise RuntimeError("db down")

        with patch.object(audit_module.db, "admin_api_audit") as mock_coll:
            mock_coll.insert_one = AsyncMock(side_effect=failing_insert)
            result = await server.call_tool(
                "list_user_trusts", {"user_id": "user_001"}
            )
        # Tool result still succeeds even though audit write failed
        assert "error" not in result
        assert result["trust_count"] == 1

    @pytest.mark.asyncio
    async def test_audit_failure_logged(self, server, caplog):
        async def failing_insert(doc):
            raise RuntimeError("db down")

        with patch.object(audit_module.db, "admin_api_audit") as mock_coll:
            mock_coll.insert_one = AsyncMock(side_effect=failing_insert)
            with caplog.at_level("ERROR"):
                await server.call_tool("list_user_trusts", {"user_id": "user_001"})
        assert any("MCP audit log failed" in r.message for r in caplog.records)


# ==================== RATE LIMIT VIA SERVER TESTS ====================

class TestServerRateLimit:
    @pytest.mark.asyncio
    async def test_rate_limit_enforced_through_server(self, mock_client):
        reset_rate_limits()
        s = MCPServer(api_key=TEST_API_KEY, client=mock_client)
        results = []
        for _ in range(61):
            results.append(await s.call_tool("list_user_trusts", {"user_id": "user_001"}))
        last = results[-1]
        assert last["status"] == 429
        assert last["error"] == "rate_limit_exceeded"
        assert last["retry_after_seconds"] >= 1
        reset_rate_limits()


# ==================== HELPER TESTS ====================

class TestHelpers:
    def test_days_remaining_future(self):
        future = (date.today() + timedelta(days=10)).isoformat()
        assert _days_remaining(future) == 10

    def test_days_remaining_past(self):
        past = (date.today() - timedelta(days=10)).isoformat()
        assert _days_remaining(past) == -10

    def test_days_remaining_today(self):
        assert _days_remaining(date.today().isoformat()) == 0

    def test_days_remaining_none(self):
        assert _days_remaining(None) == 9999

    def test_days_remaining_invalid(self):
        assert _days_remaining("not-a-date") == 9999

    def test_days_remaining_iso_datetime(self):
        future_dt = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        assert _days_remaining(future_dt) == 5


# ==================== ENTRYPOINT SMOKE TEST ====================

class TestEntrypoint:
    def test_main_exits_without_key(self, capsys):
        from mcp_server import server as srv
        env = {k: v for k, v in os.environ.items() if k != "ADMIN_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SystemExit) as exc:
                srv.main()
            assert exc.value.code == 1

    def test_main_prints_tool_list_with_key(self, capsys):
        from mcp_server import server as srv
        with patch.dict(os.environ, {"ADMIN_API_KEY": TEST_API_KEY}):
            srv.main()
        out = capsys.readouterr().out
        assert "TrustOffice MCP Server" in out
        assert "get_trust_state" in out
        assert "STUBBED" in out
        assert "READ" in out