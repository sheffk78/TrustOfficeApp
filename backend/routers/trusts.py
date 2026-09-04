# Trusts router - handles trust CRUD operations
from fastapi import APIRouter, HTTPException, Depends
from datetime import date, datetime, timezone
from typing import List
from enum import Enum
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
from models import TrustCreate, TrustUpdate, TrustResponse
from utils.tax_calendar_math import _generate_entries, _seed_tax_year
from utils.audit import log_audit_event

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
    """Get all real (non-demo) trusts for the current user.

    Demo trusts (is_demo: True) are excluded: they must never appear in the
    sidebar trust selector or count against trust limits once a user has real
    data. Use GET /demo/status for demo-data visibility.
    """
    trusts = await db.trusts.find(
        {"user_id": user["user_id"], "is_demo": {"$ne": True}},
        {"_id": 0}
    ).to_list(100)
    
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
