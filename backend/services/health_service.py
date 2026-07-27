"""
Health service — health score trends, alerts, snapshots, and cross-trust summaries.

Phase 3 (Health Score & Deadline Tracking) of the TrustOffice plan.

The scoring engine itself lives in routers/governance.py (calculate_health_score);
this service provides read-oriented operations over db.health_score_snapshots
plus a thin wrapper to force fresh snapshots.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from database import db

# Action suggestions per health criterion (mirrors CRITERIA_CONFIG in governance.py)
_ACTION_SUGGESTIONS = {
    "Quarterly Minutes": "Record quarterly minutes to document trustee decisions.",
    "Task Compliance": "Complete overdue governance tasks on the calendar.",
    "Compensation Alignment": "Review trustee compensation against the approved plan.",
    "Distribution Documentation": "Log distributions with proper documentation.",
    "Annual Review": "Schedule and complete the annual trust review.",
    "Asset Valuation Freshness": "Update asset valuations on Schedule A.",
    "Transaction Classification": "Classify untagged trust transactions.",
    "Separation Alert Health": "Review and resolve active separation alerts.",
}


async def get_owned_trust(trust_id: str, user_id: str) -> Optional[dict]:
    """Fetch a trust only if owned by this user (mirrors meeting_service pattern)."""
    return await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )


async def get_health_trend(trust_id: str, user_id: str, days: int = 90) -> List[dict]:
    """Health score trend over time.

    Queries db.health_score_snapshots, deduplicates by calendar date (keeps the
    latest snapshot per day), and returns ascending by date. Each entry includes
    the criteria breakdown when available (schema v2 snapshots).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    snapshots = await db.health_score_snapshots.find(
        {"trust_id": trust_id, "user_id": user_id, "calculated_at": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("calculated_at", -1).to_list(2000)

    daily: dict = {}
    for snap in snapshots:
        date_key = snap["calculated_at"][:10]
        if date_key not in daily:  # first seen = latest for that date (sorted desc)
            entry = {
                "date": date_key,
                "score": snap.get("score_value", 0),
                "color": snap.get("color", "unknown"),
            }
            if snap.get("criteria_breakdown"):
                entry["criteria_breakdown"] = snap["criteria_breakdown"]
            if snap.get("base_score") is not None:
                entry["base_score"] = snap["base_score"]
            if snap.get("risk_penalty") is not None:
                entry["risk_penalty"] = snap["risk_penalty"]
            daily[date_key] = entry

    return sorted(daily.values(), key=lambda x: x["date"])


async def get_health_alerts(trust_id: str, user_id: str) -> List[dict]:
    """Active health alerts derived from the most recent snapshot.

    Failed criteria (achieved=False, no_data=False) become alerts with a
    human-readable action suggestion. If no snapshot exists, a fresh score is
    calculated (without saving) and its criteria used instead.
    """
    snapshot = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        sort=[("calculated_at", -1)],
        projection={"_id": 0},
    )

    criteria: List[dict] = []
    if snapshot and snapshot.get("criteria_breakdown"):
        criteria = snapshot["criteria_breakdown"]
    else:
        # No snapshot yet — calculate on the fly (no save)
        from routers.governance import calculate_health_score
        result = await calculate_health_score(trust_id, user_id, save_snapshot=False)
        criteria = result.get("criteria", [])

    alerts: List[dict] = []
    for c in criteria:
        if c.get("achieved") or c.get("no_data"):
            continue
        name = c.get("name", "Unknown")
        points_lost = c.get("max_points", 0) - c.get("points", 0)
        if points_lost <= 0:
            continue
        alerts.append({
            "criterion_name": name,
            "description": c.get("description") or f"{name} is not satisfied.",
            "points_lost": points_lost,
            "action_suggestion": _ACTION_SUGGESTIONS.get(
                name, "Review this criterion in the governance dashboard."
            ),
        })

    alerts.sort(key=lambda a: a["points_lost"], reverse=True)
    return alerts


async def get_snapshots(trust_id: str, user_id: str, limit: int = 30) -> List[dict]:
    """Raw snapshot list, most recent first, for detailed analysis."""
    return await db.health_score_snapshots.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
    ).sort("calculated_at", -1).to_list(limit)


async def force_snapshot(trust_id: str, user_id: str) -> dict:
    """Force a fresh health score calculation and persist a snapshot."""
    from routers.governance import calculate_health_score
    return await calculate_health_score(trust_id, user_id, save_snapshot=True)


async def get_client_health_summary(client_id: str, user_id: str) -> dict:
    """Aggregate health across all trusts linked to a client.

    Returns avg score (latest snapshot per trust), trust count by color, and
    the worst-performing criteria across all trusts.
    """
    trusts = await db.trusts.find(
        {"client_id": client_id, "user_id": user_id},
        {"_id": 0, "trust_id": 1, "trust_name": 1},
    ).to_list(500)

    trust_ids = [t["trust_id"] for t in trusts]
    if not trust_ids:
        return {
            "client_id": client_id,
            "trust_count": 0,
            "avg_score": None,
            "by_color": {},
            "worst_criteria": [],
            "trusts": [],
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Latest snapshot per trust
    per_trust: List[dict] = []
    color_counts: dict = {"green": 0, "yellow": 0, "red": 0}
    scores: List[int] = []
    criteria_totals: dict = {}  # name -> {"points_lost": int, "trusts": int}

    for trust in trusts:
        snap = await db.health_score_snapshots.find_one(
            {"trust_id": trust["trust_id"], "user_id": user_id},
            sort=[("calculated_at", -1)],
            projection={"_id": 0},
        )
        if not snap:
            per_trust.append({
                "trust_id": trust["trust_id"],
                "trust_name": trust.get("trust_name"),
                "score": None,
                "color": "no_data",
            })
            continue

        score = snap.get("score_value", 0)
        color = snap.get("color", "unknown")
        scores.append(score)
        color_counts[color] = color_counts.get(color, 0) + 1
        per_trust.append({
            "trust_id": trust["trust_id"],
            "trust_name": trust.get("trust_name"),
            "score": score,
            "color": color,
            "calculated_at": snap.get("calculated_at"),
        })

        for c in snap.get("criteria_breakdown", []) or []:
            if c.get("achieved") or c.get("no_data"):
                continue
            name = c.get("name", "Unknown")
            lost = c.get("max_points", 0) - c.get("points", 0)
            if lost <= 0:
                continue
            agg = criteria_totals.setdefault(name, {"points_lost": 0, "trusts": 0})
            agg["points_lost"] += lost
            agg["trusts"] += 1

    worst = sorted(
        (
            {
                "criterion_name": name,
                "total_points_lost": v["points_lost"],
                "affected_trusts": v["trusts"],
                "action_suggestion": _ACTION_SUGGESTIONS.get(
                    name, "Review this criterion in the governance dashboard."
                ),
            }
            for name, v in criteria_totals.items()
        ),
        key=lambda x: x["total_points_lost"],
        reverse=True,
    )

    return {
        "client_id": client_id,
        "trust_count": len(trusts),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "by_color": color_counts,
        "worst_criteria": worst,
        "trusts": per_trust,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
