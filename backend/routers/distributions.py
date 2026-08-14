# Distributions router - handles distribution records and benevolence log
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import re

from database import db
from dependencies import get_current_user, require_write_access, auto_update_onboarding, check_feature_access, Feature, PREMIUM_FEATURE_ERROR_CODE, PREMIUM_FEATURE_ERROR_MESSAGE
from trustee_utils import parse_trustees
from models import (
    DistributionCreate, DistributionUpdate, DistributionResponse,
    DistributionApprove, DistributionStatusUpdate,
    BenevolenceLogResponse, BenevolenceMonthlyAggregate, BenevolenceYearlyAggregate
)
from email_service import email_service

router = APIRouter(tags=["distributions"])


# ==================== Helpers ====================

# Valid non-approved statuses for PATCH/PUT status endpoints
VALID_PATCH_STATUSES = ['review', 'declined', 'pending']

# Dispatch map for the status filter in GET /distributions.
# Each value is a callable that mutates the mongo query dict in place.
def _apply_approved_filter(query):
    query["approved_at"] = {"$ne": None}
    query["status"] = {"$ne": "declined"}


def _apply_pending_or_review_filter(query):
    query["approved_at"] = None
    query["status"] = {"$ne": "declined"}


def _apply_declined_filter(query):
    query["status"] = "declined"


STATUS_FILTER_DISPATCH = {
    "approved": _apply_approved_filter,
    "pending": _apply_pending_or_review_filter,
    "review": _apply_pending_or_review_filter,
    "declined": _apply_declined_filter,
}


# Named predicate: does the value look like a non-empty trimmed string?
def _is_non_empty_str(value):
    return bool(value) and bool(str(value).strip())


# Validate benevolence fields when is_benevolence is true.
# Raises HTTPException(400) if required fields are missing.
def _validate_benevolence_fields(recipient_name, need_description):
    if not _is_non_empty_str(recipient_name):
        raise HTTPException(
            status_code=400,
            detail="Benevolence recipient name is required when is_benevolence is true"
        )
    if not _is_non_empty_str(need_description):
        raise HTTPException(
            status_code=400,
            detail="Benevolence need description is required when is_benevolence is true"
        )


# Look up a beneficiary in trust_unit_certificates by name (case-insensitive exact match).
# Returns the certificate doc or None.
async def _find_beneficiary_certificate(trust_id, user_id, beneficiary_name):
    escaped_name = re.escape(beneficiary_name.strip())
    query = {
        "trust_id": trust_id,
        "holder_name": {"$regex": f"^{escaped_name}$", "$options": "i"},
        "status": "active",
    }
    if user_id is not None:
        query["user_id"] = user_id
    return await db.trust_unit_certificates.find_one(query)


# Resolve the trustee name for an approval audit trail.
# Preference order: stored dist trustee_name (if in parsed list) → first parsed trustee →
# stored dist trustee_name → trust role → empty string.
def _resolve_approval_trustee_name(dist_trustee_name, parsed_trustees, trust):
    if dist_trustee_name and dist_trustee_name in parsed_trustees:
        return dist_trustee_name
    if parsed_trustees:
        return parsed_trustees[0]
    return dist_trustee_name or (trust or {}).get("role", "") or ""


# Build the reset fields applied when a status moves back to review/declined/pending.
def _build_status_reset_fields():
    return {
        "approved_by": None,
        "approved_at": None,
        "solvency_confirmed": False,
        "recusal_acknowledged": False,
    }


# Common 404 message for missing distributions.
DISTRIBUTION_NOT_FOUND_MSG = (
    "Distribution not found. It may have been deleted. Please refresh the page and try again."
)


