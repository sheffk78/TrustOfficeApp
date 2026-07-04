# Governance router - handles health score, history, onboarding, activity, and dashboard
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid

from database import db
from dependencies import (
    get_current_user, get_subscription_state, 
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
        "insight_title": "Annual Review Due",
        "insight_desc": "Complete annual review for +{max_points} points",
        "action_path": "/calendar",
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


async def _gather_score_data(trust_id: str, user_id: str, use_cache: bool = False) -> dict:
    """Async: gather all raw DB data needed for health score. Returns dict of raw metrics.
    If use_cache=True, tries to load risk findings from TTL cache (5 min) before gathering fresh.
    """
    now = datetime.now(timezone.utc)
    quarter_start = get_quarter_start(now)
    year_start = get_year_start(now)
    one_year_ago = (now - timedelta(days=365))
    twelve_months_ago = one_year_ago

    # 1. Quarterly Minutes
    quarterly_minutes = await db.minutes_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$gte": quarter_start.isoformat()}
    })

    # 2. Task Compliance
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

    # 3. Compensation Alignment
    comp_plan = await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    ytd_payments = []
    ytd_total = 0
    approved_amount = 0
    if comp_plan:
        ytd_payments = await db.compensation_payments.find(
            {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start.isoformat()}},
            {"_id": 0}
        ).to_list(1000)
        ytd_total = sum(p.get("amount", 0) for p in ytd_payments)
        approved_amount = comp_plan.get("annual_approved_amount") or comp_plan.get("annual_fee") or comp_plan.get("annual_amount", 0)

    # 4. Distribution Documentation
    dist_count = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    benevolence_dists = await db.distribution_records.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "is_benevolence": True
    }, {"_id": 0}).to_list(1000)

    # 5. Annual Review
    annual_review = await db.governance_tasks.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "task_type": "annual_review",
        "completed_at": {"$gte": one_year_ago.isoformat()}
    }, {"_id": 0})

    # 6. Asset Valuation Freshness
    active_assets = await db.schedule_a_items.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    }, {"_id": 0, "description": 1, "last_valued_date": 1, "date_conveyed": 1}).to_list(1000)

    # 7. Transaction Classification
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

    # 8. Separation Alert Health
    active_alert_count = await db.separation_alerts.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    })

    # 9. Risk findings (for penalty computation, excludes separation alerts)
    trust_doc = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0}) or {}
    today = now.date()

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
        "active_assets": active_assets,
        "twelve_months_ago": twelve_months_ago,
        "total_txns": total_txns,
        "classified_txns": classified_txns,
        "active_alert_count": active_alert_count,
        "risk_findings": risk_findings,
    }


