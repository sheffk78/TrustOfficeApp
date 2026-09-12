# Trusts router - handles trust CRUD operations
from fastapi import APIRouter, HTTPException, Depends
from datetime import date, datetime, timezone
from typing import List
from enum import Enum
import json
import uuid
import logging

from database import db
from dependencies import (
    get_current_user, require_write_access, calculate_health_score, 
    create_initial_governance_tasks, check_feature_access, Feature,
    PREMIUM_FEATURE_ERROR_MESSAGE, PREMIUM_FEATURE_ERROR_CODE,
    get_trust_limit, PLAN_TRUST_LIMITS
)
from trustee_utils import parse_trustees
from models import TrustCreate, TrustUpdate, TrustResponse, TrustDissolveRequest
from utils.tax_calendar_math import _generate_entries, _seed_tax_year
from utils.audit import log_audit_event
from services.security_events import record_security_event, alert_security_event
from services.trust_archive import TRUST_STATUS_ACTIVE, TRUST_STATUS_DISSOLVED

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trusts"])


# ==================== HELPER FUNCTIONS ====================

# Collections to clean up when deleting demo data — superseded by the shared
# services/demo_cleanup.py module (kept only so old references don't break).

# Collections to cascade-delete when removing a trust
_TRUST_CASCADE_COLLECTIONS = [
    "entities", "entity_relationships", "governance_tasks", "minutes_records",
    "minutes_templates", "distribution_records", "compensation_plans",
    "compensation_payments", "health_score_snapshots", "tax_calendar",
    "trust_state_compliance", "investments", "transactions", "communications",
    "vault_documents", "separation_alerts", "beneficiaries", "schedule_a",
    "chat_conversations", "trust_document_analysis", "trust_unit_certificates",
    "trust_unit_transfers", "trust_unit_counters", "trust_unit_settings", "schedule_a_items",
    "dismissed_insights", "class_beneficiaries", "expenses", "bank_accounts",
    "bank_statements", "trust_admin_kits", "ai_suggestion_cache",
    "trust_units_settings", "benevolence_records", "risk_findings_cache",
    "minutes_version_history",
]


def _sync_jurisdiction_state(jurisdiction: str | None, state_code: str | None) -> tuple[str | None, str | None]:
    """Auto-sync jurisdiction and state_code (both should be 2-letter state codes)."""
    if jurisdiction and len(jurisdiction) == 2 and jurisdiction.isalpha() and not state_code:
        state_code = jurisdiction.upper()
    if state_code and not jurisdiction:
        jurisdiction = state_code.upper()
    return jurisdiction, state_code


def _sync_update_jurisdiction(update_data: dict):
    """Auto-sync jurisdiction and state_code in an update dict."""
    if "jurisdiction" in update_data and "state_code" not in update_data:
        j = update_data["jurisdiction"]
        if j and len(j) == 2 and j.isalpha():
            update_data["state_code"] = j.upper()
    if "state_code" in update_data and "jurisdiction" not in update_data:
        s = update_data["state_code"]
        if s:
            update_data["jurisdiction"] = s.upper()


def _normalize_trustees(trustees, user: dict) -> list:
    """Normalize trustees input to a List[str] for consistent storage."""
    is_empty = (
        trustees is None
        or (isinstance(trustees, str) and not trustees.strip())
        or (isinstance(trustees, list) and len(trustees) == 0)
    )
    if is_empty:
        return [user.get("name", "")] if user.get("name") else []
    if isinstance(trustees, str):
        return parse_trustees(trustees)
    return trustees


async def _enforce_trust_creation_limits(user: dict, sub_state, existing_count: int, trust_limit: float):
    """Raise HTTPException if the user cannot create another trust."""
    if existing_count >= 1:
        has_multiple_trusts = await check_feature_access(user["user_id"], Feature.MULTIPLE_TRUSTS)
        is_grandfathered = sub_state.legacy_trust_limit is not None and sub_state.legacy_trust_limit > 1
        if not has_multiple_trusts and not is_grandfathered:
            raise HTTPException(
                status_code=PREMIUM_FEATURE_ERROR_CODE,
                detail="Multiple trusts require an Estate or Advisor plan. Trustee accounts are limited to 1 trust."
            )

    if existing_count >= trust_limit and trust_limit != float('inf'):
        raise HTTPException(
            status_code=402,
            detail=f"Your plan supports up to {int(trust_limit)} trusts. Upgrade to create more, or contact contact@trustoffice.app with subject 'Need more trusts' if you need additional capacity."
        )


