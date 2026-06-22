# Calendar router — unified calendar events endpoint
# Aggregates governance tasks and tax calendar entries into a single feed
from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, date

from database import db
from dependencies import get_current_user

router = APIRouter(tags=["calendar"])


@router.get("/calendar/events")
async def get_calendar_events(
    trust_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Unified calendar events feed — aggregates governance tasks and tax calendar entries.
    Optional filters: trust_id, start_date (ISO), end_date (ISO).
    """
    events = []

    # Build governance tasks query
    task_query = {"user_id": user["user_id"]}
    if trust_id:
        task_query["trust_id"] = trust_id

    tasks = await db.governance_tasks.find(task_query, {"_id": 0}).to_list(10000)
    
    # Get trust names
    trust_ids = list(set(t.get("trust_id") for t in tasks if t.get("trust_id")))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100) if trust_ids else []
    trust_map = {t["trust_id"]: t["name"] for t in trusts}

    for task in tasks:
        due_date = task.get("due_date", "")
        if start_date and due_date < start_date:
            continue
        if end_date and due_date > end_date:
            continue
        events.append({
            "id": task.get("task_id", ""),
            "type": "governance_task",
            "title": task.get("task_type", "").replace("_", " ").title(),
            "date": due_date,
            "description": task.get("description", ""),
            "trust_id": task.get("trust_id"),
            "trust_name": trust_map.get(task.get("trust_id"), ""),
            "completed": bool(task.get("completed_at")),
            "status": "completed" if task.get("completed_at") else ("overdue" if due_date and due_date < date.today().isoformat() else "upcoming"),
        })

    # Build tax calendar query
    tax_query = {}
    if trust_id:
        tax_query["trust_id"] = trust_id

    # If filtering by date range, apply to tax calendar too
    tax_query_filter = dict(tax_query)
    if start_date:
        tax_query_filter.setdefault("due_date", {})
        if isinstance(tax_query_filter.get("due_date"), dict):
            tax_query_filter["due_date"]["$gte"] = start_date
    if end_date:
        tax_query_filter.setdefault("due_date", {})
        if isinstance(tax_query_filter.get("due_date"), dict):
            tax_query_filter["due_date"]["$lte"] = end_date

    tax_entries = await db.tax_calendar.find(tax_query_filter, {"_id": 0}).to_list(1000)
    
    for entry in tax_entries:
        events.append({
            "id": str(entry.get("_id", entry.get("entry_id", ""))),
            "type": "tax_deadline",
            "title": entry.get("form", "") or entry.get("title", "Tax Deadline"),
            "date": entry.get("due_date", ""),
            "description": entry.get("description", ""),
            "trust_id": entry.get("trust_id"),
            "trust_name": trust_map.get(entry.get("trust_id"), ""),
            "completed": entry.get("completed", False),
            "status": "completed" if entry.get("completed") else ("overdue" if entry.get("due_date", "") and entry["due_date"] < date.today().isoformat() else "upcoming"),
        })

    # Sort by date
    events.sort(key=lambda e: e.get("date", ""))

    return {"events": events, "count": len(events)}