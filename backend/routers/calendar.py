# Calendar router — unified calendar events endpoint
# Aggregates governance tasks, tax calendar entries, Money section events
# (distributions, compensation payments, investments), and Structure section
# events (entity formations, Schedule A conveyances, communications) into a
# single feed.
from fastapi import APIRouter, Depends
from typing import Optional
from datetime import datetime, date

from database import db
from dependencies import get_current_user
from utils.tax_calendar_math import _days_remaining

router = APIRouter(tags=["calendar"])

# Governance task types that overlap with auto-generated tax calendar entries.
# When a governance task of one of these types has a matching tax calendar entry
# (same trust, same tax_year, matching deadline_type), the governance task is
# skipped in the unified feed in favor of the richer tax calendar entry.
_TAX_OVERLAP_TASK_TYPES = {
    "tax_filing_1041": "federal_1041",
    "tax_filing_k1": "k1_beneficiaries",
}


def _status_from_date(event_date: str) -> str:
    """Derive a simple upcoming/completed status from a date.

    Past events are treated as 'completed' (they happened).
    Today and future events are 'upcoming'.
    """
    if not event_date:
        return "upcoming"
    try:
        d = event_date[:10]
        if d < date.today().isoformat():
            return "completed"
    except Exception:
        pass
    return "upcoming"


