# Compensation router - handles trustee compensation plans and payments
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List
import uuid

from database import db
from dependencies import get_current_user, require_write_access, get_year_start
from models import (
    CompensationPlanCreate, CompensationPlanResponse,
    CompensationPaymentCreate, CompensationPaymentResponse
)

router = APIRouter(tags=["compensation"])

# ==================== HELPER FUNCTIONS ====================

async def auto_update_onboarding(user_id: str, trust_id: str):
    """Auto-update onboarding state based on user actions"""
    updates = {}
    
    entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
    if entity_count > 0:
        updates["entities_confirmed"] = True
    
    task_count = await db.governance_tasks.count_documents({
        "trust_id": trust_id, 
        "user_id": user_id,
        "task_type": {"$ne": "custom"}
    })
    if task_count > 0:
        updates["calendar_set"] = True
    
    minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    if minutes_count > 0:
        updates["minutes_generated"] = True
    
    dist_count = await db.distribution_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    comp_count = await db.compensation_payments.count_documents({"trust_id": trust_id, "user_id": user_id})
    if dist_count > 0 or comp_count > 0:
        updates["distribution_logged"] = True
    
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.user_onboarding.update_one(
            {"user_id": user_id},
            {"$set": updates},
            upsert=True
        )


# ==================== COMPENSATION PLAN ENDPOINTS ====================

@router.post("/compensation-plans", response_model=CompensationPlanResponse)
async def create_comp_plan(plan: CompensationPlanCreate, user: dict = Depends(require_write_access)):
    """Create a new compensation plan for a trust"""
    trust = await db.trusts.find_one({"trust_id": plan.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    plan_doc = {
        "plan_id": plan_id,
        "trust_id": plan.trust_id,
        "user_id": user["user_id"],
        "trustee_name": plan.trustee_name,
        "role": plan.role,
        "annual_fee": plan.annual_amount or plan.annual_approved_amount,
        "annual_amount": plan.annual_amount or plan.annual_approved_amount,
        "annual_approved_amount": plan.annual_approved_amount or plan.annual_amount,
        "fee_type": plan.fee_type,
        "effective_date": plan.effective_date,
        "notes": plan.notes,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.compensation_plans.insert_one(plan_doc)
    
    return CompensationPlanResponse(**plan_doc)


@router.get("/compensation-plans", response_model=List[CompensationPlanResponse])
async def get_comp_plans(trust_id: str, user: dict = Depends(get_current_user)):
    """Get all compensation plans for a trust"""
    plans = await db.compensation_plans.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("effective_date", -1).to_list(100)
    
    return [CompensationPlanResponse(**p) for p in plans]


# ==================== COMPENSATION PAYMENT ENDPOINTS ====================

@router.post("/compensation-payments", response_model=CompensationPaymentResponse)
async def create_comp_payment(payment: CompensationPaymentCreate, user: dict = Depends(require_write_access)):
    """Record a new compensation payment"""
    trust = await db.trusts.find_one({"trust_id": payment.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    payment_id = f"payment_{uuid.uuid4().hex[:12]}"
    
    # Check if exceeds plan
    exceeds_plan = False
    plan = await db.compensation_plans.find_one(
        {"trust_id": payment.trust_id, "user_id": user["user_id"]},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    
    if plan:
        year_start = get_year_start(datetime.now(timezone.utc))
        existing = await db.compensation_payments.find(
            {"trust_id": payment.trust_id, "user_id": user["user_id"], "date": {"$gte": year_start.isoformat()}},
            {"_id": 0}
        ).to_list(1000)
        ytd_total = sum(p.get("amount", 0) for p in existing) + payment.amount
        # Support both annual_approved_amount and annual_fee fields
        approved_amount = plan.get("annual_approved_amount") or plan.get("annual_fee") or plan.get("annual_amount", 0)
        exceeds_plan = ytd_total > approved_amount
    
    payment_doc = {
        "payment_id": payment_id,
        "trust_id": payment.trust_id,
        "user_id": user["user_id"],
        "amount": payment.amount,
        "date": payment.date,
        "classification_text": payment.classification_text,
        "exceeds_plan_flag": exceeds_plan,
        "minutes_record_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.compensation_payments.insert_one(payment_doc)
    await auto_update_onboarding(user["user_id"], payment.trust_id)
    
    return CompensationPaymentResponse(**payment_doc)


@router.get("/compensation-payments", response_model=List[CompensationPaymentResponse])
async def get_comp_payments(trust_id: str, user: dict = Depends(get_current_user)):
    """Get all compensation payments for a trust"""
    payments = await db.compensation_payments.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("date", -1).to_list(1000)
    
    return [CompensationPaymentResponse(**p) for p in payments]


@router.get("/compensation-ytd")
async def get_comp_ytd(trust_id: str, user: dict = Depends(get_current_user)):
    """Get YTD compensation total and plan info"""
    year_start = get_year_start(datetime.now(timezone.utc))
    
    payments = await db.compensation_payments.find(
        {"trust_id": trust_id, "user_id": user["user_id"], "date": {"$gte": year_start.isoformat()}},
        {"_id": 0}
    ).to_list(1000)
    ytd_total = sum(p.get("amount", 0) for p in payments)
    
    plan = await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    # Support both annual_approved_amount and annual_fee fields
    annual_approved = 0
    if plan:
        annual_approved = plan.get("annual_approved_amount") or plan.get("annual_fee") or plan.get("annual_amount", 0)
    
    return {
        "ytd_total": ytd_total,
        "annual_approved": annual_approved,
        "exceeds_plan": ytd_total > annual_approved if plan else False,
        "remaining": max(0, annual_approved - ytd_total)
    }


@router.delete("/compensation-payments/{payment_id}")
async def delete_comp_payment(payment_id: str, user: dict = Depends(require_write_access)):
    """Delete a compensation payment"""
    result = await db.compensation_payments.delete_one({
        "payment_id": payment_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"message": "Payment deleted"}
