# Distributions router - handles distribution records and benevolence log
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import re

from database import db
from dependencies import get_current_user, require_write_access, auto_update_onboarding
from models import (
    DistributionCreate, DistributionUpdate, DistributionResponse,
    DistributionApprove, DistributionStatusUpdate,
    BenevolenceLogResponse, BenevolenceMonthlyAggregate, BenevolenceYearlyAggregate
)
from email_service import email_service

router = APIRouter(tags=["distributions"])


@router.post("/distributions", response_model=DistributionResponse)
async def create_distribution(
    dist: DistributionCreate, 
    background_tasks: BackgroundTasks, 
    user: dict = Depends(require_write_access)
):
    """Create a new distribution record"""
    trust = await db.trusts.find_one({"trust_id": dist.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    # Fix 8: Check distribution standard from the trust's associated entity
    entity = await db.entities.find_one({"trust_id": dist.trust_id}, {"_id": 0})
    distribution_standard = ""
    if entity:
        distribution_standard = entity.get("beneficiary_standard", "")

    # HEMS enforcement: if the trust uses HEMS standard, warn but don't block
    # (HEMS = Health, Education, Maintenance, Support)
    # Since PurposeClassification only has distribution/compensation/expense/other,
    # we can't hard-block non-HEMS categories. Instead, add a soft flag for review.
    if distribution_standard and distribution_standard.strip():
        dist_doc_note = f"Distribution standard: {distribution_standard}. Trustee should verify this distribution complies with the trust's beneficiary standard."

    # Fix 9: Validate beneficiary against known beneficiaries (soft warning)
    beneficiary_not_verified = False
    if dist.beneficiary_name and dist.beneficiary_name.strip():
        beneficiary = await db.beneficiaries.find_one({
            "trust_id": dist.trust_id,
            "name": {"$regex": f"^{dist.beneficiary_name.strip()}$", "$options": "i"}
        })
        if not beneficiary:
            beneficiary_not_verified = True

    # Validate benevolence fields if is_benevolence is true
    if dist.is_benevolence:
        if not dist.benevolence_recipient_name or not dist.benevolence_recipient_name.strip():
            raise HTTPException(
                status_code=400, 
                detail="Benevolence recipient name is required when is_benevolence is true"
            )
        if not dist.benevolence_need_description or not dist.benevolence_need_description.strip():
            raise HTTPException(
                status_code=400, 
                detail="Benevolence need description is required when is_benevolence is true"
            )
    
    dist_id = f"dist_{uuid.uuid4().hex[:12]}"
    # Auto-populate trustee_name from trust if not provided
    trustee_name = dist.trustee_name
    if not trustee_name:
        trustee_name = trust.get("trustees", "").split(",")[0].strip() if trust.get("trustees") else ""
    
    dist_doc = {
        "distribution_id": dist_id,
        "trust_id": dist.trust_id,
        "user_id": user["user_id"],
        "beneficiary_name": dist.beneficiary_name,
        "amount": dist.amount,
        "date": dist.date,
        "purpose_classification": dist.purpose_classification.value,
        "authority_clause_ref": dist.authority_clause_ref,
        "notes": dist.notes,
        "trustee_name": trustee_name,
        "solvency_confirmed": False,
        "recusal_acknowledged": False,
        "approved_by": None,
        "approved_at": None,
        "minutes_record_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        # Benevolence fields
        "is_benevolence": dist.is_benevolence,
        "benevolence_recipient_name": dist.benevolence_recipient_name if dist.is_benevolence else None,
        "benevolence_need_description": dist.benevolence_need_description if dist.is_benevolence else None,
        "benevolence_notes": dist.benevolence_notes if dist.is_benevolence else None,
        # Fix 8: distribution standard from entity
        "distribution_standard": distribution_standard if distribution_standard else None,
        # Fix 9: beneficiary validation flag
        "beneficiary_not_verified": beneficiary_not_verified
    }
    
    await db.distribution_records.insert_one(dist_doc)
    await auto_update_onboarding(user["user_id"], dist.trust_id)
    
    # Send notification email
    background_tasks.add_task(
        email_service.send_distribution_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", ""),
        amount=dist.amount,
        beneficiary=dist.beneficiary_name,
        category=dist.purpose_classification.value,
        date=dist.date,
        status="review"
    )
    
    return DistributionResponse(**dist_doc)


@router.get("/distributions/validate-beneficiary")
async def validate_distribution_beneficiary(
    trust_id: str,
    name: str,
    user: dict = Depends(get_current_user)
):
    """Check if a beneficiary name matches a known beneficiary of the trust"""
    beneficiary = await db.beneficiaries.find_one({
        "trust_id": trust_id,
        "name": {"$regex": f"^{name.strip()}$", "$options": "i"}
    })
    return {"valid": bool(beneficiary), "beneficiary": beneficiary}


@router.get("/distributions", response_model=List[DistributionResponse])
async def get_distributions(
    trust_id: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    purpose: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Get distributions with optional search and filters"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    # Filter by approval status
    if status == "approved":
        query["approved_at"] = {"$ne": None}
    elif status == "pending":
        query["approved_at"] = None
    
    # Filter by purpose classification
    if purpose:
        query["purpose_classification"] = purpose
    
    # Add text search across beneficiary name and notes
    if search:
        search_term = re.escape(search.strip())
        query["$or"] = [
            {"beneficiary_name": {"$regex": search_term, "$options": "i"}},
            {"notes": {"$regex": search_term, "$options": "i"}},
            {"authority_clause_ref": {"$regex": search_term, "$options": "i"}}
        ]
    
    dists = await db.distribution_records.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return [DistributionResponse(**d) for d in dists]


@router.patch("/distributions/{distribution_id}", response_model=DistributionResponse)
async def update_distribution(
    distribution_id: str, 
    update: DistributionUpdate, 
    user: dict = Depends(require_write_access)
):
    """Update a distribution record"""
    dist = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been deleted. Please refresh the page and try again.")
    
    # Build update dict with only provided fields
    update_data = {}
    update_dict = update.model_dump(exclude_unset=True)
    
    for field, value in update_dict.items():
        if field == "purpose_classification" and value is not None:
            update_data[field] = value.value
        else:
            update_data[field] = value
    
    # Validate benevolence fields if is_benevolence is being set or already true
    is_benevolence = update_data.get("is_benevolence", dist.get("is_benevolence", False))
    if is_benevolence:
        recipient = update_data.get("benevolence_recipient_name", dist.get("benevolence_recipient_name"))
        need_desc = update_data.get("benevolence_need_description", dist.get("benevolence_need_description"))
        
        if not recipient or not str(recipient).strip():
            raise HTTPException(
                status_code=400, 
                detail="Benevolence recipient name is required when is_benevolence is true"
            )
        if not need_desc or not str(need_desc).strip():
            raise HTTPException(
                status_code=400, 
                detail="Benevolence need description is required when is_benevolence is true"
            )
    
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.distribution_records.update_one(
            {"distribution_id": distribution_id},
            {"$set": update_data}
        )
    
    updated = await db.distribution_records.find_one(
        {"distribution_id": distribution_id},
        {"_id": 0}
    )
    return DistributionResponse(**updated)


@router.patch("/distributions/{distribution_id}/approve", response_model=DistributionResponse)
async def approve_distribution(
    distribution_id: str, 
    approval: DistributionApprove, 
    background_tasks: BackgroundTasks, 
    user: dict = Depends(require_write_access)
):
    """Approve a distribution with solvency and recusal confirmation"""
    dist = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been deleted. Please refresh the page and try again.")
    
    if not approval.solvency_confirmed:
        raise HTTPException(status_code=400, detail="Solvency must be confirmed to approve the distribution. Please review the trust's financial position and check the solvency confirmation box.")
    
    if not approval.recusal_acknowledged:
        raise HTTPException(status_code=400, detail="Recusal must be acknowledged. Please confirm that no trustee has a conflict of interest before approving.")
    
    approval_time = datetime.now(timezone.utc).isoformat()
    
    # Resolve trustee name from the trust record for human-readable audit trail
    trust = await db.trusts.find_one({"trust_id": dist["trust_id"]}, {"_id": 0})
    trustees_str = (trust or {}).get("trustees", "") or ""
    parsed_trustees = [t.strip() for t in trustees_str.split(",") if t.strip()]
    
    # Prefer the trustee_name already stored on the distribution; otherwise try
    # to match the approving user's identity against the trust's trustees, and
    # finally fall back to the first listed trustee.
    dist_trustee_name = dist.get("trustee_name", "") or ""
    if dist_trustee_name and dist_trustee_name in parsed_trustees:
        trustee_name = dist_trustee_name
    elif parsed_trustees:
        trustee_name = parsed_trustees[0]
    else:
        trustee_name = dist_trustee_name or (trust or {}).get("role", "") or ""
    
    await db.distribution_records.update_one(
        {"distribution_id": distribution_id},
        {"$set": {
            "solvency_confirmed": True,
            "recusal_acknowledged": True,
            "approved_by": user["user_id"],
            "trustee_name": trustee_name,
            "approved_at": approval_time
        }}
    )
    
    updated = await db.distribution_records.find_one({"distribution_id": distribution_id}, {"_id": 0})
    
    # Send approval notification
    background_tasks.add_task(
        email_service.send_distribution_approved_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", "") if trust else "",
        amount=dist["amount"],
        beneficiary=dist["beneficiary_name"],
        approved_by=user.get("name", user["email"]),
        approval_date=approval_time.split("T")[0]
    )
    
    return DistributionResponse(**updated)


@router.patch("/distributions/{distribution_id}/status")
async def patch_distribution_status(
    distribution_id: str, 
    status_update: DistributionStatusUpdate,
    user: dict = Depends(require_write_access)
):
    """Update distribution status via PATCH (set to review, declined, etc.)"""
    valid_statuses = ['review', 'declined', 'pending']
    status = status_update.status
    
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Must be one of: {valid_statuses}. Please select a valid status from the dropdown.")
    
    distribution = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not distribution:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been deleted. Please refresh the page and try again.")
    
    update_fields = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if status in ['review', 'declined', 'pending']:
        update_fields["approved_by"] = None
        update_fields["approved_at"] = None
        update_fields["solvency_confirmed"] = False
        update_fields["recusal_acknowledged"] = False
    
    await db.distribution_records.update_one(
        {"distribution_id": distribution_id},
        {"$set": update_fields}
    )
    
    updated = await db.distribution_records.find_one(
        {"distribution_id": distribution_id},
        {"_id": 0}
    )
    
    return DistributionResponse(**updated)


@router.put("/distributions/{distribution_id}")
async def update_distribution_status(
    distribution_id: str, 
    status: str,
    user: dict = Depends(require_write_access)
):
    """Update distribution status - DEPRECATED, use PATCH /status"""
    valid_statuses = ['review', 'declined', 'pending']
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Must be one of: {valid_statuses}. Please select a valid status from the dropdown.")
    
    distribution = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not distribution:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been deleted. Please refresh the page and try again.")
    
    update_fields = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if status in ['review', 'declined', 'pending']:
        update_fields["approved_by"] = None
        update_fields["approved_at"] = None
        update_fields["solvency_confirmed"] = False
        update_fields["recusal_acknowledged"] = False
    
    await db.distribution_records.update_one(
        {"distribution_id": distribution_id},
        {"$set": update_fields}
    )
    
    updated = await db.distribution_records.find_one(
        {"distribution_id": distribution_id},
        {"_id": 0}
    )
    
    return DistributionResponse(**updated)


@router.patch("/distributions/{distribution_id}/attach-minutes", response_model=DistributionResponse)
async def attach_minutes_to_distribution(
    distribution_id: str,
    request: dict,
    user: dict = Depends(require_write_access)
):
    """
    Attach existing minutes to a distribution record.
    
    This is the "Money → Minutes" flow where the trustee links an existing
    distribution to a minutes record that documented the approval decision.
    Does NOT modify the minutes text - only creates the reference link.
    """
    from datetime import timezone
    
    dist = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been deleted. Please refresh the page and try again.")
    
    minutes_record_id = request.get("minutes_record_id")
    if not minutes_record_id:
        raise HTTPException(status_code=400, detail="minutes_record_id is required. Please select a minutes record to link this distribution to.")
    
    # Verify the minutes record exists and belongs to the user
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes record not found. It may have been deleted. Please refresh the page and try again.")
    
    await db.distribution_records.update_one(
        {"distribution_id": distribution_id},
        {"$set": {
            "minutes_record_id": minutes_record_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    updated = await db.distribution_records.find_one(
        {"distribution_id": distribution_id},
        {"_id": 0}
    )
    return DistributionResponse(**updated)


@router.delete("/distributions/{distribution_id}")
async def delete_distribution(distribution_id: str, user: dict = Depends(require_write_access)):
    """Delete a distribution record"""
    result = await db.distribution_records.delete_one({
        "distribution_id": distribution_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been already deleted. Please refresh the page and try again.")
    return {"message": "Distribution deleted"}


# ==================== BENEVOLENCE LOG ====================

@router.get("/benevolence-log", response_model=BenevolenceLogResponse)
async def get_benevolence_log(
    trust_id: Optional[str] = None,
    user: dict = Depends(require_write_access)
):
    """
    Get all benevolence distributions for a trust with aggregated totals.
    
    Returns:
    - All distributions where is_benevolence = true
    - Monthly aggregates (amount and count)
    - Yearly aggregates (amount and count)
    - Count of distributions with incomplete documentation
    """
    user_id = user["user_id"]
    
    # Get trust
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
        if not trust:
            raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    else:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        if not trust:
            raise HTTPException(status_code=404, detail="No trust found for your account. Please create a trust first.")
    
    trust_id = trust["trust_id"]
    trust_name = trust.get("name", "Unnamed Trust")
    
    # Get all benevolence distributions
    query = {
        "trust_id": trust_id,
        "user_id": user_id,
        "is_benevolence": True
    }
    
    benevolence_dists = await db.distribution_records.find(
        query, {"_id": 0}
    ).sort("date", -1).to_list(10000)
    
    # Calculate aggregates
    monthly_map = {}
    yearly_map = {}
    total_amount = 0
    incomplete_count = 0
    
    for dist in benevolence_dists:
        amount = dist.get("amount", 0)
        total_amount += amount
        
        # Check for incomplete documentation
        if not dist.get("benevolence_recipient_name") or not dist.get("benevolence_need_description"):
            incomplete_count += 1
        elif not dist.get("approved_at") and not dist.get("minutes_record_id"):
            incomplete_count += 1
        
        # Parse date for aggregation
        date_str = dist.get("date", "")
        if date_str:
            try:
                parts = date_str.split("-")
                if len(parts) >= 2:
                    year = int(parts[0])
                    month = f"{parts[0]}-{parts[1]}"
                    
                    if month not in monthly_map:
                        monthly_map[month] = {"total_amount": 0, "count": 0}
                    monthly_map[month]["total_amount"] += amount
                    monthly_map[month]["count"] += 1
                    
                    if year not in yearly_map:
                        yearly_map[year] = {"total_amount": 0, "count": 0}
                    yearly_map[year]["total_amount"] += amount
                    yearly_map[year]["count"] += 1
            except (ValueError, IndexError):
                pass
    
    monthly_aggregates = [
        BenevolenceMonthlyAggregate(month=k, total_amount=v["total_amount"], count=v["count"])
        for k, v in sorted(monthly_map.items(), reverse=True)
    ]
    
    yearly_aggregates = [
        BenevolenceYearlyAggregate(year=k, total_amount=v["total_amount"], count=v["count"])
        for k, v in sorted(yearly_map.items(), reverse=True)
    ]
    
    distributions = [DistributionResponse(**d) for d in benevolence_dists]
    
    return BenevolenceLogResponse(
        trust_id=trust_id,
        trust_name=trust_name,
        distributions=distributions,
        monthly_aggregates=monthly_aggregates,
        yearly_aggregates=yearly_aggregates,
        total_all_time=total_amount,
        total_count=len(benevolence_dists),
        incomplete_documentation_count=incomplete_count
    )


@router.post("/distributions/{distribution_id}/send-notice")
async def send_distribution_notice(
    distribution_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_write_access)
):
    """Send a distribution notice email to the beneficiary.
    
    Looks up the beneficiary's email from certificate records (Phase 1 data).
    Requires the distribution to exist and the beneficiary to have an email on file.
    """
    # Find the distribution
    dist = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been deleted. Please refresh the page and try again.")
    
    # Get trust info
    trust = await db.trusts.find_one(
        {"trust_id": dist["trust_id"], "user_id": user["user_id"]},
        {"_id": 0, "name": 1, "trust_id": 1}
    )
    trust_name = trust.get("name", "Trust") if trust else "Trust"
    
    # Idempotency check — reject if notice was already sent
    if dist.get("notice_sent_at"):
        existing_cert = await db.trust_unit_certificates.find_one(
            {"trust_id": dist["trust_id"], "holder_name": dist.get("beneficiary_name", "")},
            {"_id": 0, "email": 1}
        )
        existing_email = existing_cert.get("email") if existing_cert else None
        raise HTTPException(
            status_code=409,
            detail=f"Distribution notice was already sent on {dist['notice_sent_at']}"
        )

    # Look up beneficiary email from certificate records (case-insensitive)
    beneficiary_name = dist.get("beneficiary_name", "")
    escaped_name = re.escape(beneficiary_name.strip())
    cert = await db.trust_unit_certificates.find_one(
        {"trust_id": dist["trust_id"], "holder_name": {"$regex": f"^{escaped_name}$", "$options": "i"}},
        {"_id": 0, "email": 1, "phone": 1, "holder_name": 1}
    )
    
    beneficiary_email = cert.get("email") if cert else None
    
    if not beneficiary_email:
        raise HTTPException(
            status_code=400,
            detail=f"No email address on file for beneficiary '{beneficiary_name}'. Add an email to their certificate record first."
        )
    
    # Format amount
    amount = dist.get("amount", 0)
    date_str = dist.get("date", "")
    status = "approved" if dist.get("approved_at") else "review"
    category = dist.get("purpose_classification", "Distribution")
    notes = dist.get("notes", "")
    
    # Send the notice
    background_tasks.add_task(
        email_service.send_distribution_notice_to_beneficiary,
        to_email=beneficiary_email,
        beneficiary_name=beneficiary_name,
        trust_name=trust_name,
        amount=amount,
        date=date_str,
        category=category,
        status=status,
        notes=notes,
        from_user_name=user.get("name", "")
    )
    
    # Record that notice was sent (idempotency)
    notice_sent_at = datetime.now(timezone.utc).isoformat()
    await db.distribution_records.update_one(
        {"distribution_id": distribution_id},
        {"$set": {"notice_sent_at": notice_sent_at}}
    )
    
    return {
        "message": "Distribution notice sent",
        "recipient_email": beneficiary_email,
        "beneficiary_name": beneficiary_name,
        "notice_sent_at": notice_sent_at
    }
