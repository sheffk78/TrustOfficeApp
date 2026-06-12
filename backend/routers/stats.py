"""
Stats Router - Revenue dashboard for stats users and admins.
Provides aggregated revenue data from Stripe without exposing customer-level details.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import os
import logging
import calendar

import stripe

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["stats"])

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_MONTHLY_PRICE_ID = os.environ.get('STRIPE_MONTHLY_PRICE_ID')
STRIPE_ANNUAL_PRICE_ID = os.environ.get('STRIPE_ANNUAL_PRICE_ID')

TRUSTOFFICE_PRICE_IDS = {STRIPE_MONTHLY_PRICE_ID, STRIPE_ANNUAL_PRICE_ID}


def _is_trustoffice_invoice(inv) -> bool:
    """Check if an invoice has a line item matching a TrustOffice Price ID."""
    if not STRIPE_MONTHLY_PRICE_ID and not STRIPE_ANNUAL_PRICE_ID:
        return True
    try:
        for line in inv.lines.data:
            price_obj = getattr(line, 'price', None)
            if price_obj and getattr(price_obj, 'id', None) in TRUSTOFFICE_PRICE_IDS:
                return True
    except Exception:
        pass
    return False


# ==================== AUTH ====================

async def require_stats_or_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency that requires user to be either a stats user or an admin.
    Raises 403 if neither.
    """
    user_doc = await db.users.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0, "is_admin": 1, "is_stats_user": 1, "email": 1}
    )

    if not user_doc:
        raise HTTPException(status_code=403, detail="User not found")

    is_admin = user_doc.get("is_admin", False)
    is_stats = user_doc.get("is_stats_user", False)

    # Also check by email for bootstrap admin
    admin_emails = {"contact@trustoffice.app"}
    if user_doc.get("email", "").lower() in admin_emails:
        is_admin = True

    if not is_admin and not is_stats:
        raise HTTPException(status_code=403, detail="Stats access required")

    return user


# ==================== HELPER FUNCTIONS ====================

def _date_range_from_preset(preset: str):
    """Convert a preset string to (start_date, end_date) in UTC."""
    now = datetime.now(timezone.utc)

    if preset == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif preset == "this_week":
        # Start of week (Monday)
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start, now
    elif preset == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif preset == "last_30_days":
        return now - timedelta(days=30), now
    elif preset == "last_90_days":
        return now - timedelta(days=90), now
    elif preset == "all_time":
        # Use a date far in the past
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        return start, now
    else:
        # Default to last 30 days
        return now - timedelta(days=30), now