def _compute_health_score(data: dict) -> dict:
    """Pure sync: compute criteria, points, color from gathered data. No DB calls."""
    now = data["now"]
    criteria = []
    total_score = 0

    # 1. Quarterly Minutes (+15)
    mp = CRITERIA_CONFIG["Quarterly Minutes"]["max_points"]
    quarterly_achieved = data["quarterly_minutes"] > 0
    q_points = mp if quarterly_achieved else 0
    criteria.append(HealthScoreCriterion(
        name="Quarterly Minutes",
        description="Minutes generated this quarter",
        points=q_points,
        max_points=mp,
        achieved=quarterly_achieved,
        no_data=False
    ))
    total_score += q_points

    # 2. Task Compliance (+15)
    mp = CRITERIA_CONFIG["Task Compliance"]["max_points"]
    total_tasks = data["total_tasks"]
    overdue_tasks = data["overdue_tasks"]
    if total_tasks > 0:
        task_compliance = overdue_tasks == 0
        task_points = mp if task_compliance else max(0, mp - (overdue_tasks * 3))
    else:
        task_compliance = None
        task_points = 0
    criteria.append(HealthScoreCriterion(
        name="Task Compliance",
        description="No overdue governance tasks" if total_tasks > 0 else "No governance tasks tracked yet",
        points=task_points,
        max_points=mp,
        achieved=task_compliance if task_compliance is not None else False,
        no_data=total_tasks == 0
    ))
    total_score += task_points

    # 3. Compensation Alignment (+15)
    mp = CRITERIA_CONFIG["Compensation Alignment"]["max_points"]
    comp_plan = data["comp_plan"]
    if comp_plan:
        comp_aligned = data["ytd_total"] <= data["approved_amount"]
        comp_points = mp if comp_aligned else 0
    else:
        comp_aligned = None
        comp_points = 0
    criteria.append(HealthScoreCriterion(
        name="Compensation Alignment",
        description="YTD compensation within approved plan" if comp_plan else "No compensation plan set up yet",
        points=comp_points,
        max_points=mp,
        achieved=comp_aligned if comp_aligned is not None else False,
        no_data=comp_plan is None
    ))
    total_score += comp_points

    # 4. Distribution Documentation (+15)
    mp = CRITERIA_CONFIG["Distribution Documentation"]["max_points"]
    dist_count = data["dist_count"]
    benevolence_dists = data["benevolence_dists"]
    benevolence_count = len(benevolence_dists)
    incomplete_benevolence = 0
    for bd in benevolence_dists:
        if not bd.get("benevolence_recipient_name") or not bd.get("benevolence_need_description"):
            incomplete_benevolence += 1
        elif not bd.get("approved_at") and not bd.get("minutes_record_id"):
            incomplete_benevolence += 1

    if dist_count == 0:
        dist_documented = False
        dist_points = 0
        dist_description = "No distributions logged"
    elif benevolence_count > 0 and incomplete_benevolence > 0:
        dist_documented = True
        completeness_ratio = (benevolence_count - incomplete_benevolence) / benevolence_count
        dist_points = int(mp * (0.5 + 0.5 * completeness_ratio))
        dist_description = f"Distributions logged; {incomplete_benevolence}/{benevolence_count} benevolence distributions need documentation"
    else:
        dist_documented = True
        dist_points = mp
        if benevolence_count > 0:
            dist_description = f"All distributions documented ({benevolence_count} benevolence distributions fully documented)"
        else:
            dist_description = "Distributions logged"
    criteria.append(HealthScoreCriterion(
        name="Distribution Documentation",
        description=dist_description,
        points=dist_points,
        max_points=mp,
        achieved=dist_documented,
        no_data=dist_count == 0
    ))
    total_score += dist_points

    # 5. Annual Review (+10)
    mp = CRITERIA_CONFIG["Annual Review"]["max_points"]
    annual_done = data["annual_review"] is not None
    annual_points = mp if annual_done else 0
    criteria.append(HealthScoreCriterion(
        name="Annual Review",
        description="Annual review completed in last 12 months",
        points=annual_points,
        max_points=mp,
        achieved=annual_done,
        no_data=False
    ))
    total_score += annual_points

    # 6. Asset Valuation Freshness (+15)
    mp = CRITERIA_CONFIG["Asset Valuation Freshness"]["max_points"]
    active_assets = data["active_assets"]
    twelve_months_ago = data["twelve_months_ago"]
    total_assets = len(active_assets)
    if total_assets == 0:
        av_points = 0
        av_achieved = False
        av_desc = "No assets on Schedule A yet"
        av_no_data = True
    else:
        stale_count = 0
        for asset in active_assets:
            valuation_ref_str = asset.get("last_valued_date") or asset.get("date_conveyed")
            if not valuation_ref_str:
                stale_count += 1
                continue
            try:
                valuation_ref = datetime.fromisoformat(valuation_ref_str.replace("Z", "+00:00")) if "T" in valuation_ref_str else datetime.fromisoformat(valuation_ref_str).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                stale_count += 1
                continue
            if valuation_ref < twelve_months_ago:
                stale_count += 1
        fresh_count = total_assets - stale_count
        if stale_count == 0:
            av_points = mp
            av_achieved = True
        else:
            av_points = int(mp * fresh_count / total_assets)
            av_achieved = False
        av_desc = f"{stale_count} of {total_assets} asset(s) need re-valuation (last valued >12 months ago)"
        av_no_data = False
    criteria.append(HealthScoreCriterion(
        name="Asset Valuation Freshness",
        description=av_desc,
        points=av_points,
        max_points=mp,
        achieved=av_achieved,
        no_data=av_no_data
    ))
    total_score += av_points

    # 7. Transaction Classification (+15)
    mp = CRITERIA_CONFIG["Transaction Classification"]["max_points"]
    total_txns = data["total_txns"]
    classified_txns = data["classified_txns"]
    if total_txns == 0:
        tc_points = 0
        tc_achieved = False
        tc_desc = "No transactions to classify yet"
        tc_no_data = True
    else:
        classified_ratio = classified_txns / total_txns
        tc_points = int(mp * classified_ratio)
        tc_achieved = classified_ratio >= 1.0
        tc_desc = f"{classified_txns}/{total_txns} transactions classified"
        tc_no_data = False
    criteria.append(HealthScoreCriterion(
        name="Transaction Classification",
        description=tc_desc,
        points=tc_points,
        max_points=mp,
        achieved=tc_achieved,
        no_data=tc_no_data
    ))
    total_score += tc_points

    # 8. Separation Alert Health (+15)
    mp = CRITERIA_CONFIG["Separation Alert Health"]["max_points"]
    total_txns = data["total_txns"]
    active_alert_count = data["active_alert_count"]
    if total_txns == 0:
        sa_points = 0
        sa_achieved = False
        sa_desc = "No transactions to monitor for separation yet"
        sa_no_data = True
    elif active_alert_count == 0:
        sa_points = mp
        sa_achieved = True
        sa_desc = "No active separation alerts"
        sa_no_data = False
    else:
        sa_points = max(0, mp - active_alert_count * 3)
        sa_achieved = False
        sa_desc = f"{active_alert_count} active separation alert(s)"
        sa_no_data = False
    criteria.append(HealthScoreCriterion(
        name="Separation Alert Health",
        description=sa_desc,
        points=sa_points,
        max_points=mp,
        achieved=sa_achieved,
        no_data=sa_no_data
    ))
    total_score += sa_points

    # --- Risk Penalty (separate from criteria) ---
    risk_findings = data.get("risk_findings", [])
    penalty_result = compute_risk_penalty(risk_findings)
    total_penalty = penalty_result["total_penalty"]
    has_critical = penalty_result["has_critical"]
    breakdown = penalty_result["breakdown"]
    findings_with_penalty = penalty_result["findings_with_penalty"]

    base_score = sum(c["points"] for c in [cr.model_dump() for cr in criteria])

    # --- Final Score with Hard Floor ---
    if has_critical:
        final_score = max(50, base_score + total_penalty)
    else:
        final_score = max(0, base_score + total_penalty)

    # Color from final_score
    if final_score >= 96:
        color = HealthColor.green
    elif final_score >= 72:
        color = HealthColor.yellow
    else:
        color = HealthColor.red

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
    achieved_names = [c.name for c in criteria if c.achieved]
    if achieved_names:
        await db.dismissed_insights.delete_many({
            "trust_id": trust_id,
            "user_id": user_id,
            "criterion_name": {"$in": achieved_names}
        })

    # Score-change notification: detect 5+ point drop from new risk findings
    if save_snapshot:
        prev = await db.health_score_snapshots.find_one(
            {"trust_id": trust_id},
            sort=[("calculated_at", -1)],
            projection={"_id": 0, "score_value": 1}
        )
        if prev and prev.get("score_value", 100) - total_score >= 5:
            new_findings = [r for r in risk_findings if r.get("severity") in ("critical", "high")]
            if new_findings:
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

    # Save snapshot (schema v2)
    if save_snapshot:
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


