# Trust Administrative Services router.
#
# Entitled users (purchased or gifted free quarter) get the scheduling link
# to Kenneth. Admin endpoints: grant the gifted free quarter, list whose
# free quarter has elapsed (purchase invites — drafts only, nothing auto-sends).
#
# Invite clock: anchor = earliest trusts.created_at per user, + 3 months
# (Kenneth directive 2026-09-12).

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import os
import logging

from database import db
from dependencies import get_current_user
from trust_admin_service import (
    new_gift_entitlement,
    resolve_entitlement,
    days_past_quarter,
    _as_date,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trust_admin_service"])

# Canonical scheduler (booking-trustoffice, owner=kenneth, brand=trustoffice).
# book.trustoffice.app is the vanity domain once its SSL cert finishes issuing;
# the Railway URL is the verified-live fallback.
SCHEDULING_URL_KENNETH = os.environ.get(
    "SCHEDULING_URL_KENNETH",
    "https://booking-trustoffice-production.up.railway.app/",
)


def _is_admin(user: dict) -> bool:
    return bool(user.get("is_admin", False))


async def _first_trust_created_at(user_id: str) -> Optional[str]:
    doc = await db.trusts.find_one(
        {"user_id": user_id}, {"created_at": 1, "_id": 0}, sort=[("created_at", 1)]
    )
    return (doc or {}).get("created_at")


@router.get("/trust-admin-service/scheduling")
async def get_scheduling_availability(user: dict = Depends(get_current_user)):
    """Dashboard card source of truth: is this user entitled to schedule with Kenneth."""
    sub = await db.subscriptions.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not sub:
        return {"entitled": False, "source": "none", "status": "none",
                "scheduling_url": None}

    ent = dict(sub)
    # Gifted quarters derive their clock from the first trust submission.
    if (ent.get("trust_admin_service") or {}).get("source") == "gifted":
        anchor = await _first_trust_created_at(user["user_id"])
        ent["_first_trust_created_at"] = anchor

    resolved = resolve_entitlement(ent)
    resolved["scheduling_url"] = SCHEDULING_URL_KENNETH if resolved["entitled"] else None
    return resolved


@router.get("/admin/invites-due")
async def list_invites_due(user: dict = Depends(get_current_user)):
    """Gifted users whose free quarter has fully elapsed — the purchase-invite list.

    Computed, never stored: anchor is always the live earliest trusts.created_at.
    No email is sent from this endpoint.
    """
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    today = datetime.now(timezone.utc).date()
    results = []
    async for sub in db.subscriptions.find(
        {"trust_admin_service.source": "gifted"}, {"_id": 0}
    ):
        user_doc = await db.users.find_one(
            {"user_id": sub["user_id"]}, {"_id": 0, "name": 1, "email": 1}
        )
        anchor = await _first_trust_created_at(sub["user_id"])
        past = days_past_quarter(anchor, now=today)
        if past is None or past < 0:
            continue
        granted = (sub.get("trust_admin_service") or {})
        results.append({
            "user_id": sub["user_id"],
            "name": (user_doc or {}).get("name") or "Unknown",
            "email": (user_doc or {}).get("email"),
            "first_trust_at": anchor,
            "quarter_ended_at": _as_date(anchor).isoformat() if anchor else None,
            "days_past_quarter": past,
            "gifted_at": granted.get("granted_at"),
            "granted_by": granted.get("granted_by"),
        })
    results.sort(key=lambda r: r["days_past_quarter"], reverse=True)
    return {"count": len(results), "invites": results,
            "note": "Draft list only. Sending requires Kenneth's approval."}


class GiftRequest(BaseModel):
    user_id: str
    note: str = ""


@router.post("/admin/trust-admin-service/gift")
async def gift_free_quarter(payload: GiftRequest, user: dict = Depends(get_current_user)):
    """Admin grants the gifted free quarter ( Kenneth directive 2026-09-12)."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    target = await db.users.find_one({"user_id": payload.user_id}, {"_id": 0, "user_id": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    ent = new_gift_entitlement(granted_by=user.get("email") or user.get("user_id") or "unknown",
                               note=payload.note)
    await db.subscriptions.update_one(
        {"user_id": payload.user_id},
        {"$set": {"trust_admin_service": ent},
         "$setOnInsert": {"subscription_id": f"sub_{payload.user_id}",
                          "plan_type": "none", "status": "expired"}},
        upsert=True,
    )
    logger.info("trust_admin_service gifted: user=%s by=%s", payload.user_id, user.get("email"))
    return {"ok": True, "user_id": payload.user_id,
            "trust_admin_service": ent,
            "quarter_ends_on": "first trust submission + 3 months (computed at read time)"}


@router.post("/admin/trust-admin-service/revoke")
async def revoke_entitlement(payload: GiftRequest, user: dict = Depends(get_current_user)):
    """Admin revoke — sets status to cancelled (purchased) or removes the gift."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")

    sub = await db.subscriptions.find_one({"user_id": payload.user_id})
    if not sub or not sub.get("trust_admin_service"):
        raise HTTPException(status_code=404, detail="No trust-admin entitlement on record")

    if sub["trust_admin_service"].get("source") == "gifted":
        await db.subscriptions.update_one(
            {"user_id": payload.user_id}, {"$unset": {"trust_admin_service": ""}}
        )
        return {"ok": True, "user_id": payload.user_id, "action": "gift_removed"}
    await db.subscriptions.update_one(
        {"user_id": payload.user_id},
        {"$set": {"trust_admin_service.status": "cancelled"}},
    )
    return {"ok": True, "user_id": payload.user_id, "action": "purchased_cancelled"}