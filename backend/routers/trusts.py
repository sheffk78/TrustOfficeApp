# Trusts router - handles trust CRUD operations
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List
from enum import Enum
import uuid

from database import db
from dependencies import (
    get_current_user, require_write_access, calculate_health_score, 
    create_initial_governance_tasks, check_feature_access, Feature,
    PREMIUM_FEATURE_ERROR_MESSAGE, PREMIUM_FEATURE_ERROR_CODE
)
from models import TrustCreate, TrustUpdate, TrustResponse
from utils.tax_calendar_math import _generate_entries

router = APIRouter(tags=["trusts"])


# ==================== TRUST CRUD ENDPOINTS ====================

@router.post("/trusts", response_model=TrustResponse)
async def create_trust(trust: TrustCreate, user: dict = Depends(require_write_access)):
    """
    Create a new trust.
    
    Feature Gate: MULTIPLE_TRUSTS
    - Trial users can only have 1 trust
    - Paid users (monthly/annual) can create up to 10 trusts
    """
    TRUST_LIMIT = 10
    
    # Check if user already has a trust - need MULTIPLE_TRUSTS feature for more
    existing_count = await db.trusts.count_documents({"user_id": user["user_id"]})
    if existing_count >= 1:
        has_multiple_trusts = await check_feature_access(user["user_id"], Feature.MULTIPLE_TRUSTS)
        if not has_multiple_trusts:
            raise HTTPException(
                status_code=PREMIUM_FEATURE_ERROR_CODE,
                detail="Multiple trusts require a paid subscription. Trial accounts are limited to 1 trust."
            )
    
    # Hard cap for paid users
    if existing_count >= TRUST_LIMIT:
        raise HTTPException(
            status_code=402,
            detail=f"Your account can manage up to {TRUST_LIMIT} trusts. Contact contact@trustoffice.app with subject 'Need more trusts' if you need more."
        )
    
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    # Auto-sync jurisdiction and state_code (both should be 2-letter state codes)
    jurisdiction = trust.jurisdiction
    state_code = trust.state_code
    if jurisdiction and len(jurisdiction) == 2 and jurisdiction.isalpha() and not state_code:
        state_code = jurisdiction.upper()
    if state_code and not jurisdiction:
        jurisdiction = state_code.upper()
    
    trust_doc = {
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "name": trust.name,
        "trust_type": trust.trust_type.value,
        "jurisdiction": jurisdiction,
        "role": trust.role or "Trustee",
        "start_date": trust.start_date,
        "trustees": trust.trustees,
        "authority_clause": trust.authority_clause,
        "ein": trust.ein,
        "state_code": state_code,
        "tax_year_end_month": trust.tax_year_end_month,
        "tax_year_end_day": trust.tax_year_end_day,
        "is_fiscal_year": trust.tax_year_end_month is not None and trust.tax_year_end_day is not None and (trust.tax_year_end_month != 12 or trust.tax_year_end_day != 31),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.trusts.insert_one(trust_doc)
    
    # Create initial governance tasks
    await create_initial_governance_tasks(trust_id, user["user_id"])
    
    # Auto-generate tax deadlines for the current tax year
    from datetime import date
    current_tax_year = date.today().year
    existing_count = await db.tax_calendar.count_documents({
        "trust_id": trust_id, "tax_year": current_tax_year
    })
    if existing_count == 0:
        tax_entries = _generate_entries(trust_doc, current_tax_year)
        if tax_entries:
            await db.tax_calendar.insert_many(tax_entries)
    
    return TrustResponse(**trust_doc, governance_score=0)


@router.get("/trusts", response_model=List[TrustResponse])
async def get_trusts(user: dict = Depends(get_current_user)):
    """Get all trusts for the current user"""
    trusts = await db.trusts.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
    
    result = []
    for trust in trusts:
        health = await calculate_health_score(trust["trust_id"], user["user_id"])
        result.append(TrustResponse(**trust, governance_score=health["total_score"]))
    
    return result


@router.get("/trusts/{trust_id}", response_model=TrustResponse)
async def get_trust(trust_id: str, user: dict = Depends(get_current_user)):
    """Get a single trust by ID"""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    health = await calculate_health_score(trust_id, user["user_id"])
    return TrustResponse(**trust, governance_score=health["total_score"])


@router.put("/trusts/{trust_id}", response_model=TrustResponse)
async def update_trust(trust_id: str, update: TrustUpdate, user: dict = Depends(require_write_access)):
    """Update a trust"""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    update_data = {k: v.value if isinstance(v, Enum) else v for k, v in update.model_dump().items() if v is not None}
    
    # Auto-sync jurisdiction and state_code
    if "jurisdiction" in update_data and "state_code" not in update_data:
        j = update_data["jurisdiction"]
        if j and len(j) == 2 and j.isalpha():
            update_data["state_code"] = j.upper()
    if "state_code" in update_data and "jurisdiction" not in update_data:
        s = update_data["state_code"]
        if s:
            update_data["jurisdiction"] = s.upper()
    
    # Auto-compute is_fiscal_year from tax year end date
    month = update_data.get("tax_year_end_month", trust.get("tax_year_end_month"))
    day = update_data.get("tax_year_end_day", trust.get("tax_year_end_day"))
    if month is not None and day is not None:
        update_data["is_fiscal_year"] = (month != 12 or day != 31)
    
    if update_data:
        await db.trusts.update_one({"trust_id": trust_id}, {"$set": update_data})
    
    updated = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0})
    health = await calculate_health_score(trust_id, user["user_id"])
    return TrustResponse(**updated, governance_score=health["total_score"])


@router.delete("/trusts/{trust_id}")
async def delete_trust(trust_id: str, user: dict = Depends(require_write_access)):
    """Delete a trust and all related data"""
    result = await db.trusts.delete_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Delete related data
    await db.entities.delete_many({"trust_id": trust_id})
    await db.entity_relationships.delete_many({"trust_id": trust_id})
    await db.governance_tasks.delete_many({"trust_id": trust_id})
    await db.minutes_records.delete_many({"trust_id": trust_id})
    await db.distribution_records.delete_many({"trust_id": trust_id})
    await db.compensation_plans.delete_many({"trust_id": trust_id})
    await db.compensation_payments.delete_many({"trust_id": trust_id})
    await db.health_score_snapshots.delete_many({"trust_id": trust_id})
    await db.tax_calendar.delete_many({"trust_id": trust_id})
    await db.trust_state_compliance.delete_many({"trust_id": trust_id})
    await db.investments.delete_many({"trust_id": trust_id})
    await db.transactions.delete_many({"trust_id": trust_id})
    await db.communications.delete_many({"trust_id": trust_id})
    await db.vault_documents.delete_many({"trust_id": trust_id})
    await db.alerts.delete_many({"trust_id": trust_id})
    
    return {"message": "Trust deleted"}