def generate_governance_insights(criteria: List[dict]) -> List[GovernanceInsight]:
    """Generate actionable insights from health score criteria."""
    insights = []
    
    for c in criteria:
        if not c["achieved"] and not c.get("no_data", False):
            cfg = CRITERIA_CONFIG.get(c["name"])
            if not cfg:
                continue
            max_points = cfg["max_points"]
            recoverable = max_points - c.get("points", 0)
            if recoverable <= 0:
                continue
            
            # Special cases with custom descriptions
            if c["name"] == "Distribution Documentation":
                desc = c.get("description", "")
                if "benevolence" in desc.lower():
                    description = desc
                else:
                    description = f"Log your first distribution to earn +{max_points} points"
            elif c["name"] == "Asset Valuation Freshness":
                description = c.get("description", cfg["insight_desc"].format(max_points=max_points))
            elif c["name"] == "Transaction Classification":
                description = c.get("description", cfg["insight_desc"].format(max_points=max_points))
            elif c["name"] == "Separation Alert Health":
                description = c.get("description", cfg["insight_desc"].format(max_points=max_points))
            else:
                description = cfg["insight_desc"].format(max_points=max_points)
            
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


async def get_dashboard_stats(trust_id: str, user_id: str) -> DashboardStats:
    """Calculate dashboard statistics for a trust."""
    now = datetime.now(timezone.utc)
    year_start = get_year_start(now)
    
    total_decisions = await db.minutes_records.count_documents({
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


async def get_onboarding_state(user_id: str, trust_id: Optional[str] = None) -> OnboardingState:
    """Get user's onboarding state, auto-updating based on their activity."""
    existing = await db.user_onboarding.find_one({"user_id": user_id}, {"_id": 0})
    
    if not existing:
        existing = {
            "user_id": user_id,
            "formation_date_added": False,
            "ein_entered": False,
            "trust_doc_uploaded": False,
            "ein_doc_uploaded": False,
            "beneficiaries_added": False,
            "assets_added": False,
            "minutes_generated": False,
            "calendar_set": False,
            "checklist_dismissed": False
        }
        await db.user_onboarding.insert_one(existing)
    
    # Auto-check based on actual data if trust_id provided
    # Bidirectional: sets True when data exists, resets False when data is gone
    if trust_id:
        updates = {}
        
        # Check trust profile completion (formation date + EIN)
        trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
        if trust:
            has_formation = bool(trust.get("start_date"))
            has_ein = bool(trust.get("ein"))
            if has_formation != existing.get("formation_date_added"):
                updates["formation_date_added"] = has_formation
            if has_ein != existing.get("ein_entered"):
                updates["ein_entered"] = has_ein
        
        # Check document uploads in vault
        trust_doc_count = await db.vault_documents.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "category": {"$in": ["trust_instrument", "trust_document", "declaration_of_trust"]}
        })
        if bool(trust_doc_count > 0) != existing.get("trust_doc_uploaded"):
            updates["trust_doc_uploaded"] = trust_doc_count > 0
        
        ein_doc_count = await db.vault_documents.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "category": {"$in": ["ein_letter", "irs_notice"]}
        })
        if bool(ein_doc_count > 0) != existing.get("ein_doc_uploaded"):
            updates["ein_doc_uploaded"] = ein_doc_count > 0
        
        # Check beneficiaries
        beneficiary_count = await db.beneficiaries.count_documents({"trust_id": trust_id, "user_id": user_id})
        if bool(beneficiary_count > 0) != existing.get("beneficiaries_added"):
            updates["beneficiaries_added"] = beneficiary_count > 0
        
        # Check assets (via entities) — auto-created entity from trust creation counts
        entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
        if bool(entity_count > 0) != existing.get("assets_added"):
            updates["assets_added"] = entity_count > 0
        
        # Check governance tasks (calendar) — only count tasks the USER created,
        # NOT the auto-seeded ones from create_initial_governance_tasks
        # (annual_review, quarterly_review, compensation_review, asset_revaluation)
        auto_seeded_types = {"annual_review", "quarterly_review", "compensation_review", "asset_revaluation"}
        user_task_count = await db.governance_tasks.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": {"$nin": list(auto_seeded_types | {"custom"})}
        })
        if bool(user_task_count > 0) != existing.get("calendar_set"):
            updates["calendar_set"] = user_task_count > 0
        
        # Check minutes (both records from unified flow and templates from template form)
        minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
        templates_count = await db.minutes_templates.count_documents({"trust_id": trust_id, "user_id": user_id})
        has_minutes = minutes_count > 0 or templates_count > 0
        if has_minutes != existing.get("minutes_generated"):
            updates["minutes_generated"] = has_minutes
        
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.user_onboarding.update_one(
                {"user_id": user_id},
                {"$set": updates}
            )
            existing = await db.user_onboarding.find_one({"user_id": user_id}, {"_id": 0})
    
    return OnboardingState(**existing)