def _fetch_stripe_revenue(start_date: datetime, end_date: datetime):
    """
    Fetch revenue data from Stripe invoices.
    Returns dict with revenue metrics.
    """
    start_ts = int(start_date.timestamp())
    end_ts = int(end_date.timestamp())

    total_revenue_cents = 0
    total_transactions = 0
    customer_ids = set()
    revenue_by_month = defaultdict(int)
    subscriptions_by_plan = {"monthly": 0, "annual": 0}
    recent_transactions = []

    try:
        # Fetch all paid invoices in the date range using pagination
        has_more = True
        starting_after = None
        invoice_count = 0
        max_invoices = 5000  # Safety limit

        while has_more and invoice_count < max_invoices:
            params = {
                "status": "paid",
                "created": {
                    "gte": start_ts,
                    "lte": end_ts,
                },
                "limit": 100,
            }
            if starting_after:
                params["starting_after"] = starting_after

            invoices = stripe.Invoice.list(**params)

            for inv in invoices.data:
                if not _is_trustoffice_invoice(inv):
                    continue
                invoice_count += 1
                amount = inv.amount_paid or inv.total or 0
                total_revenue_cents += amount
                total_transactions += 1

                # Stripe Invoice uses .customer (not .customer_id) for the customer ID
                customer_id = getattr(inv, 'customer', None)
                if customer_id:
                    customer_ids.add(customer_id)

                # Revenue by month
                inv_date = datetime.fromtimestamp(inv.created, tz=timezone.utc)
                month_key = inv_date.strftime("%Y-%m")
                revenue_by_month[month_key] += amount

                # Plan detection from line items
                plan_type = "monthly"
                try:
                    for line in inv.lines.data:
                        price_obj = getattr(line, 'price', None)
                        if price_obj:
                            price_id = getattr(price_obj, 'id', None)
                            if price_id == STRIPE_ANNUAL_PRICE_ID:
                                plan_type = "annual"
                                break
                            elif price_id == STRIPE_MONTHLY_PRICE_ID:
                                plan_type = "monthly"
                                break
                except Exception:
                    plan_type = "monthly"

                subscriptions_by_plan[plan_type] = subscriptions_by_plan.get(plan_type, 0) + 1

                # Recent transactions (keep last 50 for admin view)
                recent_transactions.append({
                    "date": inv_date.isoformat(),
                    "amount_cents": amount,
                    "plan": plan_type,
                    "status": inv.status,
                })

            has_more = invoices.has_more
            if has_more and invoices.data:
                starting_after = invoices.data[-1].id
            else:
                break

    except stripe.StripeError as e:
        logger.error(f"Stripe API error fetching revenue data: {e}")
        # Return partial data with error flag
        return {
            "stripe_error": str(e),
            "total_revenue_cents": 0,
            "total_transactions": 0,
            "paid_customers": 0,
            "revenue_by_month": {},
            "subscriptions_by_plan": {"monthly": 0, "annual": 0},
            "recent_transactions": [],
        }

    # Sort recent transactions by date descending, keep last 50
    recent_transactions.sort(key=lambda t: t["date"], reverse=True)
    recent_transactions = recent_transactions[:50]

    # Format revenue by month for response
    revenue_by_month_list = [
        {"month": k, "amount_cents": v}
        for k, v in sorted(revenue_by_month.items())
    ]

    return {
        "total_revenue_cents": total_revenue_cents,
        "total_transactions": total_transactions,
        "paid_customers": len(customer_ids),
        "revenue_by_month": revenue_by_month_list,
        "subscriptions_by_plan": subscriptions_by_plan,
        "recent_transactions": recent_transactions,
    }


async def _fetch_db_revenue_fallback(start_date: datetime, end_date: datetime):
    """
    Fallback: aggregate revenue from payment_transactions collection in MongoDB.
    """
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    pipeline = [
        {
            "$match": {
                "$or": [
                    {"payment_status": "paid"},
                    {"payment_status": "succeeded"},
                    {"status": "succeeded"},
                    {"status": "paid"},
                ],
                "created_at": {"$gte": start_str, "$lte": end_str},
            }
        },
        {
            "$group": {
                "_id": None,
                "total_cents": {"$sum": {"$multiply": ["$amount", 100]}},
                "count": {"$sum": 1},
            }
        },
    ]

    result = await db.payment_transactions.aggregate(pipeline).to_list(length=1)
    if result:
        return {
            "total_revenue_cents": result[0].get("total_cents", 0),
            "total_transactions": result[0].get("count", 0),
        }
    return {"total_revenue_cents": 0, "total_transactions": 0}


# ==================== STATS DASHBOARD ENDPOINT ====================

