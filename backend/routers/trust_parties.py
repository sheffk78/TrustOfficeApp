# Trust parties router (M2) - behind TOGGLE_TRUST_PARTIES flag
# Returns 404 when flag is off. All operations are additive.

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import json
import os

from database import db
from dependencies import get_current_user, _toggle_trust_parties, _party_level_rank, _my_party_ids
from models import TrustPartyCreate, TrustParty, PartyGrantCreate, PartyGrant, PartyAudit, PartyType, PartyLevel

router = APIRouter(tags=["trust_parties"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_toggle():
    if not _toggle_trust_parties():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})


@router.post("/trust-parties")
async def create_trust_party(
    payload: TrustPartyCreate,
    user: dict = Depends(get_current_user),
):
    _require_toggle()
    # M3: only trust owner may create parties
    trust = await db.trusts.find_one({"trust_id": payload.trust_id})
    if not trust or trust.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail={"code": "owner_only"})
    # Validate protector powers against trust_protector_powers.json
    if payload.party_type == PartyType.protector and payload.powers:
        powers_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "trust_protector_powers.json"
        )
        try:
            with open(powers_path) as f:
                allowed = {p["value"] for p in json.load(f).get("powers", [])}
        except Exception:
            allowed = set()
        invalid = [p for p in payload.powers if p not in allowed]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_protector_powers", "powers": invalid},
            )
    party_id = f"party_{uuid.uuid4().hex[:12]}"
    doc = {
        "party_id": party_id,
        "trust_id": payload.trust_id,
        "party_type": payload.party_type.value,
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "powers": payload.powers or [],
        "notes": payload.notes,
        "status": "invited",
        "invited_at": _now(),
        "activated_at": None,
        "user_id": None,
        "source": "manual",
    }
    await db.trust_parties.insert_one(doc)
    return {"party_id": party_id, **doc}


@router.get("/trust-parties/{trust_id}")
async def list_trust_parties(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    _require_toggle()
    # M6: owner-or-party access
    trust = await db.trusts.find_one({"trust_id": trust_id})
    is_owner = trust and trust.get("user_id") == user["user_id"]
    if not is_owner:
        party_ids = await _my_party_ids(user)
        if not party_ids:
            raise HTTPException(status_code=403, detail={"code": "party_access_denied"})
    cursor = db.trust_parties.find(
        {"trust_id": trust_id}, {"_id": 0}
    ).sort("invited_at", -1)
    return [p async for p in cursor]


@router.post("/trust-parties/{party_id}/accept")
async def accept_trust_party_invite(
    party_id: str,
    user: dict = Depends(get_current_user),
):
    _require_toggle()
    result = await db.trust_parties.update_one(
        {"party_id": party_id, "email": user.get("email")},
        {"$set": {
            "status": "active",
            "user_id": user["user_id"],
            "activated_at": _now(),
        }},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=404, detail="Party invite not found or already accepted")
    return {"party_id": party_id, "status": "active"}


@router.post("/trust-parties/{party_id}/grants")
async def grant_party_access(
    party_id: str,
    payload: PartyGrantCreate,
    user: dict = Depends(get_current_user),
):
    _require_toggle()
    party = await db.trust_parties.find_one({"party_id": party_id}, {"_id": 0})
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    # M5: only trust owner may grant
    trust = await db.trusts.find_one({"trust_id": party["trust_id"]})
    if not trust or trust.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail={"code": "owner_only"})
    grant_id = f"pgrant_{uuid.uuid4().hex[:12]}"
    doc = {
        "grant_id": grant_id,
        "trust_id": party["trust_id"],
        "party_id": party_id,
        "level": payload.level.value,
        "status": "active",
        "granted_by": user["user_id"],
        "granted_at": _now(),
        "expires_at": payload.expires_at,
        "revoked_at": None,
        "client_notified_at": None,
    }
    await db.party_grants.insert_one(doc)
    return {"grant_id": grant_id, **doc}


@router.get("/trusts/{trust_id}/party-grants")
async def list_party_grants(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    _require_toggle()
    # Caller filtering: owner sees all; parties see only their own
    trust = await db.trusts.find_one({"trust_id": trust_id})
    is_owner = trust and trust.get("user_id") == user["user_id"]
    party_ids = []
    if not is_owner:
        party_ids = await _my_party_ids(user)
    query: dict = {"trust_id": trust_id}
    if not is_owner:
        query["party_id"] = {"$in": party_ids}
    cursor = db.party_grants.find(
        query, {"_id": 0}
    ).sort("granted_at", -1)
    return [g async for g in cursor]


@router.delete("/trusts/{trust_id}/party-grants/{grant_id}")
async def revoke_party_grant(
    trust_id: str,
    grant_id: str,
    user: dict = Depends(get_current_user),
):
    _require_toggle()
    grant = await db.party_grants.find_one({"grant_id": grant_id, "trust_id": trust_id})
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    trust = await db.trusts.find_one({"trust_id": trust_id})
    is_owner = trust and trust.get("user_id") == user["user_id"]
    party_ids = await _my_party_ids(user)
    is_granted_party = grant["party_id"] in party_ids
    if not is_owner and not is_granted_party:
        raise HTTPException(status_code=403, detail={"code": "party_access_denied"})
    result = await db.party_grants.update_one(
        {"grant_id": grant_id, "trust_id": trust_id},
        {"$set": {
            "status": "revoked",
            "revoked_at": _now(),
            "revoked_by": user["user_id"],
        }},
    )
    if result.modified_count != 1:
        raise HTTPException(status_code=404, detail="Grant not found")
    return {"grant_id": grant_id, "status": "revoked"}


@router.post("/trusts/{trust_id}/party-audit")
async def record_party_audit(
    trust_id: str,
    payload: PartyAudit,
    user: dict = Depends(get_current_user),
):
    _require_toggle()
    # M8: restrict to trust owner or verified party actors
    trust = await db.trusts.find_one({"trust_id": trust_id})
    is_owner = trust and trust.get("user_id") == user["user_id"]
    party_ids = await _my_party_ids(user)
    if not is_owner and payload.party_id not in party_ids:
        raise HTTPException(status_code=403, detail={"code": "party_access_denied"})
    audit_id = f"paudit_{uuid.uuid4().hex[:12]}"
    doc = {
        "audit_id": audit_id,
        "trust_id": trust_id,
        "party_id": payload.party_id,
        "action": payload.action,
        "attribution": payload.attribution,
        "at": payload.at or _now(),
        "meta": payload.meta,
    }
    await db.party_audit.insert_one(doc)
    return {"audit_id": audit_id}
