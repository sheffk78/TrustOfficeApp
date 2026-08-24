"""
Beneficiaries router - Beneficiary dashboard for trust unit allocations
Migrated from server.py
"""
import re
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from dependencies import get_current_user, require_write_access, auto_update_onboarding
from database import db
from models import (
    BeneficiaryDashboardResponse, BeneficiaryAllocation,
    ClassBeneficiaryCreate, ClassBeneficiaryResponse, ClassBeneficiaryType,
    BeneficiaryCreate, BeneficiaryUpdate, SendCertificateRequest,
    TrustUnitCertificateCreate,
)
from routers.trust_units import create_unit_certificate as _create_cert, get_or_create_units_settings, get_next_certificate_number

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])


# ========== CLASS BENEFICIARY LABELS ==========
CLASS_BENEFICIARY_LABELS = {
    "children": "Children (including after-born)",
    "descendants": "Descendants",
    "issue": "Issue (lineal descendants)",
    "heirs": "Heirs",
    "heirs_at_law": "Heirs at Law",
    "blood_relatives": "Blood Relatives",
    "per_stirpes": "Per Stirpes (by branch)",
    "per_capita": "Per Capita (by head)",
    "custom": "Custom Class",
}


# ========== CLASS BENEFICIARY ENDPOINTS ==========