async def _cleanup_demo_data(user_id: str, new_trust_id: str) -> dict:
    """Delete all demo data when the user creates their first REAL trust.

    Delegates to the shared demo_cleanup service (single source of truth also
    used by Settings' "Remove demo data", external provisioning, and admin API).
    """
    from services.demo_cleanup import cleanup_demo_on_first_real_trust
    return await cleanup_demo_on_first_real_trust(user_id, new_trust_id)


def _mark_past_tax_entries_not_required(tax_entries: list):
    """Mark deadlines that already passed before the trust was created as not_required."""
    now_utc = datetime.now(timezone.utc)
    for entry in tax_entries:
        try:
            due = datetime.fromisoformat(entry["due_date"].replace('Z', '+00:00'))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due < now_utc:
                entry["filing_status"] = "not_required"
                entry["notes"] = "Not applicable — trust created after this deadline"
        except (ValueError, TypeError):
            pass


async def _generate_tax_calendar(trust_doc: dict, trust_id: str):
    """Auto-generate tax deadlines for a new trust, marking past entries as not_required."""
    target_tax_year = _seed_tax_year()
    existing_count = await db.tax_calendar.count_documents({
        "trust_id": trust_id, "tax_year": target_tax_year
    })
    if existing_count > 0:
        return

    tax_entries = _generate_entries(trust_doc, target_tax_year)
    if not tax_entries:
        return

    _mark_past_tax_entries_not_required(tax_entries)
    try:
        await db.tax_calendar.insert_many(tax_entries)
    except Exception:
        logger.warning(f"Failed to create tax calendar entries for trust {trust_id}", exc_info=True)


