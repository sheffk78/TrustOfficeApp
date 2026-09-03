"""
Admin API client for the MCP server.

This module provides a thin client layer that the MCP tools call to interact
with the TrustOffice MongoDB collections. It mirrors the patterns used in
routers/admin_api.py and routers/governance.py but is designed to be mockable
for unit testing.

The client does NOT import or depend on the FastAPI app or routers — it talks
directly to MongoDB via the shared `database.db` object, exactly as the
existing routers do. This ensures no modification to existing API behavior.
"""

from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Any
import uuid
import logging

from database import db

logger = logging.getLogger(__name__)


class AdminAPIClient:
    """
    Thin async client over TrustOffice MongoDB collections.

    All methods are read-only in Phase 1. Write methods are defined but
    raise NotImplementedError to make the stub explicit.
    """

    # ==================== READ OPERATIONS ====================

    async def get_user_trusts(self, user_id: str) -> Dict[str, Any]:
        """List all trusts for a user. Mirrors admin_api GET /users/{user_id}/trusts."""
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
        if not user:
            return {"error": "User not found", "status": 404}

        trusts = await db.trusts.find({"user_id": user_id}, {"_id": 0}).to_list(100)

        return {
            "user_id": user_id,
            "email": user.get("email"),
            "name": user.get("name"),
            "trust_count": len(trusts),
            "trusts": trusts,
        }

    async def get_trust_state(self, user_id: str, trust_id: str) -> Dict[str, Any]:
        """Get a single trust's details. Mirrors trusts router pattern."""
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
        )
        if not trust:
            return {"error": "Trust not found", "status": 404}

        return {
            "trust_id": trust_id,
            "user_id": user_id,
            "name": trust.get("name"),
            "trust_type": trust.get("trust_type", "family"),
            "jurisdiction": trust.get("jurisdiction", ""),
            "state_code": trust.get("state_code", ""),
            "role": trust.get("role", "Trustee"),
            "trustees": trust.get("trustees", []),
            "start_date": trust.get("start_date"),
            "ein": trust.get("ein"),
            "is_fiscal_year": trust.get("is_fiscal_year", False),
            "tax_year_end_month": trust.get("tax_year_end_month"),
            "tax_year_end_day": trust.get("tax_year_end_day"),
            "created_at": trust.get("created_at"),
        }

    async def get_governance_health(self, user_id: str, trust_id: str) -> Dict[str, Any]:
        """
        Get the latest governance health score for a trust.

        Reads from db.health_score_snapshots (same collection as
        services/health_service.py). Returns the most recent snapshot.
        """
        # Verify trust ownership
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id}, {"_id": 0, "name": 1}
        )
        if not trust:
            return {"error": "Trust not found", "status": 404}

        # Get the latest health score snapshot
        snapshot = await db.health_score_snapshots.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0},
            sort=[("calculated_at", -1)],
        )

        if not snapshot:
            return {
                "trust_id": trust_id,
                "trust_name": trust.get("name"),
                "health_score": None,
                "criteria": [],
                "calculated_at": None,
                "message": "No health score snapshot available. Health score will be calculated on next governance review.",
            }

        return {
            "trust_id": trust_id,
            "trust_name": trust.get("name"),
            "health_score": snapshot.get("health_score"),
            "criteria": snapshot.get("criteria", []),
            "calculated_at": snapshot.get("calculated_at"),
        }

    async def get_tax_calendar(
        self, user_id: str, trust_id: str, tax_year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get tax calendar entries for a trust.

        Mirrors the tax_calendar router GET /trusts/{trust_id}/tax-calendar
        pattern, including days_remaining and overdue calculation.
        """
        # Verify trust ownership
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id}, {"_id": 0, "name": 1}
        )
        if not trust:
            return {"error": "Trust not found", "status": 404}

        year = tax_year or date.today().year
        raw = await db.tax_calendar.find(
            {"trust_id": trust_id, "tax_year": year},
            {"_id": 0},
        ).sort("due_date", 1).to_list(50)

        entries = []
        for doc in raw:
            days_remaining = _days_remaining(doc.get("due_date"))
            entries.append({
                **doc,
                "days_remaining": days_remaining,
                "is_overdue": days_remaining < 0,
            })

        filed = sum(1 for e in entries if e.get("filing_status") in ("filed", "not_required"))
        pending = sum(1 for e in entries if e.get("filing_status") == "pending")
        overdue = sum(1 for e in entries if e.get("is_overdue") and e.get("filing_status") == "pending")

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

    async def get_task_list(
        self, user_id: str, trust_id: str, status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get governance tasks for a trust.

        Mirrors the tasks router GET /tasks pattern, filtered by trust_id
        and optionally by completion status.
        """
        # Verify trust ownership
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id}, {"_id": 0, "name": 1}
        )
        if not trust:
            return {"error": "Trust not found", "status": 404}

        query: Dict[str, Any] = {"trust_id": trust_id, "user_id": user_id}
        if status == "completed":
            query["completed"] = True
        elif status == "pending":
            query["completed"] = False
        elif status == "overdue":
            query["completed"] = False
            query["due_date"] = {"$lt": datetime.now(timezone.utc).isoformat()}

        tasks = await db.governance_tasks.find(
            query, {"_id": 0}
        ).sort("due_date", 1).to_list(200)

        completed_count = sum(1 for t in tasks if t.get("completed"))
        pending_count = len(tasks) - completed_count

        return {
            "trust_id": trust_id,
            "trust_name": trust.get("name"),
            "total_tasks": len(tasks),
            "completed_count": completed_count,
            "pending_count": pending_count,
            "tasks": tasks,
        }

    # ==================== WRITE OPERATIONS (STUBBED — PHASE 2) ====================

    async def submit_trust_update(
        self, user_id: str, trust_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """STUBBED — Write operations not available in Phase 1."""
        return {
            "error": "Write operations not available in Phase 1",
            "status": 501,
            "tool": "submit_trust_update",
            "phase": "Phase 2 (planned)",
        }

    async def submit_asset_values(
        self, user_id: str, trust_id: str, asset_values: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """STUBBED — Write operations not available in Phase 1."""
        return {
            "error": "Write operations not available in Phase 1",
            "status": 501,
            "tool": "submit_asset_values",
            "phase": "Phase 2 (planned)",
        }

    async def complete_task(self, user_id: str, trust_id: str, task_id: str) -> Dict[str, Any]:
        """STUBBED — Write operations not available in Phase 1."""
        return {
            "error": "Write operations not available in Phase 1",
            "status": 501,
            "tool": "complete_task",
            "phase": "Phase 2 (planned)",
        }

    async def submit_minutes_draft(
        self, user_id: str, trust_id: str, minutes_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """STUBBED — Write operations not available in Phase 1."""
        return {
            "error": "Write operations not available in Phase 1",
            "status": 501,
            "tool": "submit_minutes_draft",
            "phase": "Phase 2 (planned)",
        }

    async def update_beneficiary(
        self, user_id: str, trust_id: str, beneficiary_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """STUBBED — Write operations not available in Phase 1."""
        return {
            "error": "Write operations not available in Phase 1",
            "status": 501,
            "tool": "update_beneficiary",
            "phase": "Phase 2 (planned)",
        }


# ==================== HELPERS ====================

def _days_remaining(due_date_str: Optional[str]) -> int:
    """Calculate days remaining until a due date. Mirrors tax_calendar_math._days_remaining."""
    if not due_date_str:
        return 9999
    try:
        # Parse ISO date string (may be full datetime or date-only)
        if "T" in due_date_str:
            due = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
            due_date = due.date()
        else:
            due_date = date.fromisoformat(due_date_str[:10])

        today = date.today()
        return (due_date - today).days
    except (ValueError, TypeError):
        return 9999