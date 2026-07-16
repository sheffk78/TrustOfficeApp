# Compensation router - handles trustee compensation plans and payments
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, require_write_access, get_year_start
from trustee_utils import parse_trustees
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
    
    # Check trust profile completion
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
    if trust:
        if trust.get("start_date"):
            updates["formation_date_added"] = True
        if trust.get("ein"):
            updates["ein_entered"] = True
    
    # Check document uploads in vault
    trust_doc_count = await db.vault_documents.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "category": {"$in": ["trust_instrument", "trust_document", "declaration_of_trust"]}
    })
    if trust_doc_count > 0:
        updates["trust_doc_uploaded"] = True
    
    ein_doc_count = await db.vault_documents.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "category": {"$in": ["ein_letter", "irs_notice"]}
    })
    if ein_doc_count > 0:
        updates["ein_doc_uploaded"] = True
    
    # Check beneficiaries (stored in trust_unit_certificates, not db.beneficiaries)
    beneficiary_count = await db.trust_unit_certificates.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    })
    if beneficiary_count > 0:
        updates["beneficiaries_added"] = True
    
    # Check assets (via entities)
    entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
    if entity_count > 0:
        updates["assets_added"] = True
    
    # Check governance tasks (calendar)
    task_count = await db.governance_tasks.count_documents({
        "trust_id": trust_id, 
        "user_id": user_id,
        "task_type": {"$ne": "custom"}
    })
    if task_count > 0:
        updates["calendar_set"] = True
    
    # Check minutes
    minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    if minutes_count > 0:
        updates["minutes_generated"] = True
    
    # Check bank accounts
    bank_account_count = await db.bank_accounts.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "is_archived": {"$ne": True}
    })
    if bank_account_count > 0:
        updates["bank_account_added"] = True

    # Check bank statements (completed or needs_review extraction)
    bank_statement_count = await db.bank_statements.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "extraction_status": {"$in": ["completed", "needs_review"]}
    })
    if bank_statement_count > 0:
        updates["bank_statement_uploaded"] = True

    # Check spending threshold configured
    trust_for_threshold = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "governance_settings": 1}
    )
    gov_settings = trust_for_threshold.get("governance_settings") if trust_for_threshold else None
    if gov_settings and gov_settings.get("spending_threshold") and gov_settings["spending_threshold"].get("amount"):
        updates["spending_threshold_set"] = True
    
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
    
    # Auto-populate trustee_name from the trust record when omitted and the
    # trust has exactly one trustee. Multi-trustee trusts require an explicit
    # choice to avoid silently attributing the plan to the wrong person.
    plan_trustee_name = plan.trustee_name or ""
    if not plan_trustee_name:
        trustees_str = (trust or {}).get("trustees", "") or ""
        parsed_trustees = parse_trustees(trustees_str)
        if len(parsed_trustees) == 1:
            plan_trustee_name = parsed_trustees[0]
    
    plan_doc = {
        "plan_id": plan_id,
        "trust_id": plan.trust_id,
        "user_id": user["user_id"],
        "trustee_name": plan_trustee_name,
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


@router.get("/compensation-plans")
async def get_comp_plans(
    trust_id: str,
    year: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """
    Get compensation plans for a trust (paginated).
    
    If year is specified, returns plans for that year.
    Otherwise, returns all plans sorted by is_primary desc, effective_date desc.
    """
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    
    if year:
        query["year"] = year
    
    total = await db.compensation_plans.count_documents(query)
    plans = await db.compensation_plans.find(
        query,
        {"_id": 0}
    ).sort([("is_primary", -1), ("effective_date", -1)]).skip(skip).limit(limit).to_list(limit)
    
    return {
        "items": [CompensationPlanResponse(**p) for p in plans],
        "total": total,
        "skip": skip,
        "limit": limit
    }


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
        "trustee_name": payment.trustee_name,
        "exceeds_plan_flag": exceeds_plan,
        "plan_id": primary_plan.get("plan_id") if primary_plan else None,
        "minutes_record_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.compensation_payments.insert_one(payment_doc)
    await auto_update_onboarding(user["user_id"], payment.trust_id)
    
    return CompensationPaymentResponse(**payment_doc)


@router.get("/compensation-payments")
async def get_comp_payments(
    trust_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """Get all compensation payments for a trust (paginated)"""
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    
    total = await db.compensation_payments.count_documents(query)
    payments = await db.compensation_payments.find(
        query,
        {"_id": 0}
    ).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "items": [CompensationPaymentResponse(**p) for p in payments],
        "total": total,
        "skip": skip,
        "limit": limit
    }


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
