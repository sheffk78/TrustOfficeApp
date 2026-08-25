# Trust Units router - handles trust unit certificates, transfers, and settings
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import io
import base64
import math

from pymongo import ReturnDocument

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from pydantic import BaseModel

from database import db
from dependencies import (
    get_current_user, require_write_access, should_show_watermark,
)
from models import (
    TrustUnitsSettingsUpdate, TrustUnitsSettingsResponse,
    TrustUnitCertificateCreate, TrustUnitCertificateUpdate, TrustUnitCertificateResponse,
    TrustUnitTransferCreate, TrustUnitTransferResponse,
    TrustUnitsSummaryResponse
)

router = APIRouter(tags=["trust-units"])


# ==================== HELPER FUNCTIONS ====================

def _calc_percentage(units: float, total_authorized: float) -> float:
    """Calculate percentage of total authorized, handling zero division."""
    return round((units / total_authorized * 100) if total_authorized > 0 else 0, 4)


async def _find_or_create_trust_entity(trust_id: str, user_id: str) -> dict:
    """Find an existing Trust-type entity for the given trust, or create one.

    Each trust should have a Trust-type entity representing it in the
    Structures hierarchy.  If it doesn't exist yet (e.g. the user hasn't
    visited the Structures page), we create a minimal one here so that
    beneficiary auto-linking always has entities to connect.
    """
    entity = await db.entities.find_one(
        {"trust_id": trust_id, "entity_type": "Trust", "user_id": user_id},
        {"_id": 0}
    )
    if entity:
        return entity

    # Fetch the trust record so we can name the entity sensibly
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )
    entity_name = trust.get("name", trust_id) if trust else trust_id

    entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    entity_doc = {
        "entity_id": entity_id,
        "user_id": user_id,
        "trust_id": trust_id,
        "name": entity_name,
        "legal_name": entity_name,
        "entity_type": "Trust",
        "formation_date": None,
        "governing_law": "",
        "ein": None,
        "trustee_names": "",
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": "",
        "article_ref_profit_distribution": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.entities.insert_one(entity_doc)
    return entity_doc


async def _find_trust_entities(trust_id: str, holder_trust_id: str, user_id: str):
    """Find or create the trust's own entity and the holder trust's entity.

    Both entities are Trust-type.  If either doesn't exist yet in
    db.entities, it is created on the fly (find-or-create) so that the
    auto-link relationship can always be established.
    """
    trust_entity = await _find_or_create_trust_entity(trust_id, user_id)
    holder_entity = await _find_or_create_trust_entity(holder_trust_id, user_id)
    return trust_entity, holder_entity


async def _create_auto_link_relationship(
    trust_entity: dict, holder_entity: dict, user_id: str,
    certificate_id: str, units: float, total_authorized: float
):
    """Create an auto-link entity relationship if one doesn't already exist.

    Relationship direction: the current trust (parent) distributes TO the
    beneficiary trust (child).  So parent_entity_id = current trust entity,
    child_entity_id = holder (beneficiary) trust entity, with
    relationship_type = 'receives_distributions_from' (the child receives
    distributions from the parent).  In the tree the current trust appears
    at the top and the beneficiary trust below it.
    """
    # Upsert: don't create a duplicate relationship
    existing = await db.entity_relationships.find_one({
        "parent_entity_id": trust_entity["entity_id"],
        "child_entity_id": holder_entity["entity_id"],
        "relationship_type": "receives_distributions_from",
        "user_id": user_id
    })
    if existing:
        return
    ownership_pct = (units / total_authorized * 100) if total_authorized > 0 else 100
    rel_doc = {
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "parent_entity_id": trust_entity["entity_id"],
        "child_entity_id": holder_entity["entity_id"],
        "relationship_type": "receives_distributions_from",
        "ownership_percentage": ownership_pct,
        "trust_id": trust_entity["trust_id"],
        "user_id": user_id,
        "source": "certificate_autolink",
        "certificate_id": certificate_id,
        "notes": "",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.entity_relationships.insert_one(rel_doc)


async def _remove_auto_link_relationships(certificate_id: str, user_id: str):
    """Remove auto-linked entity relationships for a certificate."""
    await db.entity_relationships.delete_many({
        "certificate_id": certificate_id,
        "source": "certificate_autolink",
        "user_id": user_id
    })


async def _try_auto_link_on_create(certificate: TrustUnitCertificateCreate, trust_id: str, user_id: str, certificate_id: str, units: float, total_authorized: float):
    """Auto-link entity relationship when holder_type='trust' and holder_trust_id is set."""
    if certificate.holder_type != "trust" or not certificate.holder_trust_id:
        return
    try:
        trust_entity, holder_entity = await _find_trust_entities(trust_id, certificate.holder_trust_id, user_id)
        if trust_entity and holder_entity:
            await _create_auto_link_relationship(
                trust_entity, holder_entity, user_id, certificate_id, units, total_authorized
            )
    except Exception:
        pass  # Certificate is already created; skip auto-link on error


async def _sync_auto_link_on_update(cert: dict, update_fields: dict, user_id: str, certificate_id: str, settings: dict, updated_cert: dict):
    """Sync auto-link relationships when holder_type / holder_trust_id changes during update."""
    try:
        old_type = cert.get("holder_type")
        new_type = update_fields.get("holder_type", old_type)

        if new_type != "trust":
            await _remove_auto_link_relationships(certificate_id, user_id)
            return

        old_holder_trust_id = cert.get("holder_trust_id")
        new_holder_trust_id = update_fields.get("holder_trust_id", old_holder_trust_id)

        if new_holder_trust_id == old_holder_trust_id:
            return  # No change — keep existing auto-link

        # Remove old auto-link, create new one if holder_trust_id is set
        await _remove_auto_link_relationships(certificate_id, user_id)
        if not new_holder_trust_id:
            return

        trust_entity, holder_entity = await _find_trust_entities(cert["trust_id"], new_holder_trust_id, user_id)
        if trust_entity and holder_entity:
            total_authorized = settings["total_authorized_units"]
            await _create_auto_link_relationship(
                trust_entity, holder_entity, user_id, certificate_id,
                updated_cert["units"], total_authorized
            )
    except Exception:
        pass  # Auto-link sync failure should not block the certificate update


def _build_cert_doc(certificate_id: str, trust_id: str, user_id: str, certificate, units: float, certificate_number: str) -> dict:
    """Build a certificate document for insertion."""
    return {
        "certificate_id": certificate_id,
        "trust_id": trust_id,
        "user_id": user_id,
        "holder_name": certificate.holder_name,
        "holder_identifier": certificate.holder_identifier,
        "holder_type": certificate.holder_type,
        "holder_trust_id": certificate.holder_trust_id,
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


def _build_transfer_doc(trust_id: str, user_id: str, from_holder, to_holder, units: float, reason: str, minutes_record_id=None) -> dict:
    """Build a transfer document for insertion."""
    return {
        "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user_id,
        "from_holder": from_holder,
        "to_holder": to_holder,
        "units": units,
        "reason": reason,
        "minutes_record_id": minutes_record_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }


async def get_or_create_units_settings(trust_id: str, user_id: str) -> dict:
    """Get or create default units settings for a trust"""
    settings = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not settings:
        # Create default settings with dual allocation mode support
        settings = {
            "trust_id": trust_id,
            "user_id": user_id,
            "total_authorized_units": 100,
            "allocation_mode": "percentage",
            "authorized_units_ceiling": 100,
            "unlimited_units": False,
            "class_distribution_convention": "per_capita",
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
    
    pipeline = [{"$match": query}, {"$group": {"_id": None, "total": {"$sum": "$units"}}}]
    rows = await db.trust_unit_certificates.aggregate(pipeline).to_list(None)
    return rows[0].get("total", 0) if rows else 0


async def _initialize_unit_counter(trust_id: str, user_id: str):
    """Initialize the counter from existing data, without overwriting a live counter."""
    active = await get_total_active_units(trust_id, user_id)
    latest = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "user_id": user_id}, {"certificate_number": 1}
    ).sort("certificate_number", -1).limit(1).to_list(1)
    next_number = 1
    if latest:
        try:
            next_number = int(str(latest[0].get("certificate_number", "")).split("-")[-1]) + 1
        except (ValueError, TypeError):
            next_number = await db.trust_unit_certificates.count_documents({"trust_id": trust_id, "user_id": user_id}) + 1
    await db.trust_unit_counters.update_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"$setOnInsert": {"trust_id": trust_id, "user_id": user_id,
                           "next_cert_number": next_number, "reserved_units": active}},
        upsert=True,
    )


