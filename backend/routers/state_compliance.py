# State Compliance router — seed data + per-trust compliance tracking
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List
import uuid

from database import db
from dependencies import get_current_user

router = APIRouter(tags=["state_compliance"])

# ==================== SEED DATA: State Compliance Rules ====================
STATE_COMPLIANCE_SEED = [
    {"state_code": "AL", "state_name": "Alabama", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "AK", "state_name": "Alaska", "utc_adopted": "full", "utc_adoption_date": "2012-04-02", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "AZ", "state_name": "Arizona", "utc_adopted": "partial", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": False},
    {"state_code": "CA", "state_name": "California", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "CO", "state_name": "Colorado", "utc_adopted": "full", "utc_adoption_date": "2019-05-02", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "FL", "state_name": "Florida", "utc_adopted": "partial", "notice_required": True, "notice_timing_days": 45, "accounting_frequency": "quarterly", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "GA", "state_name": "Georgia", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
    {"state_code": "IL", "state_name": "Illinois", "utc_adopted": "full", "utc_adoption_date": "2020-01-01", "notice_required": True, "notice_timing_days": 30, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "LA", "state_name": "Louisiana", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 30, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "MD", "state_name": "Maryland", "utc_adopted": "full", "utc_adoption_date": "2014-01-01", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "MA", "state_name": "Massachusetts", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 30, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NC", "state_name": "North Carolina", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "NY", "state_name": "New York", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "TX", "state_name": "Texas", "utc_adopted": "no", "notice_required": True, "notice_timing_days": 60, "accounting_frequency": "annual", "trustee_removal_standard": "breach of trust", "spendthrift_default": True},
    {"state_code": "WA", "state_name": "Washington", "utc_adopted": "full", "utc_adoption_date": "2016-01-01", "notice_required": False, "accounting_frequency": "annual", "trustee_removal_standard": "reasonable grounds", "spendthrift_default": True},
]


@router.post("/state-compliance/seed")
async def seed_state_compliance(user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
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

    return {
        "trust_id": trust_id,
        "state_code": state_code.upper(),
        "state_name": profile.get("state_name") if profile else None,
        "profile": profile,
        "compliance": compliance,
    }


@router.patch("/trusts/{trust_id}/state-compliance")
async def update_trust_state_compliance(
    trust_id: str, update: dict, user: dict = Depends(get_current_user)
):
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    update_data = {k: v for k, v in update.items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    state_code = trust.get("state_code", "").upper()
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
        raise HTTPException(status_code=404, detail="State profile not found")

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

    return {"trust_id": trust_id, "state_code": state_code.upper(), "requirements": requirements}
