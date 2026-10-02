"""Phase 2 — real recurring-task automation (council #2).

Materializes the NEXT cycle of completed recurring governance tasks ~30 days
ahead, so 'Recurring task automation' is a visible engine, not a hidden
post-completion cascade. Idempotent (dedupe on trust+type+due), stamps
provenance created_via='recurring_automation', honors the same cycles as
routers/tasks.complete_task. Manual trigger endpoint for verification.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import dependencies as _deps

CYCLES = {
    "annual_review": 365,
    "quarterly_review": 90,
    "compensation_review": 180,
    "asset_revaluation": 365,
}
LOOKAHEAD_DAYS = 30


async def materialize_recurring(db, dry_run: bool = False, max_create: int = 500):
    """One pass: for each completed recurring task with no uncompleted successor
    in the book, create the next open instance dated due + cycle, when its due
    date lands within the look-ahead window."""
    today = datetime.now(timezone.utc)
    window_end = (today + timedelta(days=LOOKAHEAD_DAYS)).strftime("%Y-%m-%d")
    created = []
    async for task in db.governance_tasks.find({
        "task_type": {"$in": list(CYCLES.keys())},
        "completed_at": {"$ne": None},
        "materialized": {"$ne": True},   # one materialization per completed task
    }, {"_id": 0, "task_id": 1, "trust_id": 1, "user_id": 1, "task_type": 1,
        "due_date": 1, "description": 1, "checklist_items": 1, "created_at": 1}):
        if len(created) >= max_create:
            break
        task_type = task.get("task_type")
        cycle_days = CYCLES.get(task_type)
        due = task.get("due_date")
        if not cycle_days or not due:
            continue
        try:
            orig = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        # next open instance due-date == orig + cycle (string form preserved)
        nxt = (orig + timedelta(days=cycle_days)).strftime("%Y-%m-%d")
        if nxt > window_end:
            # not yet in the visible window — leave for a later pass
            continue
        exists = await db.governance_tasks.count_documents({
            "trust_id": task["trust_id"],
            "task_type": task_type,
            "completed_at": None,
            "due_date": {"$gte": nxt},
        })
        if exists:
            await db.governance_tasks.update_one(
                {"task_id": task["task_id"]}, {"$set": {"materialized": True, "materialized_note": "successor_exists"}}
            )
            continue
        import uuid
        new_task = {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": task["trust_id"],
            "user_id": task.get("user_id"),
            "task_type": task_type,
            "due_date": nxt,
            "completed_at": None,
            "description": task.get("description", ""),
            "checklist_items": [dict(i) for i in (task.get("checklist_items") or [])],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_via": "recurring_automation",
            "recurring_from": task["task_id"],
        }
        if not dry_run:
            await db.governance_tasks.insert_one(new_task)
            await db.governance_tasks.update_one(
                {"task_id": task["task_id"]}, {"$set": {"materialized": True, "materialized_note": "created"}}
            )
        created.append({"task_id": task["task_id"], "new_task_id": new_task["task_id"],
                        "trust_id": task["trust_id"], "next_due": nxt})
    return {"created": created, "dry_run": dry_run, "window_end": window_end}


async def scheduled_recurring_pass(db):
    """Daily scheduler entry (idempotent — safe to run repeatedly)."""
    return await materialize_recurring(db, dry_run=False)


def register_recurring_job(scheduler):
    """Wire into the background_tasks scheduler (AsyncIOScheduler)."""
    from apscheduler.triggers.cron import CronTrigger
    from database import db
    scheduler.add_job(
        scheduled_recurring_pass,
        CronTrigger(hour=3, minute=45),
        args=[db],
        id="recurring_task_materialization",
        replace_existing=True,
    )
