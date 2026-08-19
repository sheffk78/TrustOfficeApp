# Governance router - handles health score, history, onboarding, activity, and dashboard
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid

from database import db
from dependencies import (
    get_current_user, get_subscription_state, require_write_access,
    check_feature_access, Feature,
    PREMIUM_FEATURE_ERROR_MESSAGE, PREMIUM_FEATURE_ERROR_CODE
)
from models import (
    HealthScoreResponse, HealthScoreCriterion, HealthColor,
    OnboardingState, GovernanceInsight, DashboardStats,
    DashboardResponse, DashboardSubscriptionState,
    DismissedInsightCreate, DismissedInsightResponse
)
from routers.tasks import CHECKLIST_TEMPLATES
from services.risk_gathering import gather_risk_findings, compute_risk_penalty

router = APIRouter(tags=["governance"])


# ==================== CRITERIA CONFIG ====================

CRITERIA_CONFIG = {
    "Quarterly Minutes": {
        "max_points": 15,
        "insight_type": "warning",
        "insight_title": "Missing Q Minutes",
        "insight_desc": "Generate minutes this quarter to earn +{max_points} points",
        "action_path": "/minutes/new",
        "action_label": "Record Now",
    },
    "Task Compliance": {
        "max_points": 15,
        "insight_type": "error",
        "insight_title": "Overdue Tasks",
        "insight_desc": "Complete overdue tasks to earn +{max_points} points",
        "action_path": "/calendar",
        "action_label": "View Tasks",
    },
    "Compensation Alignment": {
        "max_points": 15,
        "insight_type": "error",
        "insight_title": "Compensation Over Plan",
        "insight_desc": "YTD compensation exceeds approved amount",
        "action_path": "/compensation",
        "action_label": "Review",
    },
    "Distribution Documentation": {
        "max_points": 15,
        "insight_type": "warning",
        "insight_title": "Distribution Documentation",
        "insight_desc": "Log distributions and document benevolence details",
        "action_path": "/distributions",
        "action_label": "Review Distributions",
    },
    "Annual Review": {
        "max_points": 15,
        "insight_type": "warning",
        "insight_title": "Schedule Annual Review",
        "insight_desc": "Schedule your annual review for +{max_points} points",
        "action_path": "/calendar?action=create_annual_review",
        "action_label": "Schedule Review",
    },
    "Asset Valuation Freshness": {
        "max_points": 15,
        "insight_type": "warning",
        "insight_title": "Asset Re-Valuation Needed",
        "insight_desc": "Update asset valuations to earn +{max_points} points",
        "action_path": "/schedule-a",
        "action_label": "Update Assets",
    },
    "Transaction Classification": {
        "max_points": 10,
        "insight_type": "warning",
        "insight_title": "Classify Transactions",
        "insight_desc": "Classify untagged transactions to earn +{max_points} points",
        "action_path": "/transactions",
        "action_label": "Review Transactions",
    },
    "Separation Alert Health": {
        "max_points": 15,
        "insight_type": "error",
        "insight_title": "Active Separation Alerts",
        "insight_desc": "Review and resolve separation alerts to earn +{max_points} points",
        "action_path": "/risk",
        "action_label": "View Alerts",
    },
}

TOTAL_MAX_POINTS = sum(c["max_points"] for c in CRITERIA_CONFIG.values())  # 115


# ==================== HELPER FUNCTIONS ====================

def get_quarter_start(dt: datetime) -> datetime:
    """Get the start of the current quarter"""
    quarter = (dt.month - 1) // 3
    month = quarter * 3 + 1
    return datetime(dt.year, month, 1, tzinfo=timezone.utc)


def get_year_start(dt: datetime) -> datetime:
    """Get the start of the current year"""
    return datetime(dt.year, 1, 1, tzinfo=timezone.utc)


async def ensure_transaction_review_task(trust_id: str, user_id: str):
    """Ensure a monthly transaction classification review task exists for the current month"""
    now = datetime.now(timezone.utc)
    # Check for an existing transaction_review task due this month
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc).isoformat()

    existing = await db.governance_tasks.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "task_type": "transaction_review",
        "due_date": {"$gte": month_start, "$lt": next_month}
    })

    if not existing:
        # Only create if this trust has transactions
        txn_count = await db.transactions.count_documents({"trust_id": trust_id, "user_id": user_id})
        if txn_count > 0:
            # Due on the last day of the month
            if now.month == 12:
                due = datetime(now.year, 12, 31, tzinfo=timezone.utc)
            else:
                due = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)

            task_type = "transaction_review"
            checklist_items = CHECKLIST_TEMPLATES.get(task_type, [])
            
            await db.governance_tasks.insert_one({
                "task_id": f"task_{uuid.uuid4().hex[:12]}",
                "trust_id": trust_id,
                "user_id": user_id,
                "task_type": task_type,
                "due_date": due.isoformat(),
                "description": "Monthly Transaction Classification Review — classify any untagged imported transactions and review separation alerts",
                "checklist_items": checklist_items,
                "status": "pending",
                "completed_at": None,
                "created_at": now.isoformat()
            })


async def _gather_minutes_data(trust_id: str, user_id: str, quarter_start: datetime) -> int:
    """Count quarterly minutes from both minutes_records and minutes_templates."""
    quarterly_minutes_records = await db.minutes_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$gte": quarter_start.isoformat()}
    })
    quarterly_minutes_templates = await db.minutes_templates.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$gte": quarter_start.isoformat()},
        "status": {"$in": ["final", "finalized", "draft"]}
    })
    return quarterly_minutes_records + quarterly_minutes_templates


