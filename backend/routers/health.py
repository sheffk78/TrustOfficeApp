# Health router — Phase 3 Health Score & Deadline Tracking (health score trends, alerts, snapshots)
from typing import List

from fastapi import APIRouter, HTTPException, Depends

from dependencies import get_current_user, require_write_access
from services import health_service

router = APIRouter(tags=["health"])


async def _require_owned_trust(trust_id: str, user: dict) -> dict:
    trust = await health_service.get_owned_trust(trust_id, user["user_id"])
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return trust


@router.get("/health/{trust_id}/trend")
async def get_health_trend(
    trust_id: str,
    days: int = 90,
    user: dict = Depends(get_current_user),
):
    """Health score trend over time (deduped by date, ascending)."""
    await _require_owned_trust(trust_id, user)
    days = max(1, min(days, 365))
    trend = await health_service.get_health_trend(trust_id, user["user_id"], days=days)
    return {"trust_id": trust_id, "days": days, "trend": trend}


@router.get("/health/{trust_id}/alerts")
async def get_health_alerts(trust_id: str, user: dict = Depends(get_current_user)):
    """Active health alerts from failed criteria (most recent snapshot)."""
    await _require_owned_trust(trust_id, user)
    alerts = await health_service.get_health_alerts(trust_id, user["user_id"])
    return {"trust_id": trust_id, "alert_count": len(alerts), "alerts": alerts}


@router.get("/health/{trust_id}/snapshots")
async def get_snapshots(
    trust_id: str,
    limit: int = 30,
    user: dict = Depends(get_current_user),
):
    """Raw health score snapshots, most recent first."""
    await _require_owned_trust(trust_id, user)
    limit = max(1, min(limit, 365))
    snapshots = await health_service.get_snapshots(trust_id, user["user_id"], limit=limit)
    return {"trust_id": trust_id, "count": len(snapshots), "snapshots": snapshots}


@router.post("/health/{trust_id}/snapshot", status_code=201)
async def force_snapshot(trust_id: str, user: dict = Depends(require_write_access)):
    """Force a fresh health score calculation and persist a snapshot."""
    await _require_owned_trust(trust_id, user)
    result = await health_service.force_snapshot(trust_id, user["user_id"])
    return result


@router.get("/health/client/{client_id}/summary")
async def get_client_health_summary(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    """Cross-trust health summary for a client (avg score, colors, worst criteria)."""
    summary = await health_service.get_client_health_summary(client_id, user["user_id"])
    return summary
