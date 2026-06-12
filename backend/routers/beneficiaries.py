"""
Beneficiaries router - Beneficiary dashboard for trust unit allocations
Migrated from server.py
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from dependencies import require_premium_feature, Feature
from database import db
from models import BeneficiaryDashboardResponse, BeneficiaryAllocation
from routers.trust_units import get_or_create_units_settings

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])


@router.get("/dashboard", response_model=BeneficiaryDashboardResponse)
async def get_beneficiary_dashboard(
    trust_id: Optional[str] = None,
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
):
    """
    Beneficiary Dashboard showing current unit allocations per certificate holder.
    
    Feature Gate: BENEFICIARY_DASHBOARD
    - Trial users cannot access the beneficiary dashboard
    - Paid users can view unit allocations and transfer history
    
    Returns:
    - Trust unit settings and totals
    - List of beneficiaries with their aggregated holdings
    - Recent transfers
    """
    user_id = user["user_id"]
    
    # Get trust (use provided or default to most recent)
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
    
    # Aggregate by holder
    holder_map = {}
    for cert in certificates:
        holder = cert["holder_name"]
        if holder not in holder_map:
            holder_map[holder] = {
                "holder_name": holder,
                "holder_identifier": cert.get("holder_identifier"),
                "email": cert.get("email"),
                "phone": cert.get("phone"),
                "total_units": 0,
                "certificates": []
            }
        holder_map[holder]["total_units"] += cert["units"]
        holder_map[holder]["certificates"].append({
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
            email=holder_data.get("email"),
            phone=holder_data.get("phone"),
            total_units=holder_data["total_units"],
            percentage=round(percentage, 4),
            certificate_count=len(holder_data["certificates"]),
            certificates=holder_data["certificates"]
        ))
    
    # Sort by total_units descending
    beneficiaries.sort(key=lambda x: x.total_units, reverse=True)
    
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
        recent_transfers=transfers
    )
