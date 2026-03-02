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
    DashboardResponse, DashboardSubscriptionState
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


async def calculate_health_score(trust_id: str, user_id: str) -> dict:
    """
    Calculate governance health score using 5 criteria (20 points each):
    1. Quarterly Minutes - minutes generated this quarter
    2. Task Compliance - no overdue tasks
    3. Compensation Alignment - YTD ≤ approved annual
    4. Distribution Documentation - at least 1 distribution logged
    5. Annual Review - annual_review task completed in last 12 months
    """
    now = datetime.now(timezone.utc)
    criteria = []
    total_score = 0
    
    # 1. Quarterly Minutes (+20)
    quarter_start = get_quarter_start(now)
    quarterly_minutes = await db.minutes_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$gte": quarter_start.isoformat()}
    })
    quarterly_achieved = quarterly_minutes > 0
    criteria.append(HealthScoreCriterion(
        name="Quarterly Minutes",
        description="Minutes generated this quarter",
        points=20 if quarterly_achieved else 0,
        achieved=quarterly_achieved
    ))
    if quarterly_achieved:
        total_score += 20
    
    # 2. Task Compliance (+20)
    overdue_tasks = await db.governance_tasks.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "completed_at": None,
        "due_date": {"$lt": now.isoformat()}
    })
    task_compliance = overdue_tasks == 0
    criteria.append(HealthScoreCriterion(
        name="Task Compliance",
        description="No overdue governance tasks",
        points=20 if task_compliance else 0,
        achieved=task_compliance
    ))
    if task_compliance:
        total_score += 20
    
    # 3. Compensation Alignment (+20)
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
    else:
        comp_aligned = True
    
    criteria.append(HealthScoreCriterion(
        name="Compensation Alignment",
        description="YTD compensation within approved plan",
        points=20 if comp_aligned else 0,
        achieved=comp_aligned
    ))
    if comp_aligned:
        total_score += 20
    
    # 4. Distribution Documentation (+20) - includes benevolence documentation quality
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
        dist_points = int(20 * (0.5 + 0.5 * completeness_ratio))
        dist_description = f"Distributions logged; {incomplete_benevolence}/{benevolence_count} benevolence distributions need documentation"
    else:
        dist_documented = True
        dist_points = 20
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
    
    # 5. Annual Review (+20)
    one_year_ago = (now - timedelta(days=365)).isoformat()
    annual_review = await db.governance_tasks.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "task_type": "annual_review",
        "completed_at": {"$gte": one_year_ago}
    }, {"_id": 0})
    annual_done = annual_review is not None
    criteria.append(HealthScoreCriterion(
        name="Annual Review",
        description="Annual review completed in last 12 months",
        points=20 if annual_done else 0,
        achieved=annual_done
    ))
    if annual_done:
        total_score += 20
    
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
            "entities_confirmed": False,
            "calendar_set": False,
            "minutes_generated": False,
            "distribution_logged": False,
            "checklist_dismissed": False
        }
        await db.user_onboarding.insert_one(existing)
    
    # Auto-check based on actual data if trust_id provided
    if trust_id:
        updates = {}
        
        entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
        if entity_count > 0 and not existing.get("entities_confirmed"):
            updates["entities_confirmed"] = True
        
        task_count = await db.governance_tasks.count_documents({
            "trust_id": trust_id, 
            "user_id": user_id,
            "task_type": {"$ne": "custom"}
        })
        if task_count > 0 and not existing.get("calendar_set"):
            updates["calendar_set"] = True
        
        minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
        if minutes_count > 0 and not existing.get("minutes_generated"):
            updates["minutes_generated"] = True
        
        dist_count = await db.distribution_records.count_documents({"trust_id": trust_id, "user_id": user_id})
        comp_count = await db.compensation_payments.count_documents({"trust_id": trust_id, "user_id": user_id})
        if (dist_count > 0 or comp_count > 0) and not existing.get("distribution_logged"):
            updates["distribution_logged"] = True
        
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
    """Get historical health score snapshots for charting"""
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
    allowed_fields = ["entities_confirmed", "calendar_set", "minutes_generated", "distribution_logged", "checklist_dismissed"]
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
    
    governance_insights = generate_governance_insights(health_data["criteria"])
    
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
