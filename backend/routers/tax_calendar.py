# Tax Calendar router — Federal tax deadlines for trusts (calendar + fiscal year aware)
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, date
import uuid

from database import db
from dependencies import get_current_user
from models import (
    TaxCalendarEntryCreate, TaxCalendarEntryUpdate, TaxCalendarEntryResponse,
    TaxCalendarSummaryResponse, TrustTaxProfile
)
from utils.tax_calendar_math import (
    _generate_entries,
    _days_remaining,
    CALENDAR_RULES,
    FISCAL_RULES,
)

router = APIRouter(tags=["tax_calendar"])

# Local alias removed — using imported _days_remaining directly


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
