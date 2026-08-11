"""
Analytics Events Router — Durable funnel event recording
=========================================================
Provides an internal idempotent event recording system for funnel measurement.
Events are stored in MongoDB for durability and deduplication.

This is the server-side counterpart to client-side GA4/Meta Pixel tracking.
When external ad platform credentials are absent in server-side contexts,
we record events internally and document the delivery blocker.

Events recorded:
    - lead_captured: Fired when a new lead is captured via any marketing form
    - purchase_complete: Fired when Stripe confirms checkout.session.completed
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from routers.admin import require_admin
from pydantic import BaseModel
from typing import Optional

from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# ==================== EVENT SCHEMA ====================\

class AnalyticsEventIn(BaseModel):
    """Schema for recording an analytics event."""
    event_name: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None  # For idempotency
    metadata: Optional[dict] = None


# ==================== INTERNAL EVENT RECORDING ====================\

async def _record_event(
    event_name: str,
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """
    Record an analytics event durably in MongoDB.
    Idempotent: if an event with the same idempotency_key already exists,
    it returns the existing record without creating a duplicate.

    Args:
        event_name: The event type (e.g. 'lead_captured', 'purchase_complete')
        user_id: Optional user identifier
        session_id: Optional session identifier
        metadata: Additional event data (source, UTM params, etc.)
        idempotency_key: Optional key for deduplication

    Returns:
        dict: The inserted or existing event record
    """
    now = datetime.now(timezone.utc)
    event_doc = {
        "event_name": event_name,
        "user_id": user_id,
        "session_id": session_id,
        "metadata": metadata or {},
        "idempotency_key": idempotency_key,
        "created_at": now.isoformat(),
    }

    # The unique sparse index on idempotency_key is the race-safe dedupe gate.
    # A read-then-insert alone can duplicate under concurrent webhook delivery.
    if idempotency_key:
        try:
            result = await db.analytics_events.insert_one(event_doc)
        except Exception as exc:
            if "duplicate" not in str(exc).lower() and "e11000" not in str(exc).lower():
                raise
            existing = await db.analytics_events.find_one({"idempotency_key": idempotency_key})
            if existing:
                return existing
            raise
    else:
        result = await db.analytics_events.insert_one(event_doc)
    event_doc["_id"] = str(result.inserted_id)
    logger.info(
        f"Analytics event recorded: {event_name} "
        f"(idempotency_key={idempotency_key or 'none'})"
    )
    return event_doc


# ==================== PUBLIC HELPERS ====================\

async def record_lead_capture(
    *,
    lead_id: str,
    source: Optional[str] = None,
    utm_source: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_medium: Optional[str] = None,
    referrer: Optional[str] = None,
    is_returning: bool = False,
) -> dict:
    """
    Record a lead_capture analytics event with full attribution data.
    Idempotent by lead_id + source combination.

    This is called from the /admin/leads/capture endpoint after a lead
    is successfully created or updated in the CRM.
    """
    idempotency_key = f"lead_capture_{lead_id}_{source or 'unknown'}"

    metadata = {
        "lead_id": lead_id,
        "source": source or "unknown",
        "utm_source": utm_source,
        "utm_campaign": utm_campaign,
        "utm_medium": utm_medium,
        "referrer": referrer,
        "is_returning": is_returning,
    }

    return await _record_event(
        "lead_captured",
        user_id=None,  # Leads may not have user accounts yet
        session_id=lead_id,
        metadata=metadata,
        idempotency_key=idempotency_key,
    )


async def record_purchase_complete(
    *,
    user_id: str,
    plan_type: str,
    billing_period: str,
    amount: float,
    checkout_session_id: str,
    stripe_subscription_id: Optional[str] = None,
    referral_id: Optional[str] = None,
    coupon: Optional[str] = None,
) -> dict:
    """
    Record a purchase_complete analytics event server-side.
    Idempotent by checkout_session_id.

    This is called from the Stripe webhook handler when
    checkout.session.completed is received. It provides a durable,
    server-confirmed record of the purchase that does not depend
    on the browser executing JavaScript.

    EXTERNAL DELIVERY BLOCKER: GA4 and Meta Pixel server-side APIs
    are not configured for this deployment. The event is recorded
    internally for funnel measurement. To forward events to GA4/Meta,
    configure server-side API credentials and add delivery calls here.

    Args:
        user_id: TrustOffice user ID
        plan_type: e.g. 'trustee', 'estate', 'advisor', 'wingpoint'
        billing_period: 'monthly' or 'annual'
        amount: Revenue in USD
        checkout_session_id: Stripe checkout session ID
        stripe_subscription_id: Stripe subscription ID if available
        referral_id: Rewardful referral ID if applicable
        coupon: Coupon code if applied
    """
    idempotency_key = f"purchase_{checkout_session_id}"

    metadata = {
        "user_id": user_id,
        "plan_type": plan_type,
        "billing_period": billing_period,
        "amount": amount,
        "currency": "USD",
        "checkout_session_id": checkout_session_id,
        "stripe_subscription_id": stripe_subscription_id,
        "referral_id": referral_id,
        "coupon": coupon,
    }

    event = await _record_event(
        "purchase_complete",
        user_id=user_id,
        session_id=checkout_session_id,
        metadata=metadata,
        idempotency_key=idempotency_key,
    )

    logger.info(
        f"Purchase recorded: user={user_id} plan={plan_type} "
        f"amount=${amount} session={checkout_session_id}"
    )

    return event


# ==================== ANALYTICS ENDPOINTS (Admin) ====================\

@router.get("/events")
async def get_analytics_events(
    event_name: Optional[str] = None,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    skip: int = 0,
    admin: dict = Depends(require_admin),
):
    """
    Query analytics events for reporting and funnel analysis.
    Admin-only in production — add auth if exposing externally.
    """
    query = {}
    if event_name:
        query["event_name"] = event_name
    if user_id:
        query["user_id"] = user_id
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date and "created_at" in query:
        query["created_at"]["$lte"] = end_date
    elif end_date:
        query["created_at"] = {"$lte": end_date}

    cursor = db.analytics_events.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit)
    events = await cursor.to_list(length=limit)

    total = await db.analytics_events.count_documents(query)

    return {
        "events": events,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@router.get("/funnel-summary")
async def get_funnel_summary(admin: dict = Depends(require_admin)):
    """
    Get funnel conversion summary: lead captures vs purchase completions.
    """
    total_leads = await db.analytics_events.count_documents(
        {"event_name": "lead_captured"}
    )
    total_purchases = await db.analytics_events.count_documents(
        {"event_name": "purchase_complete"}
    )

    # Unique users who purchased
    purchase_pipeline = [
        {"$match": {"event_name": "purchase_complete"}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "unique_purchasers"},
    ]
    purchase_users = list(
        await db.analytics_events.aggregate(purchase_pipeline).to_list(1)
    )
    unique_purchasers = (
        purchase_users[0]["unique_purchasers"] if purchase_users else 0
    )

    # Conversion rate
    conversion_rate = (
        round((total_purchases / total_leads) * 100, 2) if total_leads > 0 else 0
    )

    # Purchase by plan type
    plan_pipeline = [
        {"$match": {"event_name": "purchase_complete"}},
        {"$group": {
            "_id": "$metadata.plan_type",
            "count": {"$sum": 1},
            "total_revenue": {"$sum": "$metadata.amount"},
        }},
        {"$sort": {"count": -1}},
    ]
    plan_breakdown = list(await db.analytics_events.aggregate(plan_pipeline).to_list(50))

    return {
        "total_lead_captures": total_leads,
        "total_purchases": total_purchases,
        "unique_purchasers": unique_purchasers,
        "conversion_rate_pct": conversion_rate,
        "plan_breakdown": [
            {
                "plan_type": p["_id"],
                "count": p["count"],
                "total_revenue": p["total_revenue"],
            }
            for p in plan_breakdown
        ],
    }