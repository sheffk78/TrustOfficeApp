# Tax Calendar router — Federal tax deadlines for trusts
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, date
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user
from models import (
    TaxCalendarEntryCreate, TaxCalendarEntryUpdate, TaxCalendarEntryResponse,
    TaxCalendarSummaryResponse, TrustTaxProfile
)

router = APIRouter(tags=["tax_calendar"])


# ==================== FEDERAL DEADLINE RULES (calendar year) ====================
FEDERAL_DEADLINE_RULES = [
    {"deadline_type": "federal_1041", "month": 4, "day": 15, "description": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension", "month": 9, "day": 15, "description": "Form 1041 — Extended filing deadline"},
    {"deadline_type": "k1_beneficiaries", "month": 3, "day": 15, "description": "Schedule K-1 — Beneficiary income allocations"},
    {"deadline_type": "estimated_q1", "month": 4, "day": 15, "description": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2", "month": 6, "day": 15, "description": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3", "month": 9, "day": 15, "description": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4", "month": 1, "day": 15, "description": "Q4 Estimated tax payment (due following year)"},
]


def _build_due_date(tax_year: int, month: int, day: int) -> str:
    """Build ISO date string. Q4 estimated is in Jan of following year."""
    if month == 1 and day == 15:
        # Q4 estimated — next year
        due = date(tax_year + 1, month, day)
    else:
        due = date(tax_year, month, day)
    return due.isoformat()


def _days_remaining(due_date_str: str) -> int:
    """Calculate days until/overdue a deadline."""
    due = date.fromisoformat(due_date_str)
    today = date.today()
    return (due - today).days


# ==================== API ENDPOINTS ====================

@router.post("/trusts/{trust_id}/tax-calendar/generate")
async def generate_tax_calendar(trust_id: str, request: dict, user: dict = Depends(get_current_user)):
    """Auto-generate federal tax calendar entries for a tax year."""
    tax_year = request.get("tax_year")
    if not tax_year:
        raise HTTPException(status_code=400, detail="tax_year is required")
    tax_year = int(tax_year)
    # Verify trust ownership
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Check if calendar already exists for this year
    existing = await db.tax_calendar.count_documents({"trust_id": trust_id, "tax_year": tax_year})
    if existing > 0:
        raise HTTPException(status_code=409, detail=f"Tax calendar for tax year {tax_year} already exists")

    entries = []
    now = datetime.now(timezone.utc).isoformat()
    for rule in FEDERAL_DEADLINE_RULES:
        entry_doc = {
            "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "tax_year": tax_year,
            "deadline_type": rule["deadline_type"],
            "due_date": _build_due_date(tax_year, rule["month"], rule["day"]),
            "filing_status": "pending",
            "filed_date": None,
            "description": rule["description"],
            "notes": None,
            "accountant_engaged": False,
            "created_at": now,
            "updated_at": now,
        }
        entries.append(entry_doc)

    if entries:
        await db.tax_calendar.insert_many(entries)

    return {"trust_id": trust_id, "tax_year": tax_year, "entries_created": len(entries)}


@router.get("/trusts/{trust_id}/tax-calendar", response_model=TaxCalendarSummaryResponse)
async def get_tax_calendar(trust_id: str, tax_year: Optional[int] = None, user: dict = Depends(get_current_user)):
    """Get tax calendar for a trust. If no tax_year, uses the current year."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    year = tax_year or date.today().year
    raw = await db.tax_calendar.find(
        {"trust_id": trust_id, "tax_year": year},
        {"_id": 0}
    ).sort("due_date", 1).to_list(50)

    entries = []
    now = datetime.now(timezone.utc).isoformat()
    for doc in raw:
        days = _days_remaining(doc["due_date"])
        entries.append({
            **doc,
            "days_remaining": days,
            "is_overdue": days < 0
        })

    filed = sum(1 for e in entries if e["filing_status"] in ("filed", "not_required"))
    pend = sum(1 for e in entries if e["filing_status"] == "pending")
    overdue = sum(1 for e in entries if e["is_overdue"] and e["filing_status"] == "pending")

    return TaxCalendarSummaryResponse(
        trust_id=trust_id,
        tax_year=year,
        total_entries=len(entries),
        filed_count=filed,
        pending_count=pend,
        overdue_count=overdue,
        entries=entries
    )


@router.get("/trusts/{trust_id}/tax-calendar/upcoming")
async def get_upcoming_deadlines(trust_id: str, days: int = 90, user: dict = Depends(get_current_user)):
    """Get upcoming tax deadlines within N days."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    year = date.today().year
    raw = await db.tax_calendar.find(
        {"trust_id": trust_id, "tax_year": year, "filing_status": "pending"},
        {"_id": 0}
    ).sort("due_date", 1).to_list(50)

    results = []
    for doc in raw:
        dr = _days_remaining(doc["due_date"])
        if dr <= days:
            results.append({**doc, "days_remaining": dr, "is_overdue": dr < 0})

    return {"trust_id": trust_id, "upcoming": results, "days_window": days}


@router.patch("/tax-calendar/{entry_id}")
async def update_tax_entry(entry_id: str, update: TaxCalendarEntryUpdate, user: dict = Depends(get_current_user)):
    """Update a tax calendar entry — mark filed, add notes, etc."""
    entry = await db.tax_calendar.find_one({"entry_id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Verify ownership via trust
    trust = await db.trusts.find_one({"trust_id": entry["trust_id"], "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if update_data.get("filing_status") in ("filed", "extended") and not update_data.get("filed_date"):
        update_data["filed_date"] = datetime.now(timezone.utc).isoformat()

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.tax_calendar.update_one({"entry_id": entry_id}, {"$set": update_data})

    # Re-fetch
    updated = await db.tax_calendar.find_one({"entry_id": entry_id}, {"_id": 0})
    days = _days_remaining(updated["due_date"])
    updated["days_remaining"] = days
    updated["is_overdue"] = days < 0

    return TaxCalendarEntryResponse(**updated)