async def _gather_compensation_data(trust_id: str, user_id: str, year_start: datetime) -> tuple:
    """Return (comp_plan, ytd_total, approved_amount) for compensation alignment."""
    comp_plan = await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    ytd_total = 0
    approved_amount = 0
    if comp_plan:
        ytd_payments = await db.compensation_payments.find(
            {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start.isoformat()}},
            {"_id": 0}
        ).to_list(1000)
        ytd_total = sum(p.get("amount", 0) for p in ytd_payments)
        approved_amount = comp_plan.get("annual_approved_amount") or comp_plan.get("annual_fee") or comp_plan.get("annual_amount", 0)
    return comp_plan, ytd_total, approved_amount


async def _gather_risk_findings(trust_id: str, trust_doc: dict, now: datetime, today, use_cache: bool) -> list:
    """Gather risk findings, using TTL cache (5 min) if use_cache=True."""
    risk_findings = None
    if use_cache:
        cached = await db.risk_findings_cache.find_one({
            "trust_id": trust_id,
            "cached_at": {"$gte": (now - timedelta(minutes=5)).isoformat()}
        })
        if cached:
            risk_findings = cached.get("findings")

    if risk_findings is None:
        risk_findings = await gather_risk_findings(
            trust_id, trust_doc, db, today, include_separation_alerts=False
        )
        if use_cache:
            await db.risk_findings_cache.update_one(
                {"trust_id": trust_id},
                {"$set": {"findings": risk_findings, "cached_at": now.isoformat()}},
                upsert=True
            )
    return risk_findings


async def _gather_score_data(trust_id: str, user_id: str, use_cache: bool = False) -> dict:
    """Async: gather all raw DB data needed for health score. Returns dict of raw metrics.
    If use_cache=True, tries to load risk findings from TTL cache (5 min) before gathering fresh.
    """
    now = datetime.now(timezone.utc)
    quarter_start = get_quarter_start(now)
    year_start = get_year_start(now)
    one_year_ago = (now - timedelta(days=365))

    quarterly_minutes = await _gather_minutes_data(trust_id, user_id, quarter_start)

    total_tasks = await db.governance_tasks.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    overdue_tasks = await db.governance_tasks.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "completed_at": None,
        "due_date": {"$lt": now.isoformat()}
    })

    comp_plan, ytd_total, approved_amount = await _gather_compensation_data(trust_id, user_id, year_start)

    dist_count = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    benevolence_dists = await db.distribution_records.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "is_benevolence": True
    }, {"_id": 0}).to_list(1000)

    annual_review = await db.governance_tasks.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "task_type": "annual_review",
        "completed_at": {"$gte": one_year_ago.isoformat()}
    }, {"_id": 0})

    trust_doc_for_created = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0, "created_at": 1})
    trust_created_at = trust_doc_for_created.get("created_at") if trust_doc_for_created else None

    active_assets = await db.schedule_a_items.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    }, {"_id": 0, "description": 1, "last_valued_date": 1, "date_conveyed": 1}).to_list(1000)

    total_txns = await db.transactions.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    classified_txns = 0
    if total_txns > 0:
        classified_txns = await db.transactions.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "classification": {"$exists": True, "$ne": None, "$ne": ""}
        })

    active_alert_count = await db.separation_alerts.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    })

    trust_doc = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0}) or {}
    today = now.date()
    risk_findings = await _gather_risk_findings(trust_id, trust_doc, now, today, use_cache)

    return {
        "now": now,
        "quarterly_minutes": quarterly_minutes,
        "total_tasks": total_tasks,
        "overdue_tasks": overdue_tasks,
        "comp_plan": comp_plan,
        "ytd_total": ytd_total,
        "approved_amount": approved_amount,
        "dist_count": dist_count,
        "benevolence_dists": benevolence_dists,
        "annual_review": annual_review,
        "trust_created_at": trust_created_at,
        "active_assets": active_assets,
        "twelve_months_ago": one_year_ago,
        "total_txns": total_txns,
        "classified_txns": classified_txns,
        "active_alert_count": active_alert_count,
        "risk_findings": risk_findings,
    }


def _parse_trust_created_age(trust_created_at: Optional[str], now: datetime) -> bool:
    """Check if trust is new (created <90 days ago). Returns False if no valid date."""
    if not trust_created_at:
        return False
    try:
        if "T" in trust_created_at:
            created = datetime.fromisoformat(trust_created_at.replace("Z", "+00:00"))
        else:
            created = datetime.fromisoformat(trust_created_at).replace(tzinfo=timezone.utc)
        return (now - created).days < 90
    except (ValueError, TypeError):
        return False


def _parse_asset_valuation_date(valuation_ref_str: str) -> Optional[datetime]:
    """Parse an asset valuation/conveyance date string, returning None on failure."""
    if not valuation_ref_str:
        return None
    try:
        if "T" in valuation_ref_str:
            return datetime.fromisoformat(valuation_ref_str.replace("Z", "+00:00"))
        return datetime.fromisoformat(valuation_ref_str).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _is_asset_stale(asset: dict, twelve_months_ago: datetime) -> bool:
    """Check if a single asset's valuation is stale (>12 months old or missing)."""
    valuation_ref_str = asset.get("last_valued_date") or asset.get("date_conveyed")
    if not valuation_ref_str:
        return True
    valuation_ref = _parse_asset_valuation_date(valuation_ref_str)
    if valuation_ref is None:
        return True
    return valuation_ref < twelve_months_ago


def _compute_quarterly_minutes_criterion(data: dict) -> tuple:
    """Returns (HealthScoreCriterion, points) for Quarterly Minutes."""
    mp = CRITERIA_CONFIG["Quarterly Minutes"]["max_points"]
    achieved = data["quarterly_minutes"] > 0
    points = mp if achieved else 0
    criterion = HealthScoreCriterion(
        name="Quarterly Minutes",
        description="Minutes generated this quarter",
        points=points, max_points=mp, achieved=achieved, no_data=False
    )
    return criterion, points


