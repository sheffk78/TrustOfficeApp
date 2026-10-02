"""Phase 0 — GET /orgs/{org_id}/trusts/search (advisor hundreds-scale filtering).

Contract mirrors GET /orgs/{org_id}/trusts (same grant-scoping, same payload
fields) and adds server-side q/level/status/client/deadline filters, sort,
page/page_size with a total count. Indexes ensured on first use (idempotent).

Router pattern: standalone APIRouter module registered in server.py include
list (matches routers/email_archive.py etc.), importing helpers from routers.orgs.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException

from dependencies import get_current_user
from database import db

from .orgs import (
    _toggle_institution,
    _level_rank,
    _trustee_display_name,
    _my_memberships,
)

router = APIRouter(tags=["org-console"])


async def _ensure_indexes():
    """Idempotent (MongoDB no-ops existing-index creates). Same pattern as
    email_archive.ensure_email_archive_indexes — awaited create_index."""
    await db.trusts.create_index([("name", 1)], name="orgsearch_name")
    await db.trusts.create_index([("user_id", 1)], name="orgsearch_owner")
    await db.trust_grants.create_index(
        [("org_id", 1), ("status", 1), ("level", 1), ("member_id", 1)],
        name="orgsearch_grant",
    )
    await db.governance_tasks.create_index(
        [("trust_id", 1), ("due_date", 1), ("completed_at", 1)],
        name="orgsearch_tasks",
    )
    await db.health_score_snapshots.create_index(
        [("trust_id", 1), ("created_at", -1)],
        name="orgsearch_health",
    )


@router.get("/orgs/{org_id}/trusts/search")
async def org_trusts_search(
    org_id: str,
    q: str = "",
    level: str = "all",           # all | preparer | viewer
    status: str = "all",          # all | attention | healthy
    client: str = "",             # owner_user_id
    deadline: str = "all",        # overdue | 7d | 30d | quarter | none | all
    sort: str = "pending_desc",   # pending_desc | deadline_asc | health_asc | name_asc | recently_active
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    # direct-async-invocation (tests) passes Query objects — coerce:
    page = int(page.default if hasattr(page, "default") else page)
    page_size = int(page_size.default if hasattr(page_size, "default") else page_size)
    """Search/filter the org's granted trusts — server-side, paginated.

    Same trust payload as GET /orgs/{org_id}/trusts plus health_score; adds
    q/level/status/client/deadline filters, sort, page/page_size + total.
    """
    memberships = await _my_memberships(user)
    member_ids = [
        m["member_id"] for m in memberships
        if m.get("status") == "active" and m.get("org_id") == org_id
    ]
    if not member_ids:
        # auth/membership BEFORE feature-toggle: unauthenticated/non-member
        # 403s must not leak route existence (tenant-isolation contract:
        # unauth probes return 401/403, never 404).
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    org = await db.orgs.find_one({"org_id": org_id}, {"_id": 0, "org_id": 1, "name": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org_name = org.get("name", "")

    try:
        await _ensure_indexes()
    except Exception:
        pass  # indexes are an optimization, never a read blocker

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    week = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    month_30 = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    month_92 = (datetime.now(timezone.utc) + timedelta(days=92)).strftime("%Y-%m-%d")

    # 1) grants (identical scoping to org_trusts)
    cursor = db.trust_grants.find(
        {
            "org_id": org_id,
            "member_id": {"$in": member_ids},
            "status": "active",
            "$or": [
                {"expires_at": {"$gte": today}},
                {"expires_at": {"$exists": False}},
                {"expires_at": None},
            ],
        },
        {"_id": 0, "trust_id": 1, "member_id": 1, "level": 1},
    )
    grants = []
    async for g in cursor:
        grants.append(g)
    if not grants:
        return {
            "org_id": org_id, "org_name": org_name, "trusts": [],
            "total": 0, "page": {"page": page, "page_size": page_size, "pages": 0},
        }
    level_by_trust: dict = {}
    trust_ids: list = []
    for g in grants:
        tid = g["trust_id"]
        if tid not in trust_ids:
            trust_ids.append(tid)
        if _level_rank(g.get("level", "viewer")) > _level_rank(level_by_trust.get(tid, "viewer")):
            level_by_trust[tid] = g.get("level", "viewer")

    # 2) trusts fetch
    tquery: dict = {"trust_id": {"$in": trust_ids}}
    if q:
        rx = {"$regex": _escape(q), "$options": "i"}
        tquery["$or"] = [
            {"name": rx}, {"trust_name": rx},
            {"grantor_name": rx}, {"trustee_full_name": rx},
        ]
    if client:
        tquery["user_id"] = client

    trust_rows = []
    async for t in db.trusts.find(tquery, {"_id": 0}):
        trust_rows.append(t)

    owner_ids = sorted({t.get("user_id") for t in trust_rows if t.get("user_id")})
    owner_map = {}
    if owner_ids:
        async for u in db.users.find(
            {"user_id": {"$in": owner_ids}},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1},
        ):
            owner_map[u["user_id"]] = u

    # 3) pending minutes + deadlines (batched, mirrors org_trusts)
    APPROVAL_OPEN = ("draft", "pending_review", "under_review", "changes_requested")
    ids_now = [t["trust_id"] for t in trust_rows]
    pending_by_trust: dict = {}
    if ids_now:
        async for row in db.meeting_minutes.aggregate([
            {"$match": {"trust_id": {"$in": ids_now}}},
            {"$lookup": {"from": "minutes_approval_status", "localField": "minutes_id", "foreignField": "minutes_id", "as": "_appr"}},
            {"$addFields": {"_st": {"$ifNull": [{"$arrayElemAt": ["$_appr.current_status", 0]}, "$status"]}}},
            {"$match": {"_st": {"$in": list(APPROVAL_OPEN)}}},
            {"$group": {"_id": "$trust_id", "n": {"$sum": 1}}},
        ]):
            pending_by_trust[row["_id"]] = row["n"]

    deadline_by_trust: dict = {}
    dl_match: dict = {
        "trust_id": {"$in": ids_now},
        "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}],
    }
    if deadline == "overdue":
        dl_match["due_date"] = {"$lt": today}
    elif deadline == "7d":
        dl_match["due_date"] = {"$gte": today, "$lte": week}
    elif deadline == "30d":
        dl_match["due_date"] = {"$gte": today, "$lte": month_30}
    elif deadline in ("all", "quarter", "none"):
        dl_match["due_date"] = {"$gte": today}  # forward-looking default
    if ids_now:
        async for row in db.governance_tasks.aggregate([
            {"$match": dl_match},
            {"$group": {"_id": "$trust_id", "earliest": {"$min": "$due_date"}}},
        ]):
            deadline_by_trust[row["_id"]] = row["earliest"]

    # 4) latest health snapshot per trust
    health_by_trust: dict = {}
    if ids_now:
        async for row in db.health_score_snapshots.aggregate([
            {"$match": {"trust_id": {"$in": ids_now}}},
            {"$sort": {"created_at": -1}},
            {"$group": {"_id": "$trust_id", "score": {"$first": "$score"}}},
        ]):
            health_by_trust[row["_id"]] = row["score"]

    # 5) assemble rows
    rows = []
    for t in trust_rows:
        tid = t["trust_id"]
        rows.append({
            "trust_id": tid,
            "name": t.get("name") or t.get("trust_name"),
            "owner_user_id": t.get("user_id"),
            "owner_name": (owner_map.get(t.get("user_id")) or {}).get("name"),
            "owner_email": (owner_map.get(t.get("user_id")) or {}).get("email"),
            "grantor_name": t.get("grantor_name"),
            "trustee_name": _trustee_display_name(t),
            "grant_level": level_by_trust.get(tid, "viewer"),
            "pending_minutes": pending_by_trust.get(tid, 0),
            "next_deadline": deadline_by_trust.get(tid),
            "health_score": health_by_trust.get(tid),
        })

    # 6) envelope-level filters
    if level != "all":
        rows = [r for r in rows if r["grant_level"] == level]

    def is_attention(r):
        if r["pending_minutes"] > 0:
            return True
        nd = r["next_deadline"]
        if nd and today <= nd[:10] <= week:
            return True
        hs = r.get("health_score")
        return hs is not None and hs < 60

    if status == "attention":
        rows = [r for r in rows if is_attention(r)]
    elif status == "healthy":
        rows = [r for r in rows if not is_attention(r)]

    if deadline == "none":
        rows = [r for r in rows if not r["next_deadline"]]
    elif deadline == "quarter":
        rows = [r for r in rows if r["next_deadline"] and today <= r["next_deadline"][:10] <= month_92]
    elif deadline == "overdue":
        # overdue bucket re-aggregates with $lt today (deadline_by_trust)
        rows = [r for r in rows if r["next_deadline"]]
    elif deadline in ("7d", "30d"):
        rows = [r for r in rows if r["next_deadline"]]

    # 7) sort
    if sort == "pending_desc":
        rows.sort(key=lambda r: (-r["pending_minutes"], r["next_deadline"] or "9999-12-31"))
    elif sort == "deadline_asc":
        rows.sort(key=lambda r: r["next_deadline"] or "9999-12-31", reverse=deadline == "overdue")
    elif sort == "health_asc":
        rows.sort(key=lambda r: r["health_score"] if r["health_score"] is not None else 999)
    elif sort == "name_asc":
        rows.sort(key=lambda r: (r["name"] or "").lower())
    elif sort == "recently_active":
        rows.sort(key=lambda r: r["trust_id"])

    # 8) paginate
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]
    pages = (total + page_size - 1) // page_size if total else 0
    return {
        "org_id": org_id, "org_name": org_name,
        "trusts": page_rows, "total": total,
        "page": {"page": page, "page_size": page_size, "pages": pages},
    }


def _escape(s: str) -> str:
    import re as _re
    return _re.escape(s)