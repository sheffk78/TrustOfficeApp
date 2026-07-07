# Trust Units router - handles trust unit certificates, transfers, and settings
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import io
import base64

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from pydantic import BaseModel

from database import db
from dependencies import (
    get_current_user, require_write_access, should_show_watermark,
    require_premium_feature, Feature
)
from models import (
    TrustUnitsSettingsUpdate, TrustUnitsSettingsResponse,
    TrustUnitCertificateCreate, TrustUnitCertificateUpdate, TrustUnitCertificateResponse,
    TrustUnitTransferCreate, TrustUnitTransferResponse,
    TrustUnitsSummaryResponse
)

router = APIRouter(tags=["trust-units"])


# ==================== HELPER FUNCTIONS ====================

async def get_or_create_units_settings(trust_id: str, user_id: str) -> dict:
    """Get or create default units settings for a trust"""
    settings = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not settings:
        # Create default settings
        settings = {
            "trust_id": trust_id,
            "user_id": user_id,
            "total_authorized_units": 100,
            "unit_label": "Certificate Unit",
            "allow_fractional": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_units_settings.insert_one(settings)
    return settings


async def get_total_active_units(trust_id: str, user_id: str, exclude_certificate_id: str = None) -> float:
    """Calculate total units across all active certificates for a trust"""
    query = {
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    }
    if exclude_certificate_id:
        query["certificate_id"] = {"$ne": exclude_certificate_id}
    
    certificates = await db.trust_unit_certificates.find(query, {"_id": 0, "units": 1}).to_list(1000)
    return sum(cert.get("units", 0) for cert in certificates)


async def get_next_certificate_number(trust_id: str, user_id: str) -> str:
    """Get the next sequential certificate number for a trust"""
    count = await db.trust_unit_certificates.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    return f"CU-{str(count + 1).zfill(3)}"


def validate_units(units: float, allow_fractional: bool) -> float:
    """Validate and normalize unit value"""
    if not allow_fractional:
        if units != int(units):
            raise HTTPException(
                status_code=400, 
                detail="Fractional units not allowed. Enable 'allow_fractional' in settings first."
            )
        return int(units)
    return round(units, 4)


# ==================== TRUST UNITS SUMMARY ====================

@router.get("/trust-units/summary", response_model=TrustUnitsSummaryResponse)
async def get_trust_units_summary(
    trust_id: str, 
    user: dict = Depends(require_premium_feature(Feature.TRUST_UNITS))
):
    """
    Get complete units summary for a trust including settings, certificates, and aggregates.
    
    Feature Gate: TRUST_UNITS
    - Trial users cannot access trust unit management
    - Paid users can manage unit certificates and transfers
    """
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(trust_id, user["user_id"])
    
    certificates_raw = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("certificate_number", 1).to_list(1000)
    
    total_authorized = settings["total_authorized_units"]
    
    certificates = []
    total_issued = 0
    active_count = 0
    
    for cert in certificates_raw:
        percentage = (cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
        cert_response = TrustUnitCertificateResponse(
            **cert,
            percentage=round(percentage, 4)
        )
        certificates.append(cert_response)
        
        if cert["status"] == "active":
            total_issued += cert["units"]
            active_count += 1
    
    return TrustUnitsSummaryResponse(
        settings=TrustUnitsSettingsResponse(**settings),
        certificates=certificates,
        total_issued_units=total_issued,
        remaining_units=total_authorized - total_issued,
        active_certificate_count=active_count
    )


# ==================== TRUST UNITS SETTINGS ====================

@router.patch("/trust-units/settings", response_model=TrustUnitsSettingsResponse)
async def update_trust_units_settings(
    trust_id: str, 
    update: TrustUnitsSettingsUpdate, 
    user: dict = Depends(require_write_access)
):
    """Update units settings for a trust"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    await get_or_create_units_settings(trust_id, user["user_id"])
    
    if update.total_authorized_units is not None:
        current_active_units = await get_total_active_units(trust_id, user["user_id"])
        if update.total_authorized_units < current_active_units:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reduce total authorized units to {update.total_authorized_units}. "
                       f"There are currently {current_active_units} active units issued."
            )
    
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if update.total_authorized_units is not None:
        update_fields["total_authorized_units"] = update.total_authorized_units
    if update.unit_label is not None:
        update_fields["unit_label"] = update.unit_label
    if update.allow_fractional is not None:
        update_fields["allow_fractional"] = update.allow_fractional
    
    await db.trust_units_settings.update_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": update_fields}
    )
    
    updated = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    return TrustUnitsSettingsResponse(**updated)


# ==================== CERTIFICATE CRUD ====================

@router.post("/trust-units/certificates", response_model=TrustUnitCertificateResponse)
async def create_unit_certificate(
    certificate: TrustUnitCertificateCreate, 
    user: dict = Depends(require_write_access)
):
    """Issue a new unit certificate"""
    trust = await db.trusts.find_one({"trust_id": certificate.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(certificate.trust_id, user["user_id"])
    
    units = validate_units(certificate.units, settings["allow_fractional"])
    
    if units <= 0:
        raise HTTPException(status_code=400, detail="Units must be greater than 0")
    
    current_active = await get_total_active_units(certificate.trust_id, user["user_id"])
    total_authorized = settings["total_authorized_units"]
    
    if current_active + units > total_authorized:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot issue {units} units. Only {total_authorized - current_active} units remaining. "
                   f"(Active: {current_active}, Authorized: {total_authorized})"
        )
    
    certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
    certificate_number = await get_next_certificate_number(certificate.trust_id, user["user_id"])
    
    cert_doc = {
        "certificate_id": certificate_id,
        "trust_id": certificate.trust_id,
        "user_id": user["user_id"],
        "holder_name": certificate.holder_name,
        "holder_identifier": certificate.holder_identifier,
        "holder_type": certificate.holder_type,
        "email": certificate.email,
        "phone": certificate.phone,
        "units": units,
        "issue_date": certificate.issue_date,
        "certificate_number": certificate_number,
        "status": "active",
        "replaced_by_certificate_id": None,
        "notes": certificate.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None
    }
    
    await db.trust_unit_certificates.insert_one(cert_doc)
    
    # Record the transfer (issuance)
    transfer_doc = {
        "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
        "trust_id": certificate.trust_id,
        "user_id": user["user_id"],
        "from_holder": None,
        "to_holder": certificate.holder_name,
        "units": units,
        "reason": "Initial certificate issuance",
        "minutes_record_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.trust_unit_transfers.insert_one(transfer_doc)
    
    percentage = (units / total_authorized * 100) if total_authorized > 0 else 0
    
    return TrustUnitCertificateResponse(**cert_doc, percentage=round(percentage, 4))


@router.patch("/trust-units/certificates/{certificate_id}", response_model=TrustUnitCertificateResponse)
async def update_unit_certificate(
    certificate_id: str,
    update: TrustUnitCertificateUpdate,
    user: dict = Depends(require_write_access)
):
    """Update a unit certificate"""
    cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    settings = await get_or_create_units_settings(cert["trust_id"], user["user_id"])
    
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if update.holder_name is not None:
        update_fields["holder_name"] = update.holder_name
    if update.holder_identifier is not None:
        update_fields["holder_identifier"] = update.holder_identifier
    if update.holder_type is not None:
        update_fields["holder_type"] = update.holder_type
    if update.notes is not None:
        update_fields["notes"] = update.notes
    if update.email is not None:
        update_fields["email"] = update.email
    if update.phone is not None:
        update_fields["phone"] = update.phone
    if update.status is not None:
        update_fields["status"] = update.status.value
    
    if update.units is not None:
        units = validate_units(update.units, settings["allow_fractional"])
        
        if units <= 0:
            raise HTTPException(status_code=400, detail="Units must be greater than 0")
        
        current_active_excluding_this = await get_total_active_units(
            cert["trust_id"], 
            user["user_id"], 
            exclude_certificate_id=certificate_id
        )
        
        new_status = update.status.value if update.status else cert["status"]
        if new_status == "active":
            total_authorized = settings["total_authorized_units"]
            if current_active_excluding_this + units > total_authorized:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update to {units} units. Would exceed authorized total. "
                           f"(Other active: {current_active_excluding_this}, Authorized: {total_authorized})"
                )
        
        update_fields["units"] = units
    
    await db.trust_unit_certificates.update_one(
        {"certificate_id": certificate_id},
        {"$set": update_fields}
    )
    
    updated_cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id},
        {"_id": 0}
    )
    
    total_authorized = settings["total_authorized_units"]
    percentage = (updated_cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
    
    return TrustUnitCertificateResponse(**updated_cert, percentage=round(percentage, 4))


@router.get("/trust-units/certificates", response_model=List[TrustUnitCertificateResponse])
async def list_unit_certificates(
    trust_id: str,
    status: Optional[str] = None,
    user: dict = Depends(require_premium_feature(Feature.TRUST_UNITS))
):
    """
    List all certificates for a trust, optionally filtered by status.
    
    Feature Gate: TRUST_UNITS
    """
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(trust_id, user["user_id"])
    total_authorized = settings["total_authorized_units"]
    
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    if status:
        query["status"] = status
    
    certificates = await db.trust_unit_certificates.find(query, {"_id": 0}).sort("certificate_number", 1).to_list(1000)
    
    result = []
    for cert in certificates:
        percentage = (cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
        result.append(TrustUnitCertificateResponse(**cert, percentage=round(percentage, 4)))
    
    return result


# ==================== REVOKE ====================

class CertificateRevokeRequest(BaseModel):
    trust_id: str
    reason: str = ""
    minutes_record_id: Optional[str] = None

@router.post("/trust-units/certificates/{certificate_id}/revoke", response_model=TrustUnitCertificateResponse)
async def revoke_unit_certificate(
    certificate_id: str,
    revoke: CertificateRevokeRequest,
    user: dict = Depends(require_write_access)
):
    """Revoke a certificate, returning its units to the available pool."""
    cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    if cert["status"] != "active":
        raise HTTPException(status_code=400, detail=f"Cannot revoke certificate with status '{cert['status']}'. Only active certificates can be revoked.")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.trust_unit_certificates.update_one(
        {"certificate_id": certificate_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": now,
            "cancelled_by": user.get("name", user.get("email", "Unknown")),
            "cancelled_reason": revoke.reason,
            "updated_at": now
        }}
    )
    
    # Record a transfer entry for audit trail
    transfer_doc = {
        "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
        "trust_id": revoke.trust_id,
        "user_id": user["user_id"],
        "from_holder": cert["holder_name"],
        "to_holder": None,
        "units": cert["units"],
        "reason": f"Certificate revoked: {revoke.reason}" if revoke.reason else "Certificate revoked",
        "minutes_record_id": revoke.minutes_record_id,
        "created_at": now
    }
    await db.trust_unit_transfers.insert_one(transfer_doc)
    
    updated_cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id},
        {"_id": 0}
    )
    
    settings = await get_or_create_units_settings(revoke.trust_id, user["user_id"])
    total_authorized = settings["total_authorized_units"]
    percentage = (updated_cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
    
    return TrustUnitCertificateResponse(**updated_cert, percentage=round(percentage, 4))


# ==================== TRANSFERS ====================

@router.post("/trust-units/transfers", response_model=TrustUnitTransferResponse)
async def create_unit_transfer(
    transfer: TrustUnitTransferCreate,
    user: dict = Depends(require_write_access)
):
    """Record a unit transfer between holders (cancels old certificate, issues new one)"""
    trust = await db.trusts.find_one({"trust_id": transfer.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(transfer.trust_id, user["user_id"])
    
    units = validate_units(transfer.units, settings["allow_fractional"])
    
    if units <= 0:
        raise HTTPException(status_code=400, detail="Transfer units must be greater than 0")
    
    if transfer.from_holder:
        from_cert = await db.trust_unit_certificates.find_one({
            "trust_id": transfer.trust_id,
            "user_id": user["user_id"],
            "holder_name": transfer.from_holder,
            "status": "active"
        }, {"_id": 0})
        
        if not from_cert:
            raise HTTPException(
                status_code=404, 
                detail=f"No active certificate found for holder '{transfer.from_holder}'"
            )
        
        if from_cert["units"] < units:
            raise HTTPException(
                status_code=400,
                detail=f"Holder '{transfer.from_holder}' only has {from_cert['units']} units. Cannot transfer {units}."
            )
        
        new_cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        await db.trust_unit_certificates.update_one(
            {"certificate_id": from_cert["certificate_id"]},
            {"$set": {
                "status": "replaced",
                "replaced_by_certificate_id": new_cert_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        remaining_units = from_cert["units"] - units
        if remaining_units > 0:
            remainder_cert_number = await get_next_certificate_number(transfer.trust_id, user["user_id"])
            remainder_cert = {
                "certificate_id": new_cert_id,
                "trust_id": transfer.trust_id,
                "user_id": user["user_id"],
                "holder_name": transfer.from_holder,
                "holder_identifier": from_cert.get("holder_identifier"),
                "holder_type": from_cert.get("holder_type", "individual"),
                "email": from_cert.get("email"),
                "phone": from_cert.get("phone"),
                "units": remaining_units,
                "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "certificate_number": remainder_cert_number,
                "status": "active",
                "replaced_by_certificate_id": None,
                "notes": f"Remainder after transfer of {units} units to {transfer.to_holder}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None
            }
            await db.trust_unit_certificates.insert_one(remainder_cert)
    
    existing_to_cert = await db.trust_unit_certificates.find_one({
        "trust_id": transfer.trust_id,
        "user_id": user["user_id"],
        "holder_name": transfer.to_holder,
        "status": "active"
    }, {"_id": 0})
    
    if existing_to_cert:
        combined_units = existing_to_cert["units"] + units
        new_to_cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        
        await db.trust_unit_certificates.update_one(
            {"certificate_id": existing_to_cert["certificate_id"]},
            {"$set": {
                "status": "replaced",
                "replaced_by_certificate_id": new_to_cert_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        new_cert_number = await get_next_certificate_number(transfer.trust_id, user["user_id"])
        new_to_cert = {
            "certificate_id": new_to_cert_id,
            "trust_id": transfer.trust_id,
            "user_id": user["user_id"],
            "holder_name": transfer.to_holder,
            "holder_identifier": existing_to_cert.get("holder_identifier"),
            "holder_type": existing_to_cert.get("holder_type", "individual"),
            "email": existing_to_cert.get("email"),
            "phone": existing_to_cert.get("phone"),
            "units": combined_units,
            "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "certificate_number": new_cert_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": f"Combined certificate after receiving {units} units" + 
                     (f" from {transfer.from_holder}" if transfer.from_holder else ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_unit_certificates.insert_one(new_to_cert)
    else:
        new_cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        new_cert_number = await get_next_certificate_number(transfer.trust_id, user["user_id"])
        
        new_cert = {
            "certificate_id": new_cert_id,
            "trust_id": transfer.trust_id,
            "user_id": user["user_id"],
            "holder_name": transfer.to_holder,
            "holder_identifier": None,
            "holder_type": "individual",
            "email": None,
            "phone": None,
            "units": units,
            "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "certificate_number": new_cert_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": "Transfer" + (f" from {transfer.from_holder}" if transfer.from_holder else " (new issuance)"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_unit_certificates.insert_one(new_cert)
    
    transfer_id = f"transfer_{uuid.uuid4().hex[:12]}"
    transfer_doc = {
        "transfer_id": transfer_id,
        "trust_id": transfer.trust_id,
        "user_id": user["user_id"],
        "from_holder": transfer.from_holder,
        "to_holder": transfer.to_holder,
        "units": units,
        "reason": transfer.reason,
        "minutes_record_id": transfer.minutes_record_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.trust_unit_transfers.insert_one(transfer_doc)
    
    return TrustUnitTransferResponse(**transfer_doc)


@router.get("/trust-units/transfers", response_model=List[TrustUnitTransferResponse])
async def list_unit_transfers(
    trust_id: str,
    user: dict = Depends(get_current_user)
):
    """List all transfers for a trust"""
    transfers = await db.trust_unit_transfers.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    
    return [TrustUnitTransferResponse(**t) for t in transfers]


# ==================== CERTIFICATE PDF ====================

def generate_certificate_pdf(cert: dict, trust: dict, settings: dict, hide_watermark: bool = False) -> bytes:
    """Generate a professional landscape PDF certificate for trust units - stock certificate style"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.colors import HexColor
    import math
    
    buffer = io.BytesIO()
    page_width, page_height = landscape(letter)  # 11 x 8.5 inches
    c = canvas.Canvas(buffer, pagesize=landscape(letter))
    
    # Colors
    navy = HexColor('#010079')
    gold = HexColor('#D5AD36')
    light_grey = HexColor('#F0F0F0')
    dark_grey = HexColor('#666666')
    
    # Margins
    margin = 0.5 * inch
    
    # === WATERMARK (Background) ===
    if not hide_watermark:
        c.saveState()
        c.setFillColor(light_grey)
        c.setFont('Helvetica-Bold', 60)
        c.translate(page_width / 2, page_height / 2)
        c.rotate(30)
        c.drawCentredString(0, 0, trust.get('name', 'TRUST CERTIFICATE').upper())
        c.restoreState()
    
    # === DECORATIVE BORDER ===
    # Outer Navy border (3pt)
    c.setStrokeColor(navy)
    c.setLineWidth(3)
    c.rect(margin, margin, page_width - 2 * margin, page_height - 2 * margin, stroke=1, fill=0)
    
    # Inner Gold border (1pt) with 4pt gap
    gap = 6
    c.setStrokeColor(gold)
    c.setLineWidth(1)
    c.rect(margin + gap, margin + gap, page_width - 2 * margin - 2 * gap, page_height - 2 * margin - 2 * gap, stroke=1, fill=0)
    
    # Corner ornaments - Gold filled squares at inner border corners
    corner_size = 8
    inner_margin = margin + gap
    corners = [
        (inner_margin - corner_size/2, inner_margin - corner_size/2),  # Bottom-left
        (page_width - inner_margin - corner_size/2, inner_margin - corner_size/2),  # Bottom-right
        (inner_margin - corner_size/2, page_height - inner_margin - corner_size/2),  # Top-left
        (page_width - inner_margin - corner_size/2, page_height - inner_margin - corner_size/2),  # Top-right
    ]
    c.setFillColor(gold)
    for cx, cy in corners:
        c.rect(cx, cy, corner_size, corner_size, stroke=0, fill=1)
    
    # === CONTENT AREA ===
    content_margin = margin + 30
    center_x = page_width / 2
    
    # Certificate data
    holder_name = cert.get('holder_name', 'Unknown')
    units = cert.get('units', 0)
    percentage = cert.get('percentage', 0)
    cert_number = cert.get('certificate_number', 'N/A')
    issue_date = cert.get('issue_date', '')
    if 'T' in issue_date:
        issue_date = issue_date.split('T')[0]
    trust_name = trust.get('name', 'Trust')
    total_units = settings.get('total_authorized_units', 100)
    unit_label = settings.get('unit_label', 'Unit')
    
    # === HEADER ===
    y_pos = page_height - content_margin - 20
    
    # Certificate Number (Top Right)
    c.setFont('Courier-Bold', 12)
    c.setFillColor(navy)
    c.drawRightString(page_width - content_margin, y_pos + 10, f"No. {cert_number}")
    
    # Units (Top Left)
    c.drawString(content_margin, y_pos + 10, f"{units} {unit_label}{'s' if units != 1 else ''}")
    
    # Title
    c.setFont('Times-Bold', 32)
    c.setFillColor(navy)
    c.drawCentredString(center_x, y_pos - 20, "CERTIFICATE OF BENEFICIAL INTEREST")
    
    # Trust Name
    y_pos -= 60
    c.setFont('Times-Bold', 24)
    c.drawCentredString(center_x, y_pos, trust_name.upper())
    
    # Decorative line under title
    y_pos -= 15
    c.setStrokeColor(gold)
    c.setLineWidth(2)
    line_width = 200
    c.line(center_x - line_width, y_pos, center_x + line_width, y_pos)
    
    # === MAIN BODY ===
    y_pos -= 50
    c.setFont('Times-Roman', 14)
    c.setFillColor(HexColor('#000000'))
    c.drawCentredString(center_x, y_pos, "This Certifies That")
    
    # Holder Name (Centered, Prominent)
    y_pos -= 45
    c.setFont('Times-Bold', 28)
    c.setFillColor(navy)
    c.drawCentredString(center_x, y_pos, holder_name)
    
    # Holder Type (if not individual)
    holder_type = cert.get('holder_type', 'individual')
    if holder_type and holder_type != 'individual':
        holder_type_labels = {
            'trust': 'Trust',
            'llc': 'LLC',
            'corporation': 'Corporation',
            'charity': 'Charity / Nonprofit',
            'estate': 'Estate',
            'other': 'Entity',
        }
        type_label = holder_type_labels.get(holder_type, holder_type.title())
        y_pos -= 22
        c.setFont('Times-Italic', 12)
        c.setFillColor(dark_grey)
        c.drawCentredString(center_x, y_pos, type_label)
    
    # Identifier line
    holder_id = cert.get('holder_identifier', '')
    if holder_id:
        y_pos -= 20
        c.setFont('Times-Italic', 12)
        c.setFillColor(dark_grey)
        c.drawCentredString(center_x, y_pos, holder_id)
    
    # Ownership statement
    y_pos -= 40
    c.setFont('Times-Roman', 14)
    c.setFillColor(HexColor('#000000'))
    c.drawCentredString(center_x, y_pos, "is the registered holder of")
    
    # Units display (prominent)
    y_pos -= 35
    c.setFont('Courier-Bold', 22)
    c.setFillColor(navy)
    c.drawCentredString(center_x, y_pos, f"{units} {unit_label}{'s' if units != 1 else ''}")
    
    # Percentage
    y_pos -= 25
    c.setFont('Times-Roman', 14)
    c.setFillColor(HexColor('#000000'))
    c.drawCentredString(center_x, y_pos, f"representing {percentage:.2f}% of the total authorized beneficial interest")
    
    y_pos -= 20
    c.drawCentredString(center_x, y_pos, f"({units} of {total_units} total authorized units)")
    
    # === GOLD SEAL (Programmatic star polygon) ===
    seal_x = page_width - content_margin - 60
    seal_y = page_height / 2 - 20
    seal_radius = 35
    
    # Draw star seal
    c.setFillColor(gold)
    c.setStrokeColor(HexColor('#B8940B'))  # Darker gold for outline
    c.setLineWidth(1)
    
    # 12-point star
    points = 12
    inner_radius = seal_radius * 0.5
    path = c.beginPath()
    for i in range(points * 2):
        angle = math.pi / 2 + (i * math.pi / points)
        radius = seal_radius if i % 2 == 0 else inner_radius
        x = seal_x + radius * math.cos(angle)
        y = seal_y + radius * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.close()
    c.drawPath(path, stroke=1, fill=1)
    
    # Seal text
    c.setFillColor(HexColor('#FFFFFF'))
    c.setFont('Helvetica-Bold', 7)
    c.drawCentredString(seal_x, seal_y + 3, "OFFICIAL")
    c.drawCentredString(seal_x, seal_y - 6, "SEAL")
    
    # === BOTTOM SECTION ===
    # Issue date
    y_pos = content_margin + 120
    c.setFont('Times-Roman', 11)
    c.setFillColor(HexColor('#000000'))
    c.drawCentredString(center_x, y_pos, f"Issued on {issue_date}")
    
    # Signature lines
    y_pos -= 50
    sig_width = 180
    sig_gap = 100
    left_sig_x = center_x - sig_gap - sig_width / 2
    right_sig_x = center_x + sig_gap - sig_width / 2
    
    # Lines
    c.setStrokeColor(HexColor('#000000'))
    c.setLineWidth(0.5)
    c.line(left_sig_x, y_pos, left_sig_x + sig_width, y_pos)
    c.line(right_sig_x, y_pos, right_sig_x + sig_width, y_pos)
    
    # Labels
    c.setFont('Helvetica', 9)
    c.setFillColor(dark_grey)
    c.drawCentredString(left_sig_x + sig_width / 2, y_pos - 12, "Trustee Signature")
    c.drawCentredString(right_sig_x + sig_width / 2, y_pos - 12, "Date")
    
    # Footer
    if not hide_watermark:
        c.setFont('Helvetica', 7)
        c.setFillColor(HexColor('#999999'))
        c.drawCentredString(center_x, content_margin + 15, 
                          f"Generated by TrustOffice on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}")
    
    c.save()
    return buffer.getvalue()


@router.get("/trust-units/certificates/{certificate_id}/pdf")
async def get_certificate_pdf(certificate_id: str, user: dict = Depends(get_current_user)):
    """Generate and return PDF for a unit certificate"""
    cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    trust = await db.trusts.find_one(
        {"trust_id": cert["trust_id"], "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    settings = await get_or_create_units_settings(cert["trust_id"], user["user_id"])
    
    total_authorized = settings["total_authorized_units"]
    cert["percentage"] = (cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
    
    show_watermark = await should_show_watermark(user["user_id"])
    
    pdf_bytes = generate_certificate_pdf(cert, trust or {}, settings, hide_watermark=not show_watermark)
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    return {
        "pdf_base64": pdf_base64,
        "filename": f"certificate_{cert.get('certificate_number', certificate_id)}.pdf"
    }


# ==================== BOOTSTRAP FROM MINUTES ====================

class BootstrapFromMinutesResponse(BaseModel):
    """Response model for bootstrap-from-minutes endpoint"""
    success: bool
    message: str
    minutes_id: str
    trust_id: str
    total_authorized_units: int
    certificates_created: int
    certificates: List[TrustUnitCertificateResponse]
    total_issued_units: float
    remaining_units: float


async def create_certificates_from_beneficiary_designation(minutes_id: str, user_id: str) -> List[dict]:
    """
    Helper function to create initial certificates from a 'Designation of Beneficiaries' minutes template.
    Returns list of created certificate IDs.
    """
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user_id},
        {"_id": 0}
    )
    
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    if minutes.get("template_type") != "designation_of_beneficiaries":
        raise HTTPException(status_code=400, detail="Minutes is not a beneficiary designation template")
    
    template_data = minutes.get("template_data", {})
    beneficiaries = template_data.get("beneficiaries", [])
    total_units = template_data.get("total_units", 100)
    trust_id = minutes["trust_id"]
    
    if not beneficiaries:
        raise HTTPException(status_code=400, detail="No beneficiaries found in minutes template")
    
    settings = await get_or_create_units_settings(trust_id, user_id)
    
    if settings["total_authorized_units"] != total_units:
        await db.trust_units_settings.update_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"$set": {
                "total_authorized_units": total_units,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    created_certificates = []
    
    for ben in beneficiaries:
        name = ben.get("name", "").strip()
        units = ben.get("units", 0)
        
        if not name or not units:
            continue
        
        try:
            units = float(units) if settings["allow_fractional"] else int(units)
        except (ValueError, TypeError):
            continue
        
        if units <= 0:
            continue
        
        certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
        certificate_number = await get_next_certificate_number(trust_id, user_id)
        
        cert_doc = {
            "certificate_id": certificate_id,
            "trust_id": trust_id,
            "user_id": user_id,
            "holder_name": name,
            "holder_identifier": None,
            "holder_type": "individual",
            "email": None,
            "phone": None,
            "units": units,
            "issue_date": minutes.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "certificate_number": certificate_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": f"Created from beneficiary designation minutes ({minutes_id})",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        
        await db.trust_unit_certificates.insert_one(cert_doc)
        
        transfer_doc = {
            "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "from_holder": None,
            "to_holder": name,
            "units": units,
            "reason": f"Initial designation per minutes {minutes_id}",
            "minutes_record_id": minutes_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.trust_unit_transfers.insert_one(transfer_doc)
        
        created_certificates.append(certificate_id)
    
    return created_certificates


@router.post("/trust-units/create-from-minutes/{minutes_id}")
async def create_certificates_from_minutes(
    minutes_id: str,
    user: dict = Depends(require_write_access)
):
    """Create certificates from a finalized beneficiary designation minutes template"""
    created_ids = await create_certificates_from_beneficiary_designation(minutes_id, user["user_id"])
    
    return {
        "message": f"Created {len(created_ids)} certificates from minutes designation",
        "certificate_ids": created_ids
    }


@router.post("/trust-units/bootstrap-from-minutes/{minutes_id}", response_model=BootstrapFromMinutesResponse)
async def bootstrap_certificates_from_minutes(
    minutes_id: str,
    user: dict = Depends(require_write_access)
):
    """
    Populate Trust Unit Certificates from an existing 'Designation of Beneficiaries' minutes record.
    """
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    if minutes.get("template_type") != "designation_of_beneficiaries":
        raise HTTPException(
            status_code=400, 
            detail=f"Minutes is not a beneficiary designation template. Found type: {minutes.get('template_type')}"
        )
    
    template_data = minutes.get("template_data", {})
    beneficiaries = template_data.get("beneficiaries", [])
    total_units_from_minutes = template_data.get("total_units", 100)
    trust_id = minutes["trust_id"]
    meeting_date = minutes.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    
    if not beneficiaries:
        raise HTTPException(status_code=400, detail="No beneficiaries found in minutes template_data")
    
    total_requested_units = 0
    valid_beneficiaries = []
    for ben in beneficiaries:
        name = ben.get("name", "").strip()
        units = ben.get("units", 0)
        
        if not name or not units:
            continue
        
        try:
            units = float(units)
        except (ValueError, TypeError):
            continue
        
        if units <= 0:
            continue
        
        total_requested_units += units
        valid_beneficiaries.append({"name": name, "units": units})
    
    if not valid_beneficiaries:
        raise HTTPException(status_code=400, detail="No valid beneficiaries with units found in minutes template_data")
    
    if total_requested_units > total_units_from_minutes:
        raise HTTPException(
            status_code=400,
            detail=f"Sum of beneficiary units ({total_requested_units}) exceeds total_units in designation ({total_units_from_minutes})"
        )
    
    existing_settings = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    if not existing_settings:
        settings = {
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "total_authorized_units": total_units_from_minutes,
            "unit_label": "Certificate Unit",
            "allow_fractional": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_units_settings.insert_one(settings)
        total_authorized = total_units_from_minutes
        allow_fractional = False
    else:
        total_authorized = existing_settings["total_authorized_units"]
        allow_fractional = existing_settings.get("allow_fractional", False)
    
    existing_from_minutes = await db.trust_unit_certificates.count_documents({
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "notes": {"$regex": f"minutes \\({minutes_id}\\)"}
    })
    
    if existing_from_minutes > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Certificates have already been created from this minutes record ({existing_from_minutes} found). "
                   "This operation can only be performed once per minutes record."
        )
    
    current_active_units = await get_total_active_units(trust_id, user["user_id"])
    
    if current_active_units + total_requested_units > total_authorized:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create certificates. Current active: {current_active_units}, "
                   f"Requested: {total_requested_units}, Authorized: {total_authorized}. "
                   f"Would exceed by {current_active_units + total_requested_units - total_authorized} units."
        )
    
    created_certificates = []
    
    for ben in valid_beneficiaries:
        name = ben["name"]
        units = ben["units"]
        
        if not allow_fractional:
            units = int(units)
        else:
            units = round(units, 4)
        
        certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
        certificate_number = await get_next_certificate_number(trust_id, user["user_id"])
        
        cert_doc = {
            "certificate_id": certificate_id,
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "holder_name": name,
            "holder_identifier": None,
            "holder_type": "individual",
            "email": None,
            "phone": None,
            "units": units,
            "issue_date": meeting_date,
            "certificate_number": certificate_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": f"Created from beneficiary designation minutes ({minutes_id})",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        
        await db.trust_unit_certificates.insert_one(cert_doc)
        
        transfer_doc = {
            "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "from_holder": None,
            "to_holder": name,
            "units": units,
            "reason": f"Initial designation per minutes {minutes_id}",
            "minutes_record_id": minutes_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.trust_unit_transfers.insert_one(transfer_doc)
        
        percentage = (units / total_authorized * 100) if total_authorized > 0 else 0
        created_certificates.append(TrustUnitCertificateResponse(
            **cert_doc,
            percentage=round(percentage, 4)
        ))
    
    total_issued = sum(cert.units for cert in created_certificates)
    
    return BootstrapFromMinutesResponse(
        success=True,
        message=f"Successfully created {len(created_certificates)} certificates from beneficiary designation",
        minutes_id=minutes_id,
        trust_id=trust_id,
        total_authorized_units=total_authorized,
        certificates_created=len(created_certificates),
        certificates=created_certificates,
        total_issued_units=total_issued,
        remaining_units=total_authorized - (current_active_units + total_issued)
    )