def _safe_date(raw: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    """Return a clean YYYY-MM-DD date or None."""
    if raw and len(raw) >= 10:
        return raw[:10]
    return fallback[:10] if fallback and len(fallback) >= 10 else None


@router.get("/calendar/events")
async def get_calendar_events(
    trust_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Unified calendar events feed — aggregates governance tasks and tax calendar entries.
    Optional filters: trust_id, start_date (ISO), end_date (ISO).

    Every event has:
      - event_type: "governance_task" | "tax_deadline"
      - days_remaining: int (negative = overdue)
      - status: "upcoming" | "overdue" | "completed"

    Tax deadline events additionally carry: filing_status, deadline_type,
    accountant_engaged, notes, tax_year, is_fiscal_year, entry_id.
    """
    events = []

    # ------------------------------------------------------------------
    # 1. Fetch tax calendar entries first (needed for dedup of governance tasks)
    # ------------------------------------------------------------------
    tax_query = {}
    if trust_id:
        tax_query["trust_id"] = trust_id

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

    # Build a set of (trust_id, tax_year, deadline_type) for dedup lookup
    tax_dedup_keys = set()
    tax_events = []

    # We need trust info for fiscal-year awareness on tax entries
    tax_trust_ids = list(set(e.get("trust_id") for e in tax_entries if e.get("trust_id")))
    tax_trusts = (
        await db.trusts.find({"trust_id": {"$in": tax_trust_ids}}, {"_id": 0}).to_list(100)
        if tax_trust_ids
        else []
    )
    tax_trust_map = {t["trust_id"]: t for t in tax_trusts}

    for entry in tax_entries:
        t_id = entry.get("trust_id")
        t_year = entry.get("tax_year")
        d_type = entry.get("deadline_type")

        if t_id and t_year and d_type:
            tax_dedup_keys.add((t_id, t_year, d_type))

        due_date = entry.get("due_date", "")
        filing_status = entry.get("filing_status", "pending")
        is_completed = filing_status in ("filed", "not_required")
        dr = _days_remaining(due_date) if due_date else 999

        # Derive status from filing_status + date
        if is_completed:
            status = "completed"
        elif due_date and due_date < date.today().isoformat():
            status = "overdue"
        else:
            status = "upcoming"

        trust_doc = tax_trust_map.get(t_id, {})
        is_fiscal = trust_doc.get("is_fiscal_year") is True

        tax_events.append({
            "id": entry.get("entry_id", str(entry.get("_id", ""))),
            "entry_id": entry.get("entry_id", ""),
            "event_type": "tax_deadline",
            "type": "tax_deadline",  # backward compat
            "title": entry.get("form", "") or entry.get("title", "Tax Deadline"),
            "date": due_date,
            "description": entry.get("description", ""),
            "trust_id": t_id,
            "trust_name": trust_doc.get("name", ""),
            "completed": is_completed,
            "status": status,
            "days_remaining": dr,
            # Tax-specific metadata
            "filing_status": filing_status,
            "deadline_type": d_type,
            "accountant_engaged": entry.get("accountant_engaged", False),
            "notes": entry.get("notes"),
            "tax_year": t_year,
            "is_fiscal_year": is_fiscal,
            "filed_date": entry.get("filed_date"),
        })

    # ------------------------------------------------------------------
    # 2. Fetch governance tasks (skip dedup-overlapped ones)
    # ------------------------------------------------------------------
    task_query = {"user_id": user["user_id"]}
    if trust_id:
        task_query["trust_id"] = trust_id

    tasks = await db.governance_tasks.find(task_query, {"_id": 0}).to_list(10000)

    # Get trust names for governance tasks
    trust_ids = list(set(t.get("trust_id") for t in tasks if t.get("trust_id")))
    trusts = (
        await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
        if trust_ids
        else []
    )
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    # Merge into tax_trust_map so governance events also get fiscal-year info if needed
    for t in trusts:
        if t["trust_id"] not in tax_trust_map:
            tax_trust_map[t["trust_id"]] = t

    for task in tasks:
        due_date = task.get("due_date", "")
        if start_date and due_date < start_date:
            continue
        if end_date and due_date > end_date:
            continue

        # Dedup: skip governance tasks that duplicate a tax calendar entry
        task_type = task.get("task_type", "")
        if task_type in _TAX_OVERLAP_TASK_TYPES:
            matching_deadline_type = _TAX_OVERLAP_TASK_TYPES[task_type]
            # Derive tax_year from the due_date year
            try:
                task_tax_year = int(due_date[:4]) if due_date else None
            except (ValueError, TypeError):
                task_tax_year = None

            t_id = task.get("trust_id")
            if t_id and task_tax_year:
                # Exact year match: always dedup
                if (t_id, task_tax_year, matching_deadline_type) in tax_dedup_keys:
                    continue
                # Adjacent year: only for fiscal-year trusts (date math may shift the calendar year)
                trust_doc = tax_trust_map.get(t_id, {})
                if trust_doc.get("is_fiscal_year") is True:
                    if (t_id, task_tax_year - 1, matching_deadline_type) in tax_dedup_keys:
                        continue
                    if (t_id, task_tax_year + 1, matching_deadline_type) in tax_dedup_keys:
                        continue

        # Compute days_remaining for governance events
        dr = _days_remaining(due_date) if due_date else 999

        is_completed = bool(task.get("completed_at"))
        if is_completed:
            status = "completed"
        elif due_date and due_date < date.today().isoformat():
            status = "overdue"
        else:
            status = "upcoming"

        events.append({
            "id": task.get("task_id", ""),
            "event_type": "governance_task",
            "type": "governance_task",  # backward compat
            "title": task_type.replace("_", " ").title(),
            "date": due_date,
            "description": task.get("description", ""),
            "trust_id": task.get("trust_id"),
            "trust_name": trust_map.get(task.get("trust_id"), ""),
            "completed": is_completed,
            "status": status,
            "days_remaining": dr,
            # Governance-specific metadata
            "task_type": task_type,
            "completed_at": task.get("completed_at"),
            "checklist": task.get("checklist"),
        })

    # ------------------------------------------------------------------
    # 3. Money section events — distributions, compensation, investments
    # ------------------------------------------------------------------
    money_query = {"user_id": user["user_id"]}
    if trust_id:
        money_query["trust_id"] = trust_id

    # 3a. Distributions
    distributions = await db.distribution_records.find(money_query, {"_id": 0}).to_list(1000)
    for dist in distributions:
        d_date = _safe_date(dist.get("date"), dist.get("created_at"))
        if not d_date:
            continue
        beneficiary = dist.get("beneficiary_name") or "Beneficiary"
        amount = dist.get("amount")
        title = f"Distribution to {beneficiary}"
        if amount is not None:
            try:
                title += f": ${float(amount):,.2f}"
            except (ValueError, TypeError):
                pass
        events.append({
            "id": dist.get("distribution_id", ""),
            "event_type": "distribution",
            "type": "distribution",
            "title": title,
            "date": d_date,
            "description": dist.get("notes") or "",
            "trust_id": dist.get("trust_id"),
            "completed": True,
            "status": _status_from_date(d_date),
            "days_remaining": _days_remaining(d_date),
            "link": "/distributions",
            "category": "money",
        })

    # 3b. Compensation payments
    comp_payments = await db.compensation_payments.find(money_query, {"_id": 0}).to_list(1000)
    for pmt in comp_payments:
        p_date = _safe_date(pmt.get("date"), pmt.get("created_at"))
        if not p_date:
            continue
        amount = pmt.get("amount")
        trustee = pmt.get("trustee_name") or ""
        title = "Compensation Payment"
        if trustee:
            title += f": {trustee}"
        if amount is not None:
            try:
                title += f" — ${float(amount):,.2f}"
            except (ValueError, TypeError):
                pass
        events.append({
            "id": pmt.get("payment_id", ""),
            "event_type": "compensation_payment",
            "type": "compensation_payment",
            "title": title,
            "date": p_date,
            "description": pmt.get("classification_text") or "",
            "trust_id": pmt.get("trust_id"),
            "completed": True,
            "status": _status_from_date(p_date),
            "days_remaining": _days_remaining(p_date),
            "link": "/compensation",
            "category": "money",
        })

    # 3c. Investments
    investments = await db.investments.find({**money_query, "is_active": True}, {"_id": 0}).to_list(1000)
    for inv in investments:
        i_date = _safe_date(inv.get("purchase_date"), inv.get("created_at"))
        if not i_date:
            continue
        asset_name = inv.get("asset_name") or "Investment"
        title = f"Investment Purchased: {asset_name}"
        events.append({
            "id": inv.get("investment_id", ""),
            "event_type": "investment",
            "type": "investment",
            "title": title,
            "date": i_date,
            "description": inv.get("asset_type") or "",
            "trust_id": inv.get("trust_id"),
            "completed": True,
            "status": _status_from_date(i_date),
            "days_remaining": _days_remaining(i_date),
            "link": "/investments",
            "category": "money",
        })

    # ------------------------------------------------------------------
    # 4. Structure section events — entities, Schedule A, communications
    # ------------------------------------------------------------------
    structure_query = {"user_id": user["user_id"]}
    if trust_id:
        structure_query["trust_id"] = trust_id

    # 4a. Entity formation dates
    entities = await db.entities.find(structure_query, {"_id": 0}).to_list(1000)
    for ent in entities:
        e_date = _safe_date(ent.get("formation_date"))
        if not e_date:
            continue
        name = ent.get("name") or ent.get("legal_name") or "Entity"
        title = f"Entity Formed: {name}"
        events.append({
            "id": ent.get("entity_id", ""),
            "event_type": "entity_formation",
            "type": "entity_formation",
            "title": title,
            "date": e_date,
            "description": ent.get("entity_type") or "",
            "trust_id": ent.get("trust_id"),
            "completed": True,
            "status": _status_from_date(e_date),
            "days_remaining": _days_remaining(e_date),
            "link": "/structures",
            "category": "structure",
        })

    # 4b. Schedule A conveyance dates
    schedule_a_items = await db.schedule_a_items.find(structure_query, {"_id": 0}).to_list(1000)
    for item in schedule_a_items:
        s_date = _safe_date(item.get("date_conveyed"))
        if not s_date:
            continue
        desc = item.get("description") or "Asset"
        title = f"Asset Conveyed: {desc}"
        events.append({
            "id": item.get("item_id", ""),
            "event_type": "schedule_a_conveyance",
            "type": "schedule_a_conveyance",
            "title": title,
            "date": s_date,
            "description": item.get("category") or "",
            "trust_id": item.get("trust_id"),
            "completed": True,
            "status": _status_from_date(s_date),
            "days_remaining": _days_remaining(s_date),
            "link": "/schedule-a",
            "category": "structure",
        })

    # 4c. Communication dates
    communications = await db.communications.find(structure_query, {"_id": 0}).to_list(1000)
    for comm in communications:
        c_date = _safe_date(comm.get("created_at"))
        if not c_date:
            continue
        subject = comm.get("subject") or comm.get("comm_type_label") or "Communication"
        title = f"Communication: {subject}"
        events.append({
            "id": comm.get("comm_id", ""),
            "event_type": "communication",
            "type": "communication",
            "title": title,
            "date": c_date,
            "description": comm.get("comm_type_label") or "",
            "trust_id": comm.get("trust_id"),
            "completed": True,
            "status": _status_from_date(c_date),
            "days_remaining": _days_remaining(c_date),
            "link": "/communications",
            "category": "structure",
        })

    # ------------------------------------------------------------------
    # 5. Merge + sort
    # ------------------------------------------------------------------
    events.extend(tax_events)
    events.sort(key=lambda e: e.get("date") or "")

    return {"events": events, "count": len(events)}