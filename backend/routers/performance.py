# Performance router — contractor/lead performance metrics dashboard
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict
import logging

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["performance"])


# ==================== HELPERS ====================\

def _month_key(dt: datetime) -> str:
    """Return 'YYYY-MM' string for a datetime."""
    return dt.strftime("%Y-%m")


def _start_of_month(year: int, month: int) -> datetime:
    """Return timezone-aware start-of-month datetime."""
    return datetime(year, month, 1, tzinfo=timezone.utc)


def _compute_compliance_score(trust: dict) -> int:
    """
    Compute a simple compliance score (0-100) for a trust based on:
    - Governance tasks completion rate
    - Minutes-to-distributions ratio
    - Health score snapshot
    """
    score = 50  # base

    # Boost if governance tasks exist and some are completed
    governance_tasks = trust.get("governance_task_count", 0)
    if governance_tasks > 0:
        score += min(20, governance_tasks * 5)

    # Boost if minutes exist
    minutes_count = trust.get("minutes_count", 0)
    if minutes_count > 0:
        score += min(15, minutes_count * 3)

    # Boost if distributions exist
    distributions_count = trust.get("distributions_count", 0)
    if distributions_count > 0:
        score += min(15, distributions_count * 2)

    return min(100, score)


async def _get_user_trusts(user_id: str) -> list:
    """Fetch all trusts for the given user with performance-relevant counts."""
    trusts_cursor = db.trusts.find({"user_id": user_id}, {"_id": 0})
    trusts_list = await trusts_cursor.to_list(length=200)

    enriched = []
    for trust in trusts_list:
        trust_id = trust.get("trust_id")

        # Count minutes
        minutes_count = await db.minutes_records.count_documents(
            {"trust_id": trust_id, "user_id": user_id}
        )

        # Count distributions
        distributions_count = await db.distribution_records.count_documents(
            {"trust_id": trust_id, "user_id": user_id}
        )

        # Count governance tasks
        governance_count = await db.governance_tasks.count_documents(
            {"trust_id": trust_id, "user_id": user_id}
        )

        enriched.append({
            **trust,
            "minutes_count": minutes_count,
            "distributions_count": distributions_count,
            "governance_task_count": governance_count,
            "compliance_score": _compute_compliance_score({
                **trust,
                "governance_task_count": governance_count,
                "minutes_count": minutes_count,
                "distributions_count": distributions_count,
            }),
        })

    return enriched


# ==================== ENDPOINTS ====================\


@router.get("/summary")
async def get_performance_summary(user: dict = Depends(get_current_user)):
    """
    GET /api/performance/summary
    Aggregated KPIs for the current user's trusts:
    - trusts managed
    - minutes created
    - distributions processed
    - compliance score (average across trusts)
    """
    user_id = user["user_id"]
    trusts = await _get_user_trusts(user_id)

    total_trusts = len(trusts)
    total_minutes = sum(t.get("minutes_count", 0) for t in trusts)
    total_distributions = sum(t.get("distributions_count", 0) for t in trusts)
    avg_compliance = round(
        sum(t.get("compliance_score", 0) for t in trusts) / max(total_trusts, 1)
    )

    # Distributions by status
    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }
        },
    ]
    dist_status = await db.distribution_records.aggregate(pipeline).to_list(length=20)
    distribution_status_breakdown = {
        s["_id"]: s["count"] for s in dist_status
    }

    return {
        "trusts_managed": total_trusts,
        "minutes_created": total_minutes,
        "distributions_processed": total_distributions,
        "compliance_score": avg_compliance,
        "distribution_status_breakdown": distribution_status_breakdown,
        "trusts": [
            {
                "trust_id": t["trust_id"],
                "name": t.get("name", ""),
                "minutes_count": t["minutes_count"],
                "distributions_count": t["distributions_count"],
                "compliance_score": t["compliance_score"],
            }
            for t in trusts
        ],
    }


@router.get("/trends")
async def get_performance_trends(
    months: int = Query(6, ge=1, le=12, description="Number of months to look back"),
    user: dict = Depends(get_current_user),
):
    """
    GET /api/performance/trends
    Monthly trends for the last N months:
    - minutes created per month
    - distributions processed per month
    - distributions approved per month
    """
    user_id = user["user_id"]
    now = datetime.now(timezone.utc)

    months_data = []
    for i in range(months - 1, -1, -1):
        target = now - timedelta(days=i * 30)
        year = target.year
        month = target.month

        start_of_month = _start_of_month(year, month)
        if month == 12:
            end_of_month = _start_of_month(year + 1, 1)
        else:
            end_of_month = _start_of_month(year, month + 1)

        month_key = _month_key(target)

        # Count minutes for this month
        minutes_count = await db.minutes_records.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": start_of_month.isoformat(), "$lt": end_of_month.isoformat()},
        })

        # Count distributions for this month
        dist_count = await db.distribution_records.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": start_of_month.isoformat(), "$lt": end_of_month.isoformat()},
        })

        # Count approved distributions
        approved_count = await db.distribution_records.count_documents({
            "user_id": user_id,
            "approved_at": {"$ne": None},
            "created_at": {"$gte": start_of_month.isoformat(), "$lt": end_of_month.isoformat()},
        })

        months_data.append({
            "month": month_key,
            "minutes_created": minutes_count,
            "distributions_processed": dist_count,
            "distributions_approved": approved_count,
        })

    return {"trends": months_data, "period_months": months}


