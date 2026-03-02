# Compensation router - handles trustee compensation plans and payments
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, require_write_access, get_year_start
from models import (
    CompensationPlanCreate, CompensationPlanResponse,
    CompensationPaymentCreate, CompensationPaymentResponse
)

router = APIRouter(tags=["compensation"])

# ==================== HELPER FUNCTIONS ====================

def get_year_from_date(date_str: str) -> int:
    """Extract year from date string (YYYY-MM-DD or ISO format)"""
    try:
        return int(date_str[:4])
    except (ValueError, TypeError, IndexError):
        return datetime.now(timezone.utc).year


async def get_primary_plan_for_year(trust_id: str, user_id: str, year: int):
    """Get the primary compensation plan for a given trust and year"""
    # First try to find a plan explicitly marked as primary for this year
    primary_plan = await db.compensation_plans.find_one(
        {
            "trust_id": trust_id, 
            "user_id": user_id,
            "year": year,
            "is_primary": True
        },
        {"_id": 0}
    )
    
    if primary_plan:
        return primary_plan
    
    # Fallback: find any plan for this year (legacy support)
    plan = await db.compensation_plans.find_one(
        {
            "trust_id": trust_id, 
            "user_id": user_id,
            "$or": [
                {"year": year},
                {"effective_date": {"$regex": f"^{year}"}}
            ]
        },
        {"_id": 0},
        sort=[("is_primary", -1), ("effective_date", -1)]
    )
    
    if plan:
        return plan
    
    # Last fallback: most recent plan regardless of year
    return await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )


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
    """
    Create a new compensation plan for a trust.
    
    For most use cases, there should be one primary plan per trust per year.
    Additional plans are allowed for trustee-specific or role-specific caps.
    
    If is_primary is True and another primary plan exists for the same year,
    the existing plan is demoted to non-primary.
    """
    trust = await db.trusts.find_one({"trust_id": plan.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Determine the year from effective_date
    year = get_year_from_date(plan.effective_date)
    
    # Determine if this should be a primary plan
    # Default to primary if no trustee_name/role specified and no primary exists for this year
    is_primary = plan.is_primary if hasattr(plan, 'is_primary') and plan.is_primary is not None else None
    
    if is_primary is None:
        # If no trustee name specified, it's likely intended as the trust-wide primary plan
        if not plan.trustee_name and not plan.role:
            # Check if a primary plan already exists for this year
            existing_primary = await db.compensation_plans.find_one(
                {"trust_id": plan.trust_id, "user_id": user["user_id"], "year": year, "is_primary": True},
                {"_id": 0}
            )
            is_primary = not existing_primary
        else:
            # Trustee-specific plan - not primary by default
            is_primary = False
    
    # If setting as primary, demote any existing primary plan for this year
    if is_primary:
        await db.compensation_plans.update_many(
            {"trust_id": plan.trust_id, "user_id": user["user_id"], "year": year, "is_primary": True},
            {"$set": {"is_primary": False}}
        )
    
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    approved_amount = plan.annual_approved_amount or plan.annual_amount or 0
    
    plan_doc = {
        "plan_id": plan_id,
        "trust_id": plan.trust_id,
        "user_id": user["user_id"],
        "trustee_name": plan.trustee_name or "",
        "role": plan.role or "",
        "annual_fee": approved_amount,
        "annual_amount": approved_amount,
        "annual_approved_amount": approved_amount,
        "fee_type": plan.fee_type,
        "effective_date": plan.effective_date,
        "year": year,
        "is_primary": is_primary,
        "notes": plan.notes,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.compensation_plans.insert_one(plan_doc)
    
    return CompensationPlanResponse(**plan_doc)


@router.put("/compensation-plans/{plan_id}", response_model=CompensationPlanResponse)
async def update_comp_plan(plan_id: str, updates: dict, user: dict = Depends(require_write_access)):
    """Update an existing compensation plan"""
    existing = await db.compensation_plans.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    allowed_fields = ["annual_approved_amount", "effective_date", "notes", "trustee_name", "role", "is_primary"]
    update_doc = {}
    
    for field in allowed_fields:
        if field in updates and updates[field] is not None:
            update_doc[field] = updates[field]
    
    # Handle amount field synchronization
    if "annual_approved_amount" in update_doc:
        update_doc["annual_amount"] = update_doc["annual_approved_amount"]
        update_doc["annual_fee"] = update_doc["annual_approved_amount"]
    
    # If updating effective_date, update year
    if "effective_date" in update_doc:
        update_doc["year"] = get_year_from_date(update_doc["effective_date"])
    
    # If setting as primary, demote other primary plans for this year
    if update_doc.get("is_primary"):
        year = update_doc.get("year", existing.get("year", datetime.now(timezone.utc).year))
        await db.compensation_plans.update_many(
            {
                "trust_id": existing["trust_id"], 
                "user_id": user["user_id"], 
                "year": year, 
                "is_primary": True,
                "plan_id": {"$ne": plan_id}
            },
            {"$set": {"is_primary": False}}
        )
    
    update_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.compensation_plans.update_one(
        {"plan_id": plan_id},
        {"$set": update_doc}
    )
    
    updated = await db.compensation_plans.find_one({"plan_id": plan_id}, {"_id": 0})
    return CompensationPlanResponse(**updated)


@router.delete("/compensation-plans/{plan_id}")
async def delete_comp_plan(plan_id: str, user: dict = Depends(require_write_access)):
    """Delete a compensation plan"""
    result = await db.compensation_plans.delete_one({
        "plan_id": plan_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"message": "Plan deleted"}


@router.get("/compensation-plans", response_model=List[CompensationPlanResponse])
async def get_comp_plans(trust_id: str, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    """
    Get compensation plans for a trust.
    
    If year is specified, returns plans for that year.
    Otherwise, returns all plans sorted by is_primary desc, effective_date desc.
    """
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    
    if year:
        query["$or"] = [
            {"year": year},
            {"effective_date": {"$regex": f"^{year}"}}
        ]
    
    plans = await db.compensation_plans.find(
        query,
        {"_id": 0}
    ).sort([("is_primary", -1), ("effective_date", -1)]).to_list(100)
    
    return [CompensationPlanResponse(**p) for p in plans]


@router.get("/compensation-plans/primary")
async def get_primary_plan(trust_id: str, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    """
    Get the primary compensation plan for a trust and year.
    
    If no year specified, uses the current year.
    """
    if not year:
        year = datetime.now(timezone.utc).year
    
    plan = await get_primary_plan_for_year(trust_id, user["user_id"], year)
    
    if not plan:
        return {"plan": None, "year": year}
    
    return {
        "plan": CompensationPlanResponse(**plan),
        "year": year
    }


# ==================== COMPENSATION PAYMENT ENDPOINTS ====================

@router.post("/compensation-payments", response_model=CompensationPaymentResponse)
async def create_comp_payment(payment: CompensationPaymentCreate, user: dict = Depends(require_write_access)):
    """
    Record a new compensation payment.
    
    The payment is checked against the current year's primary plan to determine
    if it exceeds the approved annual amount.
    """
    trust = await db.trusts.find_one({"trust_id": payment.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    payment_id = f"payment_{uuid.uuid4().hex[:12]}"
    
    # Determine the year from payment date
    payment_year = get_year_from_date(payment.date)
    
    # Get the primary plan for the payment year
    primary_plan = await get_primary_plan_for_year(payment.trust_id, user["user_id"], payment_year)
    
    # Check if payment exceeds plan
    exceeds_plan = False
    if primary_plan:
        year_start = datetime(payment_year, 1, 1, tzinfo=timezone.utc)
        year_end = datetime(payment_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        
        existing = await db.compensation_payments.find(
            {
                "trust_id": payment.trust_id, 
                "user_id": user["user_id"], 
                "date": {"$gte": year_start.isoformat()[:10], "$lte": year_end.isoformat()[:10]}
            },
            {"_id": 0}
        ).to_list(1000)
        
        ytd_total = sum(p.get("amount", 0) for p in existing) + payment.amount
        approved_amount = primary_plan.get("annual_approved_amount") or primary_plan.get("annual_fee") or primary_plan.get("annual_amount", 0)
        exceeds_plan = ytd_total > approved_amount
    
    payment_doc = {
        "payment_id": payment_id,
        "trust_id": payment.trust_id,
        "user_id": user["user_id"],
        "amount": payment.amount,
        "date": payment.date,
        "classification_text": payment.classification_text,
        "exceeds_plan_flag": exceeds_plan,
        "plan_id": primary_plan.get("plan_id") if primary_plan else None,
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
async def get_comp_ytd(trust_id: str, year: Optional[int] = None, user: dict = Depends(get_current_user)):
    """
    Get YTD compensation total and plan info.
    
    Uses the primary plan for the specified year (or current year).
    Returns comparison against the trust-wide compensation envelope.
    """
    if not year:
        year = datetime.now(timezone.utc).year
    
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"
    
    payments = await db.compensation_payments.find(
        {
            "trust_id": trust_id, 
            "user_id": user["user_id"], 
            "date": {"$gte": year_start, "$lte": year_end}
        },
        {"_id": 0}
    ).to_list(1000)
    ytd_total = sum(p.get("amount", 0) for p in payments)
    
    # Get the primary plan for this year
    primary_plan = await get_primary_plan_for_year(trust_id, user["user_id"], year)
    
    annual_approved = 0
    plan_info = None
    if primary_plan:
        annual_approved = primary_plan.get("annual_approved_amount") or primary_plan.get("annual_fee") or primary_plan.get("annual_amount", 0)
        plan_info = {
            "plan_id": primary_plan.get("plan_id"),
            "annual_approved_amount": annual_approved,
            "effective_date": primary_plan.get("effective_date"),
            "notes": primary_plan.get("notes"),
            "is_primary": primary_plan.get("is_primary", True),
            "trustee_name": primary_plan.get("trustee_name", ""),
            "year": primary_plan.get("year", year)
        }
    
    return {
        "year": year,
        "ytd_total": ytd_total,
        "annual_approved": annual_approved,
        "exceeds_plan": ytd_total > annual_approved if annual_approved > 0 else False,
        "remaining": max(0, annual_approved - ytd_total),
        "percent_used": round((ytd_total / annual_approved * 100), 1) if annual_approved > 0 else 0,
        "payment_count": len(payments),
        "primary_plan": plan_info
    }


@router.patch("/compensation-payments/{payment_id}/attach-minutes", response_model=CompensationPaymentResponse)
async def attach_minutes_to_compensation(
    payment_id: str,
    request: dict,
    user: dict = Depends(require_write_access)
):
    """
    Attach existing minutes to a compensation payment record.
    
    This is the "Money → Minutes" flow where the trustee links an existing
    compensation payment to a minutes record that documented the approval decision.
    Does NOT modify the minutes text - only creates the reference link.
    """
    payment = await db.compensation_payments.find_one(
        {"payment_id": payment_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Compensation payment not found")
    
    minutes_record_id = request.get("minutes_record_id")
    if not minutes_record_id:
        raise HTTPException(status_code=400, detail="minutes_record_id is required")
    
    # Verify the minutes record exists and belongs to the user
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes record not found")
    
    await db.compensation_payments.update_one(
        {"payment_id": payment_id},
        {"$set": {
            "minutes_record_id": minutes_record_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    updated = await db.compensation_payments.find_one(
        {"payment_id": payment_id},
        {"_id": 0}
    )
    return CompensationPaymentResponse(**updated)


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
