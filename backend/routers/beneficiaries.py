"""
Beneficiaries router - Beneficiary dashboard for trust unit allocations
Migrated from server.py
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from dependencies import require_premium_feature, Feature, auto_update_onboarding
from database import db
from models import (
    BeneficiaryDashboardResponse, BeneficiaryAllocation,
    ClassBeneficiaryCreate, ClassBeneficiaryResponse, ClassBeneficiaryType,
    BeneficiaryCreate, BeneficiaryUpdate, SendCertificateRequest,
    TrustUnitCertificateCreate,
)
from routers.trust_units import create_unit_certificate as _create_cert, get_or_create_units_settings

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
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
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
    
    class_beneficiary = {
        "class_beneficiary_id": f"cb_{uuid.uuid4().hex[:16]}",
        "trust_id": data.trust_id,
        "user_id": user_id,
        "class_type": data.class_type.value,
        "class_type_label": CLASS_BENEFICIARY_LABELS.get(data.class_type.value, data.class_type.value),
        "description": data.description,
        "percentage": data.percentage,
        "notes": data.notes,
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
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
):
    """List all class beneficiaries for a trust (paginated)"""
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
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
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


# ========== DASHBOARD ENDPOINT (updated) ==========

@router.get("/dashboard", response_model=BeneficiaryDashboardResponse)
async def get_beneficiary_dashboard(
    trust_id: Optional[str] = None,
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
):
    """
    Beneficiary Dashboard showing current unit allocations per certificate holder.
    Also includes class beneficiary designations.
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
    
    # Get all active certificates
    certificates = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "user_id": user_id, "status": "active"},
        {"_id": 0}
    ).to_list(1000)
    
    # Aggregate by holder (use composite key to avoid merging different entities with same name)
    holder_map = {}
    for cert in certificates:
        holder_key = (cert["holder_name"], cert.get("holder_identifier") or "", cert.get("holder_type") or "individual")
        holder = cert["holder_name"]
        if holder_key not in holder_map:
            holder_map[holder_key] = {
                "holder_name": holder,
                "holder_identifier": cert.get("holder_identifier"),
                "holder_type": cert.get("holder_type", "individual"),
                "email": cert.get("email"),
                "phone": cert.get("phone"),
                "total_units": 0,
                "certificates": []
            }
        holder_map[holder_key]["total_units"] += cert["units"]
        holder_map[holder_key]["certificates"].append({
            "certificate_id": cert["certificate_id"],
            "certificate_number": cert["certificate_number"],
            "units": cert["units"],
            "issue_date": cert["issue_date"],
            "notes": cert.get("notes", ""),
            "email": cert.get("email", ""),
            "phone": cert.get("phone", ""),
        })
    
    # Build beneficiary allocations with percentages
    beneficiaries = []
    total_issued = 0
    for holder_data in holder_map.values():
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
    
    # Sort by total_units descending
    beneficiaries.sort(key=lambda x: x.total_units, reverse=True)
    
    # Get class beneficiaries
    class_beneficiaries = await db.class_beneficiaries.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # Get recent transfers
    transfers = await db.trust_unit_transfers.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)
    
    return BeneficiaryDashboardResponse(
        trust_id=trust_id,
        trust_name=trust_name,
        total_authorized_units=total_authorized,
        total_issued_units=total_issued,
        remaining_units=total_authorized - total_issued,
        unit_label=unit_label,
        active_certificate_count=len(certificates),
        beneficiaries=beneficiaries,
        class_beneficiaries=class_beneficiaries,
        recent_transfers=transfers
    )


# ========== BENEFICIARY MANAGEMENT ENDPOINTS ==========
# These mirror the logic in routers/chat.py _execute_approved_action
# (lines 796-957) but exposed as proper REST handlers so the
# action_registry.py endpoints resolve to real HTTP routes.

@router.post("/create")
async def create_beneficiary(
    data: BeneficiaryCreate,
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
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

    # Get unit settings to convert allocation_pct to units
    settings = await get_or_create_units_settings(data.trust_id, user_id)
    total_authorized = settings.get("total_authorized_units", 0)

    allocation_pct = data.allocation_pct
    if total_authorized > 0 and isinstance(allocation_pct, (int, float)) and allocation_pct < 100:
        units = max(1, round(total_authorized * allocation_pct / 100))
    elif isinstance(allocation_pct, (int, float)):
        units = int(allocation_pct) if allocation_pct > 0 else 1
    else:
        units = 1

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
        return result
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create beneficiary: {str(e)}")


@router.patch("/{beneficiary_id}")
async def update_beneficiary(
    beneficiary_id: str,
    data: BeneficiaryUpdate,
    trust_id: str = Query(..., description="Trust ID the certificate belongs to"),
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
):
    """Update a beneficiary's contact info (email/phone/notes).

    The beneficiary_id path param is the certificate_id of an active
    trust unit certificate.
    """
    user_id = user["user_id"]

    existing = await db.trust_unit_certificates.find_one(
        {
            "certificate_id": beneficiary_id,
            "trust_id": trust_id,
            "user_id": user_id,
            "status": "active",
        },
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Beneficiary certificate not found")

    update_fields = {}
    if data.email is not None:
        update_fields["email"] = data.email
    if data.phone is not None:
        update_fields["phone"] = data.phone
    if data.notes is not None:
        update_fields["notes"] = data.notes

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.trust_unit_certificates.update_one(
            {"certificate_id": beneficiary_id},
            {"$set": update_fields}
        )

    updated = await db.trust_unit_certificates.find_one(
        {"certificate_id": beneficiary_id},
        {"_id": 0}
    )
    return updated


@router.delete("/{beneficiary_id}")
async def delete_beneficiary(
    beneficiary_id: str,
    trust_id: str = Query(..., description="Trust ID the certificate belongs to"),
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
):
    """Remove (deactivate) a beneficiary.

    Marks the underlying trust unit certificate as inactive rather than
    deleting the record, preserving an audit trail.
    """
    user_id = user["user_id"]

    existing = await db.trust_unit_certificates.find_one(
        {
            "certificate_id": beneficiary_id,
            "trust_id": trust_id,
            "user_id": user_id,
            "status": "active",
        },
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Beneficiary certificate not found")

    await db.trust_unit_certificates.update_one(
        {"certificate_id": beneficiary_id},
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
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
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
    import re
    holder_name = data.beneficiary_name
    certs = await db.trust_unit_certificates.find(
        {
            "trust_id": data.trust_id,
            "user_id": user_id,
            "holder_name": {"$regex": f"^{re.escape(holder_name)}$", "$options": "i"},
            "status": "active",
        },
        {"_id": 0}
    ).to_list(100)

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
