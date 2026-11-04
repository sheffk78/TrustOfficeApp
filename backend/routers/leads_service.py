"""TrustOffice "leads service" lane (Phase 1).

Scoped, service-to-service endpoints consumed by the Agentic OS overview
card (Kit's command center). Authenticated with a single static service key
sent in the `X-Service-Key` header â NOT a user JWT. The OS backend calls
these server-side, so no browser CORS is opened here.

Endpoints (mounted under /api/service/leads):
  GET  /latest                 -> 3 newest leads + each lead's 3 latest activities
  POST /{lead_id}/note         -> append a manual note (through the same
                                  _log_activity helper the admin notes use)
  PATCH /{lead_id}/stage       -> set stage (validated) + log a system activity
"""
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from database import db
from routers.leads import LEAD_STAGES, _log_activity

logger = logging.getLogger(__name__)

# Service key header (constant-time compare against TRUSTOFFICE_LEADS_SERVICE_KEY).
SERVICE_KEY_HEADER = APIKeyHeader(name="X-Service-Key", auto_error=False)

# Projected lead fields returned to the OS card (never the Mongo _id).
LEAD_PROJECTION = {
    "_id": 0,
    "lead_id": 1,
    "name": 1,
    "email": 1,
    "phone": 1,
    "stage": 1,
    "source": 1,
    "created_at": 1,
    "updated_at": 1,
    "notes": 1,
}

ACTIVITY_CONTENT_LIMIT = 160


# ==================== AUTH ====================

async def require_leads_service(service_key: str = Depends(SERVICE_KEY_HEADER)) -> str:
    """Gate every endpoint on the scoped service key.

    Reads the expected key at request time (not import time) so test/live
    envs can supply it without reloading the module.
    """
    expected = os.environ.get("TRUSTOFFICE_LEADS_SERVICE_KEY")
    if not expected:
        # Service key not provisioned in this environment.
        raise HTTPException(status_code=503, detail="leads service not configured")
    if not service_key:
        raise HTTPException(
            status_code=401,
            detail="Missing service key. Send the key in the X-Service-Key header.",
        )
    if not secrets.compare_digest(service_key, expected):
        raise HTTPException(status_code=401, detail="Invalid service key")
    return service_key


# ==================== MODELS ====================

class ServiceNoteRequest(BaseModel):
    content: str


class ServiceStageRequest(BaseModel):
    stage: str


# ==================== ROUTER ====================

router = APIRouter(
    prefix="/service/leads",
    tags=["leads-service"],
    dependencies=[Depends(require_leads_service)],
)


def _iso(value):
    """Render a datetime as ISO; pass through strings/None."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _activity_view(activity: dict) -> dict:
    content = activity.get("content") or ""
    return {
        "action_type": activity.get("action_type"),
        "content": content[:ACTIVITY_CONTENT_LIMIT],
        "created_at": _iso(activity.get("created_at")),
    }


@router.get("/latest")
async def get_latest_leads():
    """Return the 3 newest leads, each with its 3 most recent activities."""
    leads_out: List[dict] = []

    cursor = (
        db.leads.find({}, LEAD_PROJECTION)
        .sort("created_at", -1)
        .limit(3)
    )
    async for lead in cursor:
        lead_id = lead.get("lead_id")
        activities: List[dict] = []
        act_cursor = (
            db.lead_activities.find({"lead_id": lead_id})
            .sort("created_at", -1)
            .limit(3)
        )
        async for act in act_cursor:
            activities.append(_activity_view(act))
        leads_out.append(
            {
                "lead_id": lead_id,
                "name": lead.get("name"),
                "email": lead.get("email"),
                "phone": lead.get("phone"),
                "stage": lead.get("stage"),
                "source": lead.get("source"),
                "created_at": _iso(lead.get("created_at")),
                "updated_at": _iso(lead.get("updated_at")),
                "notes": lead.get("notes"),
                "activities": activities,
            }
        )

    return {"leads": leads_out, "asOf": datetime.now(timezone.utc).isoformat()}


@router.post("/{lead_id}/note")
async def add_service_note(lead_id: str, body: ServiceNoteRequest):
    """Append a manual note to a lead's activity log."""
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    content = (body.content or "").strip()
    if not content or len(content) > 2000:
        raise HTTPException(
            status_code=400,
            detail="content must be a non-empty string between 1 and 2000 characters",
        )

    await _log_activity(lead_id, "manual", content)
    return {"success": True}


@router.patch("/{lead_id}/stage")
async def set_service_stage(lead_id: str, body: ServiceStageRequest):
    """Set a lead's stage (validated) and log a system activity."""
    stage = (body.stage or "").strip()
    if stage not in LEAD_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage. Must be one of: {', '.join(LEAD_STAGES)}",
        )

    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    now = datetime.now(timezone.utc)
    await db.leads.update_one(
        {"lead_id": lead_id},
        {"$set": {"stage": stage, "updated_at": now.isoformat()}},
    )
    await _log_activity(
        lead_id, "system", f"Stage set to {stage} from OS overview by Kit"
    )
    return {"success": True, "stage": stage}
