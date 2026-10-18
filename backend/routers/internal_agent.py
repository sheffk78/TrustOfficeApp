"""
Internal Agent API - programmatic endpoints for TrustOffice's proactive agent.

Authentication: API Key via X-Internal-API-Key header (separate namespace from
customer-facing and admin-api routes so a future customer-bridge scope can never
reach these routes).

Endpoints:
- POST /api/internal/agent/activity        - Log an agent action
- GET  /api/internal/agent/status/{trust_id} - Agent status for one trust
- POST /api/internal/agent/enable          - Enable the agent for a customer
- POST /api/internal/agent/disable         - Disable the agent for a customer
"""

import os
import uuid
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from database import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["internal-agent"])

api_key_header = APIKeyHeader(name="X-Internal-API-Key", auto_error=False)


async def verify_internal_api_key(request: Request, api_key: str = Depends(api_key_header)):
    """Verify the Internal API key used by agent tooling and admin automation."""
    # Lazy env read so tests and runners can set the key after module import.
    key = os.environ.get("INTERNAL_API_KEY") or os.environ.get("ADMIN_API_KEY")
    if not key:
        logger.error("INTERNAL_API_KEY / ADMIN_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Internal API not configured")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Use X-Internal-API-Key header.")
    if not secrets.compare_digest(api_key, key):
        logger.warning("Internal API key mismatch")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


class AgentActivityRequest(BaseModel):
    customer_id: str
    trust_id: Optional[str] = None
    action: str
    payload: Optional[dict] = None
    run_id: Optional[str] = None


class AgentToggleRequest(BaseModel):
    customer_id: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _log_agent_activity(
    customer_id: str,
    action: str,
    trust_id: Optional[str] = None,
    payload: Optional[dict] = None,
    run_id: Optional[str] = None,
) -> str:
    """Persist an agent action to the agent_activity collection."""
    activity_id = f"agent_act_{uuid.uuid4().hex[:12]}"
    await db.agent_activity.insert_one({
        "activity_id": activity_id,
        "customer_id": customer_id,
        "trust_id": trust_id,
        "action": action,
        "payload": payload or {},
        "run_id": run_id,
        "ts": _now_iso(),
    })
    return activity_id


@router.post("/activity")
async def log_agent_activity(
    body: AgentActivityRequest,
    request: Request,
    api_key: str = Depends(verify_internal_api_key),
):
    """Log a single agent action to the agent_activity collection."""
    activity_id = await _log_agent_activity(
        customer_id=body.customer_id,
        action=body.action,
        trust_id=body.trust_id,
        payload=body.payload,
        run_id=body.run_id,
    )
    logger.info(f"Internal agent API: logged activity {activity_id} for {body.customer_id}")
    return {
        "activity_id": activity_id,
        "customer_id": body.customer_id,
        "trust_id": body.trust_id,
        "action": body.action,
        "ts": _now_iso(),
    }


@router.get("/status/{trust_id}")
async def get_agent_status(
    trust_id: str,
    request: Request,
    api_key: str = Depends(verify_internal_api_key),
):
    """Return agent status for a single trust: enabled/consent flags, latest health
    snapshot, next upcoming deadline, and recent agent activity count."""
    trust = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0, "user_id": 1, "name": 1})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    customer_id = trust["user_id"]
    user = await db.users.find_one(
        {"user_id": customer_id},
        {"_id": 0, "agent_enabled": 1, "agent_consent": 1, "email": 1, "name": 1},
    )
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")

    latest_snapshot = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id},
        {"_id": 0, "score_value": 1, "color": 1, "calculated_at": 1},
        sort=[("calculated_at", -1)],
    )

    next_deadline = await db.deadlines.find_one(
        {"trust_id": trust_id, "status": {"$nin": ["completed", "waived"]}},
        {"_id": 0, "deadline_id": 1, "title": 1, "due_date": 1, "priority": 1, "status": 1, "days_remaining": 1},
        sort=[("due_date", 1)],
    )

    activity_count = await db.agent_activity.count_documents({"trust_id": trust_id})

    return {
        "trust_id": trust_id,
        "trust_name": trust.get("name"),
        "customer_id": customer_id,
        "customer_email": user.get("email"),
        "agent_enabled": bool(user.get("agent_enabled", False)),
        "agent_consent": bool(user.get("agent_consent", False)),
        "health_score": {
            "score": latest_snapshot.get("score_value") if latest_snapshot else None,
            "color": latest_snapshot.get("color") if latest_snapshot else None,
            "calculated_at": latest_snapshot.get("calculated_at") if latest_snapshot else None,
        },
        "next_deadline": next_deadline,
        "agent_activity_count": activity_count,
    }


@router.post("/enable")
async def enable_agent(
    body: AgentToggleRequest,
    request: Request,
    api_key: str = Depends(verify_internal_api_key),
):
    """Enable the proactive agent for a customer."""
    user = await db.users.find_one({"user_id": body.customer_id}, {"_id": 0, "user_id": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")

    await db.users.update_one(
        {"user_id": body.customer_id},
        {"$set": {"agent_enabled": True, "agent_enabled_at": _now_iso()}},
    )
    activity_id = await _log_agent_activity(
        customer_id=body.customer_id,
        action="agent_enabled",
        payload={"via": "internal_api"},
    )
    return {
        "customer_id": body.customer_id,
        "agent_enabled": True,
        "activity_id": activity_id,
    }


@router.post("/disable")
async def disable_agent(
    body: AgentToggleRequest,
    request: Request,
    api_key: str = Depends(verify_internal_api_key),
):
    """Disable the proactive agent for a customer."""
    user = await db.users.find_one({"user_id": body.customer_id}, {"_id": 0, "user_id": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")

    await db.users.update_one(
        {"user_id": body.customer_id},
        {"$set": {"agent_enabled": False, "agent_disabled_at": _now_iso()}},
    )
    activity_id = await _log_agent_activity(
        customer_id=body.customer_id,
        action="agent_disabled",
        payload={"via": "internal_api"},
    )
    return {
        "customer_id": body.customer_id,
        "agent_enabled": False,
        "activity_id": activity_id,
    }