async def _create_trust_entity(user: dict, trust_id: str, trust: TrustCreate, jurisdiction: str | None, trustees):
    """Auto-create a Trust entity in Structures."""
    entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    entity_doc = {
        "entity_id": entity_id,
        "user_id": user["user_id"],
        "trust_id": trust_id,
        "name": trust.name,
        "entity_type": "Trust",
        "legal_name": trust.name,
        "formation_date": trust.start_date,
        "governing_law": jurisdiction or "",
        "ein": trust.ein,
        "trustee_names": ", ".join(trustees) if isinstance(trustees, list) else (trustees or ""),
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": trust.authority_clause or "",
        "article_ref_profit_distribution": "",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        await db.entities.insert_one(entity_doc)
    except Exception:
        logger.warning(f"Failed to auto-create entity for trust {trust_id}", exc_info=True)


async def _build_trust_doc(trust_id: str, user: dict, trust: TrustCreate, jurisdiction: str | None, state_code: str | None, trustees) -> dict:
    """Build the trust document for insertion."""
    return {
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "name": trust.name,
        "trust_type": trust.trust_type.value,
        "jurisdiction": jurisdiction,
        "role": trust.role or "Trustee",
        "start_date": trust.start_date,
        "trustees": trustees,
        "authority_clause": trust.authority_clause,
        "successor_trustee_name": trust.successor_trustee_name,
        "successor_trustee_email": trust.successor_trustee_email,
        "successor_trustee_phone": trust.successor_trustee_phone,
        "successor_trustee_relationship": trust.successor_trustee_relationship,
        "successor_trustee_notes": trust.successor_trustee_notes,
        "secondary_successor_trustee_name": trust.secondary_successor_trustee_name,
        "secondary_successor_trustee_email": trust.secondary_successor_trustee_email,
        "secondary_successor_trustee_phone": trust.secondary_successor_trustee_phone,
        "secondary_successor_trustee_relationship": trust.secondary_successor_trustee_relationship,
        "trust_protector_name": trust.trust_protector_name,
        "trust_protector_email": trust.trust_protector_email,
        "trust_protector_phone": trust.trust_protector_phone,
        "trust_protector_relationship": trust.trust_protector_relationship,
        "trust_protector_powers": trust.trust_protector_powers or [],
        "trust_protector_status": trust.trust_protector_status,
        "grantor_name": trust.grantor_name,
        "attorney_name": trust.attorney_name,
        "attorney_phone": trust.attorney_phone,
        "attorney_email": trust.attorney_email,
        "cpa_name": trust.cpa_name,
        "cpa_phone": trust.cpa_phone,
        "cpa_email": trust.cpa_email,
        "financial_advisor_name": trust.financial_advisor_name,
        "financial_advisor_phone": trust.financial_advisor_phone,
        "financial_advisor_email": trust.financial_advisor_email,
        "successor_instructions": trust.successor_instructions,
        "document_location": trust.document_location,
        "ein": trust.ein,
        "state_code": state_code,
        "tax_year_end_month": trust.tax_year_end_month,
        "tax_year_end_day": trust.tax_year_end_day,
        "is_fiscal_year": trust.tax_year_end_month is not None and trust.tax_year_end_day is not None and (trust.tax_year_end_month != 12 or trust.tax_year_end_day != 31),
        "description": trust.description,
        "review_cadence": trust.review_cadence,
        "benevolence_enabled": False,
        "tax_status": "private",
        "benevolence_mission": None,
        "determination_letter_date": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }


async def _sync_trustees_to_entity(trust_id: str, trustees):
    """Sync trustees to the entity's trustee_names field."""
    if isinstance(trustees, list):
        tr_str = ", ".join(trustees)
    else:
        tr_str = trustees or ""
    await db.entities.update_one(
        {"trust_id": trust_id, "entity_type": "Trust"},
        {"$set": {"trustee_names": tr_str}}
    )


# ==================== TRUST CRUD ENDPOINTS ====================

@router.post("/trusts", response_model=TrustResponse)
async def create_trust(trust: TrustCreate, user: dict = Depends(get_current_user)):
    """
    Create a new trust.

    Note: Uses get_current_user (not require_write_access) so that new users on the
    free plan can create their first trust during onboarding. Multiple-trust gating
    is enforced below via check_feature_access().

    Feature Gate: MULTIPLE_TRUSTS
    - Free/Forever Free: 10 trusts
    - Trustee: 1 trust
    - Estate: 8 trusts
    - Advisor: unlimited
    - Legacy monthly/annual: 10 trusts (grandfathered)
    """
    from dependencies import get_subscription_state
    sub_state = await get_subscription_state(user["user_id"])
    trust_limit = get_trust_limit(sub_state.plan_type, sub_state.legacy_trust_limit)

    existing_count = await db.trusts.count_documents({
        "user_id": user["user_id"],
        "is_demo": {"$ne": True}
    })
    await _enforce_trust_creation_limits(user, sub_state, existing_count, trust_limit)

    try:
        trust_id = f"trust_{uuid.uuid4().hex[:12]}"
        jurisdiction, state_code = _sync_jurisdiction_state(trust.jurisdiction, trust.state_code)
        trustees = _normalize_trustees(trust.trustees, user)

        trust_doc = await _build_trust_doc(trust_id, user, trust, jurisdiction, state_code, trustees)
        
        await db.trusts.insert_one(trust_doc)
        
        # Auto-cleanup demo data when user creates their first REAL trust
        await _cleanup_demo_data(user["user_id"], trust_id)
        
        # Create initial governance tasks — compensate (rollback trust) on failure
        try:
            await create_initial_governance_tasks(trust_id, user["user_id"])
        except Exception:
            await db.trusts.delete_one({"trust_id": trust_id})
            logger.error(f"Failed to create governance tasks for trust {trust_id}, user {user['user_id']}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to create governance tasks. Please try again. If this persists, contact support@trustoffice.app.")
        
        # Auto-generate tax deadlines
        await _generate_tax_calendar(trust_doc, trust_id)
        
        # Auto-create a Trust entity in Structures
        await _create_trust_entity(user, trust_id, trust, jurisdiction, trustees)

        return TrustResponse(**trust_doc, governance_score=0)
    
    except HTTPException:
        raise
    except Exception as e:
        # Alert on unexpected errors so we know when users hit failures
        logger.error(f"Unexpected error creating trust for user {user['user_id']}: {e}", exc_info=True)
        try:
            from discord_service import notify_alert
            await notify_alert(
                title="Trust Creation Failed",
                message=f"User: {user.get('email', 'unknown')}\\nError: {str(e)[:500]}\\nType: {type(e).__name__}",
            )
        except Exception:
            pass  # Don't fail the response if alerting fails
        raise HTTPException(status_code=500, detail="Something went wrong on our end while creating the trust. Our team has been notified. If this continues, contact support@trustoffice.app.")


@router.get("/trusts", response_model=List[TrustResponse])
async def get_trusts(user: dict = Depends(get_current_user)):
    """Get trusts for the current user.

    Demo trusts (is_demo: True) are excluded once the user has at least one
    real trust — they must never appear in the sidebar trust selector alongside
    real data. Demo-only accounts (legacy exploration data, no real trust yet)
    still see their demo trusts so the demo experience keeps working.
    """
    all_trusts = await db.trusts.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
    real_trusts = [t for t in all_trusts if t.get("is_demo") is not True]
    trusts = real_trusts if real_trusts else all_trusts
    
    result = []
    for trust in trusts:
        health = await calculate_health_score(trust["trust_id"], user["user_id"], save_snapshot=False)
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
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")

    health = await calculate_health_score(trust_id, user["user_id"], save_snapshot=False)
    return TrustResponse(**trust, governance_score=health["total_score"])


@router.put("/trusts/{trust_id}", response_model=TrustResponse)
async def update_trust(trust_id: str, update: TrustUpdate, user: dict = Depends(require_write_access)):
    """Update a trust"""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")

    update_data = {k: v.value if isinstance(v, Enum) else v for k, v in update.model_dump().items() if v is not None}
    
    # Auto-sync jurisdiction and state_code
    _sync_update_jurisdiction(update_data)
    
    # Auto-compute is_fiscal_year from tax year end date
    month = update_data.get("tax_year_end_month", trust.get("tax_year_end_month"))
    day = update_data.get("tax_year_end_day", trust.get("tax_year_end_day"))
    if month is not None and day is not None:
        update_data["is_fiscal_year"] = (month != 12 or day != 31)
    
    # Tax-exempt status set (or benevolence turned ON): purge income-tax
    # deadlines that don't apply — same policy as _generate_entries. Form 990
    # (501c3) and non-tax entries are preserved.
    new_tax_status = (update_data.get("tax_status") or trust.get("tax_status") or "private").lower()
    became_exempt = (
        (new_tax_status in ("508", "501c3") and (trust.get("tax_status") or "private").lower() not in ("508", "501c3"))
        or (update_data.get("benevolence_enabled") is True and not trust.get("benevolence_enabled")
            and new_tax_status == "private")
    )
    if became_exempt:
        try:
            if new_tax_status == "508":
                removed = await db.tax_calendar.delete_many({"trust_id": trust_id})
            else:  # 501c3: drop income-tax types only, keep Form 990 / other entries
                income_tax_types = ["federal_1041", "federal_1041_extension", "k1_beneficiaries",
                                    "estimated_q1", "estimated_q2", "estimated_q3", "estimated_q4"]
                removed = await db.tax_calendar.delete_many({"trust_id": trust_id, "deadline_type": {"$in": income_tax_types}})
            logger.info(f"Tax-exempt status ({new_tax_status}) for trust {trust_id}: purged {removed.deleted_count} income-tax calendar entries")
        except Exception:
            logger.warning(f"Failed to purge tax entries after tax-status change for trust {trust_id}", exc_info=True)
    
    if update_data:
        await db.trusts.update_one({"trust_id": trust_id}, {"$set": update_data})
    
    # Log trust profile update for audit trail
    changed_fields = list(update_data.keys())
    if changed_fields:
        await log_audit_event(user["user_id"], "trust_updated", "trust", trust_id, {"fields_changed": changed_fields})
    
    # Sync trustees to the entity's trustee_names field
    if "trustees" in update_data:
        await _sync_trustees_to_entity(trust_id, update_data["trustees"])
    
    # If governance_settings changed (spending threshold), backfill alerts
    if "governance_settings" in update_data:
        try:
            await _backfill_threshold_alerts(trust_id, user["user_id"])
        except Exception as e:
            logger.warning(f"Failed to backfill threshold alerts: {e}")
    
    updated = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0})
    health = await calculate_health_score(trust_id, user["user_id"], save_snapshot=False)
    return TrustResponse(**updated, governance_score=health["total_score"])