def _compute_task_compliance_criterion(data: dict) -> tuple:
    """Returns (HealthScoreCriterion, points) for Task Compliance."""
    mp = CRITERIA_CONFIG["Task Compliance"]["max_points"]
    total_tasks = data["total_tasks"]
    overdue_tasks = data["overdue_tasks"]
    if total_tasks > 0:
        task_compliance = overdue_tasks == 0
        points = mp if task_compliance else max(0, mp - (overdue_tasks * 3))
    else:
        task_compliance = None
        points = 0
    criterion = HealthScoreCriterion(
        name="Task Compliance",
        description="No overdue governance tasks" if total_tasks > 0 else "No governance tasks tracked yet",
        points=points, max_points=mp,
        achieved=task_compliance if task_compliance is not None else False,
        no_data=total_tasks == 0
    )
    return criterion, points


def _compute_compensation_criterion(data: dict) -> tuple:
    """Returns (HealthScoreCriterion, points) for Compensation Alignment."""
    mp = CRITERIA_CONFIG["Compensation Alignment"]["max_points"]
    comp_plan = data["comp_plan"]
    if comp_plan:
        aligned = data["ytd_total"] <= data["approved_amount"]
        points = mp if aligned else 0
    else:
        aligned = None
        points = 0
    criterion = HealthScoreCriterion(
        name="Compensation Alignment",
        description="YTD compensation within approved plan" if comp_plan else "No compensation plan set up yet",
        points=points, max_points=mp,
        achieved=aligned if aligned is not None else False,
        no_data=comp_plan is None
    )
    return criterion, points


def _compute_distribution_criterion(data: dict) -> tuple:
    """Returns (HealthScoreCriterion, points) for Distribution Documentation."""
    mp = CRITERIA_CONFIG["Distribution Documentation"]["max_points"]
    dist_count = data["dist_count"]
    benevolence_dists = data["benevolence_dists"]
    benevolence_count = len(benevolence_dists)
    incomplete = _count_incomplete_benevolence(benevolence_dists)

    if dist_count == 0:
        return HealthScoreCriterion(
            name="Distribution Documentation", description="No distributions logged",
            points=0, max_points=mp, achieved=False, no_data=True,
        ), 0

    if benevolence_count > 0 and incomplete > 0:
        ratio = (benevolence_count - incomplete) / benevolence_count
        points = int(mp * (0.5 + 0.5 * ratio))
        desc = f"Distributions logged; {incomplete}/{benevolence_count} benevolence distributions need documentation"
    else:
        points = mp
        if benevolence_count > 0:
            desc = f"All distributions documented ({benevolence_count} benevolence distributions fully documented)"
        else:
            desc = "Distributions logged"

    return HealthScoreCriterion(
        name="Distribution Documentation", description=desc,
        points=points, max_points=mp, achieved=True, no_data=False,
    ), points


def _count_incomplete_benevolence(benevolence_dists: list) -> int:
    """Count distributions with incomplete benevolence documentation."""
    incomplete = 0
    for bd in benevolence_dists:
        if not bd.get("benevolence_recipient_name") or not bd.get("benevolence_need_description"):
            incomplete += 1
        elif not bd.get("approved_at") and not bd.get("minutes_record_id"):
            incomplete += 1
    return incomplete


def _compute_annual_review_criterion(data: dict, now: datetime) -> tuple:
    """Returns (HealthScoreCriterion, points) for Annual Review."""
    mp = CRITERIA_CONFIG["Annual Review"]["max_points"]
    annual_done = data["annual_review"] is not None
    points = mp if annual_done else 0
    is_new_trust = _parse_trust_created_age(data.get("trust_created_at"), now)
    criterion = HealthScoreCriterion(
        name="Annual Review",
        description="Annual review completed in last 12 months" if not is_new_trust else "Annual review not due yet — schedule it for later",
        points=points, max_points=mp, achieved=annual_done, no_data=is_new_trust
    )
    return criterion, points


def _compute_asset_valuation_criterion(data: dict) -> tuple:
    """Returns (HealthScoreCriterion, points) for Asset Valuation Freshness."""
    mp = CRITERIA_CONFIG["Asset Valuation Freshness"]["max_points"]
    active_assets = data["active_assets"]
    twelve_months_ago = data["twelve_months_ago"]
    total_assets = len(active_assets)

    if total_assets == 0:
        criterion = HealthScoreCriterion(
            name="Asset Valuation Freshness", description="No assets on Schedule A yet",
            points=0, max_points=mp, achieved=False, no_data=True
        )
        return criterion, 0

    stale_count = sum(1 for a in active_assets if _is_asset_stale(a, twelve_months_ago))
    fresh_count = total_assets - stale_count
    if stale_count == 0:
        points = mp
        achieved = True
    else:
        points = int(mp * fresh_count / total_assets)
        achieved = False
    desc = f"{stale_count} of {total_assets} asset(s) need re-valuation (last valued >12 months ago)"
    criterion = HealthScoreCriterion(
        name="Asset Valuation Freshness", description=desc,
        points=points, max_points=mp, achieved=achieved, no_data=False
    )
    return criterion, points


def _compute_transaction_classification_criterion(data: dict) -> tuple:
    """Returns (HealthScoreCriterion, points) for Transaction Classification."""
    mp = CRITERIA_CONFIG["Transaction Classification"]["max_points"]
    total_txns = data["total_txns"]
    classified_txns = data["classified_txns"]
    if total_txns == 0:
        return HealthScoreCriterion(
            name="Transaction Classification", description="No transactions to classify yet",
            points=0, max_points=mp, achieved=False, no_data=True
        ), 0

    ratio = classified_txns / total_txns
    points = int(mp * ratio)
    achieved = ratio >= 1.0
    desc = f"{classified_txns}/{total_txns} transactions classified"
    return HealthScoreCriterion(
        name="Transaction Classification", description=desc,
        points=points, max_points=mp, achieved=achieved, no_data=False
    ), points


