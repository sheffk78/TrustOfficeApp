# Tax Calendar router — Federal tax deadlines for trusts (calendar + fiscal year aware)
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


# ==================== DEADLINE RULES ====================
# Calendar year: fixed month/day
# Fiscal year: offset in months from year-end, plus a fixed day

CALENDAR_RULES = [
    {"deadline_type": "federal_1041",          "month": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","month": 9,  "day": 15, "desc": "Form 1041 — Extended filing deadline"},
    {"deadline_type": "k1_beneficiaries",      "month": 3,  "day": 15, "desc": "Schedule K-1 — Beneficiary income allocations"},
    {"deadline_type": "estimated_q1",          "month": 4,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "month": 6,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "month": 9,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "month": 1,  "day": 15, "desc": "Q4 Estimated tax payment (due following year)"},
]

# Fiscal year: (months_after_year_end, day_of_month, description)
# For a June 30 year-end: +4 months = October 15 for 1041
FISCAL_RULES = [
    {"deadline_type": "federal_1041",          "months_after": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","months_after": 10, "day": 15, "desc": "Form 1041 — Extended filing deadline"},
    {"deadline_type": "k1_beneficiaries",      "months_after": 4,  "day": 15, "desc": "Schedule K-1 — Beneficiary income allocations"},
    # Estimated taxes are calendar-based regardless of fiscal year
    {"deadline_type": "estimated_q1",          "month": 4,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "month": 6,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "month": 9,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "month": 1,  "day": 15, "desc": "Q4 Estimated tax payment (due following year)"},
]


def _fiscal_due_date(year_end: date, months_after: int, day: int) -> date:
    """Compute deadline: year_end + N months, then set to specified day."""
    m = year_end.month + months_after
    y = year_end.year
    while m > 12:
        m -= 12
        y += 1
    # Clamp to valid day for that month
    import calendar
    last_day = calendar.monthrange(y, m)[1]
    d = min(day, last_day)
    return date(y, m, d)


def _days_remaining(due_date_str: str) -> int:
    """Calculate days until/overdue a deadline."""
    due = date.fromisoformat(due_date_str)
    today = date.today()
    return (due - today).days


def _generate_entries(trust: dict, tax_year: int) -> list:
    """Generate deadline entries based on trust's tax year configuration."""
    entries = []
    now = datetime.now(timezone.utc).isoformat()
    
    is_fiscal = trust.get("is_fiscal_year") is True
    fy_month = trust.get("tax_year_end_month")
    fy_day = trust.get("tax_year_end_day")
    
    if is_fiscal and fy_month and fy_day:
        # Fiscal year: year_end is in the tax_year (e.g., June 30, 2026 for tax year 2026)
        import calendar
        last_day = calendar.monthrange(tax_year, fy_month)[1]
        year_end = date(tax_year, fy_month, min(fy_day, last_day))
        
        for rule in FISCAL_RULES:
            if "months_after" in rule:
                due = _fiscal_due_date(year_end, rule["months_after"], rule["day"])
            else:
                # Calendar-based estimated taxes
                due = _calendar_due_date(tax_year, rule["month"], rule["day"])
            
            entries.append({
                "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
                "trust_id": trust["trust_id"],
                "tax_year": tax_year,
                "deadline_type": rule["deadline_type"],
                "due_date": due.isoformat(),
                "filing_status": "pending",
                "filed_date": None,
                "description": rule["desc"],
                "notes": None,
                "accountant_engaged": False,
                "created_at": now,
                "updated_at": now,
            })
    else:
        # Calendar year (or no fiscal data set)
        for rule in CALENDAR_RULES:
            due = _calendar_due_date(tax_year, rule["month"], rule["day"])
            entries.append({
                "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
                "trust_id": trust["trust_id"],
                "tax_year": tax_year,
                "deadline_type": rule["deadline_type"],
                "due_date": due.isoformat(),
                "filing_status": "pending",
                "filed_date": None,
                "description": rule["desc"],
                "notes": None,
                "accountant_engaged": False,
                "created_at": now,
                "updated_at": now,
            })
    
    return entries


def _calendar_due_date(tax_year: int, month: int, day: int) -> date:
    """Build ISO date string. Q4 estimated is in Jan of following year."""
    if month == 1 and day == 15:
        due = date(tax_year + 1, month, day)
    else:
        due = date(tax_year, month, day)
    return due


# ==================== API ENDPOINTS ====================

@router.post("/trusts/{trust_id}/tax-calendar/generate")
async def generate_tax_calendar(trust_id: str, request: dict, user: dict = Depends(get_current_user)):
    """Auto-generate federal tax calendar entries for a tax year."""
    tax_year = request.get("tax_year")
    if not tax_year:
        raise HTTPException(status_code=400, detail="tax_year is required")
    tax_year = int(tax_year)
    
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    existing = await db.tax_calendar.count_documents({"trust_id": trust_id, "tax_year": tax_year})
    if existing > 0:
        raise HTTPException(status_code=409, detail=f"Tax calendar for tax year {tax_year} already exists")

    entries = _generate_entries(trust, tax_year)
    
    if entries:
        await db.tax_calendar.insert_many(entries)

    return {"trust_id": trust_id, "tax_year": tax_year, "entries_created": len(entries), "fiscal_year": trust.get("is_fiscal_year") is True}


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

    trust = await db.trusts.find_one({"trust_id": entry["trust_id"], "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if update_data.get("filing_status") in ("filed", "extended") and not update_data.get("filed_date"):
        update_data["filed_date"] = datetime.now(timezone.utc).isoformat()

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.tax_calendar.update_one({"entry_id": entry_id}, {"$set": update_data})

    updated = await db.tax_calendar.find_one({"entry_id": entry_id}, {"_id": 0})
    days = _days_remaining(updated["due_date"])
    updated["days_remaining"] = days
    updated["is_overdue"] = days < 0

    return TaxCalendarEntryResponse(**updated)