@router.get("/dashboard")
async def get_stats_dashboard(
    preset: str = Query("last_30_days", description="Date range preset: today, this_week, this_month, last_30_days, last_90_days, all_time"),
    start_date: Optional[str] = Query(None, description="Custom start date (ISO format). Overrides preset."),
    end_date: Optional[str] = Query(None, description="Custom end date (ISO format). Overrides preset."),
    user: dict = Depends(require_stats_or_admin),
):
    """
    Get revenue dashboard data for stats users and admins.
    Returns aggregated revenue data WITHOUT any customer-level details.
    """
    # Determine date range
    if start_date and end_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if end_dt <= start_dt:
                raise HTTPException(status_code=400, detail="end_date must be after start_date")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format.")
    else:
        start_dt, end_dt = _date_range_from_preset(preset)

    # Fetch Stripe data
    stripe_data = _fetch_stripe_revenue(start_dt, end_dt)

    # Fallback to DB if Stripe fails
    db_fallback = None
    if stripe_data.get("stripe_error"):
        db_fallback = await _fetch_db_revenue_fallback(start_dt, end_dt)

    # Calculate MRR and ARR from active subscriptions
    now = datetime.now(timezone.utc)
    monthly_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "monthly"})
    annual_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "annual"})

    # Monthly: $79/mo, Annual: $790/yr ≈ $65.83/mo
    mrr_cents = (monthly_active * 7900) + (annual_active * 6583)
    arr_cents = mrr_cents * 12

    # Total all-time from Stripe (quick query)
    all_time_data = _fetch_stripe_revenue(
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        now
    )

    # Calculate period-specific amounts
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    revenue_today_data = _fetch_stripe_revenue(today_start, now)
    revenue_this_week_data = _fetch_stripe_revenue(week_start, now)
    revenue_this_month_data = _fetch_stripe_revenue(month_start, now)

    # Average revenue per customer
    paid_customers = stripe_data.get("paid_customers", 0)
    avg_revenue_per_customer_cents = (
        stripe_data.get("total_revenue_cents", 0) // paid_customers
        if paid_customers > 0
        else 0
    )

    # Build response (NO customer-level data)
    response = {
        "total_revenue_cents": stripe_data.get("total_revenue_cents", 0),
        "total_revenue_formatted": f"${stripe_data.get('total_revenue_cents', 0) / 100:,.2f}",
        "mrr_cents": mrr_cents,
        "mrr_formatted": f"${mrr_cents / 100:,.2f}",
        "arr_cents": arr_cents,
        "arr_formatted": f"${arr_cents / 100:,.2f}",
        "total_transactions": stripe_data.get("total_transactions", 0),
        "paid_customers": paid_customers,
        "avg_revenue_per_customer_cents": avg_revenue_per_customer_cents,
        "avg_revenue_per_customer_formatted": f"${avg_revenue_per_customer_cents / 100:,.2f}",
        "revenue_by_month": stripe_data.get("revenue_by_month", []),
        "subscriptions_by_plan": stripe_data.get("subscriptions_by_plan", {"monthly": 0, "annual": 0}),
        "revenue_today_cents": revenue_today_data.get("total_revenue_cents", 0),
        "revenue_today_formatted": f"${revenue_today_data.get('total_revenue_cents', 0) / 100:,.2f}",
        "revenue_this_week_cents": revenue_this_week_data.get("total_revenue_cents", 0),
        "revenue_this_week_formatted": f"${revenue_this_week_data.get('total_revenue_cents', 0) / 100:,.2f}",
        "revenue_this_month_cents": revenue_this_month_data.get("total_revenue_cents", 0),
        "revenue_this_month_formatted": f"${revenue_this_month_data.get('total_revenue_cents', 0) / 100:,.2f}",
        "revenue_all_time_cents": all_time_data.get("total_revenue_cents", 0),
        "revenue_all_time_formatted": f"${all_time_data.get('total_revenue_cents', 0) / 100:,.2f}",
        "date_range": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "preset": preset,
        },
        "stripe_error": stripe_data.get("stripe_error"),
    }

    # If Stripe failed, use DB fallback
    if stripe_data.get("stripe_error") and db_fallback:
        response["total_revenue_cents"] = db_fallback.get("total_revenue_cents", 0)
        response["total_revenue_formatted"] = f"${db_fallback.get('total_revenue_cents', 0) / 100:,.2f}"
        response["total_transactions"] = db_fallback.get("total_transactions", 0)
        response["db_fallback_used"] = True

    return response