def _compute_separation_alert_criterion(data: dict) -> tuple:
    """Returns (HealthScoreCriterion, points) for Separation Alert Health."""
    mp = CRITERIA_CONFIG["Separation Alert Health"]["max_points"]
    total_txns = data["total_txns"]
    active_alert_count = data["active_alert_count"]

    if total_txns == 0:
        return HealthScoreCriterion(
            name="Separation Alert Health", description="No transactions to monitor for separation yet",
            points=0, max_points=mp, achieved=False, no_data=True
        ), 0

    if active_alert_count == 0:
        return HealthScoreCriterion(
            name="Separation Alert Health", description="No active separation alerts",
            points=mp, max_points=mp, achieved=True, no_data=False
        ), mp

    points = max(0, mp - active_alert_count * 3)
    desc = f"{active_alert_count} active separation alert(s)"
    return HealthScoreCriterion(
        name="Separation Alert Health", description=desc,
        points=points, max_points=mp, achieved=False, no_data=False
    ), points


def _score_to_color(final_score: int) -> HealthColor:
    """Map a numeric score to a HealthColor."""
    if final_score >= 96:
        return HealthColor.green
    if final_score >= 72:
        return HealthColor.yellow
    return HealthColor.red


def _compute_health_score(data: dict) -> dict:
    """Pure sync: compute criteria, points, color from gathered data. No DB calls."""
    now = data["now"]
    criteria = []
    total_score = 0

    # 1–8: compute each criterion via dedicated helpers
    c, pts = _compute_quarterly_minutes_criterion(data)
    criteria.append(c); total_score += pts

    c, pts = _compute_task_compliance_criterion(data)
    criteria.append(c); total_score += pts

    c, pts = _compute_compensation_criterion(data)
    criteria.append(c); total_score += pts

    c, pts = _compute_distribution_criterion(data)
    criteria.append(c); total_score += pts

    c, pts = _compute_annual_review_criterion(data, now)
    criteria.append(c); total_score += pts

    c, pts = _compute_asset_valuation_criterion(data)
    criteria.append(c); total_score += pts

    c, pts = _compute_transaction_classification_criterion(data)
    criteria.append(c); total_score += pts

    c, pts = _compute_separation_alert_criterion(data)
    criteria.append(c); total_score += pts

    # --- Risk Penalty (separate from criteria) ---
    risk_findings = data.get("risk_findings", [])
    penalty_result = compute_risk_penalty(risk_findings)
    total_penalty = penalty_result["total_penalty"]
    has_critical = penalty_result["has_critical"]
    breakdown = penalty_result["breakdown"]
    findings_with_penalty = penalty_result["findings_with_penalty"]

    base_score = sum(c["points"] for c in [cr.model_dump() for cr in criteria])

    # --- Final Score with Critical Cap ---
    if has_critical:
        final_score = min(50, max(0, base_score + total_penalty))
    else:
        final_score = max(0, base_score + total_penalty)

    color = _score_to_color(final_score)

    return {
        "criteria": criteria,
        "base_score": base_score,
        "risk_penalty": total_penalty,
        "has_critical_risk": has_critical,
        "total_score": final_score,
        "max_score": TOTAL_MAX_POINTS,
        "color": color,
        "risk_findings": findings_with_penalty,
        "risk_penalty_breakdown": breakdown,
        "now": now,
    }


async def _clear_achieved_dismissals(trust_id: str, user_id: str, criteria: list) -> None:
    """Auto-clear dismissals for criteria that are now achieved."""
    achieved_names = [c.name for c in criteria if c.achieved]
    if not achieved_names:
        return
    await db.dismissed_insights.delete_many({
        "trust_id": trust_id,
        "user_id": user_id,
        "criterion_name": {"$in": achieved_names}
    })


async def _maybe_notify_score_drop(
    trust_id: str, user_id: str, total_score: int, risk_findings: list, now: datetime
) -> None:
    """Insert a notification when the score drops 5+ points due to new high/critical risks."""
    prev = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id},
        sort=[("calculated_at", -1)],
        projection={"_id": 0, "score_value": 1}
    )
    if not prev or prev.get("score_value", 100) - total_score < 5:
        return
    new_findings = [r for r in risk_findings if r.get("severity") in ("critical", "high")]
    if not new_findings:
        return
    await db.notifications.insert_one({
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "trust_id": trust_id,
        "type": "score_drop",
        "title": "Your Trust Health Score changed",
        "message": f"Your score is now {total_score}/{TOTAL_MAX_POINTS}. "
                   f"{len(new_findings)} new risk{'s' if len(new_findings) > 1 else ''} "
                   f"affecting your score. Review and resolve to recover points.",
        "action_path": "/governance",
        "created_at": now.isoformat(),
        "read": False
    })


async def _save_health_snapshot(
    trust_id: str, user_id: str, criteria: list, base_score: int,
    risk_penalty: int, total_score: int, color: HealthColor,
    risk_penalty_breakdown: dict, now: datetime
) -> None:
    """Persist a health-score snapshot (schema v2)."""
    snapshot = {
        "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user_id,
        "schema_version": 2,
        "base_score": base_score,
        "risk_penalty": risk_penalty,
        "score_value": total_score,
        "color": color.value,
        "calculated_at": now.isoformat(),
        "criteria_breakdown": [
            {"name": c.name, "points": c.points, "max_points": c.max_points, "achieved": c.achieved}
            for c in criteria
        ],
        "risk_findings_count": {
            "critical": risk_penalty_breakdown["critical"]["count"],
            "high": risk_penalty_breakdown["high"]["count"],
            "medium": risk_penalty_breakdown["medium"]["count"],
            "low": risk_penalty_breakdown["low"]["count"],
        }
    }
    await db.health_score_snapshots.insert_one(snapshot)