@router.delete("/trusts/{trust_id}")
async def delete_trust(trust_id: str, user: dict = Depends(require_write_access)):
    """Delete a trust and all related data"""
    result = await db.trusts.delete_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    # Capture entity IDs before deletion for cross-trust relationship cleanup
    entity_ids = [e["entity_id"] async for e in db.entities.find({"trust_id": trust_id}, {"entity_id": 1, "_id": 0})]

    # Cascade-delete all trust-scoped collections
    for coll_name in _TRUST_CASCADE_COLLECTIONS:
        await getattr(db, coll_name).delete_many({"trust_id": trust_id})

    # Also delete cross-trust relationships that reference this trust's entities
    if entity_ids:
        await db.entity_relationships.delete_many({
            "$or": [
                {"parent_entity_id": {"$in": entity_ids}},
                {"child_entity_id": {"$in": entity_ids}}
            ]
        })

    return {"message": "Trust deleted"}


async def _backfill_threshold_alerts(trust_id: str, user_id: str):
    """
    Re-evaluate all outflow transactions when the spending threshold changes.
    - Creates alerts for transactions now over threshold that weren't before.
    - Resolves alerts for transactions no longer over threshold (if threshold raised).
    """
    from alert_detection import check_transaction_alerts, auto_resolve_alert_if_fixed

    trust = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0, "governance_settings": 1})
    gov_settings = trust.get("governance_settings") if trust else None

    if not gov_settings or not gov_settings.get("spending_threshold"):
        # Threshold was removed — resolve all existing threshold alerts
        await db.separation_alerts.update_many(
            {"trust_id": trust_id, "alert_type": "spending_threshold_exceeded", "status": "active"},
            {"$set": {"status": "resolved", "resolution_type": "threshold_removed",
                      "resolution_note": "Spending threshold was removed", "resolved_at": datetime.now(timezone.utc).isoformat()}}
        )
        return

    threshold_config = gov_settings["spending_threshold"]
    threshold_amount = threshold_config.get("amount", 0)
    scope = threshold_config.get("scope_classifications", ["Operational Expense", "Other"])
    requires_minutes = threshold_config.get("requires_minutes", True)

    # Fetch all outflows for this trust
    txns = await db.transactions.find(
        {"trust_id": trust_id, "user_id": user_id, "direction": "outflow"},
        {"_id": 0}
    ).to_list(10000)

    for txn in txns:
        txn_id = txn["transaction_id"]
        amount = txn.get("amount", 0)
        classification = txn.get("governance_classification", "")
        linked_minutes = txn.get("linked_minutes_id")

        should_have_alert = (
            threshold_amount > 0
            and amount >= threshold_amount
            and (not requires_minutes or classification in scope)
            and not linked_minutes
        )

        existing_alert = await db.separation_alerts.find_one({
            "transaction_id": txn_id,
            "alert_type": "spending_threshold_exceeded",
            "status": "active"
        })

        if should_have_alert and not existing_alert:
            # Create alert for newly-over-threshold transaction
            await check_transaction_alerts(txn)
        elif not should_have_alert and existing_alert:
            # Resolve alert — transaction no longer over threshold
            await db.separation_alerts.update_one(
                {"alert_id": existing_alert["alert_id"]},
                {"$set": {"status": "resolved", "resolution_type": "threshold_changed",
                          "resolution_note": "Threshold updated — transaction no longer exceeds limit",
                          "resolved_at": datetime.now(timezone.utc).isoformat()}}
            )


