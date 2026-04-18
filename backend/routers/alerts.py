# Separation Alerts router — commingling detection alert management
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, require_write_access
from models import AlertResponse, AlertResolveRequest, AlertCountResponse
from alert_detection import run_pattern_alerts

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    trust_id: str,
    entity_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: str = "active",
    alert_type: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    user: dict = Depends(get_current_user)
):
    """Get separation alerts for a trust"""
    query = {"trust_id": trust_id, "user_id": user["user_id"], "status": status}
    if entity_id:
        query["entity_id"] = entity_id
    if severity:
        query["severity"] = severity
    if alert_type:
        query["alert_type"] = alert_type

    alerts = await db.separation_alerts.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    # Enrich with entity names
    entity_ids = list(set(a.get("entity_id") for a in alerts if a.get("entity_id")))
    if entity_ids:
        entities = await db.entities.find(
            {"entity_id": {"$in": entity_ids}},
            {"_id": 0, "entity_id": 1, "name": 1}
        ).to_list(100)
        entity_map = {e["entity_id"]: e["name"] for e in entities}
        for a in alerts:
            a["entity_name"] = entity_map.get(a.get("entity_id"), "")

    return [AlertResponse(**a) for a in alerts]


@router.get("/alerts/count")
async def get_alert_counts(trust_id: str, user: dict = Depends(get_current_user)):
    """Get alert counts for a trust — used by dashboard and entity map"""
    query = {"trust_id": trust_id, "user_id": user["user_id"], "status": "active"}
    alerts = await db.separation_alerts.find(query, {"_id": 0}).to_list(1000)

    red = sum(1 for a in alerts if a.get("severity") == "red")
    yellow = sum(1 for a in alerts if a.get("severity") == "yellow")

    by_entity = {}
    for a in alerts:
        eid = a.get("entity_id", "unknown")
        by_entity.setdefault(eid, {"red": 0, "yellow": 0})
        by_entity[eid][a.get("severity", "yellow")] += 1

    by_type = {}
    for a in alerts:
        atype = a.get("alert_type", "unknown")
        by_type[atype] = by_type.get(atype, 0) + 1

    return {
        "trust_id": trust_id,
        "total_active": len(alerts),
        "red_count": red,
        "yellow_count": yellow,
        "by_entity": by_entity,
        "by_type": by_type
    }


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(alert_id: str, req: AlertResolveRequest, user: dict = Depends(require_write_access)):
    """Resolve a separation alert — resolution is immutable audit record"""
    alert = await db.separation_alerts.find_one(
        {"alert_id": alert_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert["status"] == "resolved":
        raise HTTPException(status_code=400, detail="Alert already resolved")

    if not req.resolution_note.strip():
        raise HTTPException(status_code=400, detail="Resolution note is required")

    valid_types = ["classified", "linked", "documented", "reviewed_no_issue"]
    if req.resolution_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"resolution_type must be one of: {valid_types}")

    now = datetime.now(timezone.utc).isoformat()
    update = {
        "status": "resolved",
        "resolution_type": req.resolution_type,
        "resolution_note": req.resolution_note,
        "resolved_at": now
    }

    await db.separation_alerts.update_one({"alert_id": alert_id}, {"$set": update})

    # Immutable audit log
    await db.alert_audit_log.insert_one({
        "audit_id": f"alert_audit_{uuid.uuid4().hex[:12]}",
        "alert_id": alert_id,
        "user_id": user["user_id"],
        "action": "resolved",
        "resolution_type": req.resolution_type,
        "resolution_note": req.resolution_note,
        "timestamp": now
    })

    updated = await db.separation_alerts.find_one({"alert_id": alert_id}, {"_id": 0})
    entity = await db.entities.find_one({"entity_id": updated.get("entity_id")}, {"_id": 0, "name": 1})
    updated["entity_name"] = entity.get("name", "") if entity else ""
    return AlertResponse(**updated)


@router.post("/alerts/scan")
async def scan_for_alerts(trust_id: str, user: dict = Depends(require_write_access)):
    """Manually trigger a full pattern scan for a trust"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    await run_pattern_alerts(trust_id, user["user_id"])

    # Return updated counts
    active = await db.separation_alerts.count_documents(
        {"trust_id": trust_id, "user_id": user["user_id"], "status": "active"}
    )

    return {"message": "Scan complete", "active_alerts": active}


@router.get("/alerts/history", response_model=List[AlertResponse])
async def get_alert_history(
    trust_id: str,
    limit: int = 50,
    user: dict = Depends(get_current_user)
):
    """Get all alerts (active + resolved) for audit trail purposes"""
    alerts = await db.separation_alerts.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    entity_ids = list(set(a.get("entity_id") for a in alerts if a.get("entity_id")))
    if entity_ids:
        entities = await db.entities.find(
            {"entity_id": {"$in": entity_ids}},
            {"_id": 0, "entity_id": 1, "name": 1}
        ).to_list(100)
        entity_map = {e["entity_id"]: e["name"] for e in entities}
        for a in alerts:
            a["entity_name"] = entity_map.get(a.get("entity_id"), "")

    return [AlertResponse(**a) for a in alerts]
