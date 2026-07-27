"""
Deadline service — CRUD, monitoring, and auto-generation of compliance deadlines.

Phase 3 (Health Score & Deadline Tracking) of the TrustOffice plan.

Deadlines live in db.deadlines. Computed fields (days_remaining, is_overdue)
are derived at read time from due_date + status.
"""
from datetime import datetime, timezone, date, timedelta
from typing import List, Optional
import uuid

from database import db
from models import (
    DeadlineCreate, DeadlineUpdate,
    DeadlineCategory, DeadlinePriority, DeadlineStatus,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(value) -> Optional[date]:
    """Parse an ISO date/datetime string into a date."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            return None


def _compute_days_remaining(due_date) -> Optional[int]:
    """Calendar days until due_date (negative when past due)."""
    due = _parse_date(due_date)
    if due is None:
        return None
    return (due - _today()).days


def _compute_is_overdue(due_date, status: str) -> bool:
    """Past due and not in a terminal state (completed/waived)."""
    if status in (DeadlineStatus.completed.value, DeadlineStatus.waived.value):
        return False
    remaining = _compute_days_remaining(due_date)
    return remaining is not None and remaining < 0


def _derive_status(due_date, status: str) -> str:
    """Re-derive the display status from due_date for non-terminal deadlines."""
    if status in (DeadlineStatus.completed.value, DeadlineStatus.waived.value):
        return status
    remaining = _compute_days_remaining(due_date)
    if remaining is None:
        return status
    if remaining < 0:
        return DeadlineStatus.overdue.value
    if remaining <= 7:
        return DeadlineStatus.due_soon.value
    return DeadlineStatus.upcoming.value


async def get_owned_trust(trust_id: str, user_id: str) -> Optional[dict]:
    """Fetch a trust only if owned by this user (mirrors meeting_service pattern)."""
    return await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )


def _enrich(doc: dict, trust_name: Optional[str] = None) -> dict:
    """Attach computed fields to a deadline document for DeadlineResponse."""
    status = doc.get("status", DeadlineStatus.upcoming.value)
    derived = _derive_status(doc.get("due_date"), status)
    return {
        **doc,
        "trust_name": trust_name or doc.get("trust_name"),
        "status": derived,
        "days_remaining": _compute_days_remaining(doc.get("due_date")),
        "is_overdue": _compute_is_overdue(doc.get("due_date"), status),
        "reminder_days_before": doc.get("reminder_days_before") or [],
    }


async def _get_deadline_for_user(deadline_id: str, user_id: str) -> Optional[dict]:
    return await db.deadlines.find_one(
        {"deadline_id": deadline_id, "user_id": user_id}, {"_id": 0}
    )


# ==================== CRUD ====================

async def create_deadline(data: DeadlineCreate, user_id: str) -> Optional[dict]:
    """Create a deadline document and insert into db.deadlines.

    Returns None when the trust doesn't exist or isn't owned by this user.
    """
    trust = await get_owned_trust(data.trust_id, user_id)
    if not trust:
        return None

    now = _now()
    doc = {
        "deadline_id": _new_id("deadline"),
        "trust_id": data.trust_id,
        "user_id": user_id,
        "category": data.category.value,
        "title": data.title,
        "description": data.description,
        "due_date": data.due_date,
        "priority": data.priority.value,
        "status": _derive_status(data.due_date, DeadlineStatus.upcoming.value),
        "recurrence": data.recurrence,
        "recurrence_end_date": data.recurrence_end_date,
        "reminder_days_before": data.reminder_days_before,
        "is_statutory": data.is_statutory,
        "state_specific": data.state_specific,
        "reference_document": data.reference_document,
        "completion_date": None,
        "completion_notes": None,
        "notes": data.notes,
        "reminder_sent_days": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.deadlines.insert_one(doc)
    doc.pop("_id", None)
    return _enrich(doc, trust.get("trust_name"))


async def get_trust_deadlines(trust_id: str, user_id: str) -> List[dict]:
    """All deadlines for a trust, enriched with computed fields."""
    trust = await get_owned_trust(trust_id, user_id)
    if not trust:
        return []

    docs = await db.deadlines.find(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    ).sort("due_date", 1).to_list(1000)

    return [_enrich(d, trust.get("trust_name")) for d in docs]


async def get_deadline_summary(trust_id: str, user_id: str) -> Optional[dict]:
    """Aggregate deadline counts for a trust."""
    trust = await get_owned_trust(trust_id, user_id)
    if not trust:
        return None

    deadlines = await get_trust_deadlines(trust_id, user_id)

    by_status = {
        "upcoming": 0, "due_soon": 0, "overdue": 0,
        "completed": 0, "waived": 0,
    }
    by_category: dict = {}
    by_priority: dict = {}
    next_deadline: Optional[dict] = None

    for d in deadlines:
        status = d["status"]
        by_status[status] = by_status.get(status, 0) + 1
        by_category[d["category"]] = by_category.get(d["category"], 0) + 1
        by_priority[d["priority"]] = by_priority.get(d["priority"], 0) + 1

        if status in (DeadlineStatus.upcoming.value, DeadlineStatus.due_soon.value):
            if next_deadline is None or d["due_date"] < next_deadline["due_date"]:
                next_deadline = d

    return {
        "trust_id": trust_id,
        "total_deadlines": len(deadlines),
        "upcoming_count": by_status.get("upcoming", 0),
        "due_soon_count": by_status.get("due_soon", 0),
        "overdue_count": by_status.get("overdue", 0),
        "completed_count": by_status.get("completed", 0),
        "by_category": by_category,
        "by_priority": by_priority,
        "next_deadline": next_deadline,
        "calculated_at": _now(),
    }


async def update_deadline(deadline_id: str, user_id: str, updates: DeadlineUpdate) -> Optional[dict]:
    """Apply a DeadlineUpdate; returns the enriched updated doc or None."""
    existing = await _get_deadline_for_user(deadline_id, user_id)
    if not existing:
        return None

    patch = {k: v for k, v in updates.model_dump(exclude_unset=True).items() if v is not None}
    if "priority" in patch and hasattr(patch["priority"], "value"):
        patch["priority"] = patch["priority"].value
    if "status" in patch and hasattr(patch["status"], "value"):
        patch["status"] = patch["status"].value
    patch["updated_at"] = _now()

    await db.deadlines.update_one(
        {"deadline_id": deadline_id, "user_id": user_id},
        {"$set": patch},
    )

    updated = await _get_deadline_for_user(deadline_id, user_id)
    if not updated:
        return None
    trust = await get_owned_trust(updated["trust_id"], user_id)
    return _enrich(updated, (trust or {}).get("trust_name"))


async def delete_deadline(deadline_id: str, user_id: str) -> bool:
    result = await db.deadlines.delete_one(
        {"deadline_id": deadline_id, "user_id": user_id}
    )
    return result.deleted_count > 0


# ==================== AUTO-GENERATION ====================

def _standard_deadlines_for_year(year: int) -> List[dict]:
    """Standard compliance deadlines for a tax year."""
    return [
        # Federal income tax (Form 1041) — April 15
        {
            "category": DeadlineCategory.tax_filing_1041,
            "title": f"Form 1041 Filing Deadline (TY{year - 1})",
            "description": f"Federal fiduciary income tax return for tax year {year - 1}.",
            "due_date": f"{year}-04-15",
            "priority": DeadlinePriority.critical,
            "recurrence": "annual",
            "is_statutory": True,
        },
        # K-1 distribution to beneficiaries — same as 1041
        {
            "category": DeadlineCategory.tax_filing_k1,
            "title": f"Schedule K-1 to Beneficiaries (TY{year - 1})",
            "description": f"Furnish beneficiary K-1s for tax year {year - 1}.",
            "due_date": f"{year}-04-15",
            "priority": DeadlinePriority.critical,
            "recurrence": "annual",
            "is_statutory": True,
        },
        # Estimated tax payments (federal quarterly)
        {
            "category": DeadlineCategory.estimated_tax_payment,
            "title": f"Q1 Estimated Tax Payment ({year})",
            "description": "First-quarter federal estimated tax payment.",
            "due_date": f"{year}-04-15",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": True,
        },
        {
            "category": DeadlineCategory.estimated_tax_payment,
            "title": f"Q2 Estimated Tax Payment ({year})",
            "description": "Second-quarter federal estimated tax payment.",
            "due_date": f"{year}-06-15",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": True,
        },
        {
            "category": DeadlineCategory.estimated_tax_payment,
            "title": f"Q3 Estimated Tax Payment ({year})",
            "description": "Third-quarter federal estimated tax payment.",
            "due_date": f"{year}-09-15",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": True,
        },
        {
            "category": DeadlineCategory.estimated_tax_payment,
            "title": f"Q4 Estimated Tax Payment ({year})",
            "description": "Fourth-quarter federal estimated tax payment.",
            "due_date": f"{year + 1}-01-15",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": True,
        },
        # Quarterly governance reviews
        {
            "category": DeadlineCategory.quarterly_review,
            "title": f"Q1 Quarterly Compliance Review ({year})",
            "description": "Quarterly review of trust governance, tasks, and financials.",
            "due_date": f"{year}-03-31",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": False,
        },
        {
            "category": DeadlineCategory.quarterly_review,
            "title": f"Q2 Quarterly Compliance Review ({year})",
            "description": "Quarterly review of trust governance, tasks, and financials.",
            "due_date": f"{year}-06-30",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": False,
        },
        {
            "category": DeadlineCategory.quarterly_review,
            "title": f"Q3 Quarterly Compliance Review ({year})",
            "description": "Quarterly review of trust governance, tasks, and financials.",
            "due_date": f"{year}-09-30",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": False,
        },
        {
            "category": DeadlineCategory.quarterly_review,
            "title": f"Q4 Quarterly Compliance Review ({year})",
            "description": "Quarterly review of trust governance, tasks, and financials.",
            "due_date": f"{year}-12-31",
            "priority": DeadlinePriority.high,
            "recurrence": "quarterly",
            "is_statutory": False,
        },
        # Annual review
        {
            "category": DeadlineCategory.annual_review,
            "title": f"Annual Trust Review ({year})",
            "description": "Comprehensive annual review of trust administration.",
            "due_date": f"{year}-12-31",
            "priority": DeadlinePriority.critical,
            "recurrence": "annual",
            "is_statutory": False,
        },
        # Trustee compensation review
        {
            "category": DeadlineCategory.trustee_compensation_review,
            "title": f"Trustee Compensation Review ({year})",
            "description": "Annual review of trustee compensation against the approved plan.",
            "due_date": f"{year}-12-31",
            "priority": DeadlinePriority.medium,
            "recurrence": "annual",
            "is_statutory": False,
        },
        # Insurance compliance check
        {
            "category": DeadlineCategory.insurance_compliance,
            "title": f"Insurance Compliance Check ({year})",
            "description": "Verify insurance coverage for trust assets is current.",
            "due_date": f"{year}-12-31",
            "priority": DeadlinePriority.medium,
            "recurrence": "annual",
            "is_statutory": False,
        },
    ]


async def auto_generate_deadlines(trust_id: str, user_id: str) -> List[dict]:
    """Generate standard deadlines for a trust based on trust type, jurisdiction,
    and the current tax year. Skips categories/titles that already exist."""
    trust = await get_owned_trust(trust_id, user_id)
    if not trust:
        return []

    year = _today().year
    specs = _standard_deadlines_for_year(year)

    # Pull existing titles to avoid duplicates
    existing = await db.deadlines.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "title": 1},
    ).to_list(1000)
    existing_titles = {d["title"] for d in existing}

    state = trust.get("jurisdiction") or trust.get("state")
    now = _now()
    created: List[dict] = []

    for spec in specs:
        if spec["title"] in existing_titles:
            continue
        doc = {
            "deadline_id": _new_id("deadline"),
            "trust_id": trust_id,
            "user_id": user_id,
            "category": spec["category"].value,
            "title": spec["title"],
            "description": spec["description"],
            "due_date": spec["due_date"],
            "priority": spec["priority"].value,
            "status": _derive_status(spec["due_date"], DeadlineStatus.upcoming.value),
            "recurrence": spec.get("recurrence"),
            "recurrence_end_date": None,
            "reminder_days_before": [30, 14, 7, 3, 1],
            "is_statutory": spec.get("is_statutory", False),
            "state_specific": state if spec["category"] == DeadlineCategory.state_compliance else None,
            "reference_document": None,
            "completion_date": None,
            "completion_notes": None,
            "notes": None,
            "reminder_sent_days": [],
            "created_at": now,
            "updated_at": now,
        }
        await db.deadlines.insert_one(doc)
        doc.pop("_id", None)
        created.append(_enrich(doc, trust.get("trust_name")))

    return created


# ==================== CROSS-TRUST MONITORING ====================

async def get_upcoming_deadlines(user_id: str, days: int = 30) -> List[dict]:
    """Upcoming deadlines across ALL of the user's trusts (next N days)."""
    today = _today()
    end = (today + timedelta(days=days)).isoformat()

    docs = await db.deadlines.find(
        {
            "user_id": user_id,
            "status": {"$nin": [DeadlineStatus.completed.value, DeadlineStatus.waived.value]},
            "due_date": {"$gte": today.isoformat(), "$lte": end},
        },
        {"_id": 0},
    ).sort("due_date", 1).to_list(1000)

    # Attach trust names
    trust_ids = {d["trust_id"] for d in docs}
    trust_names = await _trust_name_map(user_id, trust_ids)
    return [_enrich(d, trust_names.get(d["trust_id"])) for d in docs]


async def get_overdue_deadlines(user_id: str) -> List[dict]:
    """Overdue deadlines across ALL of the user's trusts."""
    today = _today().isoformat()

    docs = await db.deadlines.find(
        {
            "user_id": user_id,
            "status": {"$nin": [DeadlineStatus.completed.value, DeadlineStatus.waived.value]},
            "due_date": {"$lt": today},
        },
        {"_id": 0},
    ).sort("due_date", 1).to_list(1000)

    trust_ids = {d["trust_id"] for d in docs}
    trust_names = await _trust_name_map(user_id, trust_ids)
    return [_enrich(d, trust_names.get(d["trust_id"])) for d in docs]


async def _trust_name_map(user_id: str, trust_ids: set) -> dict:
    if not trust_ids:
        return {}
    trusts = await db.trusts.find(
        {"user_id": user_id, "trust_id": {"$in": list(trust_ids)}},
        {"_id": 0, "trust_id": 1, "trust_name": 1},
    ).to_list(500)
    return {t["trust_id"]: t.get("trust_name") for t in trusts}


# ==================== STATE TRANSITIONS ====================

async def complete_deadline(deadline_id: str, user_id: str) -> Optional[dict]:
    """Mark a deadline completed."""
    existing = await _get_deadline_for_user(deadline_id, user_id)
    if not existing:
        return None

    await db.deadlines.update_one(
        {"deadline_id": deadline_id, "user_id": user_id},
        {"$set": {
            "status": DeadlineStatus.completed.value,
            "completion_date": _now(),
            "updated_at": _now(),
        }},
    )
    updated = await _get_deadline_for_user(deadline_id, user_id)
    if not updated:
        return None
    trust = await get_owned_trust(updated["trust_id"], user_id)
    return _enrich(updated, (trust or {}).get("trust_name"))


async def waive_deadline(deadline_id: str, user_id: str, note: str) -> Optional[dict]:
    """Mark a deadline waived (note required, recorded as completion_notes)."""
    existing = await _get_deadline_for_user(deadline_id, user_id)
    if not existing:
        return None

    await db.deadlines.update_one(
        {"deadline_id": deadline_id, "user_id": user_id},
        {"$set": {
            "status": DeadlineStatus.waived.value,
            "completion_notes": note,
            "updated_at": _now(),
        }},
    )
    updated = await _get_deadline_for_user(deadline_id, user_id)
    if not updated:
        return None
    trust = await get_owned_trust(updated["trust_id"], user_id)
    return _enrich(updated, (trust or {}).get("trust_name"))


async def snooze_deadline(deadline_id: str, user_id: str, days: int) -> Optional[dict]:
    """Extend due_date by N days, keeping the deadline active."""
    existing = await _get_deadline_for_user(deadline_id, user_id)
    if not existing:
        return None

    due = _parse_date(existing.get("due_date"))
    if due is None:
        return None

    new_due = (due + timedelta(days=days)).isoformat()
    new_status = _derive_status(new_due, existing.get("status", DeadlineStatus.upcoming.value))

    await db.deadlines.update_one(
        {"deadline_id": deadline_id, "user_id": user_id},
        {"$set": {
            "due_date": new_due,
            "status": new_status,
            "updated_at": _now(),
        }},
    )
    updated = await _get_deadline_for_user(deadline_id, user_id)
    if not updated:
        return None
    trust = await get_owned_trust(updated["trust_id"], user_id)
    return _enrich(updated, (trust or {}).get("trust_name"))