# ==================== Route handlers ====================

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
    # we can't hard-block non-HEMS categories. The distribution_standard is stored
    # on the distribution record for audit/review purposes.

    # Fix 9: Validate beneficiary against known beneficiaries (soft warning)
    # Beneficiaries are stored in trust_unit_certificates, not db.beneficiaries
    beneficiary_not_verified = False
    if _is_non_empty_str(dist.beneficiary_name):
        beneficiary = await _find_beneficiary_certificate(dist.trust_id, user["user_id"], dist.beneficiary_name)
        if not beneficiary:
            beneficiary_not_verified = True

    # Validate benevolence fields if is_benevolence is true
    if dist.is_benevolence:
        if not trust.get("benevolence_enabled"):
            raise HTTPException(status_code=400, detail="Benevolence mode is not enabled for this trust.")
        if not await check_feature_access(user["user_id"], Feature.BENEVOLENCE_MODE):
            raise HTTPException(status_code=PREMIUM_FEATURE_ERROR_CODE, detail=f"{PREMIUM_FEATURE_ERROR_MESSAGE} Feature: {Feature.BENEVOLENCE_MODE}")
        _validate_benevolence_fields(dist.benevolence_recipient_name, dist.benevolence_need_description)

    # Policy limit validation — check against active policy if one exists
    policy_limit_warning = None
    active_policy = await db.benevolence_policies.find_one(
        {"trust_id": dist.trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if active_policy and active_policy.get("current_version_status") == "published":
        version = await db.benevolence_policy_versions.find_one(
            {"policy_version_id": active_policy["current_version_id"]},
            {"_id": 0}
        )
        if version:
            # Check per-recipient annual limit
            annual_limit = version.get("per_recipient_annual_limit")
            if annual_limit:
                ytd_query = {
                    "trust_id": dist.trust_id,
                    "user_id": user["user_id"],
                    "is_benevolence": True,
                    "benevolence_recipient_name": dist.benevolence_recipient_name,
                }
                # Parse date range for YTD if date is provided
                if dist.date:
                    try:
                        year = dist.date.split("-")[0]
                        ytd_query["date"] = {"$gte": f"{year}-01-01", "$lte": f"{year}-12-31"}
                    except Exception:
                        pass
                ytd_total = 0.0
                ytd_records = await db.distribution_records.find(
                    ytd_query, {"_id": 0, "amount": 1}
                ).to_list(length=None)
                for d in ytd_records:
                    ytd_total += float(d.get("amount", 0) or 0)
                if ytd_total + dist.amount > annual_limit:
                    policy_limit_warning = (
                        f"Benevolence distribution of ${dist.amount:,.2f} would exceed "
                        f"the per-recipient annual limit of ${annual_limit:,.2f} "
                        f"(YTD total: ${ytd_total:,.2f})."
                    )

            # Check assistance type exclusion
            purpose_str = dist.purpose_classification.value if hasattr(dist.purpose_classification, "value") else str(dist.purpose_classification)
            at_list = version.get("assistance_types", [])
            matching_at = [at for at in at_list if at.get("purpose") == purpose_str]
            if matching_at and any(not at.get("is_allowed", True) for at in matching_at):
                policy_limit_warning = (
                    f"Warning: '{purpose_str}' is marked as excluded in the benevolence policy."
                )

            # Attach policy version if available
            dist = dist.copy(update={"policy_version_id": version.get("policy_version_id")})

    dist_id = f"dist_{uuid.uuid4().hex[:12]}"
    # Auto-populate trustee_name from trust if not provided
    trustee_name = dist.trustee_name
    if not trustee_name:
        trustee_name = parse_trustees(trust.get("trustees", ""))[0] if trust.get("trustees") else ""

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
        "status": "review",  # Phase 5 Fix 4: distributions start in review
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
        "beneficiary_not_verified": beneficiary_not_verified,
        "policy_version_id": dist.policy_version_id,
        "policy_limit_warning": policy_limit_warning,
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
    # Beneficiaries are stored in trust_unit_certificates, not db.beneficiaries
    beneficiary = await _find_beneficiary_certificate(trust_id, user["user_id"], name)
    return {"valid": bool(beneficiary)}


@router.get("/distributions")
async def get_distributions(
    trust_id: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    purpose: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """Get distributions with optional search and filters (paginated)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id

    # Filter by approval status via dispatch map
    if status:
        apply_status_filter = STATUS_FILTER_DISPATCH.get(status)
        if apply_status_filter:
            apply_status_filter(query)

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

    total = await db.distribution_records.count_documents(query)
    dists = await db.distribution_records.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "items": [DistributionResponse(**d) for d in dists],
        "total": total,
        "skip": skip,
        "limit": limit
    }


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
        raise HTTPException(status_code=404, detail=DISTRIBUTION_NOT_FOUND_MSG)

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
        _validate_benevolence_fields(recipient, need_desc)

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
        raise HTTPException(status_code=404, detail=DISTRIBUTION_NOT_FOUND_MSG)

    if not approval.solvency_confirmed:
        raise HTTPException(status_code=400, detail="Solvency must be confirmed to approve the distribution. Please review the trust's financial position and check the solvency confirmation box.")

    if not approval.recusal_acknowledged:
        raise HTTPException(status_code=400, detail="Recusal must be acknowledged. Please confirm that no trustee has a conflict of interest before approving.")

    approval_time = datetime.now(timezone.utc).isoformat()

    # Resolve trustee name from the trust record for human-readable audit trail
    trust = await db.trusts.find_one({"trust_id": dist["trust_id"]}, {"_id": 0})
    trustees_str = (trust or {}).get("trustees", "") or ""
    parsed_trustees = parse_trustees(trustees_str)

    # Prefer the trustee_name already stored on the distribution; otherwise try
    # to match the approving user's identity against the trust's trustees, and
    # finally fall back to the first listed trustee.
    trustee_name = _resolve_approval_trustee_name(
        dist.get("trustee_name", ""),
        parsed_trustees,
        trust,
    )

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
    status = status_update.status

    if status not in VALID_PATCH_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Must be one of: {VALID_PATCH_STATUSES}. Please select a valid status from the dropdown.")

    distribution = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not distribution:
        raise HTTPException(status_code=404, detail=DISTRIBUTION_NOT_FOUND_MSG)

    update_fields = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    update_fields.update(_build_status_reset_fields())

    await db.distribution_records.update_one(
        {"distribution_id": distribution_id},
        {"$set": update_fields}
    )

    updated = await db.distribution_records.find_one(
        {"distribution_id": distribution_id},
        {"_id": 0}
    )

    return DistributionResponse(**updated)


@router.put("/distributions/{distribution_id}", deprecated=True, include_in_schema=False)
async def update_distribution_status(
    distribution_id: str,
    status: str,
    user: dict = Depends(require_write_access)
):
    """Update distribution status - DEPRECATED, use PATCH /status"""
    if status not in VALID_PATCH_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Must be one of: {VALID_PATCH_STATUSES}. Please select a valid status from the dropdown.")

    distribution = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not distribution:
        raise HTTPException(status_code=404, detail=DISTRIBUTION_NOT_FOUND_MSG)

    update_fields = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    update_fields.update(_build_status_reset_fields())

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
        raise HTTPException(status_code=404, detail=DISTRIBUTION_NOT_FOUND_MSG)

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
    dist = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been already deleted. Please refresh the page and try again.")

    result = await db.distribution_records.delete_one({
        "distribution_id": distribution_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Distribution not found. It may have been already deleted. Please refresh the page and try again.")

    # Log to audit trail
    from utils.audit import log_audit_event
    await log_audit_event(
        user_id=user["user_id"],
        action="distribution_deleted",
        entity_type="distribution",
        entity_id=distribution_id,
        details={
            "trust_id": dist.get("trust_id"),
            "beneficiary_name": dist.get("beneficiary_name"),
            "amount": dist.get("amount"),
            "date": dist.get("date"),
        }
    )

    return {"message": "Distribution deleted"}


# ==================== BENEVOLENCE LOG ====================

# Resolve the trust for the benevolence log: by trust_id if provided, else the
# most recently created trust for the user.
async def _resolve_trust_for_benevolence(trust_id, user_id):
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
    return trust


# Named predicate: is this benevolence distribution missing required documentation?
def _has_incomplete_documentation(dist):
    if not dist.get("benevolence_recipient_name") or not dist.get("benevolence_need_description"):
        return True
    if not dist.get("approved_at") and not dist.get("minutes_record_id"):
        return True
    return False


# Parse a "YYYY-MM-DD..." date string into (year:int, month:str) or (None, None).
def _parse_year_month(date_str):
    if not date_str:
        return None, None
    try:
        parts = date_str.split("-")
        if len(parts) >= 2:
            year = int(parts[0])
            month = f"{parts[0]}-{parts[1]}"
            return year, month
    except (ValueError, IndexError):
        pass
    return None, None


@router.get("/benevolence-log", response_model=BenevolenceLogResponse)
async def get_benevolence_log(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
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

    trust = await _resolve_trust_for_benevolence(trust_id, user_id)
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
        if _has_incomplete_documentation(dist):
            incomplete_count += 1

        # Parse date for aggregation
        year, month = _parse_year_month(dist.get("date", ""))
        if year is None:
            continue

        if month not in monthly_map:
            monthly_map[month] = {"total_amount": 0, "count": 0}
        monthly_map[month]["total_amount"] += amount
        monthly_map[month]["count"] += 1

        if year not in yearly_map:
            yearly_map[year] = {"total_amount": 0, "count": 0}
        yearly_map[year]["total_amount"] += amount
        yearly_map[year]["count"] += 1

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
        raise HTTPException(status_code=404, detail=DISTRIBUTION_NOT_FOUND_MSG)

    # Get trust info
    trust = await db.trusts.find_one(
        {"trust_id": dist["trust_id"], "user_id": user["user_id"]},
        {"_id": 0, "name": 1, "trust_id": 1}
    )
    trust_name = trust.get("name", "Trust") if trust else "Trust"

    # Idempotency check — reject if notice was already sent
    if dist.get("notice_sent_at"):
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