async def get_recent_activity(user_id: str, trust_id: str, limit: int = 10) -> List[dict]:
    """Get recent activity for a trust."""
    activities = []
    
    # Recent minutes
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
async def update_onboarding(updates: dict, user: dict = Depends(get_current_user)):
    """Update onboarding state"""
    allowed_fields = ["formation_date_added", "ein_entered", "trust_doc_uploaded", "ein_doc_uploaded", "beneficiaries_added", "assets_added", "minutes_generated", "calendar_set", "checklist_dismissed"]
    update_data = {k: v for k, v in updates.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.user_onboarding.update_one(
        {"user_id": user["user_id"]},
        {"$set": update_data},
        upsert=True
    )
    
    return {"message": "Onboarding updated"}


@router.post("/onboarding/dismiss")
async def dismiss_onboarding(user: dict = Depends(get_current_user)):
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
async def undismiss_onboarding(user: dict = Depends(get_current_user)):
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
    
    return {"activities": await get_recent_activity(user["user_id"], trust_id, limit)}


# ==================== DASHBOARD ENDPOINT ====================

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
    else:
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
    
    trust_id = trust["trust_id"]
    trust_name = trust.get("name", "Unnamed Trust")
    
    health_data = await calculate_health_score(trust_id, user_id, save_snapshot=False)
    health_score = HealthScoreResponse(**health_data)
    
    onboarding_state = await get_onboarding_state(user_id, trust_id)
    
    recent_activity = await get_recent_activity(user_id, trust_id, limit=10)
    
    stats = await get_dashboard_stats(trust_id, user_id)
    
    # Filter out dismissed insights for this trust
    dismissed = await db.dismissed_insights.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "criterion_name": 1}
    ).to_list(1000)
    dismissed_names = {d["criterion_name"] for d in dismissed}
    
    governance_insights = generate_governance_insights(health_data["criteria"])
    governance_insights = [i for i in governance_insights if i.criterion_name not in dismissed_names]
    
    sub_state = await get_subscription_state(user_id)
    subscription = DashboardSubscriptionState(
        plan_type=sub_state.plan_type,
        status=sub_state.status,
        is_trial=sub_state.is_trial,
        is_active=sub_state.is_active,
        is_read_only=sub_state.is_read_only,
        trial_days_remaining=sub_state.trial_days_remaining
    )
    
    return DashboardResponse(
        trust_id=trust_id,
        trust_name=trust_name,
        health_score=health_score,
        onboarding_state=onboarding_state,
        recent_activity=recent_activity,
        stats=stats,
        governance_insights=governance_insights,
        subscription=subscription
    )


# ==================== DISMISS INSIGHT ENDPOINT ====================

@router.post("/insights/dismiss")
async def dismiss_insight(
    req: DismissedInsightCreate,
    user: dict = Depends(get_current_user)
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
    user: dict = Depends(get_current_user)
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
