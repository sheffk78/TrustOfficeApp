"""
Marketing Expenses Router — Categorized marketing spend tracking for the
investor / stats-user dashboard.

Provides:
  GET  /stats/marketing-expenses          — stats users & admins: categorized summary
  POST /admin/marketing-expenses          — admins: add an expense entry
  PUT  /admin/marketing-expenses/{id}     — admins: edit an entry
  DELETE /admin/marketing-expenses/{id}   — admins: delete an entry
  POST /admin/marketing-expenses/seed     — admins: bulk seed (idempotent)

Categories (extensible):
  marketing_build   — one-time campaign build (content, ads, management)
  meta_ads          — Facebook/Meta paid ads
  google_ads        — Google Ads
  linkdaddy_seo     — LinkDaddy backlink / SEO services
  influencer        — Influencer promotions
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pydantic import BaseModel, Field
import uuid
import logging

from database import db
from dependencies import get_current_user
from routers.admin import require_admin
from routers.stats import require_stats_or_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketing-expenses"])

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

CATEGORIES = {
    "marketing_build": {
        "label": "Marketing Campaign Build",
        "description": "Content creation, ad creative, and ad management for campaign launches",
    },
    "meta_ads": {
        "label": "Meta / Facebook Ads",
        "description": "Paid advertising on Facebook and Instagram",
    },
    "google_ads": {
        "label": "Google Ads",
        "description": "Google Search and Display advertising",
    },
    "linkdaddy_seo": {
        "label": "LinkDaddy SEO",
        "description": "Backlink building and press release distribution",
    },
    "influencer": {
        "label": "Influencer Promotions",
        "description": "Sponsored content and promotions from influencers",
    },
}

# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────

class MarketingExpenseCreate(BaseModel):
    category: str = Field(..., description="One of: " + ", ".join(CATEGORIES.keys()))
    amount_cents: int = Field(..., gt=0, description="Amount in cents (e.g. 1000000 = $10,000)")
    period_month: Optional[str] = Field(None, description="YYYY-MM for recurring/monthly spend, null for one-time")
    description: str = Field("", description="Short description of the expense")
    source: str = Field("manual", description="manual | adspirer_sync | seed")
    expense_date: Optional[str] = Field(None, description="ISO date string (YYYY-MM-DD). Defaults to today.")


class MarketingExpenseUpdate(BaseModel):
    category: Optional[str] = None
    amount_cents: Optional[int] = None
    period_month: Optional[str] = None
    description: Optional[str] = None
    expense_date: Optional[str] = None


class MarketingExpenseBatch(BaseModel):
    expenses: List[MarketingExpenseCreate]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid category '{category}'. Must be one of: {', '.join(CATEGORIES.keys())}"
        )
    return category


def _parse_expense_date(date_str: Optional[str]) -> datetime:
    if date_str:
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid expense_date format. Use YYYY-MM-DD.")
    return datetime.now(timezone.utc)


def _date_range_from_preset(preset: str):
    """Same preset logic as stats.py."""
    now = datetime.now(timezone.utc)
    if preset == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif preset == "this_week":
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif preset == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif preset == "last_30_days":
        return now - timedelta(days=30), now
    elif preset == "last_90_days":
        return now - timedelta(days=90), now
    elif preset == "all_time":
        return datetime(2020, 1, 1, tzinfo=timezone.utc), now
    else:
        return now - timedelta(days=30), now


def _format_cents(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# ──────────────────────────────────────────────
# Endpoints — Stats User (read-only)
# ──────────────────────────────────────────────

@router.get("/stats/marketing-expenses")
async def get_marketing_expenses_summary(
    preset: str = Query("all_time", description="today, this_week, this_month, last_30_days, last_90_days, all_time"),
    start_date: Optional[str] = Query(None, description="Custom start (ISO). Overrides preset."),
    end_date: Optional[str] = Query(None, description="Custom end (ISO). Overrides preset."),
    user: dict = Depends(require_stats_or_admin),
):
    """
    Get categorized marketing expense summary for stats users and admins.
    Returns category-level totals and monthly breakdown — NO individual line items.
    """
    if start_date and end_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use ISO format.")
    else:
        start_dt, end_dt = _date_range_from_preset(preset)

    # Fetch all marketing expenses in range
    cursor = db.marketing_expenses.find(
        {"expense_date": {"$gte": start_dt.isoformat(), "$lte": end_dt.isoformat()}}
    )
    docs = await cursor.to_list(length=1000)

    # Aggregate by category
    by_category = {}
    by_month = defaultdict(int)
    total_cents = 0

    for doc in docs:
        cat = doc["category"]
        amount = doc["amount_cents"]
        total_cents += amount
        by_category[cat] = by_category.get(cat, 0) + amount

        # Monthly breakdown
        exp_date = doc.get("expense_date", "")
        if exp_date:
            month_key = exp_date[:7]  # YYYY-MM
            by_month[month_key] += amount

    # Build category summary with labels
    categories_summary = []
    for cat_key, cat_info in CATEGORIES.items():
        cat_total = by_category.get(cat_key, 0)
        categories_summary.append({
            "category": cat_key,
            "label": cat_info["label"],
            "description": cat_info["description"],
            "total_cents": cat_total,
            "total_formatted": _format_cents(cat_total),
        })

    # Sort categories by total descending
    categories_summary.sort(key=lambda c: c["total_cents"], reverse=True)

    # Monthly breakdown sorted
    by_month_list = [
        {"month": k, "amount_cents": v, "amount_formatted": _format_cents(v)}
        for k, v in sorted(by_month.items())
    ]

    return {
        "total_expenses_cents": total_cents,
        "total_expenses_formatted": _format_cents(total_cents),
        "by_category": categories_summary,
        "by_month": by_month_list,
        "date_range": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "preset": preset,
        },
        "category_count": len([c for c in categories_summary if c["total_cents"] > 0]),
    }


# ──────────────────────────────────────────────
# Endpoints — Admin (CRUD)
# ──────────────────────────────────────────────

@router.post("/admin/marketing-expenses")
async def create_marketing_expense(
    entry: MarketingExpenseCreate,
    admin: dict = Depends(require_admin),
):
    """Add a marketing expense entry (admin only)."""
    _validate_category(entry.category)

    exp_date = _parse_expense_date(entry.expense_date)

    doc = {
        "expense_id": str(uuid.uuid4()),
        "category": entry.category,
        "amount_cents": entry.amount_cents,
        "period_month": entry.period_month,
        "description": entry.description,
        "source": entry.source,
        "expense_date": exp_date.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin.get("user_id", "unknown"),
    }

    await db.marketing_expenses.insert_one(doc)
    logger.info(f"Admin {admin.get('email')} created marketing expense: {entry.category} = {_format_cents(entry.amount_cents)}")

    return {"status": "created", "expense_id": doc["expense_id"]}


@router.put("/admin/marketing-expenses/{expense_id}")
async def update_marketing_expense(
    expense_id: str,
    update: MarketingExpenseUpdate,
    admin: dict = Depends(require_admin),
):
    """Edit a marketing expense entry (admin only)."""
    update_fields = {}
    if update.category is not None:
        _validate_category(update.category)
        update_fields["category"] = update.category
    if update.amount_cents is not None:
        if update.amount_cents <= 0:
            raise HTTPException(status_code=422, detail="amount_cents must be positive")
        update_fields["amount_cents"] = update.amount_cents
    if update.period_month is not None:
        update_fields["period_month"] = update.period_month
    if update.description is not None:
        update_fields["description"] = update.description
    if update.expense_date is not None:
        exp_date = _parse_expense_date(update.expense_date)
        update_fields["expense_date"] = exp_date.isoformat()

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_fields["updated_by"] = admin.get("user_id", "unknown")

    result = await db.marketing_expenses.update_one(
        {"expense_id": expense_id},
        {"$set": update_fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expense entry not found")

    logger.info(f"Admin {admin.get('email')} updated marketing expense {expense_id}")
    return {"status": "updated", "expense_id": expense_id}


@router.delete("/admin/marketing-expenses/{expense_id}")
async def delete_marketing_expense(
    expense_id: str,
    admin: dict = Depends(require_admin),
):
    """Delete a marketing expense entry (admin only)."""
    result = await db.marketing_expenses.delete_one({"expense_id": expense_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense entry not found")

    logger.info(f"Admin {admin.get('email')} deleted marketing expense {expense_id}")
    return {"status": "deleted", "expense_id": expense_id}


@router.get("/admin/marketing-expenses")
async def list_all_marketing_expenses(
    admin: dict = Depends(require_admin),
):
    """List all marketing expense entries (admin only, for management)."""
    cursor = db.marketing_expenses.find({}, {"_id": 0}).sort("expense_date", -1)
    docs = await cursor.to_list(length=500)
    return {"expenses": docs, "count": len(docs)}


@router.post("/admin/marketing-expenses/seed")
async def seed_marketing_expenses(
    batch: MarketingExpenseBatch,
    admin: dict = Depends(require_admin),
):
    """
    Bulk seed marketing expenses (idempotent by description+amount).
    Only inserts entries that don't already exist (matched by description + amount_cents).
    """
    inserted = 0
    skipped = 0

    for entry in batch.expenses:
        _validate_category(entry.category)
        exp_date = _parse_expense_date(entry.expense_date)

        # Check for existing entry with same description + amount
        existing = await db.marketing_expenses.find_one({
            "description": entry.description,
            "amount_cents": entry.amount_cents,
            "category": entry.category,
        })

        if existing:
            skipped += 1
            continue

        doc = {
            "expense_id": str(uuid.uuid4()),
            "category": entry.category,
            "amount_cents": entry.amount_cents,
            "period_month": entry.period_month,
            "description": entry.description,
            "source": "seed",
            "expense_date": exp_date.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": admin.get("user_id", "unknown"),
        }

        await db.marketing_expenses.insert_one(doc)
        inserted += 1

    logger.info(f"Admin {admin.get('email')} seeded marketing expenses: {inserted} inserted, {skipped} skipped")
    return {"status": "seeded", "inserted": inserted, "skipped": skipped}