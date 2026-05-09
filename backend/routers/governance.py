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

router = APIRouter(tags=["governance"])


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

            await db.governance_tasks.insert_one({
                "task_id": f"task_{uuid.uuid4().hex[:12]}",
                "trust_id": trust_id,
                "user_id": user_id,
                "task_type": "transaction_review",
                "due_date": due.isoformat(),
                "description": "Monthly Transaction Classification Review — classify any untagged imported transactions and review separation alerts",
                "status": "pending",
                "completed_at": None,
                "created_at": now.isoformat()
            })


async def calculate_health_score(trust_id: str, user_id: str) -> dict:
    """
    Calculate governance health score using 7 criteria:
    """
    # Ensure monthly transaction review task exists for this trust
    await ensure_transaction_review_task(trust_id, user_id)
    
    now = datetime.now(timezone.utc)
    criteria = []
    total_score = 0
    
    # 1. Quarterly Minutes (+15)
    quarter_start = get_quarter_start(now)
    quarterly_minutes = await db.minutes_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$gte": quarter_start.isoformat()}
    })
    quarterly_achieved = quarterly_minutes > 0
    q_points = 15 if quarterly_achieved else 0
    criteria.append(HealthScoreCriterion(
        name="Quarterly Minutes",
        description="Minutes generated this quarter",
        points=q_points,
        achieved=quarterly_achieved
    ))
    total_score += q_points
    
    # 2. Task Compliance (+15)
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
    
    if total_tasks > 0:
        task_compliance = overdue_tasks == 0
        task_points = 15 if task_compliance else max(0, 15 - (overdue_tasks * 4))
    else:
        task_compliance = None
        task_points = 0
    
    criteria.append(HealthScoreCriterion(
        name="Task Compliance",
        description="No overdue governance tasks" if total_tasks > 0 else "No governance tasks tracked yet",
        points=task_points,
        achieved=task_compliance if task_compliance is not None else False,
        no_data=total_tasks == 0
    ))
    total_score += task_points
    
    # 3. Compensation Alignment (+15)
    year_start = get_year_start(now)
    comp_plan = await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    
    if comp_plan:
        ytd_payments = await db.compensation_payments.find(
            {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start.isoformat()}},
            {"_id": 0}
        ).to_list(1000)
        ytd_total = sum(p.get("amount", 0) for p in ytd_payments)
        approved_amount = comp_plan.get("annual_approved_amount") or comp_plan.get("annual_fee") or comp_plan.get("annual_amount", 0)
        comp_aligned = ytd_total <= approved_amount
        comp_points = 15 if comp_aligned else 0
    else:
        comp_aligned = None
        comp_points = 0
    
    criteria.append(HealthScoreCriterion(
        name="Compensation Alignment",
        description="YTD compensation within approved plan" if comp_plan else "No compensation plan set up yet",
        points=comp_points,
        achieved=comp_aligned if comp_aligned is not None else False,
        no_data=comp_plan is None
    ))
    total_score += comp_points
    
    # 4. Distribution Documentation (+15)
    dist_count = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    
    benevolence_dists = await db.distribution_records.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "is_benevolence": True
    }, {"_id": 0}).to_list(1000)
    
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
        dist_points = int(15 * (0.5 + 0.5 * completeness_ratio))
        dist_description = f"Distributions logged; {incomplete_benevolence}/{benevolence_count} benevolence distributions need documentation"
    else:
        dist_documented = True
        dist_points = 15
        if benevolence_count > 0:
            dist_description = f"All distributions documented ({benevolence_count} benevolence distributions fully documented)"
        else:
            dist_description = "Distributions logged"
    
    criteria.append(HealthScoreCriterion(
        name="Distribution Documentation",
        description=dist_description,
        points=dist_points,
        achieved=dist_documented
    ))
    total_score += dist_points
    
    # 5. Annual Review (+10)
    one_year_ago = (now - timedelta(days=365)).isoformat()
    annual_review = await db.governance_tasks.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "task_type": "annual_review",
        "completed_at": {"$gte": one_year_ago}
    }, {"_id": 0})
    annual_done = annual_review is not None
    annual_points = 10 if annual_done else 0
    criteria.append(HealthScoreCriterion(
        name="Annual Review",
        description="Annual review completed in last 12 months",
        points=annual_points,
        achieved=annual_done
    ))
    total_score += annual_points
    
    # 6. Transaction Classification (+15) - % of transactions not classified as "Other"
    total_txns = await db.transactions.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    if total_txns > 0:
        other_txns = await db.transactions.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "governance_classification": "Other"
        })
        classified_pct = ((total_txns - other_txns) / total_txns) * 100
        if classified_pct >= 90:
            txn_points = 15
        elif classified_pct >= 70:
            txn_points = 10
        elif classified_pct >= 50:
            txn_points = 5
        else:
            txn_points = 0
        txn_achieved = classified_pct >= 90
        txn_desc = f"{classified_pct:.0f}% of transactions properly classified"
    else:
        txn_points = 0
        txn_achieved = False
        txn_desc = "No transactions logged yet"
    
    criteria.append(HealthScoreCriterion(
        name="Transaction Classification",
        description=txn_desc,
        points=txn_points,
        achieved=txn_achieved,
        no_data=total_txns == 0
    ))
    total_score += txn_points
    
    # 7. Separation Alert Health (+15) - no unresolved red alerts
    red_alerts = await db.separation_alerts.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active",
        "severity": "red"
    })
    yellow_alerts = await db.separation_alerts.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active",
        "severity": "yellow"
    })
    
    if red_alerts == 0 and yellow_alerts == 0:
        alert_points = 15
        alert_achieved = True
        alert_desc = "No active separation alerts"
    elif red_alerts == 0:
        alert_points = max(0, 15 - (yellow_alerts * 2))
        alert_achieved = yellow_alerts <= 2
        alert_desc = f"{yellow_alerts} yellow alert(s) — needs attention"
    else:
        alert_points = 0
        alert_achieved = False
        alert_desc = f"{red_alerts} red alert(s) — immediate risk"
    
    criteria.append(HealthScoreCriterion(
        name="Separation Alert Health",
        description=alert_desc,
        points=alert_points,
        achieved=alert_achieved,
        no_data=total_txns == 0
    ))
    total_score += alert_points
    
    # Auto-clear dismissals for criteria that are now achieved
    # (Natural restore when user completes the action)
    achieved_names = [c.name for c in criteria if c.achieved]
    if achieved_names:
        await db.dismissed_insights.delete_many({
            "trust_id": trust_id,
            "user_id": user_id,
            "criterion_name": {"$in": achieved_names}
        })
    
    # Determine color
    if total_score >= 80:
        color = HealthColor.green
    elif total_score >= 60:
        color = HealthColor.yellow
    else:
        color = HealthColor.red
    
    # Save snapshot
    snapshot = {
        "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user_id,
        "score_value": total_score,
        "color": color.value,
        "calculated_at": now.isoformat()
    }
    await db.health_score_snapshots.insert_one(snapshot)
    
    return {
        "trust_id": trust_id,
        "total_score": total_score,
        "max_score": 100,
        "color": color.value,
        "criteria": [c.model_dump() for c in criteria],
        "calculated_at": now.isoformat()
    }


