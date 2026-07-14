"""
Beneficiaries router - Beneficiary dashboard for trust unit allocations
Migrated from server.py
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from dependencies import require_premium_feature, Feature
from database import db
from models import BeneficiaryDashboardResponse, BeneficiaryAllocation, ClassBeneficiaryCreate, ClassBeneficiaryResponse, ClassBeneficiaryType
from routers.trust_units import get_or_create_units_settings

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