@router.post("/class-beneficiaries", response_model=ClassBeneficiaryResponse)
async def create_class_beneficiary(
    data: ClassBeneficiaryCreate,
    user: dict = Depends(require_write_access)
):
    """Add a class beneficiary designation to a trust"""
    user_id = user["user_id"]
    
    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": data.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(data.trust_id, user_id)
    convention = data.distribution_convention or settings.get("class_distribution_convention", "per_capita")
    if convention not in {"per_capita", "per_stirpes"}:
        raise HTTPException(status_code=400, detail="Unsupported class distribution convention.")
    if settings.get("allocation_mode", "percentage") == "percentage":
        existing_pools = await db.class_beneficiaries.aggregate([
            {"$match": {"trust_id": data.trust_id, "user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$percentage"}}},
        ]).to_list(1)
        current_pct = existing_pools[0]["total"] if existing_pools else 0
        if current_pct + data.percentage > 100:
            raise HTTPException(status_code=400, detail="Class-beneficiary pools cannot exceed 100% combined.")

    class_beneficiary = {
        "class_beneficiary_id": f"cb_{uuid.uuid4().hex[:16]}",
        "trust_id": data.trust_id,
        "user_id": user_id,
        "class_type": data.class_type.value,
        "class_type_label": CLASS_BENEFICIARY_LABELS.get(data.class_type.value, data.class_type.value),
        "description": data.description,
        "percentage": data.percentage,
        "notes": data.notes,
        "distribution_convention": convention,
        "reserved_units": round(settings.get("total_authorized_units", 100) * data.percentage / 100, 4),
        "member_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.class_beneficiaries.insert_one(class_beneficiary)
    class_beneficiary.pop("_id", None)
    return class_beneficiary


@router.get("/class-beneficiaries")
async def list_class_beneficiaries(
    trust_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """List all class beneficiaries for a trust (paginated). READ endpoint — available to all authenticated users."""
    user_id = user["user_id"]
    
    query = {"user_id": user_id}
    if trust_id:
        query["trust_id"] = trust_id
    
    total = await db.class_beneficiaries.count_documents(query)
    class_beneficiaries = await db.class_beneficiaries.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "items": class_beneficiaries,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.delete("/class-beneficiaries/{class_beneficiary_id}")
async def delete_class_beneficiary(
    class_beneficiary_id: str,
    user: dict = Depends(require_write_access)
):
    """Remove a class beneficiary designation"""
    user_id = user["user_id"]
    
    result = await db.class_beneficiaries.delete_one({
        "class_beneficiary_id": class_beneficiary_id,
        "user_id": user_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")
    
    return {"status": "deleted"}


@router.post("/class-beneficiaries/{class_beneficiary_id}/members")
async def add_class_member(
    class_beneficiary_id: str,
    member: dict,
    user: dict = Depends(require_write_access),
):
    """Record a trustee-confirmed class member without inferring eligibility."""
    user_id = user["user_id"]
    class_doc = await db.class_beneficiaries.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    )
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")
    name = (member.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Member name is required")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "class_member_id": f"cm_{uuid.uuid4().hex[:12]}",
        "class_beneficiary_id": class_beneficiary_id,
        "trust_id": class_doc["trust_id"], "user_id": user_id,
        "name": name, "confirmed_by_user_id": user_id,
        "confirmed_at": now, "created_at": now,
    }
    await db.class_beneficiary_members.insert_one(doc)
    count = await db.class_beneficiary_members.count_documents({"class_beneficiary_id": class_beneficiary_id, "user_id": user_id})
    await db.class_beneficiaries.update_one({"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"$set": {"member_count": count}})
    doc.pop("_id", None)
    return doc


@router.get("/class-beneficiaries/{class_beneficiary_id}/members")
async def list_class_members(class_beneficiary_id: str, user: dict = Depends(get_current_user)):
    items = await db.class_beneficiary_members.find(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)
    class_doc = await db.class_beneficiaries.find_one({"class_beneficiary_id": class_beneficiary_id, "user_id": user["user_id"]}, {"_id": 0})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")
    pool_pct = class_doc.get("percentage", 0)
    share_pct = round(pool_pct / len(items), 4) if items else 0
    return {"items": items, "member_count": len(items), "pool_percentage": pool_pct, "per_member_percentage": share_pct}


# ========== DASHBOARD ENDPOINT (updated) ==========

@router.get("/dashboard", response_model=BeneficiaryDashboardResponse)
async def get_beneficiary_dashboard(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Beneficiary Dashboard showing current unit allocations per certificate holder.
    Also includes class beneficiary designations.

    READ endpoint — available to all authenticated users (free, expired, past-due).
    Users can view their beneficiary data regardless of subscription status.
    """
    user_id = user["user_id"]
    
    # Get trust
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
        if not trust:
            raise HTTPException(status_code=404, detail="Trust not found")
    else:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        if not trust:
            raise HTTPException(status_code=404, detail="No trust found")
    
    trust_id = trust["trust_id"]
    trust_name = trust.get("name", "Unnamed Trust")
    
    # Get unit settings
    settings = await get_or_create_units_settings(trust_id, user_id)
    total_authorized = settings["total_authorized_units"]
    unit_label = settings.get("unit_label", "Certificate Unit")
    
    # Aggregate certificates directly in MongoDB for correctness at any scale
    pipeline = [
        {"$match": {"trust_id": trust_id, "user_id": user_id, "status": "active"}},
        {
            "$group": {
                "_id": {
                    "holder_name": "$holder_name",
                    "holder_identifier": {"$ifNull": ["$holder_identifier", ""]},
                    "holder_type": {"$ifNull": ["$holder_type", "individual"]},
                },
                "holder_identifier": {"$first": "$holder_identifier"},
                "holder_type": {"$first": {"$ifNull": ["$holder_type", "individual"]}},
                "email": {"$first": "$email"},
                "phone": {"$first": "$phone"},
                "total_units": {"$sum": "$units"},
                "certificates": {
                    "$push": {
                        "certificate_id": "$certificate_id",
                        "certificate_number": "$certificate_number",
                        "holder_name": "$holder_name",
                        "holder_identifier": {"$ifNull": ["$holder_identifier", ""]},
                        "holder_type": {"$ifNull": ["$holder_type", "individual"]},
                        "units": "$units",
                        "issue_date": "$issue_date",
                        "notes": {"$ifNull": ["$notes", ""]},
                        "email": {"$ifNull": ["$email", ""]},
                        "phone": {"$ifNull": ["$phone", ""]},
                    }
                },
            }
        },
        {"$sort": {"total_units": -1}},
    ]
    agg_results = await db.trust_unit_certificates.aggregate(pipeline).to_list(None)

    # Build beneficiary allocations with percentages
    beneficiaries = []
    total_issued = 0
    for row in agg_results:
        holder_data = {
            "holder_name": row["_id"]["holder_name"],
            "holder_identifier": row["holder_identifier"],
            "holder_type": row["holder_type"],
            "email": row["email"],
            "phone": row["phone"],
            "total_units": row["total_units"],
            "certificates": row["certificates"],
        }
        percentage = (holder_data["total_units"] / total_authorized * 100) if total_authorized > 0 else 0
        total_issued += holder_data["total_units"]
        beneficiaries.append(BeneficiaryAllocation(
            holder_name=holder_data["holder_name"],
            holder_identifier=holder_data["holder_identifier"],
            holder_type=holder_data.get("holder_type", "individual"),
            email=holder_data.get("email"),
            phone=holder_data.get("phone"),
            total_units=holder_data["total_units"],
            percentage=round(percentage, 4),
            certificate_count=len(holder_data["certificates"]),
            certificates=holder_data["certificates"]
        ))
    
    # Get class beneficiaries
    class_beneficiaries = await db.class_beneficiaries.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    # Compute allocation totals.
    # Certificate percentages are ISSUED ownership (additive, capped at 100 by
    # create_unit_certificate). Class-beneficiary percentages are RESERVED
    # pools that may overlap with issued certificates (a descendant holding a
    # 15% certificate can also sit in a contingent descendants class), so they
    # are tracked separately and NOT summed into one "total allocated".
    # total_allocated_percentage is therefore max(certificates, classes) as a
    # conservative committed-allocation figure; cert/class totals let the UI
    # show each layer and flag when reserved pools exceed remaining capacity.
    certificate_percentage_total = round(
        sum(b.percentage for b in beneficiaries), 4
    )
    class_beneficiary_percentage_total = round(
        sum(cb.get("percentage", 0) for cb in class_beneficiaries), 4
    )
    total_allocated_percentage = round(
        max(certificate_percentage_total, class_beneficiary_percentage_total), 4
    )
    
    # Get recent transfers
    transfers = await db.trust_unit_transfers.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)

    # Total active certificate count for metadata
    active_cert_count = await db.trust_unit_certificates.count_documents(
        {"trust_id": trust_id, "user_id": user_id, "status": "active"}
    )

    return BeneficiaryDashboardResponse(
        trust_id=trust_id,
        trust_name=trust_name,
        total_authorized_units=total_authorized,
        total_issued_units=total_issued,
        remaining_units=total_authorized - total_issued,
        unit_label=unit_label,
        active_certificate_count=active_cert_count,
        beneficiaries=beneficiaries,
        class_beneficiaries=class_beneficiaries,
        recent_transfers=transfers,
        total_allocated_percentage=total_allocated_percentage,
        class_beneficiary_percentage_total=class_beneficiary_percentage_total,
        certificate_percentage_total=certificate_percentage_total,
    )


# ========== BENEFICIARY MANAGEMENT ENDPOINTS ==========
# These mirror the logic in routers/chat.py _execute_approved_action
# (lines 796-957) but exposed as proper REST handlers so the
# action_registry.py endpoints resolve to real HTTP routes.

@router.get("")
async def list_beneficiaries(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List beneficiaries for a trust.

    READ endpoint — available to all authenticated users.
    Returns {beneficiaries: [...]} with beneficiary_id, name, relationship,
    created_at, and date_added fields. Used by the Audit Trail page.
    """
    user_id = user["user_id"]

    query = {"user_id": user_id}
    if trust_id:
        query["trust_id"] = trust_id

    beneficiaries = await db.beneficiaries.find(
        query,
        {
            "_id": 0,
            "beneficiary_id": 1,
            "trust_id": 1,
            "user_id": 1,
            "name": 1,
            "relationship": 1,
            "created_at": 1,
            "date_added": 1,
        }
    ).sort("created_at", -1).to_list(1000)

    return {"beneficiaries": beneficiaries}


@router.post("/create")
async def create_beneficiary(
    data: BeneficiaryCreate,
    user: dict = Depends(require_write_access)
):
    """Add a beneficiary by issuing a trust unit certificate.

    Converts allocation_pct into a unit count using the trust's unit settings,
    then routes through the trust_units create_unit_certificate handler to
    ensure the same validation (units overflow, fractional, numbering) as a
    direct certificate issuance.
    """
    user_id = user["user_id"]

    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": data.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Get the trust's explicit allocation mode and ceiling.
    settings = await get_or_create_units_settings(data.trust_id, user_id)
    allocation_mode = settings.get("allocation_mode", "percentage")
    total_authorized = settings.get("total_authorized_units", 0)
    allow_fractional = settings.get("allow_fractional", False)

    if total_authorized <= 0:
        raise HTTPException(
            status_code=400,
            detail="Trust has no authorized units. Configure unit settings first."
        )

    allocation_pct = data.allocation_pct
    if allocation_mode == "units" and data.units is not None:
        raw_units = data.units
        allocation_pct = round(raw_units / total_authorized * 100, 4)
    else:
        if allocation_pct is None:
            raise HTTPException(status_code=400, detail="allocation_pct is required in percentage mode")
        if not isinstance(allocation_pct, (int, float)) or allocation_pct <= 0:
            raise HTTPException(status_code=400, detail="allocation_pct must be a positive number greater than 0")
        if allocation_mode == "percentage" and allocation_pct > 100:
            raise HTTPException(status_code=400, detail="Percentage allocations cannot exceed 100%.")
        # Percentage mode converts the requested share to the configured
        # certificate basis; unit mode never infers units from display values.
        raw_units = total_authorized * allocation_pct / 100.0

    if allow_fractional:
        units = round(raw_units, 4)
    else:
        units = round(raw_units)

    ceiling = settings.get("authorized_units_ceiling")
    if allocation_mode == "units" and not settings.get("unlimited_units") and ceiling and units > ceiling:
        raise HTTPException(status_code=400, detail="Allocation exceeds the configured authorized-unit ceiling.")
    if units <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"allocation_pct of {allocation_pct}% resolves to zero units "
                f"(raw={raw_units}, allow_fractional={allow_fractional}). "
                f"Increase the percentage or enable fractional units."
            )
        )

    # Effective percentage back-calculated from final units for the response
    effective_pct = round(units / total_authorized * 100, 4)

    cert_create = TrustUnitCertificateCreate(
        trust_id=data.trust_id,
        holder_name=data.name,
        holder_type=data.holder_type,
        units=float(units),
        issue_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        email=data.email,
        phone=data.phone,
        notes=data.notes or "",
    )

    # create_unit_certificate expects a user dict with user_id
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        user_doc = {"user_id": user_id, "email": "", "name": ""}

    try:
        result = await _create_cert(certificate=cert_create, user=user_doc)
        # Update onboarding checklist
        try:
            await auto_update_onboarding(user_id, data.trust_id)
        except Exception:
            pass
        # Enrich response with the effective values derived from allocation_pct
        response = dict(result) if hasattr(result, "__dict__") else dict(result)
        response["requested_allocation_pct"] = allocation_pct
        response["effective_pct"] = effective_pct
        response["effective_units"] = units
        return response
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create beneficiary: {str(e)}")


@router.patch("/{beneficiary_id}")
async def update_beneficiary(
    beneficiary_id: str,
    data: BeneficiaryUpdate,
    user: dict = Depends(require_write_access)
):
    """Update a beneficiary's contact info (email/phone/notes).

    The beneficiary_id path param is the certificate_id of an active
    trust unit certificate. The trust_id is derived from the certificate
    record itself, so callers don't need to pass it separately.
    """
    user_id = user["user_id"]

    existing = await db.trust_unit_certificates.find_one(
        {
            "certificate_id": beneficiary_id,
            "user_id": user_id,
            "status": "active",
        },
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Beneficiary certificate not found")

    trust_id = existing.get("trust_id")

    update_fields = {}
    if data.email is not None:
        update_fields["email"] = data.email
    if data.phone is not None:
        update_fields["phone"] = data.phone
    if data.notes is not None:
        update_fields["notes"] = data.notes

    # Allocation edits are replacements, not in-place mutations. Validate the
    # replacement against the same canonical trust allocation rules before
    # superseding the prior certificate.
    if data.allocation_pct is not None or data.units is not None:
        settings = await get_or_create_units_settings(trust_id, user_id)
        total_authorized = settings.get("total_authorized_units", 0)
        allocation_mode = settings.get("allocation_mode", "percentage")
        if data.allocation_pct is not None:
            if allocation_mode == "percentage" and data.allocation_pct > 100:
                raise HTTPException(status_code=400, detail="Percentage allocations cannot exceed 100%.")
            replacement_units = total_authorized * data.allocation_pct / 100.0
        else:
            replacement_units = float(data.units or 0)
        if settings.get("allow_fractional"):
            replacement_units = round(replacement_units, 4)
        else:
            replacement_units = round(replacement_units)
        if replacement_units <= 0:
            raise HTTPException(status_code=400, detail="Allocation must resolve to a positive number of units.")
        active_total = await db.trust_unit_certificates.aggregate([
            {"$match": {"trust_id": trust_id, "user_id": user_id, "status": "active", "certificate_id": {"$ne": beneficiary_id}}},
            {"$group": {"_id": None, "total": {"$sum": "$units"}}},
        ]).to_list(1)
        issued_elsewhere = active_total[0]["total"] if active_total else 0
        if issued_elsewhere + replacement_units > total_authorized:
            raise HTTPException(status_code=400, detail="Replacement allocation exceeds the trust's remaining authorized units.")
        now = datetime.now(timezone.utc).isoformat()
        replacement = dict(existing)
        replacement.pop("_id", None)
        replacement["certificate_id"] = f"cert_{uuid.uuid4().hex[:12]}"
        replacement["certificate_number"] = await get_next_certificate_number(trust_id, user_id)
        replacement["units"] = float(replacement.get("units", 0))
        if data.units is not None:
            replacement["units"] = data.units
        elif data.allocation_pct is not None:
            settings = await get_or_create_units_settings(trust_id, user_id)
            replacement["units"] = round(settings["total_authorized_units"] * data.allocation_pct / 100.0, 4 if settings.get("allow_fractional") else 0)
        replacement["supersedes_certificate_id"] = beneficiary_id
        replacement["version"] = int(existing.get("version", 1)) + 1
        replacement["created_at"] = now
        replacement["updated_at"] = now
        replacement["effective_date"] = data.effective_date or now[:10]
        replacement["status"] = "active"
        await db.trust_unit_certificates.update_one(
            {"certificate_id": beneficiary_id, "user_id": user_id, "trust_id": trust_id},
            {"$set": {"status": "superseded", "superseded_at": now, "updated_at": now}},
        )
        await db.trust_unit_certificates.insert_one(replacement)
        await db.beneficiary_allocation_audit.insert_one({
            "audit_id": f"baa_{uuid.uuid4().hex[:12]}", "trust_id": trust_id,
            "user_id": user_id, "action": "replacement_created",
            "prior_certificate_id": beneficiary_id, "replacement_certificate_id": replacement["certificate_id"],
            "created_at": now,
            "reason": data.replacement_reason or "Allocation updated",
            "effective_date": replacement["effective_date"],
        })
        update_fields = {k: v for k, v in update_fields.items() if k in {"email", "phone", "notes"}}
        if update_fields:
            await db.trust_unit_certificates.update_one({"certificate_id": replacement["certificate_id"]}, {"$set": update_fields})
        return replacement

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.trust_unit_certificates.update_one({"certificate_id": beneficiary_id, "user_id": user_id, "trust_id": trust_id}, {"$set": update_fields})

    updated = await db.trust_unit_certificates.find_one(
        {"certificate_id": beneficiary_id, "user_id": user_id},
        {"_id": 0}
    )
    return updated


@router.delete("/{beneficiary_id}")
async def delete_beneficiary(
    beneficiary_id: str,
    user: dict = Depends(require_write_access)
):
    """Remove (deactivate) a beneficiary.

    Marks the underlying trust unit certificate as inactive rather than
    deleting the record, preserving an audit trail. The trust_id is
    derived from the certificate record itself.
    """
    user_id = user["user_id"]

    existing = await db.trust_unit_certificates.find_one(
        {
            "certificate_id": beneficiary_id,
            "user_id": user_id,
            "status": "active",
        },
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Beneficiary certificate not found")

    trust_id = existing.get("trust_id")

    await db.trust_unit_certificates.update_one(
        {"certificate_id": beneficiary_id, "user_id": user_id, "trust_id": trust_id},
        {"$set": {
            "status": "inactive",
            "deactivated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    return {"status": "deleted", "certificate_id": beneficiary_id}


@router.post("/send-certificate")
async def send_beneficiary_certificate(
    data: SendCertificateRequest,
    user: dict = Depends(require_write_access)
):
    """Email a beneficiary their certificate notice.

    Looks up all active certificates for the named holder, aggregates the
    unit total, and sends a templated certificate notice email. The
    optional email field overrides the address on file.
    """
    user_id = user["user_id"]

    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": data.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Find active certificates for this holder (case-insensitive exact match)
    holder_name = data.beneficiary_name
    certs = await db.trust_unit_certificates.find(
        {
            "trust_id": data.trust_id,
            "user_id": user_id,
            "holder_name": {"$regex": f"^{re.escape(holder_name)}$", "$options": "i"},
            "status": "active",
        },
        {"_id": 0}
    ).to_list(5000)

    if not certs:
        raise HTTPException(
            status_code=404,
            detail=f"No active certificate found for beneficiary '{holder_name}'. Add them as a beneficiary first."
        )

    # Aggregate units across all certificates for this holder
    total_units = sum(c.get("units", 0) for c in certs)
    first_cert = certs[0]
    cert_number = first_cert.get("certificate_number", "N/A")
    cert_email = data.email or first_cert.get("email", "")

    if not cert_email:
        raise HTTPException(
            status_code=400,
            detail=f"No email address on file for '{holder_name}'. Provide an email address or update the beneficiary record first."
        )

    # Get trust name and unit settings
    trust_name = trust.get("name", "Your Trust")
    settings = await get_or_create_units_settings(data.trust_id, user_id)
    total_authorized = settings.get("total_authorized_units", 0)
    unit_label = settings.get("unit_label", "Certificate Unit")
    percentage = (total_units / total_authorized * 100) if total_authorized > 0 else 0

    # Get trustee name (the user's name)
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "email": 1})
    from_name = user_doc.get("name", "Trustee") if user_doc else "Trustee"

    # Send the certificate email
    import email_service
    result = await email_service.send_certificate_notice(
        to_email=cert_email,
        beneficiary_name=holder_name,
        trust_name=trust_name,
        certificate_number=cert_number,
        units=total_units,
        unit_label=unit_label,
        percentage=percentage,
        issue_date=first_cert.get("issue_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        notes=data.notes,
        from_user_name=from_name,
    )

    # Log the communication
    comm_doc = {
        "communication_id": f"comm_{uuid.uuid4().hex[:12]}",
        "trust_id": data.trust_id,
        "user_id": user_id,
        "type": "email",
        "subject": f"Certificate of Trust Units — {trust_name}",
        "participants": [holder_name],
        "notes": f"Certificate notice emailed to {holder_name} at {cert_email}. Certificate #{cert_number}, {total_units} units ({percentage:.2f}%).",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.communications.insert_one(comm_doc)

    return {
        "success": True,
        "email_sent_to": cert_email,
        "units": total_units,
        "percentage": round(percentage, 2),
        "certificate_id": first_cert.get("certificate_id"),
    }