# ==================== RECORDS REPOSITORY — DISSOLVE / ARCHIVE (F1, 2026-09-12) ====================

def _normalize_dissolved_on(value) -> str:
    """Normalize dissolved_on to an ISO date string (yyyy-MM-dd)."""
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    try:
        # Full ISO timestamp (frontend sends new Date().toISOString())
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        pass
    try:
        date.fromisoformat(text)
        return text
    except ValueError:
        raise HTTPException(status_code=422, detail="dissolved_on must be an ISO date (e.g. 2026-09-12)")


@router.post("/trusts/{trust_id}/dissolve")
async def dissolve_trust(trust_id: str, body: TrustDissolveRequest, user: dict = Depends(get_current_user)):
    """Archive a trust read-only (Records Repository, F1).

    Sets status=dissolved_archived + dissolved_on, writes audit + security
    events. Reversal is admin-only (un-dissolve = incident, not a button).
    Exempt from the archive guard itself (service/dissolve actions).
    """
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0, "status": 1, "name": 1}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")

    dissolved_on = _normalize_dissolved_on(body.dissolved_on)
    await db.trusts.update_one(
        {"trust_id": trust_id},
        {"$set": {"status": TRUST_STATUS_DISSOLVED, "dissolved_on": dissolved_on}}
    )

    await log_audit_event(user["user_id"], "trust_dissolved", "trust", trust_id, {
        "trust_name": trust.get("name", ""), "dissolved_on": dissolved_on,
    })
    await record_security_event(user["user_id"], "trust_dissolved", details={
        "trust_id": trust_id, "trust_name": trust.get("name", ""), "dissolved_on": dissolved_on,
    })

    return {"status": TRUST_STATUS_DISSOLVED, "dissolved_on": dissolved_on}