@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = Query(20, ge=1, le=100, description="Max activities to return"),
    user: dict = Depends(get_current_user),
):
    """
    GET /api/performance/recent-activity
    Last N actions across all trusts, combining:
    - Recent minutes
    - Recent distributions
    - Recent governance tasks
    """
    user_id = user["user_id"]

    activities = []

    # --- Recent minutes ---
    recent_minutes = await db.minutes_records.find(
        {"user_id": user_id},
        {"_id": 0, "minutes_id": 1, "trust_id": 1, "minutes_type": 1,
         "meeting_date": 1, "status": 1, "created_at": 1, "template_type": 1}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)

    for m in recent_minutes:
        trust = await db.trusts.find_one(
            {"trust_id": m.get("trust_id"), "user_id": user_id},
            {"_id": 0, "name": 1}
        )
        activities.append({
            "id": "minutes_" + str(m.get("minutes_id", "")),
            "type": "minutes",
            "action": "minutes_created" if m.get("status") == "finalized" else "minutes_drafted",
            "description": (
                (m.get("minutes_type", "General") or "General").title() + " minutes"
                + (" — " + (m.get("template_type") or "").replace("_", " ").title()
                   if m.get("template_type") else "")
            ),
            "trust_id": m.get("trust_id"),
            "trust_name": trust.get("name", "") if trust else "",
            "date": m.get("created_at", ""),
            "status": m.get("status", ""),
        })

    # --- Recent distributions ---
    recent_distributions = await db.distribution_records.find(
        {"user_id": user_id},
        {"_id": 0, "distribution_id": 1, "trust_id": 1, "beneficiary_name": 1,
         "amount": 1, "purpose_classification": 1, "status": 1,
         "approved_at": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)

    for d in recent_distributions:
        trust = await db.trusts.find_one(
            {"trust_id": d.get("trust_id"), "user_id": user_id},
            {"_id": 0, "name": 1}
        )
        if d.get("approved_at"):
            action = "distribution_approved"
        elif d.get("status") == "review":
            action = "distribution_reviewed"
        else:
            action = "distribution_created"

        purpose = (d.get("purpose_classification") or "").replace("_", " ").title()
        beneficiary = d.get("beneficiary_name", "Unknown")
        amount = d.get("amount", 0)

        activities.append({
            "id": "dist_" + str(d.get("distribution_id", "")),
            "type": "distribution",
            "action": action,
            "description": "Distribution to " + beneficiary + " — $" + f"{amount:,.2f}" + " (" + purpose + ")",
            "trust_id": d.get("trust_id"),
            "trust_name": trust.get("name", "") if trust else "",
            "date": d.get("created_at", ""),
            "status": d.get("status", ""),
            "amount": amount,
        })

    # --- Recent governance tasks ---
    recent_tasks = await db.governance_tasks.find(
        {"user_id": user_id},
        {"_id": 0, "task_id": 1, "trust_id": 1, "task_type": 1,
         "description": 1, "due_date": 1, "completed_at": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)

    for t in recent_tasks:
        trust = await db.trusts.find_one(
            {"trust_id": t.get("trust_id"), "user_id": user_id},
            {"_id": 0, "name": 1}
        )
        if t.get("completed_at"):
            action = "task_completed"
        else:
            action = "task_created"

        description = t.get("description") or t.get("task_type", "Task").replace("_", " ").title()
        activity_date = t.get("completed_at") or t.get("due_date") or ""
        status = "completed" if t.get("completed_at") else "upcoming"

        activities.append({
            "id": "task_" + str(t.get("task_id", "")),
            "type": "task",
            "action": action,
            "description": description,
            "trust_id": t.get("trust_id"),
            "trust_name": trust.get("name", "") if trust else "",
            "date": activity_date,
            "status": status,
        })

    # Sort all activities by date descending, take top N
    activities.sort(key=lambda a: a.get("date", ""), reverse=True)
    activities = activities[:limit]

    return {"activities": activities, "total": len(activities)}


@router.get("/benchmarks")
async def get_benchmarks(user: dict = Depends(get_current_user)):
    """
    GET /api/performance/benchmarks
    Peer comparison data aggregated across all users (anonymized).
    Returns distributions, minutes, and compliance benchmarks by plan tier.
    """
    now = datetime.now(timezone.utc)
    six_months_ago = (now - timedelta(days=180)).isoformat()

    # --- Minutes aggregate stats ---
    pipeline_minutes = [
        {"$match": {"created_at": {"$gte": six_months_ago}}},
        {
            "$group": {
                "_id": None,
                "total_minutes": {"$sum": 1},
            }
        },
    ]
    minutes_stats = await db.minutes_records.aggregate(pipeline_minutes).to_list(length=1)
    total_minutes_6mo = minutes_stats[0]["total_minutes"] if minutes_stats else 0

    # --- Distributions aggregate stats ---
    pipeline_dist = [
        {"$match": {"created_at": {"$gte": six_months_ago}}},
        {
            "$group": {
                "_id": None,
                "total_distributions": {"$sum": 1},
                "total_amount_cents": {"$sum": {"$multiply": ["$amount", 100]}},
                "approved_count": {
                    "$sum": {"$cond": [{"$ne": ["$approved_at", None]}, 1, 0]}
                },
            }
        },
    ]
    dist_stats = await db.distribution_records.aggregate(pipeline_dist).to_list(length=1)
    if dist_stats:
        total_distributions_6mo = dist_stats[0]["total_distributions"]
        total_amount_cents = dist_stats[0]["total_amount_cents"]
        approved_count = dist_stats[0]["approved_count"]
    else:
        total_distributions_6mo = 0
        total_amount_cents = 0
        approved_count = 0

    approval_rate = round(approved_count / max(total_distributions_6mo, 1) * 100, 1)

    # --- Monthly trend for platform-wide activity ---
    monthly_minutes = await db.minutes_records.aggregate([
        {"$match": {"created_at": {"$gte": six_months_ago}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": {"$toDate": "$created_at"}}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]).to_list(length=12)

    monthly_distributions = await db.distribution_records.aggregate([
        {"$match": {"created_at": {"$gte": six_months_ago}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": {"$toDate": "$created_at"}}},
                "count": {"$sum": 1},
                "approved": {
                    "$sum": {"$cond": [{"$ne": ["$approved_at", None]}, 1, 0]}
                },
            }
        },
        {"$sort": {"_id": 1}},
    ]).to_list(length=12)

    monthly_minutes_map = {m["_id"]: m["count"] for m in monthly_minutes if m.get("_id")}
    monthly_dist_map = {
        d["_id"]: {
            "total": d["count"],
            "approved": d["approved"],
        }
        for d in monthly_distributions if d.get("_id")
    }

    all_months = sorted(set(list(monthly_minutes_map.keys()) + list(monthly_dist_map.keys())))
    monthly_trends = []
    for m in all_months:
        monthly_trends.append({
            "month": m,
            "minutes": monthly_minutes_map.get(m, 0),
            "distributions_total": monthly_dist_map.get(m, {}).get("total", 0),
            "distributions_approved": monthly_dist_map.get(m, {}).get("approved", 0),
        })

    # --- Trust distribution across users ---
    pipeline_trusts = [
        {"$match": {"created_at": {"$gte": six_months_ago}}},
        {
            "$group": {
                "_id": "$user_id",
                "trust_count": {"$sum": 1},
            }
        },
        {
            "$group": {
                "_id": "$trust_count",
                "user_count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    trust_distribution = await db.trusts.aggregate(pipeline_trusts).to_list(length=20)

    # --- Top performing trusts by activity ---
    all_user_trusts = await db.trusts.find(
        {"created_at": {"$gte": six_months_ago}},
        {"_id": 0, "trust_id": 1, "user_id": 1}
    ).to_list(length=100)

    trust_activity = []
    for t in all_user_trusts[:10]:
        tid = t["trust_id"]
        uid = t["user_id"]
        mc = await db.minutes_records.count_documents({"trust_id": tid, "user_id": uid})
        dc = await db.distribution_records.count_documents({"trust_id": tid, "user_id": uid})
        trust_activity.append({
            "trust_id": tid,
            "minutes_count": mc,
            "distributions_count": dc,
        })

    trust_activity.sort(key=lambda x: x["minutes_count"] + x["distributions_count"], reverse=True)

    return {
        "platform_stats": {
            "total_minutes_6mo": total_minutes_6mo,
            "total_distributions_6mo": total_distributions_6mo,
            "total_distribution_amount_cents": total_amount_cents,
            "approval_rate": approval_rate,
        },
        "trust_distribution": [
            {"trusts_count": t["_id"], "users_count": t["user_count"]}
            for t in trust_distribution
        ],
        "monthly_trends": monthly_trends,
        "top_trusts_by_activity": trust_activity[:5],
    }