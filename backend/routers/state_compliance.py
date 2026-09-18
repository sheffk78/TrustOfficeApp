# State Compliance router — seed data + per-trust compliance tracking
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import List
import uuid

from database import db
from dependencies import get_current_user, require_write_access

router = APIRouter(tags=["state_compliance"])

# ==================== SEED DATA: State Compliance Rules ====================
STATE_COMPLIANCE_SEED = [
    {"state_code": "AK", "state_name": "Alaska", "utc_adopted": "no", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "AL", "state_name": "Alabama", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "AR", "state_name": "Arkansas", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "AZ", "state_name": "Arizona", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": False},
    {"state_code": "CA", "state_name": "California", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "CO", "state_name": "Colorado", "utc_adopted": "full", "utc_adoption_date": "2019-05-02", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "CT", "state_name": "Connecticut", "utc_adopted": "full", "utc_adoption_date": "2020-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "DE", "state_name": "Delaware", "utc_adopted": "no", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "FL", "state_name": "Florida", "utc_adopted": "partial", "notice_required": True, "notice_timing_days": 45, "accounting_frequency": "quarterly", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "GA", "state_name": "Georgia", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "HI", "state_name": "Hawaii", "utc_adopted": "full", "utc_adoption_date": "2022-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "IA", "state_name": "Iowa", "utc_adopted": "no", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "ID", "state_name": "Idaho", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 30, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "IL", "state_name": "Illinois", "utc_adopted": "full", "utc_adoption_date": "2020-01-01", "notice_required": True, "notice_timing_days": 30, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "IN", "state_name": "Indiana", "utc_adopted": "no", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "KS", "state_name": "Kansas", "utc_adopted": "full", "utc_adoption_date": "2002-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "KY", "state_name": "Kentucky", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "LA", "state_name": "Louisiana", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 30, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "MA", "state_name": "Massachusetts", "utc_adopted": "full", "notice_required": True, "notice_timing_days": 30, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "MD", "state_name": "Maryland", "utc_adopted": "full", "utc_adoption_date": "2014-01-01", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "ME", "state_name": "Maine", "utc_adopted": "full", "utc_adoption_date": "2007-01-01", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "MI", "state_name": "Michigan", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "MN", "state_name": "Minnesota", "utc_adopted": "full", "utc_adoption_date": "2019-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "MO", "state_name": "Missouri", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": False},
    {"state_code": "MS", "state_name": "Mississippi", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": False},
    {"state_code": "MT", "state_name": "Montana", "utc_adopted": "full", "utc_adoption_date": "2013-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NC", "state_name": "North Carolina", "utc_adopted": "no", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "ND", "state_name": "North Dakota", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": False},
    {"state_code": "NE", "state_name": "Nebraska", "utc_adopted": "full", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NH", "state_name": "New Hampshire", "utc_adopted": "full", "utc_adoption_date": "2007-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NJ", "state_name": "New Jersey", "utc_adopted": "full", "utc_adoption_date": "2016-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NM", "state_name": "New Mexico", "utc_adopted": "full", "utc_adoption_date": "2007-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NV", "state_name": "Nevada", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NY", "state_name": "New York", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "OH", "state_name": "Ohio", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "OK", "state_name": "Oklahoma", "utc_adopted": "full", "utc_adoption_date": "2025-11-01", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "OR", "state_name": "Oregon", "utc_adopted": "full", "utc_adoption_date": "2007-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "PA", "state_name": "Pennsylvania", "utc_adopted": "full", "utc_adoption_date": "2005-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "RI", "state_name": "Rhode Island", "utc_adopted": "no", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "SC", "state_name": "South Carolina", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "SD", "state_name": "South Dakota", "utc_adopted": "no", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "TN", "state_name": "Tennessee", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "TX", "state_name": "Texas", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "UT", "state_name": "Utah", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "VA", "state_name": "Virginia", "utc_adopted": "full", "utc_adoption_date": "2007-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "VT", "state_name": "Vermont", "utc_adopted": "full", "utc_adoption_date": "2007-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "WA", "state_name": "Washington", "utc_adopted": "full", "utc_adoption_date": "2016-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "WI", "state_name": "Wisconsin", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "WV", "state_name": "West Virginia", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "WY", "state_name": "Wyoming", "utc_adopted": "full", "utc_adoption_date": "2006-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True}
]


@router.post("/state-compliance/seed")
async def seed_state_compliance(user: dict = Depends(get_current_user), upsert_missing: bool = False):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if upsert_missing:
        # Idempotent upsert: insert only profiles whose _id (state_code) is absent
        inserted = 0
        for s in STATE_COMPLIANCE_SEED:
            doc = {"_id": s["state_code"], **s}
            result = await db.state_compliance_profiles.update_one(
                {"_id": s["state_code"]},
                {"$setOnInsert": doc},
                upsert=True,
            )
            if result.upserted_id is not None:
                inserted += 1
        return {"message": "Upserted missing states", "inserted": inserted}
    existing = await db.state_compliance_profiles.count_documents({})
    if existing > 0:
        return {"message": "Already seeded", "count": existing}
    docs = [{"_id": s["state_code"], **s} for s in STATE_COMPLIANCE_SEED]
    await db.state_compliance_profiles.insert_many(docs)
    return {"message": "Seeded", "count": len(docs)}


@router.get("/state-compliance/profiles")
async def list_state_profiles(user: dict = Depends(get_current_user)):
    docs = await db.state_compliance_profiles.find({}, {"_id": 0}).to_list(60)
    return {"states": docs, "count": len(docs)}


@router.get("/state-compliance/profiles/{state_code}")
async def get_state_profile(state_code: str, user: dict = Depends(get_current_user)):
    doc = await db.state_compliance_profiles.find_one(
        {"_id": state_code.upper()}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="State not found")
    return doc


@router.get("/trusts/{trust_id}/state-compliance")
async def get_trust_state_compliance(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    state_code = trust.get("state_code")
    if not state_code:
        return {
            "trust_id": trust_id,
            "state_code": None,
            "message": "No state set for this trust. Update trust profile in Settings.",
            "profile": None,
            "compliance": None,
        }

    profile = await db.state_compliance_profiles.find_one(
        {"_id": state_code.upper()}, {"_id": 0}
    )
    compliance = await db.trust_state_compliance.find_one(
        {"trust_id": trust_id, "state_code": state_code.upper()}, {"_id": 0}
    )

    if not compliance:
        now = datetime.now(timezone.utc).isoformat()
        compliance = {
            "compliance_id": f"sc_{uuid.uuid4().hex[:10]}",
            "trust_id": trust_id,
            "state_code": state_code.upper(),
            "notice_last_sent": None,
            "notice_next_due": None,
            "accounting_last_sent": None,
            "accounting_next_due": None,
            "compliance_items": {},
            "compliance_score": 100,
            "alert_active": False,
            "alert_reason": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.trust_state_compliance.insert_one(compliance)
        compliance.pop("_id", None)  # ObjectId not JSON-serializable

    return {
        "trust_id": trust_id,
        "state_code": state_code.upper(),
        "state_name": profile.get("state_name") if profile else None,
        "profile": profile,
        "compliance": compliance,
    }


@router.patch("/trusts/{trust_id}/state-compliance")
async def update_trust_state_compliance(
    trust_id: str, update: dict, user: dict = Depends(require_write_access)
):
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    update_data = {k: v for k, v in update.items() if v is not None}
    # Explicit deadline resets: {field: "null"} clears a stored value
    # (plain JSON null is indistinguishable from "field absent" upstream, so
    # this sentinel exists so callers can restore/clear a deadline).
    for key in ("notice_last_sent", "notice_next_due", "accounting_last_sent", "accounting_next_due"):
        if update.get(key) == "null":
            update_data[key] = None
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    state_code = trust.get("state_code", "").upper()

    # Compute next_due dates when last_sent is set
    if "notice_last_sent" in update_data and update_data["notice_last_sent"]:
        profile = await db.state_compliance_profiles.find_one(
            {"_id": state_code}, {"_id": 0}
        )
        timing_days = profile.get("notice_timing_days", 365) if profile else 365
        sent_date = datetime.fromisoformat(update_data["notice_last_sent"].replace("Z", "+00:00"))
        update_data["notice_next_due"] = (sent_date + timedelta(days=timing_days)).date().isoformat()

    if "accounting_last_sent" in update_data and update_data["accounting_last_sent"]:
        profile = await db.state_compliance_profiles.find_one(
            {"_id": state_code}, {"_id": 0}
        )
        freq = (profile.get("accounting_frequency", "annual") if profile else "annual")
        freq_days = {"annual": 365, "quarterly": 90, "monthly": 30}.get(freq, 365)
        sent_date = datetime.fromisoformat(update_data["accounting_last_sent"].replace("Z", "+00:00"))
        update_data["accounting_next_due"] = (sent_date + timedelta(days=freq_days)).date().isoformat()

    # Recompute compliance_score
    score = 100
    now = datetime.now(timezone.utc)

    # Deduct 15 per overdue deadline
    for field in ("notice_next_due", "accounting_next_due"):
        due_val = update_data.get(field)
        if due_val and not due_val.startswith("null"):
            try:
                due_date = datetime.fromisoformat(due_val).replace(tzinfo=timezone.utc)
                if due_date < now:
                    score -= 15
            except (ValueError, TypeError):
                pass

    # Deduct per-state requirement points for unsatisfied requirements
    compliance_doc = await db.trust_state_compliance.find_one(
        {"trust_id": trust_id, "state_code": state_code}, {"_id": 0}
    )
    profile = await db.state_compliance_profiles.find_one(
        {"_id": state_code}, {"_id": 0}
    )
    if profile and compliance_doc:
        reqs = compliance_doc.get("requirements", [])
        for req in reqs:
            if not req.get("satisfied"):
                score -= req.get("points", 0)

    score = max(0, score)
    update_data["compliance_score"] = score

    await db.trust_state_compliance.update_one(
        {"trust_id": trust_id, "state_code": state_code},
        {"$set": update_data},
        upsert=True,
    )

    updated = await db.trust_state_compliance.find_one({
        "trust_id": trust_id, "state_code": state_code
    }, {"_id": 0})
    return updated


@router.get("/trusts/{trust_id}/state-compliance/requirements")
async def get_trust_requirements(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    state_code = trust.get("state_code")
    if not state_code:
        raise HTTPException(status_code=400, detail="Trust has no state_code set")

    profile = await db.state_compliance_profiles.find_one(
        {"_id": state_code.upper()}, {"_id": 0}
    )
    if not profile:
        return {"trust_id": trust_id, "state_code": state_code.upper(), "requirements": [], "coverage": "uncovered"}

    requirements = []

    if profile.get("utc_adopted") == "no":
        requirements.append({
            "category": "utc_gap",
            "title": f"{profile['state_name']} has not adopted the Uniform Trust Code",
            "description": "Legacy common-law rules apply. Trustee removal may require court action. Review trust instrument for specific language.",
            "action": "Review trust instrument Article on trustee removal",
            "severity": "medium",
            "points": 10,
        })
    elif profile.get("utc_adopted") == "partial":
        requirements.append({
            "category": "utc_partial",
            "title": f"{profile['state_name']} partially adopted the UTC",
            "description": "Some UTC provisions adopted but not all. Verify which UTC sections apply to your trust.",
            "action": "Verify UTC adoption scope with estate attorney",
            "severity": "low",
            "points": 5,
        })

    if profile.get("notice_required"):
        requirements.append({
            "category": "notice",
            "title": f"{profile['state_name']} requires periodic notice to beneficiaries",
            "description": f"Beneficiaries must receive notice within {profile.get('notice_timing_days', 'N/A')} days of trust events.",
            "action": f"Schedule notice every {profile.get('notice_timing_days', 'N/A')} days",
            "severity": "high",
            "points": 15,
        })

    freq = profile.get("accounting_frequency", "annual")
    requirements.append({
        "category": "accounting",
        "title": f"{profile['state_name']} requires {freq} accounting to beneficiaries",
        "description": f"You must provide a financial accounting {freq}.",
        "action": f"Set {freq} reminder for beneficiary accounting",
        "severity": "high",
        "points": 15,
    })

    if not profile.get("spendthrift_default", True):
        requirements.append({
            "category": "spendthrift",
            "title": f"{profile['state_name']} does NOT have automatic spendthrift protection",
            "description": "Explicit spendthrift clause required in trust instrument for creditor protection.",
            "action": "Verify trust instrument includes spendthrift clause",
            "severity": "medium",
            "points": 10,
        })

    return {"trust_id": trust_id, "state_code": state_code.upper(), "requirements": requirements, "coverage": "covered"}