async def calculate_health_score(trust_id: str, user_id: str, save_snapshot: bool = True) -> dict:
    """
    Calculate governance health score using 8 criteria + risk penalty.
    Orchestrator: gathers data, computes score, optionally saves snapshot.
    """
    # Ensure monthly transaction review task exists for this trust
    await ensure_transaction_review_task(trust_id, user_id)

    # Gather all DB data (use cache for dashboard loads, fresh for snapshots)
    data = await _gather_score_data(trust_id, user_id, use_cache=not save_snapshot)

    # Compute score (pure, no DB)
    result = _compute_health_score(data)
    criteria = result["criteria"]
    base_score = result["base_score"]
    risk_penalty = result["risk_penalty"]
    has_critical_risk = result["has_critical_risk"]
    total_score = result["total_score"]
    color = result["color"]
    now = result["now"]
    risk_findings = result["risk_findings"]
    risk_penalty_breakdown = result["risk_penalty_breakdown"]

    # Auto-clear dismissals for criteria that are now achieved
    await _clear_achieved_dismissals(trust_id, user_id, criteria)

    # Score-change notification + snapshot persistence (only when saving)
    if save_snapshot:
        await _maybe_notify_score_drop(trust_id, user_id, total_score, risk_findings, now)
        await _save_health_snapshot(
            trust_id, user_id, criteria, base_score, risk_penalty,
            total_score, color, risk_penalty_breakdown, now
        )

    return {
        "trust_id": trust_id,
        "total_score": total_score,
        "max_score": TOTAL_MAX_POINTS,
        "color": color.value,
        "base_score": base_score,
        "risk_penalty": risk_penalty,
        "has_critical_risk": has_critical_risk,
        "criteria": [c.model_dump() for c in criteria],
        "risk_findings": risk_findings,
        "risk_penalty_breakdown": risk_penalty_breakdown,
        "calculated_at": now.isoformat()
    }


_INSIGHT_USE_DESC_CRITERIA = {
    "Asset Valuation Freshness",
    "Transaction Classification",
    "Separation Alert Health",
}


def _build_insight_description(c: dict, cfg: dict, max_points: int) -> str:
    """Build the human-readable description for a governance insight."""
    name = c["name"]
    if name == "Distribution Documentation":
        desc = c.get("description", "")
        if "benevolence" in desc.lower():
            return desc
        return f"Log your first distribution to earn +{max_points} points"
    if name in _INSIGHT_USE_DESC_CRITERIA:
        return c.get("description", cfg["insight_desc"].format(max_points=max_points))
    return cfg["insight_desc"].format(max_points=max_points)


def generate_governance_insights(criteria: List[dict]) -> List[GovernanceInsight]:
    """Generate actionable insights from health score criteria."""
    insights = []

    for c in criteria:
        if c["achieved"] or c.get("no_data", False):
            continue
        cfg = CRITERIA_CONFIG.get(c["name"])
        if not cfg:
            continue
        max_points = cfg["max_points"]
        recoverable = max_points - c.get("points", 0)
        if recoverable <= 0:
            continue

        description = _build_insight_description(c, cfg, max_points)
        insights.append(GovernanceInsight(
            type=cfg["insight_type"],
            criterion_name=c["name"],
            title=cfg["insight_title"],
            description=description,
            action_path=cfg["action_path"],
            action_label=cfg["action_label"],
            points=recoverable
        ))

    return insights


async def generate_additional_governance_insights(trust_id: str, user_id: str) -> List[GovernanceInsight]:
    """
    Generate supplementary governance insights that require direct DB queries
    (beyond the standard health-score criteria). These are appended to the
    insights list produced by generate_governance_insights() for the dashboard's
    Today's Focus section.

    Criteria:
      1. Undocumented Distributions — distributions older than 7 days with no
         linked minutes_record_id.
      2. Overdue Tax Filings — tax_calendar entries past their due_date that are
         not filed/not_required.

    Note: "Stale Asset Valuations" is already covered by the existing
    "Asset Valuation Freshness" health-score criterion and is intentionally not
    duplicated here.
    """
    insights: List[GovernanceInsight] = []
    now = datetime.now(timezone.utc)

    # --- 1. Undocumented Distributions ---
    # Distributions created >7 days ago that still have no linked meeting minutes.
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    undocumented_count = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$lt": seven_days_ago},
        "$or": [
            {"minutes_record_id": None},
            {"minutes_record_id": ""}
        ]
    })
    if undocumented_count > 0:
        points = min(undocumented_count * 5, 15)
        insights.append(GovernanceInsight(
            type="warning",
            criterion_name="Undocumented Distributions",
            title="Undocumented Distributions",
            description=(
                f"{undocumented_count} distribution(s) lack meeting minutes. "
                f"Document them to strengthen your records. "
                f"Draft minutes for each undocumented distribution."
            ),
            action_path="/distributions",
            action_label="Review Distributions",
            points=points
        ))

    # --- 2. Overdue Tax Filings ---
    # tax_calendar entries whose due_date has passed and are still pending.
    today_iso = now.date().isoformat()
    overdue_tax_count = await db.tax_calendar.count_documents({
        "trust_id": trust_id,
        "due_date": {"$lt": today_iso},
        "filing_status": {"$nin": ["filed", "not_required", "extended"]}
    })
    if overdue_tax_count > 0:
        points = min(overdue_tax_count * 10, 20)
        insights.append(GovernanceInsight(
            type="warning",
            criterion_name="Overdue Tax Filings",
            title="Overdue Tax Filings",
            description=(
                f"{overdue_tax_count} tax filing(s) are overdue. "
                f"Review and complete overdue filings or mark them as filed."
            ),
            action_path="/tax-calendar",
            action_label="View Tax Calendar",
            points=points
        ))

    return insights


