# Calendar router — unified calendar events endpoint
# Aggregates governance tasks, tax calendar entries, Money section events
# (distributions, compensation payments, investments), and Structure section
# events (entity formations, Schedule A conveyances, communications) into a
# single feed.
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime, date

from database import db
from dependencies import get_current_user
from utils.tax_calendar_math import _days_remaining, filter_income_tax_entries as _filter_exempt_tax

# Income-tax deadline types, mirrored for exempt-trust filtering in the feed.
_INCOME_TAX_TYPES = {
    "federal_1041", "federal_1041_extension", "k1_beneficiaries",
    "estimated_q1", "estimated_q2", "estimated_q3", "estimated_q4",
}

router = APIRouter(tags=["calendar"])

# Governance task types that overlap with auto-generated tax calendar entries.
# When a governance task of one of these types has a matching tax calendar entry
# (same trust, same tax_year, matching deadline_type), the governance task is
# skipped in the unified feed in favor of the richer tax calendar entry.
_TAX_OVERLAP_TASK_TYPES = {
    "tax_filing_1041": "federal_1041",
    "tax_filing_k1": "k1_beneficiaries",
}


def _safe_date(raw: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    """Return a clean YYYY-MM-DD date or None."""
    if raw and len(raw) >= 10:
        return raw[:10]
    return fallback[:10] if fallback and len(fallback) >= 10 else None


def _event_status(due_date: str, is_completed: bool) -> str:
    """Derive event status from due_date and completion flag."""
    if is_completed:
        return "completed"
    if due_date and due_date < date.today().isoformat():
        return "overdue"
    return "upcoming"


def _parse_tax_year(due_date: str) -> Optional[int]:
    """Extract a tax year from a due_date string, returning None on failure."""
    try:
        return int(due_date[:4]) if due_date else None
    except (ValueError, TypeError):
        return None


def _is_task_duplicated_by_tax_entry(
    task_type: str,
    trust_id: str,
    due_date: str,
    tax_dedup_keys: set,
    tax_trust_map: dict,
) -> bool:
    """Check if a governance task is duplicated by an existing tax calendar entry."""
    if task_type not in _TAX_OVERLAP_TASK_TYPES:
        return False

    matching_deadline_type = _TAX_OVERLAP_TASK_TYPES[task_type]
    task_tax_year = _parse_tax_year(due_date)

    if not trust_id or not task_tax_year:
        return False

    # Exact year match: always dedup
    if (trust_id, task_tax_year, matching_deadline_type) in tax_dedup_keys:
        return True

    # Adjacent year: only for fiscal-year trusts
    trust_doc = tax_trust_map.get(trust_id, {})
    if trust_doc.get("is_fiscal_year") is True:
        if (trust_id, task_tax_year - 1, matching_deadline_type) in tax_dedup_keys:
            return True
        if (trust_id, task_tax_year + 1, matching_deadline_type) in tax_dedup_keys:
            return True

    return False


def _passes_date_filter(due_date: str, start_date: Optional[str], end_date: Optional[str]) -> bool:
    """Check if a due_date passes the optional start/end date filters."""
    if start_date and due_date < start_date:
        return False
    if end_date and due_date > end_date:
        return False
    return True


def _build_money_query(user_id: str, trust_id: Optional[str]) -> dict:
    """Build the base query for money-section events, scoped to user (and optionally trust)."""
    query = {"user_id": user_id}
    if trust_id:
        query["trust_id"] = trust_id
    return query


def _build_tax_query_filter(tax_query: dict, start_date: Optional[str], end_date: Optional[str]) -> dict:
    """Apply optional date filters to the tax query."""
    tax_query_filter = dict(tax_query)
    if start_date:
        tax_query_filter.setdefault("due_date", {})
        if isinstance(tax_query_filter.get("due_date"), dict):
            tax_query_filter["due_date"]["$gte"] = start_date
    if end_date:
        tax_query_filter.setdefault("due_date", {})
        if isinstance(tax_query_filter.get("due_date"), dict):
            tax_query_filter["due_date"]["$lte"] = end_date
    return tax_query_filter


async def _validate_trust_ownership(trust_id: str, user_id: str):
    """Validate trust belongs to user, raising 404 if not found."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")


async def _build_tax_query(trust_id: Optional[str], user_id: str) -> dict:
    """Build the tax calendar query, scoped to user's trusts."""
    tax_query = {}
    if trust_id:
        tax_query["trust_id"] = trust_id
    else:
        user_trust_ids = await db.trusts.distinct("trust_id", {"user_id": user_id})
        tax_query["trust_id"] = {"$in": user_trust_ids}
    return tax_query


async def _fetch_tax_trust_map(tax_entries: list) -> dict:
    """Fetch trust documents for the trusts referenced in tax entries."""
    tax_trust_ids = list(set(e.get("trust_id") for e in tax_entries if e.get("trust_id")))
    tax_trusts = (
        await db.trusts.find({"trust_id": {"$in": tax_trust_ids}}, {"_id": 0}).to_list(100)
        if tax_trust_ids
        else []
    )
    return {t.get("trust_id"): t for t in tax_trusts if t.get("trust_id")}


def _build_tax_event(entry: dict, trust_doc: dict) -> dict:
    """Convert a tax calendar entry into a calendar event dict."""
    t_id = entry.get("trust_id")
    t_year = entry.get("tax_year")
    d_type = entry.get("deadline_type")
    due_date = entry.get("due_date", "")
    filing_status = entry.get("filing_status", "pending")
    is_completed = filing_status in ("filed", "not_required")
    dr = _days_remaining(due_date) if due_date else 999

    return {
        "id": entry.get("entry_id", str(entry.get("_id", ""))),
        "entry_id": entry.get("entry_id", ""),
        "event_type": "tax_deadline",
        "type": "tax_deadline",
        "title": entry.get("form", "") or entry.get("title", "Tax Deadline"),
        "date": due_date,
        "description": entry.get("description", ""),
        "trust_id": t_id,
        "trust_name": trust_doc.get("name", ""),
        "completed": is_completed,
        "status": _event_status(due_date, is_completed),
        "days_remaining": dr,
        "filing_status": filing_status,
        "deadline_type": d_type,
        "accountant_engaged": entry.get("accountant_engaged", False),
        "notes": entry.get("notes"),
        "tax_year": t_year,
        "is_fiscal_year": trust_doc.get("is_fiscal_year") is True,
        "filed_date": entry.get("filed_date"),
    }


async def _build_tax_events(tax_entries: list) -> tuple:
    """Process tax entries into events and return (tax_events, tax_dedup_keys, tax_trust_map)."""
    tax_trust_map = await _fetch_tax_trust_map(tax_entries)
    tax_dedup_keys = set()
    tax_events = []

    for entry in tax_entries:
        t_id = entry.get("trust_id")
        t_year = entry.get("tax_year")
        d_type = entry.get("deadline_type")
        if t_id and t_year and d_type:
            tax_dedup_keys.add((t_id, t_year, d_type))
        trust_doc = tax_trust_map.get(t_id, {})
        tax_events.append(_build_tax_event(entry, trust_doc))

    return tax_events, tax_dedup_keys, tax_trust_map


def _build_governance_event(task: dict, trust_map: dict) -> dict:
    """Convert a governance task into a calendar event dict."""
    due_date = task.get("due_date", "")
    task_type = task.get("task_type", "")
    is_completed = bool(task.get("completed_at"))
    dr = _days_remaining(due_date) if due_date else 999

    return {
        "id": task.get("task_id", ""),
        "event_type": "governance_task",
        "type": "governance_task",
        "title": task_type.replace("_", " ").title(),
        "date": due_date,
        "description": task.get("description", ""),
        "trust_id": task.get("trust_id"),
        "trust_name": trust_map.get(task.get("trust_id"), ""),
        "completed": is_completed,
        "status": _event_status(due_date, is_completed),
        "days_remaining": dr,
        "task_type": task_type,
        "completed_at": task.get("completed_at"),
        "checklist": task.get("checklist"),
    }


async def _build_governance_events(
    user_id: str,
    trust_id: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    tax_dedup_keys: set,
    tax_trust_map: dict,
) -> list:
    """Fetch and build governance task events, applying dedup and date filters."""
    task_query = {"user_id": user_id}
    if trust_id:
        task_query["trust_id"] = trust_id

    tasks = await db.governance_tasks.find(task_query, {"_id": 0}).to_list(10000)

    trust_ids = list(set(t.get("trust_id") for t in tasks if t.get("trust_id")))
    trusts = (
        await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
        if trust_ids
        else []
    )
    trust_map = {t.get("trust_id"): t.get("name", "") for t in trusts if t.get("trust_id")}
    for t in trusts:
        tid = t.get("trust_id")
        if tid and tid not in tax_trust_map:
            tax_trust_map[tid] = t

    events = []
    for task in tasks:
        due_date = task.get("due_date", "")
        if not _passes_date_filter(due_date, start_date, end_date):
            continue

        if _is_task_duplicated_by_tax_entry(
            task.get("task_type", ""), task.get("trust_id", ""), due_date,
            tax_dedup_keys, tax_trust_map,
        ):
            continue

        events.append(_build_governance_event(task, trust_map))

    return events


def _build_distribution_event(dist: dict) -> Optional[dict]:
    """Convert a distribution record into a calendar event, or None if no valid date."""
    d_date = _safe_date(dist.get("date"), dist.get("created_at"))
    if not d_date:
        return None

    beneficiary = dist.get("beneficiary_name") or "Beneficiary"
    title = f"Distribution to {beneficiary}"
    amount = dist.get("amount")
    if amount is not None:
        try:
            title += f": ${float(amount):,.2f}"
        except (ValueError, TypeError):
            pass

    return {
        "id": dist.get("distribution_id", ""),
        "event_type": "distribution",
        "type": "distribution",
        "title": title,
        "date": d_date,
        "description": dist.get("notes") or "",
        "trust_id": dist.get("trust_id"),
        "completed": True,
        "status": "completed",
        "link": "/distributions",
        "category": "money",
    }


def _build_compensation_event(pmt: dict) -> Optional[dict]:
    """Convert a compensation payment into a calendar event, or None if no valid date."""
    p_date = _safe_date(pmt.get("date"), pmt.get("created_at"))
    if not p_date:
        return None

    trustee = pmt.get("trustee_name") or ""
    title = "Compensation Payment"
    if trustee:
        title += f": {trustee}"
    amount = pmt.get("amount")
    if amount is not None:
        try:
            title += f" — ${float(amount):,.2f}"
        except (ValueError, TypeError):
            pass

    return {
        "id": pmt.get("payment_id", ""),
        "event_type": "compensation_payment",
        "type": "compensation_payment",
        "title": title,
        "date": p_date,
        "description": pmt.get("classification_text") or "",
        "trust_id": pmt.get("trust_id"),
        "completed": True,
        "status": "completed",
        "link": "/compensation",
        "category": "money",
    }


def _build_investment_event(inv: dict) -> Optional[dict]:
    """Convert an investment into a calendar event, or None if no valid date."""
    i_date = _safe_date(inv.get("purchase_date"), inv.get("created_at"))
    if not i_date:
        return None

    asset_name = inv.get("asset_name") or "Investment"
    return {
        "id": inv.get("investment_id", ""),
        "event_type": "investment",
        "type": "investment",
        "title": f"Investment Purchased: {asset_name}",
        "date": i_date,
        "description": inv.get("asset_type") or "",
        "trust_id": inv.get("trust_id"),
        "completed": True,
        "status": "completed",
        "link": "/investments",
        "category": "money",
    }


def _build_entity_event(ent: dict) -> Optional[dict]:
    """Convert an entity formation into a calendar event, or None if no valid date."""
    e_date = _safe_date(ent.get("formation_date"))
    if not e_date:
        return None

    name = ent.get("name") or ent.get("legal_name") or "Entity"
    return {
        "id": ent.get("entity_id", ""),
        "event_type": "entity_formation",
        "type": "entity_formation",
        "title": f"Entity Formed: {name}",
        "date": e_date,
        "description": ent.get("entity_type") or "",
        "trust_id": ent.get("trust_id"),
        "completed": True,
        "status": "completed",
        "link": "/structures",
        "category": "structure",
    }


def _build_schedule_a_event(item: dict) -> Optional[dict]:
    """Convert a Schedule A conveyance into a calendar event, or None if no valid date."""
    s_date = _safe_date(item.get("date_conveyed"))
    if not s_date:
        return None

    desc = item.get("description") or "Asset"
    return {
        "id": item.get("item_id", ""),
        "event_type": "schedule_a_conveyance",
        "type": "schedule_a_conveyance",
        "title": f"Asset Conveyed: {desc}",
        "date": s_date,
        "description": item.get("category") or "",
        "trust_id": item.get("trust_id"),
        "completed": True,
        "status": "completed",
        "link": "/schedule-a",
        "category": "structure",
    }


def _build_communication_event(comm: dict) -> Optional[dict]:
    """Convert a communication into a calendar event, or None if no valid date."""
    c_date = _safe_date(comm.get("created_at"))
    if not c_date:
        return None

    subject = comm.get("subject") or comm.get("comm_type_label") or "Communication"
    return {
        "id": comm.get("comm_id", ""),
        "event_type": "communication",
        "type": "communication",
        "title": f"Communication: {subject}",
        "date": c_date,
        "description": comm.get("comm_type_label") or "",
        "trust_id": comm.get("trust_id"),
        "completed": True,
        "status": "completed",
        "link": "/communications",
        "category": "structure",
    }


def _collect_valid_events(records: list, builder) -> list:
    """Apply builder to each record, collecting only non-None results."""
    results = []
    for record in records:
        event = builder(record)
        if event is not None:
            results.append(event)
    return results


async def _build_money_events(user_id: str, trust_id: Optional[str]) -> list:
    """Fetch and build all money-section events (distributions, compensation, investments)."""
    money_query = _build_money_query(user_id, trust_id)
    events = []

    # 3a. Distributions
    distributions = await db.distribution_records.find(money_query, {"_id": 0}).to_list(1000)
    events.extend(_collect_valid_events(distributions, _build_distribution_event))

    # 3b. Compensation payments
    comp_payments = await db.compensation_payments.find(money_query, {"_id": 0}).to_list(1000)
    events.extend(_collect_valid_events(comp_payments, _build_compensation_event))

    # 3c. Investments
    investments = await db.investments.find({**money_query, "is_active": True}, {"_id": 0}).to_list(1000)
    events.extend(_collect_valid_events(investments, _build_investment_event))

    return events


async def _build_structure_events(user_id: str, trust_id: Optional[str]) -> list:
    """Fetch and build all structure-section events (entities, Schedule A, communications)."""
    structure_query = {"user_id": user_id}
    if trust_id:
        structure_query["trust_id"] = trust_id
    events = []

    # 4a. Entity formation dates
    entities = await db.entities.find(structure_query, {"_id": 0}).to_list(1000)
    events.extend(_collect_valid_events(entities, _build_entity_event))

    # 4b. Schedule A conveyance dates
    schedule_a_items = await db.schedule_a_items.find(structure_query, {"_id": 0}).to_list(1000)
    events.extend(_collect_valid_events(schedule_a_items, _build_schedule_a_event))

    # 4c. Communication dates
    communications = await db.communications.find(structure_query, {"_id": 0}).to_list(1000)
    events.extend(_collect_valid_events(communications, _build_communication_event))

    return events


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
    # 1. Validate trust ownership if trust_id is provided
    if trust_id:
        await _validate_trust_ownership(trust_id, user["user_id"])

    # 2. Fetch and process tax calendar entries (needed for dedup of governance tasks)
    tax_query = await _build_tax_query(trust_id, user["user_id"])
    tax_query_filter = _build_tax_query_filter(tax_query, start_date, end_date)
    tax_entries = await db.tax_calendar.find(tax_query_filter, {"_id": 0}).to_list(1000)

    # Hide income-tax deadlines for tax-exempt trusts (508/501c3) — including
    # legacy entries created before per-status generation gating.
    if trust_id:
        trust_doc = await db.trusts.find_one(
            {"trust_id": trust_id}, {"_id": 0, "tax_status": 1, "benevolence_enabled": 1}
        )
        if trust_doc:
            tax_entries = _filter_exempt_tax(tax_entries, trust_doc)
    else:
        exempt_ids = {
            t.get("trust_id") for t in await db.trusts.find(
                {"user_id": user["user_id"], "$or": [
                    {"tax_status": {"$in": ["508", "501c3"]}},
                    {"benevolence_enabled": True},
                ]},
                {"_id": 0, "trust_id": 1}
            ).to_list(100)
            if t.get("trust_id")
        }
        if exempt_ids:
            tax_entries = [
                e for e in tax_entries
                if not (e.get("trust_id") in exempt_ids and e.get("deadline_type") in _INCOME_TAX_TYPES)
            ]
    tax_events, tax_dedup_keys, tax_trust_map = await _build_tax_events(tax_entries)

    # 3. Fetch and process governance tasks
    events = await _build_governance_events(
        user["user_id"], trust_id, start_date, end_date, tax_dedup_keys, tax_trust_map,
    )

    # 4. Fetch money-section events
    events.extend(await _build_money_events(user["user_id"], trust_id))

    # 5. Fetch structure-section events
    events.extend(await _build_structure_events(user["user_id"], trust_id))

    # 6. Merge tax events + sort
    events.extend(tax_events)
    events.sort(key=lambda e: e.get("date") or "")

    return {"events": events, "count": len(events)}