async def get_next_certificate_number(trust_id: str, user_id: str) -> str:
    """Atomically allocate the next certificate number for a trust."""
    await _initialize_unit_counter(trust_id, user_id)
    counter = await db.trust_unit_counters.find_one_and_update(
        {"trust_id": trust_id, "user_id": user_id},
        {"$inc": {"next_cert_number": 1}},
        projection={"next_cert_number": 1}, return_document=ReturnDocument.BEFORE,
    )
    return f"CU-{str(counter['next_cert_number']).zfill(3)}"


async def reserve_units(trust_id: str, user_id: str, units: float, authorized: float) -> str:
    """Atomically reserve capacity and allocate a certificate number."""
    await _initialize_unit_counter(trust_id, user_id)
    counter = await db.trust_unit_counters.find_one_and_update(
        {"trust_id": trust_id, "user_id": user_id,
         "reserved_units": {"$lte": authorized - units}},
        {"$inc": {"reserved_units": units, "next_cert_number": 1}},
        projection={"next_cert_number": 1}, return_document=ReturnDocument.BEFORE,
    )
    if not counter:
        current = await get_total_active_units(trust_id, user_id)
        raise HTTPException(status_code=400, detail=f"Cannot issue {units} units. Only {authorized - current} units remaining.")
    return f"CU-{str(counter['next_cert_number']).zfill(3)}"


