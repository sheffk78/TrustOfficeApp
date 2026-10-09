"""Phase 1 — Advisor Oversight Dashboard + Org Review Queue (council 1).

- GET  /orgs/{org_id}/overview      : portfolio rollup (health, deadlines, pending) per granted trust + portfolio averages.
- GET  /org/queue                   : cross-trust worklist (overdue > due 7d > due 30d > low-health), all granted trusts.
- POST /org/queue/{task_ref}/complete : inline completion delegates to the per-trust completion logic (recurrence cascade
       fires unchanged); preparer-level grant required. Audit-provenance: org_queue.

All scoping server-side via the same grant-resolution pattern as routers/orgs.py.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from database import db

from .orgs import _toggle_institution, _level_rank, _trustee_display_name, _my_memberships

router = APIRouter(tags=["org-console"])

APPROVAL_OPEN = ("draft", "pending_review", "under_review", "changes_requested")


async def _pending_minutes_by_trust(tids):
    """Two-step pending-minutes count (works on mongomock AND real mongo):
    1) minutes_approval_status rows whose current_status is open -> minutes_ids
    2) match meeting_minutes by minutes_id in that set OR bare open status
    (replaces the $lookup aggregate routers/orgs.py uses, which mongomock
    cannot execute; semantics identical for our field conventions)."""
    if not tids:
        return {}
    open_ids = set()
    async for s in db.minutes_approval_status.find(
        {"current_status": {"$in": list(APPROVAL_OPEN)}}, {"_id": 0, "minutes_id": 1}
    ):
        if s.get("minutes_id"):
            open_ids.add(s["minutes_id"])
    out: dict = {}
    match = {"$or": [{"minutes_id": {"$in": list(open_ids)}}] if open_ids else []}
    match["$or"].append({"status": {"$in": list(APPROVAL_OPEN)}})
    async for row in db.meeting_minutes.aggregate([
        {"$match": {"$and": [{"trust_id": {"$in": tids}}, match]}},
        {"$group": {"_id": "$trust_id", "n": {"$sum": 1}}},
    ]):
        out[row["_id"]] = row["n"]
    return out


def _dates(now: Optional[datetime] = None):
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    week = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    month = (now + timedelta(days=30)).strftime("%Y-%m-%d")
    return today, week, month


async def _granted_trusts(org_id: str, user: dict):
    member_ids = [
        m["member_id"] for m in await _my_memberships(user)
        if m.get("status") == "active" and m.get("org_id") == org_id
    ]
    if not member_ids:
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    grants = []
    async for g in db.trust_grants.find(
        {
            "org_id": org_id, "member_id": {"$in": member_ids}, "status": "active",
            "$or": [{"expires_at": {"$gte": _dates()[0]}}, {"expires_at": {"$exists": False}}, {"expires_at": None}],
        },
        {"_id": 0, "trust_id": 1, "member_id": 1, "level": 1},
    ):
        grants.append(g)
    level_by_trust: dict = {}
    tids: list = []
    for g in grants:
        tid = g["trust_id"]
        if tid not in tids:
            tids.append(tid)
        if _level_rank(g.get("level", "viewer")) > _level_rank(level_by_trust.get(tid, "viewer")):
            level_by_trust[tid] = g.get("level", "viewer")
    return tids, level_by_trust, member_ids


async def _overview_rows(tids, level_by_trust, today, week):
    if not tids:
        return []
    trust_map = {}
    async for t in db.trusts.find({"trust_id": {"$in": tids}}, {"_id": 0}):
        trust_map[t["trust_id"]] = t
    pending_by_trust = await _pending_minutes_by_trust(tids)
    overdue: dict = {}
    upcoming: dict = {}
    async for row in db.governance_tasks.aggregate([
        {"$match": {"trust_id": {"$in": tids}, "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}], "due_date": {"$lt": today}}},
        {"$group": {"_id": "$trust_id", "n": {"$sum": 1}}},
    ]):
        overdue[row["_id"]] = row["n"]
    quarter_end = (datetime.now(timezone.utc) + timedelta(days=92)).strftime("%Y-%m-%d")
    async for row in db.governance_tasks.aggregate([
        {"$match": {"trust_id": {"$in": tids}, "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}], "due_date": {"$gte": today, "$lte": quarter_end}}},
        {"$group": {"_id": "$trust_id", "earliest": {"$min": "$due_date"}}},
    ]):
        upcoming[row["_id"]] = row["earliest"]
    health: dict = {}
    async for row in db.health_score_snapshots.aggregate([
        {"$match": {"trust_id": {"$in": tids}}},
        {"$sort": {"created_at": -1}},
        {"$group": {"_id": "$trust_id", "score": {"$first": "$score"}}},
    ]):
        health[row["_id"]] = row["score"]

    rows = []
    for tid in tids:
        t = trust_map.get(tid) or {}
        hs = health.get(tid)
        if hs is None:
            chip = "unknown"
        elif hs >= 80:
            chip = "excellent"
        elif hs >= 60:
            chip = "watch"
        else:
            chip = "at-risk"
        rows.append({
            "trust_id": tid,
            "name": t.get("name") or t.get("trust_name"),
            "grant_level": level_by_trust.get(tid, "viewer"),
            "health_score": hs,
            "health_chip": chip,
            "pending_minutes": pending_by_trust.get(tid, 0),
            "overdue_count": overdue.get(tid, 0),
            "next_deadline": upcoming.get(tid),
        })
    return rows


@router.get("/orgs/{org_id}/overview")
async def org_overview(org_id: str, user: dict = Depends(get_current_user)):
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    today, week, month = _dates()
    tids, level_by_trust, _ = await _granted_trusts(org_id, user)
    rows = await _overview_rows(tids, level_by_trust, today, week)
    scores = [r["health_score"] for r in rows if r["health_score"] is not None]
    portfolio = {
        "trust_count": len(rows),
        "average_health": round(sum(scores) / len(scores), 1) if scores else None,
        "at_risk": sum(1 for r in rows if r["health_chip"] == "at-risk"),
        "overdue_total": sum(r["overdue_count"] for r in rows),
        "pending_minutes_total": sum(r["pending_minutes"] for r in rows),
        "due_week": sum(1 for r in rows if r["next_deadline"] and today <= r["next_deadline"][:10] <= week),
    }
    return {"org_id": org_id, "portfolio": portfolio, "trusts": rows}


@router.get("/org/queue")
async def org_queue(
    org_id: str,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """Cross-trust governance worklist: open recurring tasks + overdue deadlines
    + low-health criteria across every granted trust of the member's orgs."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    today, week, month = _dates()
    # queue spans ALL orgs the member belongs to (advisor works the whole book)
    memberships = await _my_memberships(user)
    org_ids = [m["org_id"] for m in memberships if m.get("status") == "active"]
    if not org_ids:
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    _, level_by_trust_all, member_ids_all = [], {}, []
    tids: list = []
    level_by_trust: dict = {}
    for oid in org_ids:
        t2, l2, m2 = await _granted_trusts(oid, user)
        for t in t2:
            if t not in tids:
                tids.append(t)
            if _level_rank(l2.get(t, "viewer")) > _level_rank(level_by_trust.get(t, "viewer")):
                level_by_trust[t] = l2.get(t, "viewer")
    items = []
    if tids:
        async for row in db.governance_tasks.aggregate([
            {"$match": {"trust_id": {"$in": tids}, "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}]}},
            {"$addFields": {"_bucket": {
                "$cond": [{"$lt": ["$due_date", today]}, 0,
                {"$cond": [{"$lte": ["$due_date", week]}, 1,
                {"$cond": [{"$lte": ["$due_date", month]}, 2, 3]}]}]},
            }},
            {"$sort": {"_bucket": 1, "due_date": 1, "created_at": 1}},
            {"$limit": max(1, min(int(limit or 50), 100))},
        ]):
            items.append({
                "task_id": row.get("task_id"),
                "trust_id": row.get("trust_id"),
                "task_type": row.get("task_type"),
                "title": row.get("description") or (row.get("task_type") or "").replace("_", " ").title(),
                "due_date": row.get("due_date"),
                "urgency": {0: "overdue", 1: "due_week", 2: "due_month", 3: "later"}.get(row.get("_bucket"), "later"),
                "grant_level": level_by_trust.get(row.get("trust_id"), "viewer"),
            })
        # enrich with trust names
        tmap = {}
        async for t in db.trusts.find({"trust_id": {"$in": [i["trust_id"] for i in items]}}, {"_id": 0, "trust_id": 1, "name": 1}):
            tmap[t["trust_id"]] = t.get("name")
        for i in items:
            i["trust_name"] = tmap.get(i["trust_id"])
    counts = {
        "overdue": sum(1 for i in items if i["urgency"] == "overdue"),
        "due_week": sum(1 for i in items if i["urgency"] == "due_week"),
        "later": sum(1 for i in items if i["urgency"] in ("due_month", "later")),
    }
    return {"items": items, "counts": counts}


@router.post("/org/queue/{task_id}/complete")
async def org_queue_complete(task_id: str, user: dict = Depends(get_current_user)):
    """Inline completion from the queue — ON BEHALF OF the trust owner.

    Replicates the per-trust completion core (complete_task in routers/tasks.py):
    sets completed_at, then spawns the next recurring cycle with the same
    dedupe guard (annual 365 / quarterly 90 / compensation 180 / revaluation 365)
    and checklist template. Provenance is explicit, never impersonation:
    completed_via=org_queue + on_behalf attribution recorded on the task AND in
    org_activity. Requires a preparer-level grant on the task's trust.
    """
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    task = await db.governance_tasks.find_one({"task_id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    member_ids = [
        m["member_id"] for m in await _my_memberships(user)
        if m.get("status") == "active"
    ]
    if not member_ids:
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    grant = await db.trust_grants.find_one({
        "trust_id": task["trust_id"], "member_id": {"$in": member_ids},
        "status": "active",
    })
    if not grant or _level_rank(grant.get("level", "viewer")) < _level_rank("preparer"):
        raise HTTPException(status_code=403, detail={"code": "preparer_required"})
    if task.get("completed_at"):
        return {"task_id": task_id, "status": "already_completed", "completed_via": "org_queue"}

    import uuid
    from routers.tasks import CHECKLIST_TEMPLATES
    completed_at = datetime.now(timezone.utc).isoformat()
    await db.governance_tasks.update_one(
        {"task_id": task_id},
        {"$set": {
            "completed_at": completed_at,
            "completed_via": "org_queue",
            "completed_by_member_id": member_ids[0],
        }},
    )
    # next recurring cycle (same core as routers/tasks.complete_task)
    RECURRING_TASK_TYPES = {
        "annual_review": 365,
        "quarterly_review": 90,
        "compensation_review": 180,
        "asset_revaluation": 365,
    }
    task_type = task.get("task_type")
    next_cycle = None
    if task_type in RECURRING_TASK_TYPES:
        cycle_days = RECURRING_TASK_TYPES[task_type]
        original_due = task.get("due_date")
        if original_due:
            try:
                orig_due_dt = datetime.fromisoformat(original_due.replace("Z", "+00:00"))
                next_due = (orig_due_dt + timedelta(days=cycle_days)).isoformat()
            except (ValueError, TypeError):
                next_due = (datetime.now(timezone.utc) + timedelta(days=cycle_days)).isoformat()
        else:
            next_due = (datetime.now(timezone.utc) + timedelta(days=cycle_days)).isoformat()
        existing_future = await db.governance_tasks.count_documents({
            "trust_id": task["trust_id"],
            "task_type": task_type,
            "completed_at": None,
            "due_date": {"$gte": next_due},
        })
        if existing_future == 0:
            new_task_id = f"task_{uuid.uuid4().hex[:12]}"
            next_cycle = {
                "task_id": new_task_id,
                "trust_id": task["trust_id"],
                "user_id": task.get("user_id"),
                "task_type": task_type,
                "due_date": next_due,
                "completed_at": None,
                "description": task.get("description", ""),
                "checklist_items": [item.copy() for item in CHECKLIST_TEMPLATES.get(task_type, [])],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_via": "org_queue_recurrence",
            }
            await db.governance_tasks.insert_one(next_cycle)
    # on-behalf attribution in org activity (orgs feed)
    org_id = grant.get("org_id")
    # (org activity write is additive-best-effort; failures never block completion)
    try:
        await db.org_activity.insert_one({
            "org_id": org_id,
            "action": "queue_task_completed",
            "member_id": member_ids[0],
            "member_name": user.get("name"),
            "trust_id": task.get("trust_id"),
            "detail": f"Completed {task_type or 'task'} on behalf of the owner",
            "created_at": completed_at,
        })
    except Exception:
        pass
    return {
        "task_id": task_id, "status": "completed", "completed_via": "org_queue",
        "next_cycle_task_id": next_cycle["task_id"] if next_cycle else None,
    }


@router.get("/orgs/{org_id}/calendar")
async def org_firm_calendar(
    org_id: str,
    user: dict = Depends(get_current_user),
):
    """Firm-wide governance calendar: every granted trust's upcoming tasks,
    week-bucketed (week_start), automation provenance exposed
    (created_via == recurring_automation -> automated:true)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    today, week, month = _dates()
    tids, level_by_trust, _ = await _granted_trusts(org_id, user)
    if not tids:
        return {"org_id": org_id, "weeks": [], "counts": {"total": 0}}
    quarter_end = (datetime.now(timezone.utc) + timedelta(days=92)).strftime("%Y-%m-%d")
    tmap = {}
    async for t in db.trusts.find({"trust_id": {"$in": tids}}, {"_id": 0, "trust_id": 1, "name": 1}):
        tmap[t["trust_id"]] = t.get("name")
    events = []
    async for row in db.governance_tasks.aggregate([
        {"$match": {
            "trust_id": {"$in": tids},
            "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}],
            "due_date": {"$gte": today, "$lte": quarter_end},
        }},
        {"$sort": {"due_date": 1}},
        {"$limit": 500},
    ]):
        events.append(row)
    # week bucket (ISO)
    weeks: dict = {}
    for ev in events:
        try:
            d = datetime.fromisoformat(str(ev["due_date"]).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        iso_y, iso_w, _ = d.isocalendar()
        key = f"{iso_y}-W{iso_w:02d}"
        weeks.setdefault(key, []).append({
            "task_id": ev.get("task_id"),
            "trust_id": ev.get("trust_id"),
            "trust_name": tmap.get(ev.get("trust_id")),
            "task_type": ev.get("task_type"),
            "title": ev.get("description") or (ev.get("task_type") or "").replace("_", " ").title(),
            "due_date": ev.get("due_date"),
            "automated": ev.get("created_via") == "recurring_automation",
        })
    out = [{"week": k, "items": v} for k, v in sorted(weeks.items())]
    return {"org_id": org_id, "weeks": out, "counts": {"total": len(events)}}