async def get_dashboard_stats(trust_id: str, user_id: str) -> DashboardStats:
    """Calculate dashboard statistics for a trust."""
    now = datetime.now(timezone.utc)
    year_start = get_year_start(now)
    
    total_decisions = await db.minutes_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    }) + await db.minutes_templates.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    
    pending_reviews = await db.governance_tasks.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "completed_at": None
    })
    
    total_distributions = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    
    ytd_distributions = await db.distribution_records.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "date": {"$gte": year_start.isoformat()}
    }, {"_id": 0, "amount": 1}).to_list(1000)
    ytd_amount = sum(d.get("amount", 0) for d in ytd_distributions)
    
    return DashboardStats(
        total_decisions=total_decisions,
        pending_reviews=pending_reviews,
        total_distributions=total_distributions,
        ytd_distributions_amount=ytd_amount
    )


_ONBOARDING_DEFAULTS = {
    "user_id": None,
    "formation_date_added": False,
    "ein_entered": False,
    "trust_doc_uploaded": False,
    "ein_doc_uploaded": False,
    "beneficiaries_added": False,
    "assets_added": False,
    "minutes_generated": False,
    "calendar_set": False,
    "checklist_dismissed": False,
    "successor_trustee_added": False,
    "trust_protector_added": False
}

_AUTO_SEEDED_TASK_TYPES = {"annual_review", "quarterly_review", "compensation_review", "asset_revaluation"}


def _should_update(existing_val: bool, detected: bool, manual_overrides: dict, key: str) -> bool:
    """Check if an onboarding field should be updated (not manually overridden, and value changed)."""
    return key not in manual_overrides and detected != existing_val


async def _detect_onboarding_updates(user_id: str, trust_id: str, existing: dict) -> dict:
    """Check actual DB data and return fields that need updating."""
    updates = {}
    manual_overrides = existing.get("manual_overrides", {})

    # Trust profile fields
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
    if trust:
        checks = [
            ("formation_date_added", bool(trust.get("start_date"))),
            ("ein_entered", bool(trust.get("ein"))),
            ("successor_trustee_added", bool(trust.get("successor_trustee_name"))),
            # Trust protector is "done" once the trustee has made a decision —
            # either deferring (status = "none") or naming a protector.
            ("trust_protector_added", trust.get("trust_protector_status") in ("none", "pending", "appointed")),
        ]
        for key, detected in checks:
            if _should_update(existing.get(key), detected, manual_overrides, key):
                updates[key] = detected

    # Document uploads
    doc_checks = [
        ("trust_doc_uploaded", ["trust_instrument", "trust_document", "declaration_of_trust"]),
        ("ein_doc_uploaded", ["ein_letter", "irs_notice"]),
    ]
    for key, categories in doc_checks:
        count = await db.vault_documents.count_documents({
            "trust_id": trust_id, "user_id": user_id, "category": {"$in": categories}
        })
        if _should_update(existing.get(key), count > 0, manual_overrides, key):
            updates[key] = count > 0

    # Beneficiaries
    beneficiary_count = await db.trust_unit_certificates.count_documents({
        "trust_id": trust_id, "user_id": user_id, "status": "active"
    })
    if _should_update(existing.get("beneficiaries_added"), beneficiary_count > 0, manual_overrides, "beneficiaries_added"):
        updates["beneficiaries_added"] = beneficiary_count > 0

    # Assets via entities
    entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
    if _should_update(existing.get("assets_added"), entity_count > 0, manual_overrides, "assets_added"):
        updates["assets_added"] = entity_count > 0

    # Calendar — only count user-created tasks, not auto-seeded ones
    user_task_count = await db.governance_tasks.count_documents({
        "trust_id": trust_id, "user_id": user_id,
        "task_type": {"$nin": list(_AUTO_SEEDED_TASK_TYPES | {"custom"})}
    })
    if _should_update(existing.get("calendar_set"), user_task_count > 0, manual_overrides, "calendar_set"):
        updates["calendar_set"] = user_task_count > 0

    # Minutes
    minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    templates_count = await db.minutes_templates.count_documents({"trust_id": trust_id, "user_id": user_id})
    has_minutes = minutes_count > 0 or templates_count > 0
    if _should_update(existing.get("minutes_generated"), has_minutes, manual_overrides, "minutes_generated"):
        updates["minutes_generated"] = has_minutes

    return updates


async def get_onboarding_state(user_id: str, trust_id: Optional[str] = None) -> OnboardingState:
    """Get user's onboarding state, auto-updating based on their activity."""
    existing = await db.user_onboarding.find_one({"user_id": user_id}, {"_id": 0})

    if not existing:
        existing = dict(_ONBOARDING_DEFAULTS, user_id=user_id)
        await db.user_onboarding.insert_one(existing)

    # Auto-check based on actual data if trust_id provided
    if trust_id:
        updates = await _detect_onboarding_updates(user_id, trust_id, existing)
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.user_onboarding.update_one({"user_id": user_id}, {"$set": updates})
            existing = await db.user_onboarding.find_one({"user_id": user_id}, {"_id": 0})

    return OnboardingState(**existing)