def validate_units(units: float, allow_fractional: bool) -> float:
    """Validate and normalize unit value, rejecting NaN and infinity."""
    try:
        if not math.isfinite(float(units)):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=400, detail="Units must be a finite number")
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
    user: dict = Depends(get_current_user)
):
    """
    Get complete units summary for a trust including settings, certificates, and aggregates.

    READ endpoint — available to all authenticated users (free, expired, past-due).
    Only write operations (create/update/revoke/transfer) are gated to active subscribers.
    """
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(trust_id, user["user_id"])
    
    certificates_raw = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("certificate_number", 1).to_list(None)
    
    total_authorized = settings["total_authorized_units"]
    
    certificates = []
    total_issued = 0
    active_count = 0
    
    for cert in certificates_raw:
        percentage = _calc_percentage(cert["units"], total_authorized)
        cert_response = TrustUnitCertificateResponse(
            **cert,
            percentage=percentage
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
    
    update_fields: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if update.total_authorized_units is not None:
        update_fields["total_authorized_units"] = update.total_authorized_units
    if update.unit_label is not None:
        update_fields["unit_label"] = update.unit_label
    if update.allow_fractional is not None:
        update_fields["allow_fractional"] = update.allow_fractional
    if update.allocation_mode is not None:
        if update.allocation_mode not in {"percentage", "units"}:
            raise HTTPException(status_code=400, detail="allocation_mode must be 'percentage' or 'units'.")
        update_fields["allocation_mode"] = update.allocation_mode
    if update.authorized_units_ceiling is not None:
        if update.authorized_units_ceiling < 0:
            raise HTTPException(status_code=400, detail="authorized_units_ceiling cannot be negative.")
        update_fields["authorized_units_ceiling"] = update.authorized_units_ceiling
    if update.unlimited_units is not None:
        update_fields["unlimited_units"] = update.unlimited_units
    if update.class_distribution_convention is not None:
        if update.class_distribution_convention not in {"per_capita", "per_stirpes"}:
            raise HTTPException(status_code=400, detail="Unsupported class distribution convention.")
        update_fields["class_distribution_convention"] = update.class_distribution_convention
    
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
    
    total_authorized = settings["total_authorized_units"]
    allocation_mode = settings.get("allocation_mode", "percentage")
    ceiling = settings.get("authorized_units_ceiling", total_authorized)
    capacity = total_authorized if allocation_mode == "percentage" else ceiling
    if allocation_mode == "units" and settings.get("unlimited_units"):
        capacity = None
    elif allocation_mode == "units" and ceiling is not None and units > ceiling:
        raise HTTPException(status_code=400, detail="Allocation exceeds the configured authorized-unit ceiling.")

    current_active = await get_total_active_units(certificate.trust_id, user["user_id"])
    if capacity is not None and current_active + units > capacity:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot issue {units} units. Only {capacity - current_active} units remaining. "
                   f"(Active: {current_active}, Authorized: {capacity})"
        )

    certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
    certificate_number = await reserve_units(certificate.trust_id, user["user_id"], units, total_authorized)
    
    cert_doc = _build_cert_doc(certificate_id, certificate.trust_id, user["user_id"], certificate, units, certificate_number)
    
    await db.trust_unit_certificates.insert_one(cert_doc)
    
    # Auto-link entity relationship when holder_type="trust" and holder_trust_id is set
    await _try_auto_link_on_create(certificate, certificate.trust_id, user["user_id"], certificate_id, units, total_authorized)
    
    # Record the transfer (issuance)
    transfer_doc = _build_transfer_doc(
        certificate.trust_id, user["user_id"], None, certificate.holder_name, units, "Initial certificate issuance"
    )
    await db.trust_unit_transfers.insert_one(transfer_doc)
    
    percentage = _calc_percentage(units, total_authorized)
    
    return TrustUnitCertificateResponse(**cert_doc, percentage=percentage)


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
    
    now = datetime.now(timezone.utc).isoformat()
    update_fields = {"updated_at": now}
    
    if update.holder_name is not None:
        update_fields["holder_name"] = update.holder_name
    if update.holder_identifier is not None:
        update_fields["holder_identifier"] = update.holder_identifier
    if update.holder_type is not None:
        update_fields["holder_type"] = update.holder_type
    if update.holder_trust_id is not None:
        update_fields["holder_trust_id"] = update.holder_trust_id
    if update.notes is not None:
        update_fields["notes"] = update.notes
    if update.email is not None:
        update_fields["email"] = update.email
    if update.phone is not None:
        update_fields["phone"] = update.phone
    if update.status is not None:
        if update.status.value != cert["status"]:
            raise HTTPException(status_code=400, detail="Status changes must use the dedicated revoke or transfer endpoint")
        update_fields["status"] = update.status.value
    
    allocation_changed = update.units is not None
    if allocation_changed:
        units = validate_units(update.units, settings["allow_fractional"])
        
        if units <= 0:
            raise HTTPException(status_code=400, detail="Units must be greater than 0")
        
        # Capacity check for replacement certificate
        current_active_excluding_this = await get_total_active_units(
            cert["trust_id"], user["user_id"], exclude_certificate_id=certificate_id
        )
        new_status = update.status.value if update.status else cert["status"]
        if new_status == "active":
            allocation_mode = settings.get("allocation_mode", "percentage")
            ceiling = settings.get("authorized_units_ceiling", settings["total_authorized_units"])
            capacity = settings["total_authorized_units"] if allocation_mode == "percentage" else ceiling
            if allocation_mode == "units" and settings.get("unlimited_units"):
                capacity = None
            if capacity is not None and current_active_excluding_this + units > capacity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update to {units} units. Would exceed authorized total. "
                           f"(Other active: {current_active_excluding_this}, Authorized: {capacity})"
                )
        
        # Create versioned replacement — never mutate the historical record
        replacement = dict(cert)
        replacement.pop("_id", None)
        replacement["certificate_id"] = f"cert_{uuid.uuid4().hex[:12]}"
        replacement["certificate_number"] = await get_next_certificate_number(cert["trust_id"], user["user_id"])
        replacement["units"] = units
        replacement["supersedes_certificate_id"] = certificate_id
        replacement["version"] = int(cert.get("version", 1)) + 1
        replacement["effective_date"] = update.effective_date or now[:10]
        replacement["replacement_reason"] = update.replacement_reason or "Allocation updated"
        replacement["created_at"] = now
        replacement["updated_at"] = now
        replacement["status"] = "active"
        replacement.update({k: v for k, v in update_fields.items() if k in {"holder_name", "holder_identifier", "holder_type", "holder_trust_id", "email", "phone", "notes"}})
        
        # Mark prior version as superseded
        await db.trust_unit_certificates.update_one(
            {"certificate_id": certificate_id, "user_id": user["user_id"]},
            {"$set": {"status": "superseded", "superseded_at": now, "updated_at": now}}
        )
        await db.trust_unit_certificates.insert_one(replacement)
        
        # Record audit trail
        await db.beneficiary_allocation_audit.insert_one({
            "audit_id": f"baa_{uuid.uuid4().hex[:12]}",
            "trust_id": cert["trust_id"],
            "user_id": user["user_id"],
            "action": "replacement_created",
            "prior_certificate_id": certificate_id,
            "replacement_certificate_id": replacement["certificate_id"],
            "prior_units": cert["units"],
            "new_units": units,
            "reason": replacement["replacement_reason"],
            "effective_date": replacement["effective_date"],
            "actor": user["user_id"],
            "created_at": now,
        })
        
        updated_cert = replacement
    else:
        await db.trust_unit_certificates.update_one(
            {"certificate_id": certificate_id},
            {"$set": update_fields}
        )
        updated_cert = await db.trust_unit_certificates.find_one(
            {"certificate_id": certificate_id},
            {"_id": 0}
        )

    # Auto-link sync: handle holder_type / holder_trust_id changes
    await _sync_auto_link_on_update(cert, update_fields, user["user_id"], certificate_id, settings, updated_cert)

    total_authorized = settings["total_authorized_units"]
    percentage = _calc_percentage(updated_cert["units"], total_authorized)

    return TrustUnitCertificateResponse(**updated_cert, percentage=percentage)


