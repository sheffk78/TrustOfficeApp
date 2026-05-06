# Tax Calendar router — Federal tax deadlines for trusts (calendar + fiscal year aware)
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, date, timedelta
from typing import List, Optional
import uuid
import calendar

from database import db
from dependencies import get_current_user
from models import (
    TaxCalendarEntryCreate, TaxCalendarEntryUpdate, TaxCalendarEntryResponse,
    TaxCalendarSummaryResponse, TrustTaxProfile
)

router = APIRouter(tags=["tax_calendar"])


# ==================== DEADLINE RULES ====================
# Calendar year and Fiscal year use different offset strategies:
#
# Calendar year: fixed month/day
# Fiscal year: offsets from year-end (for 1041/K1/extension) or from FY start (for estimated)
#
# IRS rules:
#   1041:   3.5 months after year-end  → approx +4 months, day 15
#   Ext:    6 months from original due  → +10 months, day 15
#   K-1:    same as 1041              → +4 months, day 15
#   Est Q1: 15th of 4th month  of FY  → FY start + 3 months, day 15
#   Est Q2: 15th of 6th month  of FY  → FY start + 5 months, day 15
#   Est Q3: 15th of 9th month  of FY  → FY start + 8 months, day 15
#   Est Q4: 15th of 12th month of FY  → FY start + 11 months, day 15

CALENDAR_RULES = [
    {"deadline_type": "federal_1041",          "month": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","month": 9,  "day": 15, "desc": "Form 1041 — Extended filing deadline"},
    {"deadline_type": "k1_beneficiaries",      "month": 3,  "day": 15, "desc": "Schedule K-1 — Beneficiary income allocations"},
    {"deadline_type": "estimated_q1",          "month": 4,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "month": 6,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "month": 9,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "month": 1,  "day": 15, "desc": "Q4 Estimated tax payment (due following year)"},
]

FISCAL_RULES = [
    # Non-estimated: offset in months from year-end
    {"deadline_type": "federal_1041",          "months_after": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","months_after": 10, "day": 15, "desc": "Form 1041 — Extended filing deadline"},
    {"deadline_type": "k1_beneficiaries",      "months_after": 4,  "day": 15, "desc": "Schedule K-1 — Beneficiary income allocations"},
    # Estimated taxes: fiscal month offsets from FY start
    {"deadline_type": "estimated_q1",          "fy_month_offset": 3,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "fy_month_offset": 5,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "fy_month_offset": 8,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "fy_month_offset": 11, "day": 15, "desc": "Q4 Estimated tax payment"},
]


def _clamp_day(year: int, month: int, day: int) -> int:
    """Clamp day to the last valid day of the month (handles Feb, leap years)."""
    last = calendar.monthrange(year, month)[1]
    return min(day, last)


def _fy_start(tax_year: int, fy_month: int, fy_day: int) -> date:
    """First day of the fiscal year that ends in `tax_year`."""
    # Year-end date (clamp day for leap year edge cases)
    effective_day = _clamp_day(tax_year, fy_month, fy_day)
    year_end = date(tax_year, fy_month, effective_day)
    # FY starts the day after the PREVIOUS year-end
    prev_year_end = year_end.replace(year=tax_year - 1)
    return prev_year_end + timedelta(days=1)


def _month_delta(base: date, months: int) -> date:
    """Add/subtract months from a date, clamping to last day if needed."""
    m = base.month + months
    y = base.year
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    d = _clamp_day(y, m, base.day)
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
    fy_day_raw = trust.get("tax_year_end_day")
    
    if is_fiscal and fy_month and fy_day_raw:
        fy_day = _clamp_day(tax_year, fy_month, fy_day_raw)
        year_end = date(tax_year, fy_month, fy_day)
        fy_start = _fy_start(tax_year, fy_month, fy_day)
        
        for rule in FISCAL_RULES:
            if "fy_month_offset" in rule:
                # Estimated taxes: offset from fiscal year start
                due = _month_delta(fy_start, rule["fy_month_offset"])
                due = due.replace(day=_clamp_day(due.year, due.month, rule["day"]))
            else:
                # 1041, extension, K-1: offset from year-end
                due = _month_delta(year_end, rule["months_after"])
                due = due.replace(day=_clamp_day(due.year, due.month, rule["day"]))
            
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
    """Calendar-year due date. Q4 estimated is in Jan of following year."""
    if month == 1 and day == 15:
        return date(tax_year + 1, month, day)
    return date(tax_year, month, day)


# ==================== API ENDPOINTS ====================

@router.post("/trusts/{trust_id}/tax-calendar/generate")
async def generate_tax_calendar(trust_id: str, request: dict, user: dict = Depends(get_current_user)):
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