async def get_recent_activity(user_id: str, trust_id: str, limit: int = 10) -> List[dict]:
    """Get recent activity for a trust."""
    activities = []
    
    # Recent minutes (from both minutes_records and minutes_templates)
    minutes = await db.minutes_records.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    for m in minutes:
        activities.append({
            "type": "minutes",
            "id": m.get("minutes_id"),
            "title": f"{m.get('minutes_type', 'Meeting').replace('_', ' ').title()} Minutes",
            "date": m.get("meeting_date") or m.get("created_at", "")[:10],
            "created_at": m.get("created_at", "")
        })
    
    # Also include template-based minutes (created via Getting Started / template flow)
    template_minutes = await db.minutes_templates.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    for m in template_minutes:
        activities.append({
            "type": "minutes",
            "id": m.get("minutes_id"),
            "title": f"{m.get('template_type', 'Meeting').replace('_', ' ').title()} Minutes",
            "date": m.get("meeting_date") or m.get("created_at", "")[:10],
            "created_at": m.get("created_at", "")
        })
    
    # Recent distributions
    distributions = await db.distribution_records.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    for d in distributions:
        activities.append({
            "type": "distribution",
            "id": d.get("distribution_id"),
            "title": f"Distribution to {d.get('beneficiary_name', 'Unknown')}",
            "amount": d.get("amount", 0),
            "date": d.get("date", ""),
            "created_at": d.get("created_at", "")
        })
    
    # Sort all activities by created_at and limit
    activities.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return activities[:limit]


# ==================== GOVERNANCE ENDPOINTS ====================

@router.get("/governance/{trust_id}", response_model=HealthScoreResponse)
async def get_governance_health(trust_id: str, user: dict = Depends(get_current_user)):
    """Get governance health score for a trust"""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    health = await calculate_health_score(trust_id, user["user_id"], save_snapshot=True)
    
    return HealthScoreResponse(**health)