@router.get("/trust-units/certificates", response_model=List[TrustUnitCertificateResponse])
async def list_unit_certificates(
    trust_id: str,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    List all certificates for a trust, optionally filtered by status.

    READ endpoint — available to all authenticated users.
    """
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(trust_id, user["user_id"])
    total_authorized = settings["total_authorized_units"]
    
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    if status:
        query["status"] = status
    
    certificates = await db.trust_unit_certificates.find(query, {"_id": 0}).sort("certificate_number", 1).to_list(None)
    
    result = []
    for cert in certificates:
        percentage = _calc_percentage(cert["units"], total_authorized)
        result.append(TrustUnitCertificateResponse(**cert, percentage=percentage))
    
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
    if revoke.trust_id != cert["trust_id"]:
        raise HTTPException(status_code=400, detail="trust_id does not match the certificate's trust")
    
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
        "trust_id": cert["trust_id"],
        "user_id": user["user_id"],
        "from_holder": cert["holder_name"],
        "to_holder": None,
        "units": cert["units"],
        "reason": f"Certificate revoked: {revoke.reason}" if revoke.reason else "Certificate revoked",
        "minutes_record_id": revoke.minutes_record_id,
        "created_at": now
    }
    await db.trust_unit_transfers.insert_one(transfer_doc)
    
    # Remove auto-linked entity relationships when certificate is revoked
    await _remove_auto_link_relationships(certificate_id, user["user_id"])
    
    updated_cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id},
        {"_id": 0}
    )
    
    await db.trust_unit_counters.update_one(
        {"trust_id": cert["trust_id"], "user_id": user["user_id"]},
        {"$inc": {"reserved_units": -cert["units"]}}
    )
    settings = await get_or_create_units_settings(cert["trust_id"], user["user_id"])
    total_authorized = settings["total_authorized_units"]
    percentage = _calc_percentage(updated_cert["units"], total_authorized)
    
    return TrustUnitCertificateResponse(**updated_cert, percentage=percentage)


# ==================== DELETE ====================

@router.delete("/trust-units/certificates/{certificate_id}")
async def delete_unit_certificate(
    certificate_id: str,
    user: dict = Depends(require_write_access)
):
    """Delete a unit certificate and remove any auto-linked entity relationships."""
    cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    # Delete the certificate
    await db.trust_unit_certificates.delete_one(
        {"certificate_id": certificate_id, "user_id": user["user_id"]}
    )

    # Remove auto-linked entity relationships for this certificate
    await _remove_auto_link_relationships(certificate_id, user["user_id"])

    return {"message": "Certificate deleted"}


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
    
    if transfer.from_holder or transfer.from_certificate_id:
        source_query = {
            "trust_id": transfer.trust_id,
            "user_id": user["user_id"],
            "status": "active"
        }
        if transfer.from_certificate_id:
            source_query["certificate_id"] = transfer.from_certificate_id
        else:
            source_query["holder_name"] = transfer.from_holder
        from_cert = await db.trust_unit_certificates.find_one(source_query, {"_id": 0})
        
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
                "holder_trust_id": from_cert.get("holder_trust_id"),
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
    else:
        # No source means new issuance; reserve capacity atomically.
        await reserve_units(transfer.trust_id, user["user_id"], units, settings["total_authorized_units"])
    
    destination_query = {
        "trust_id": transfer.trust_id,
        "user_id": user["user_id"],
        "status": "active"
    }
    if transfer.to_certificate_id:
        destination_query["certificate_id"] = transfer.to_certificate_id
    else:
        destination_query["holder_name"] = transfer.to_holder
    existing_to_cert = await db.trust_unit_certificates.find_one(destination_query, {"_id": 0})
    
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
            "holder_trust_id": existing_to_cert.get("holder_trust_id"),
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
            "holder_trust_id": None,
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
    ).sort("created_at", -1).to_list(None)
    
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
    
    # === OFFICIAL SEAL — light embossed / watermark style ===
    seal_x = page_width - content_margin - 60
    seal_y = page_height / 2 - 20
    seal_radius = 40
    watermark_gray = HexColor('#CCCCCC')  # very light gray, embossed look

    c.setStrokeColor(watermark_gray)
    c.setLineWidth(1)

    # Outer circle
    c.circle(seal_x, seal_y, seal_radius, stroke=1, fill=0)
    # Inner circle (double-ring embossed look)
    c.setLineWidth(0.5)
    c.circle(seal_x, seal_y, seal_radius - 4, stroke=1, fill=0)

    # Light starburst behind the text (outline only, no fill)
    points = 12
    inner_radius = seal_radius * 0.55
    path = c.beginPath()
    for i in range(points * 2):
        angle = math.pi / 2 + (i * math.pi / points)
        radius = (seal_radius - 8) if i % 2 == 0 else inner_radius
        x = seal_x + radius * math.cos(angle)
        y = seal_y + radius * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.close()
    c.drawPath(path, stroke=1, fill=0)

    # Seal text — light gray so it reads as a watermark placeholder
    c.setFillColor(watermark_gray)
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
                          "Generated by TrustOffice")
    
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
    cert["percentage"] = _calc_percentage(cert["units"], total_authorized)
    
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
            "holder_trust_id": None,
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
        
        percentage = _calc_percentage(units, total_authorized)
        created_certificates.append(TrustUnitCertificateResponse(
            **cert_doc,
            percentage=percentage
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