def generate_governance_insights(criteria: List[dict]) -> List[GovernanceInsight]:
    """Generate actionable insights from health score criteria."""
    insights = []
    
    for c in criteria:
        if not c["achieved"]:
            if c["name"] == "Quarterly Minutes":
                insights.append(GovernanceInsight(
                    type="warning",
                    criterion_name="Quarterly Minutes",
                    title="Missing Q Minutes",
                    description="Generate minutes this quarter to earn +20 points",
                    action_path="/minutes/new",
                    action_label="Record Now",
                    points=20
                ))
            elif c["name"] == "Task Compliance":
                insights.append(GovernanceInsight(
                    type="error",
                    criterion_name="Task Compliance",
                    title="Overdue Tasks",
                    description="Complete overdue tasks to earn +20 points",
                    action_path="/calendar",
                    action_label="View Tasks",
                    points=20
                ))
            elif c["name"] == "Compensation Alignment":
                insights.append(GovernanceInsight(
                    type="error",
                    criterion_name="Compensation Alignment",
                    title="Compensation Over Plan",
                    description="YTD compensation exceeds approved amount",
                    action_path="/compensation",
                    action_label="Review",
                    points=20
                ))
            elif c["name"] == "Distribution Documentation":
                desc = c.get("description", "")
                if "benevolence" in desc.lower():
                    insights.append(GovernanceInsight(
                        type="warning",
                        criterion_name="Distribution Documentation",
                        title="Benevolence Documentation Needed",
                        description=desc,
                        action_path="/benevolence/log",
                        action_label="Review Benevolence",
                        points=c.get("max_points", 20) - c.get("points", 0)
                    ))
                else:
                    insights.append(GovernanceInsight(
                        type="info",
                        criterion_name="Distribution Documentation",
                        title="No Distributions Logged",
                        description="Log your first distribution to earn +20 points",
                        action_path="/distributions",
                        action_label="Add Distribution",
                        points=20
                    ))
            elif c["name"] == "Annual Review":
                insights.append(GovernanceInsight(
                    type="warning",
                    criterion_name="Annual Review",
                    title="Annual Review Due",
                    description="Complete annual review for +20 points",
                    action_path="/calendar",
                    action_label="Schedule Review",
                    points=20
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
    if trust_id:
        updates = {}
        
        # Check trust profile completion
        trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
        if trust:
            if trust.get("start_date") and not existing.get("formation_date_added"):
                updates["formation_date_added"] = True
            if trust.get("ein") and not existing.get("ein_entered"):
                updates["ein_entered"] = True
        
        # Check document uploads in vault
        trust_doc_count = await db.vault_documents.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "category": {"$in": ["trust_document", "declaration_of_trust"]}
        })
        if trust_doc_count > 0 and not existing.get("trust_doc_uploaded"):
            updates["trust_doc_uploaded"] = True
        
        ein_doc_count = await db.vault_documents.count_documents({
            "trust_id": trust_id,
            "user_id": user_id,
            "category": {"$in": ["ein_letter", "irs_notice"]}
        })
        if ein_doc_count > 0 and not existing.get("ein_doc_uploaded"):
            updates["ein_doc_uploaded"] = True
        
        # Check beneficiaries
        beneficiary_count = await db.beneficiaries.count_documents({"trust_id": trust_id, "user_id": user_id})
        if beneficiary_count > 0 and not existing.get("beneficiaries_added"):
            updates["beneficiaries_added"] = True
        
        # Check assets (via entities)
        entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
        if entity_count > 0 and not existing.get("assets_added"):
            updates["assets_added"] = True
        
        # Check governance tasks (calendar)
        task_count = await db.governance_tasks.count_documents({
            "trust_id": trust_id, 
            "user_id": user_id,
            "task_type": {"$ne": "custom"}
        })
        if task_count > 0 and not existing.get("calendar_set"):
            updates["calendar_set"] = True
        
        # Check minutes
        minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
        if minutes_count > 0 and not existing.get("minutes_generated"):
            updates["minutes_generated"] = True
        
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
    
    health = await calculate_health_score(trust_id, user["user_id"])
    
    # Store snapshot for history tracking
    snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
    await db.health_score_snapshots.insert_one({
        "snapshot_id": snapshot_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "score_value": health["total_score"],
        "color": health["color"],
        "criteria_summary": {c["name"]: c["achieved"] for c in health["criteria"]},
        "calculated_at": datetime.now(timezone.utc).isoformat()
    })
    
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
    
    health_data = await calculate_health_score(trust_id, user_id)
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