@router.get("/governance/{trust_id}/history")
async def get_governance_history(trust_id: str, days: int = 30, user: dict = Depends(get_current_user)):
    """
    Get historical health score snapshots for charting.
    
    Feature Gate: GOVERNANCE_HISTORY
    - Trial users cannot access governance history
    - Paid users can view historical scores and trends
    """
    # Validate days parameter
    days = max(1, min(days, 365))
    # Check feature access
    has_history_access = await check_feature_access(user["user_id"], Feature.GOVERNANCE_HISTORY)
    if not has_history_access:
        raise HTTPException(
            status_code=PREMIUM_FEATURE_ERROR_CODE,
            detail="Governance history requires a paid subscription. Upgrade to view historical scores and trends."
        )
    
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    snapshots = await db.health_score_snapshots.find(
        {"trust_id": trust_id, "user_id": user["user_id"], "calculated_at": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("calculated_at", -1).to_list(1000)
    
    daily_scores = {}
    for snap in snapshots:
        date_key = snap["calculated_at"][:10]
        if date_key not in daily_scores:
            daily_scores[date_key] = {
                "date": date_key,
                "score": snap["score_value"],
                "color": snap["color"]
            }
    
    history = sorted(daily_scores.values(), key=lambda x: x["date"])
    
    return {
        "trust_id": trust_id,
        "days": days,
        "history": history,
        "current_score": history[-1]["score"] if history else 0
    }


# ==================== ONBOARDING ENDPOINTS ====================

@router.get("/onboarding", response_model=OnboardingState)
async def get_onboarding(user: dict = Depends(get_current_user)):
    """Get user's onboarding state"""
    trust = await db.trusts.find_one({"user_id": user["user_id"]}, {"_id": 0})
    trust_id = trust["trust_id"] if trust else None
    return await get_onboarding_state(user["user_id"], trust_id)


@router.patch("/onboarding")
async def update_onboarding(updates: dict, user: dict = Depends(require_write_access)):
    """Update onboarding state — records manual overrides for toggled fields."""
    allowed_fields = ["formation_date_added", "ein_entered", "trust_doc_uploaded", "ein_doc_uploaded", "beneficiaries_added", "assets_added", "minutes_generated", "calendar_set", "checklist_dismissed", "successor_trustee_added", "trust_protector_added"]
    update_data = {k: v for k, v in updates.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # Record which fields were manually set — auto-detection will skip these
    existing = await db.user_onboarding.find_one({"user_id": user["user_id"]}, {"_id": 0})
    manual_overrides = existing.get("manual_overrides", {}) if existing else {}
    for field in update_data:
        if field != "updated_at" and field != "checklist_dismissed":
            manual_overrides[field] = True
    update_data["manual_overrides"] = manual_overrides
    
    await db.user_onboarding.update_one(
        {"user_id": user["user_id"]},
        {"$set": update_data},
        upsert=True
    )
    
    return {"message": "Onboarding updated"}


@router.post("/onboarding/dismiss")
async def dismiss_onboarding(user: dict = Depends(require_write_access)):
    """Dismiss onboarding checklist"""
    await db.user_onboarding.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "checklist_dismissed": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    return {"message": "Onboarding dismissed"}


@router.delete("/onboarding/dismiss")
async def undismiss_onboarding(user: dict = Depends(require_write_access)):
    """Re-show onboarding checklist (undo dismiss)"""
    await db.user_onboarding.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "checklist_dismissed": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    return {"message": "Onboarding checklist re-enabled"}


# ==================== ACTIVITY ENDPOINT ====================

@router.get("/activity")
async def get_activity(
    trust_id: Optional[str] = None, 
    limit: int = 20, 
    user: dict = Depends(get_current_user)
):
    """Get recent activity timeline for a trust"""
    if not trust_id:
        trust = await db.trusts.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not trust:
            return {"activities": []}
        trust_id = trust["trust_id"]
    else:
        trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
        if not trust:
            raise HTTPException(status_code=404, detail="Trust not found")
    
    return {"activities": await get_recent_activity(user["user_id"], trust_id, limit)}


# ==================== DASHBOARD ENDPOINT ====================

async def _get_pending_quarterly_draft(trust_id: str, user_id: str) -> Optional[dict]:
    """Check for a pending auto-drafted quarterly review minutes draft."""
    pending_draft = await db.minutes_records.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "minutes_type": "quarterly_review",
        "status": "draft",
        "template_data.auto_drafted": True,
    })
    if not pending_draft:
        return None
    quarter = pending_draft.get("template_data", {}).get("quarter", "")
    return {
        "minutes_id": pending_draft["minutes_id"],
        "quarter": quarter,
        "review_link": f"/minutes/{pending_draft['minutes_id']}/edit",
    }


async def _resolve_dashboard_trust(trust_id: Optional[str], user_id: str) -> dict:
    """Resolve the trust for the dashboard — by id or the most recent one."""
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
        if not trust:
            raise HTTPException(
                status_code=404,
                detail="Trust not found or access denied."
            )
        return trust

    trust = await db.trusts.find_one(
        {"user_id": user_id},
        {"_id": 0},
        sort=[("created_at", -1)]
    )
    if not trust:
        raise HTTPException(
            status_code=404,
            detail="No trust found. Please create a trust first."
        )
    return trust


async def _get_active_insights(trust_id: str, user_id: str, criteria: list) -> list:
    """Generate governance insights, filtering out dismissed ones and adding supplementary insights."""
    dismissed = await db.dismissed_insights.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "criterion_name": 1}
    ).to_list(1000)
    dismissed_names = {d["criterion_name"] for d in dismissed}

    governance_insights = generate_governance_insights(criteria)
    governance_insights.extend(await generate_additional_governance_insights(trust_id, user_id))
    return [i for i in governance_insights if i.criterion_name not in dismissed_names]


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Unified dashboard endpoint that aggregates:
    - Health score (from calculate_health_score)
    - Onboarding state
    - Recent activity
    - Stats (total decisions, pending reviews, etc.)
    - Governance insights (actionable suggestions)
    - Subscription state (for read-only mode awareness)
    """
    user_id = user["user_id"]

    trust = await _resolve_dashboard_trust(trust_id, user_id)
    trust_id = trust["trust_id"]
    trust_name = trust.get("name", "Unnamed Trust")

    health_data = await calculate_health_score(trust_id, user_id, save_snapshot=False)
    health_score = HealthScoreResponse(**health_data)

    onboarding_state = await get_onboarding_state(user_id, trust_id)
    recent_activity = await get_recent_activity(user_id, trust_id, limit=10)
    stats = await get_dashboard_stats(trust_id, user_id)

    governance_insights = await _get_active_insights(trust_id, user_id, health_data["criteria"])

    sub_state = await get_subscription_state(user_id)
    subscription = DashboardSubscriptionState(
        plan_type=sub_state.plan_type,
        status=sub_state.status,
        is_trial=sub_state.is_trial,
        is_active=sub_state.is_active,
        is_read_only=sub_state.is_read_only,
        trial_days_remaining=sub_state.trial_days_remaining
    )

    # Check for pending quarterly draft (Fix 3)
    pending_quarterly_draft = await _get_pending_quarterly_draft(trust_id, user_id)

    return DashboardResponse(
        trust_id=trust_id,
        trust_name=trust_name,
        health_score=health_score,
        onboarding_state=onboarding_state,
        recent_activity=recent_activity,
        stats=stats,
        governance_insights=governance_insights,
        subscription=subscription,
        pending_quarterly_draft=pending_quarterly_draft,
    )


# ==================== DISMISS INSIGHT ENDPOINT ====================

@router.post("/insights/dismiss")
async def dismiss_insight(
    req: DismissedInsightCreate,
    user: dict = Depends(require_write_access)
):
    """Dismiss a governance insight so it no longer appears on the dashboard"""
    trust_id = req.trust_id
    criterion_name = req.criterion_name
    user_id = user["user_id"]
    
    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    now = datetime.now(timezone.utc).isoformat()
    dismiss_id = f"dismiss_{uuid.uuid4().hex[:12]}"
    
    # Upsert dismissal (idempotent)
    await db.dismissed_insights.update_one(
        {"trust_id": trust_id, "criterion_name": criterion_name, "user_id": user_id},
        {
            "$setOnInsert": {
                "dismiss_id": dismiss_id,
                "user_id": user_id,
                "trust_id": trust_id,
                "criterion_name": criterion_name,
                "dismissed_at": now
            }
        },
        upsert=True
    )
    
    return {
        "message": f"Insight '{criterion_name}' dismissed",
        "criterion_name": criterion_name,
        "dismissed": True
    }


@router.get("/insights/dismissed")
async def get_dismissed_insights(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Get list of dismissed insights for a trust"""
    user_id = user["user_id"]
    
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
        if not trust:
            raise HTTPException(status_code=404, detail="Trust not found")
    
    query = {"user_id": user_id}
    if trust_id:
        query["trust_id"] = trust_id
    
    dismissed = await db.dismissed_insights.find(
        query,
        {"_id": 0}
    ).to_list(1000)
    
    return {"dismissed_insights": dismissed}


@router.post("/insights/restore")
async def restore_insight(
    req: DismissedInsightCreate,
    user: dict = Depends(require_write_access)
):
    """Restore a previously dismissed governance insight"""
    trust_id = req.trust_id
    criterion_name = req.criterion_name
    user_id = user["user_id"]
    
    result = await db.dismissed_insights.delete_one(
        {"trust_id": trust_id, "criterion_name": criterion_name, "user_id": user_id}
    )
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dismissed insight not found")
    
    return {
        "message": f"Insight '{criterion_name}' restored",
        "criterion_name": criterion_name,
        "restored": True
    }