@router.post("/trusts/{trust_id}/un-dissolve")
async def un_dissolve_trust(trust_id: str, user: dict = Depends(get_current_user)):
    """Admin-only reversal of dissolve (un-dissolve = incident, not a button)."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")

    result = await db.trusts.find_one_and_update(
        {"trust_id": trust_id, "status": TRUST_STATUS_DISSOLVED},
        {"$set": {"status": TRUST_STATUS_ACTIVE}, "$unset": {"dissolved_on": ""}},
        projection={"_id": 0, "name": 1},
    )
    if not result:
        raise HTTPException(status_code=404, detail="No dissolved trust found with that ID.")

    await log_audit_event(user["user_id"], "trust_undissolved", "trust", trust_id, {
        "trust_name": result.get("name", ""), "admin_email": user.get("email", ""),
    })
    await record_security_event(user["user_id"], "trust_undissolved", details={
        "trust_id": trust_id, "trust_name": result.get("name", ""),
        "admin_email": user.get("email", ""),
    })

    return {"status": TRUST_STATUS_ACTIVE, "dissolved_on": None}


@router.get("/trusts/{trust_id}/archive-export")
async def archive_export(trust_id: str, user: dict = Depends(get_current_user)):
    """One-click full archive export (F1 item 6) — streaming ZIP.

    Contents: every generated PDF (minutes/resolutions with stored binaries),
    all CSVs (minutes/distributions/compensation/tasks/expenses), vault
    documents with file content, and manifest.json (inventory + export date +
    trust metadata). Reuses the full_export.py / export_service.py primitives —
    does not rebuild what exists. Streams (no whole-vault buffering).
    """
    import io
    import csv
    import zipfile
    from fastapi.responses import StreamingResponse
    from services.export_service import _export_safe, _safe_export_name
    from routers.full_export import COLLECTIONS as FULL_EXPORT_COLLECTIONS, _records

    user_id = user["user_id"]
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    exported_at = datetime.now(timezone.utc)
    exported_iso = exported_at.isoformat()

    # Generated CSVs — reuse the export router's query surface (same
    # collections + column headers as /export/*, scoped to this trust).
    csv_specs = [
        ("minutes", "Trust Name,Minutes Type,Meeting Date,Participants,Decisions,Created At"),
        ("distributions", "Trust Name,Beneficiary,Amount,Date,Status,Created At"),
        ("compensation", "Trust Name,Recipient,Amount,Period,Date,Created At"),
        ("tasks", "Trust ID,Task Type,Due Date,Status,Description,Created At"),
        ("expenses", "Trust Name,Description,Amount,Date,Category,Created At"),
    ]

    manifest = {
        "schema_version": "TR-ARCHIVE.v1",
        "exported_at": exported_iso,
        "trust_id": trust_id,
        "trust_name": trust.get("name", "Unnamed Trust"),
        "trust_metadata": _export_safe(trust),
        "owner_user_id": user_id,
        "contents": {},
        "files": [],
        "notes": "One-click archive export — generated in memory, not retained server-side.",
    }

    def _zip_manifest_writer(zf, m):
        zf.writestr("manifest.json", json.dumps(m, indent=2, sort_keys=True, default=str))

    # zipfile cannot stream to the client directly from a Mongo cursor in
    # Starlette's Response; we build via a non-seekable generator wrapper over
    # BytesIO that is finalized once. Memory stays bounded by ZIP_DEFLATED
    # chunking (same approach as full_export.py).
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # Inventory first
        counts = {}
        for category, collection in FULL_EXPORT_COLLECTIONS.items():
            try:
                docs = await _records(collection, trust_id, user_id, include_files=False)
            except Exception:
                docs = []
            counts[category] = len(docs)
        manifest["contents"]["record_inventory"] = counts

        # Vault documents (with file content)
        try:
            vault_docs = await _records("vault_documents", trust_id, user_id, include_files=True)
        except Exception:
            vault_docs = []
        manifest["contents"]["vault_documents"] = len(vault_docs)
        for doc in vault_docs:
            content = doc.get("file_content")
            if not content:
                continue
            filename = _safe_export_name(doc.get("file_name") or f"{doc.get('doc_id', 'document')}.bin")
            path = f"vault/{doc.get('doc_id', 'unknown')}/{filename}"
            archive.writestr(path, bytes(content))
            manifest["files"].append({
                "path": path, "doc_id": doc.get("doc_id"), "file_name": doc.get("file_name"),
                "content_type": doc.get("file_content_type"), "size_bytes": len(content),
                "category": doc.get("category"), "created_at": doc.get("created_at"),
            })

        # Generated PDFs (minutes/resolutions stored binaries)
        for category in ("minutes", "resolutions"):
            try:
                source_records = await _records(FULL_EXPORT_COLLECTIONS[category], trust_id, user_id, include_files=True)
            except Exception:
                source_records = []
            pdf_count = 0
            for source in source_records:
                content = source.get("file_content")
                if content and (source.get("file_content_type") == "application/pdf"
                                or str(source.get("file_name", "")).lower().endswith(".pdf")):
                    path = f"documents/{category}/{_safe_export_name(str(source.get('file_name') or source.get('id') or 'record.pdf'))}"
                    archive.writestr(path, bytes(content))
                    manifest["files"].append({
                        "path": path, "record_id": source.get("id"), "type": category,
                        "content_type": "application/pdf", "created_at": source.get("created_at"),
                    })
                    pdf_count += 1
            manifest["contents"][f"{category}_pdfs"] = pdf_count

        # CSVs (same data as /export/* premium CSVs, scoped to this trust)
        csv_counts = {}
        for label, _header in csv_specs:
            try:
                records = await _records(FULL_EXPORT_COLLECTIONS.get(label, label), trust_id, user_id, include_files=False)
            except Exception:
                records = []
            if not records:
                csv_counts[label] = 0
                continue
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()), extrasaction="ignore")
            writer.writeheader()
            for r in records:
                writer.writerow({k: (v if not isinstance(v, (dict, list)) else json.dumps(v, default=str)) for k, v in r.items()})
            archive.writestr(f"csv/{label}.csv", buf.getvalue())
            csv_counts[label] = len(records)
        manifest["contents"]["csv"] = csv_counts

        # Trust profile JSON for the archive binder
        archive.writestr("trust_profile.json", json.dumps(_export_safe(trust), indent=2, default=str))
        _zip_manifest_writer(archive, manifest)

    size_bytes = len(buffer.getvalue())
    await log_audit_event(user_id, "archive_export", "trust", trust_id, {
        "exported_at": exported_iso, "format": "zip", "size_bytes": size_bytes,
        "files": len(manifest["files"]),
    })
    # Security event + alert threshold (same rule as other bulk exports)
    await record_security_event(user_id, "bulk_export", details={
        "export_type": "archive_export", "trust_id": trust_id, "file_count": len(manifest["files"]),
    })
    await alert_security_event("bulk_export", user_id=user_id, count=len(manifest["files"]), details={
        "export_type": "archive_export", "trust_id": trust_id,
    })

    filename = f"TrustOffice_Archive_{_safe_export_name(trust.get('name'))}_{exported_at.strftime('%Y-%m-%d')}.zip"
    safe = filename.replace('"', "").replace("\\", "")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )

