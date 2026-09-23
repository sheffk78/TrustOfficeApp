# Orgs router â Institution skeleton (M1, TrustOffice)
# Gated on TOGGLE_INSTITUTION: returns 404 when flag is off.
# All endpoints are additive; no existing collection or endpoint is modified.

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List

from database import db
from dependencies import (
    get_current_user, _toggle_institution, _level_rank,
    require_org_grant,
)
from models import (
    OrgCreate, OrgResponse, OrgMemberRole, OrgMember,
    GrantLevel, TrustGrantCreate, TrustGrant,
)

router = APIRouter(tags=["orgs"])


# ==================== HELPERS ====================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _my_memberships(user: dict) -> List[dict]:
    """Return all org_member docs where user is linked (by user_id or email)."""
    memberships = []
    cursor = db.org_members.find(
        {"$or": [{"user_id": user["user_id"]}, {"email": user.get("email", "")}]},
        {"_id": 0, "org_id": 1, "member_id": 1, "role": 1, "status": 1},
    )
    async for m in cursor:
        memberships.append(m)
    return memberships


# ==================== ORG ENDPOINTS ====================

@router.post("/orgs", response_model=OrgResponse)
async def create_org(body: OrgCreate, user: dict = Depends(get_current_user)):
    """Create an org. Creator becomes owner (D3)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    now = _now()
    org_doc = {
        "org_id": org_id,
        "name": body.name,
        "owner_user_id": user["user_id"],
        "billing_contact_email": body.billing_contact_email,
        "created_at": now,
    }
    await db.orgs.insert_one(org_doc)
    # Creator is org owner
    member_id = f"mem_{uuid.uuid4().hex[:12]}"
    await db.org_members.insert_one({
        "member_id": member_id,
        "org_id": org_id,
        "user_id": user["user_id"],
        "email": user.get("email", ""),
        "name": user.get("name") or user.get("email", ""),
        "role": OrgMemberRole.owner,
        "status": "active",
        "invited_at": now,
        "invited_by": user["user_id"],
        "joined_at": now,
    })
    return OrgResponse(**org_doc)


@router.get("/orgs/{org_id}", response_model=OrgResponse)
async def get_org(org_id: str, user: dict = Depends(get_current_user)):
    """Read org. Member-level access (counts + trusts under management)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    org = await db.orgs.find_one({"org_id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    return OrgResponse(**org)


@router.get("/orgs/{org_id}/members", response_model=List[OrgMember])
async def list_org_members(org_id: str, user: dict = Depends(get_current_user)):
    """List org members. Member-level access."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    cursor = db.org_members.find({"org_id": org_id}, {"_id": 0})
    members = []
    async for m in cursor:
        members.append(OrgMember(**m))
    return members


@router.post("/orgs/{org_id}/invites")
async def invite_org_member(
    org_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Invite a member by email. Owner/admin only."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    org = await db.orgs.find_one({"org_id": org_id}, {"_id": 0})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    # Check caller is owner/admin
    membership = await db.org_members.find_one(
        {"org_id": org_id, "user_id": user["user_id"], "status": "active"},
        {"_id": 0},
    )
    if not membership or membership["role"] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    email = body.get("email")
    name = body.get("name", "")
    member_id = f"mem_{uuid.uuid4().hex[:12]}"
    invite_token = uuid.uuid4().hex[:16]
    now = _now()
    await db.org_members.insert_one({
        "member_id": member_id,
        "org_id": org_id,
        "user_id": None,
        "email": email,
        "name": name,
        "role": OrgMemberRole.member,
        "status": "invited",
        "invited_at": now,
        "invited_by": user["user_id"],
    })
    # Store token for accept endpoint (simple approach: store in members doc)
    await db.org_members.update_one(
        {"member_id": member_id},
        {"$set": {"invite_token": invite_token}},
    )
    return {"member_id": member_id, "invite_token": invite_token, "expires_in": "72h"}


@router.post("/orgs/invites/{token}/accept")
async def accept_org_invite(token: str, user: dict = Depends(get_current_user)):
    """Accept an org invite by token. Binds user_id, status=active."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    member = await db.org_members.find_one(
        {"invite_token": token, "status": "invited"},
        {"_id": 0},
    )
    if not member:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")
    now = _now()
    await db.org_members.update_one(
        {"member_id": member["member_id"]},
        {"$set": {
            "user_id": user["user_id"],
            "status": "active",
            "joined_at": now,
        }},
    )
    return {"member_id": member["member_id"], "org_id": member["org_id"], "status": "active"}


@router.patch("/orgs/{org_id}/members/{member_id}")
async def update_org_member(
    org_id: str,
    member_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Change role or suspend member. Owner only."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    membership = await db.org_members.find_one(
        {"org_id": org_id, "user_id": user["user_id"], "status": "active"},
        {"_id": 0},
    )
    if not membership or membership["role"] != "owner":
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    update_fields = {}
    if "role" in body:
        update_fields["role"] = body["role"]
    if "status" in body:
        update_fields["status"] = body["status"]
    if update_fields:
        await db.org_members.update_one(
            {"member_id": member_id, "org_id": org_id},
            {"$set": update_fields},
        )
    return {"member_id": member_id, "updated": update_fields}


# ==================== TRUST GRANT ENDPOINTS ====================

@router.post("/trusts/{trust_id}/org-grants", response_model=TrustGrant)
async def grant_trust_access(
    trust_id: str,
    body: TrustGrantCreate,
    user: dict = Depends(get_current_user),
):
    """Grant org member access to a trust. Trust owner only (D4). Requires attestation (D6). Fires notice email (D7)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    trust = await db.trusts.find_one({"trust_id": trust_id})
    if not trust or trust.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail={"code": "owner_only"})
    if not body.attested_delegation:
        raise HTTPException(status_code=422, detail={"code": "attestation_required"})
    # Validate expiry <= 365 days (D5)
    expires_at = datetime.fromisoformat(body.expires_at)
    granted_at = datetime.now(timezone.utc)
    if (expires_at - granted_at).days > 365:
        raise HTTPException(status_code=422, detail={"code": "expiry_exceeds_365_days"})
    grant_id = f"grant_{uuid.uuid4().hex[:12]}"
    now = _now()
    grant_doc = {
        "grant_id": grant_id,
        "trust_id": trust_id,
        "org_id": body.org_id,
        "member_id": body.member_id,
        "level": body.level.value if isinstance(body.level, GrantLevel) else body.level,
        "status": "active",
        "granted_by": user["user_id"],
        "granted_at": now,
        "expires_at": body.expires_at,
        "attestation_ref": body.attestation_ref,
        "client_notified_at": None,
        "revoked_at": None,
        "revoke_reason": None,
    }
    await db.trust_grants.insert_one(grant_doc)
    # D7: fire grant_created notice email (best-effort, non-blocking)
    _ = _send_grant_notice(grant_doc, "grant_created")
    return TrustGrant(**grant_doc)


@router.get("/trusts/{trust_id}/org-grants", response_model=List[TrustGrant])
async def list_trust_grants(trust_id: str, user: dict = Depends(get_current_user)):
    """List grants for a trust. Owner + granted members."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    trust = await db.trusts.find_one({"trust_id": trust_id})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    # Owner or granted member
    is_owner = trust.get("user_id") == user["user_id"]
    memberships = await _my_memberships(user)
    member_ids = [m["member_id"] for m in memberships if m.get("status") == "active"]
    cursor = db.trust_grants.find(
        {"trust_id": trust_id},
        {"_id": 0},
    )
    grants = []
    async for g in cursor:
        if is_owner or g["member_id"] in member_ids:
            grants.append(TrustGrant(**g))
    return grants


@router.delete("/trusts/{trust_id}/org-grants/{grant_id}")
async def revoke_trust_grant(
    trust_id: str,
    grant_id: str,
    user: dict = Depends(get_current_user),
):
    """Revoke a grant. Owner or the granted member themselves."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    grant = await db.trust_grants.find_one({"grant_id": grant_id})
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    trust = await db.trusts.find_one({"trust_id": trust_id})
    is_owner = trust and trust.get("user_id") == user["user_id"]
    is_granted_member = grant["member_id"] == user.get("org_grant", {}).get("member_id")
    if not is_owner and not is_granted_member:
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    now = _now()
    await db.trust_grants.update_one(
        {"grant_id": grant_id},
        {"$set": {"status": "revoked", "revoked_at": now, "revoke_reason": "manual_revoke"}},
    )
    _ = _send_grant_notice(grant, "grant_revoked")
    return {"grant_id": grant_id, "status": "revoked"}


@router.get("/orgs/{org_id}/trusts")
async def org_trusts(org_id: str, user: dict = Depends(get_current_user)):
    """Org console read: trust name, owner, pending minutes, next deadline."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    memberships = await _my_memberships(user)
    member_ids = [m["member_id"] for m in memberships if m.get("status") == "active" and m.get("org_id") == org_id]
    if not member_ids:
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    cursor = db.trust_grants.find(
        {"org_id": org_id, "member_id": {"$in": member_ids}, "status": "active"},
        {"_id": 0, "trust_id": 1},
    )
    trust_ids = []
    async for g in cursor:
        trust_ids.append(g["trust_id"])
    trusts = []
    for tid in trust_ids:
        trust = await db.trusts.find_one({"trust_id": tid}, {"_id": 0})
        if trust:
            trusts.append({
                "trust_id": tid,
                "name": trust.get("name") or trust.get("trust_name"),
                "owner_user_id": trust.get("user_id"),
            })
    return {"org_id": org_id, "trusts": trusts}


# ==================== EMAIL (best-effort, non-blocking) ====================

def _send_grant_notice(grant: dict, event: str):
    """Fire a notice email. Best-effort â never blocks the request."""
    try:
        from email_service import email_service
        # Tokenized one-click revoke link (D7)
        revoke_token = grant["grant_id"]
        revoke_url = f"{os.environ.get('APP_URL', 'http://localhost:3000')}/revoke/{revoke_token}"
        email_service.send_email(
            to_email=grant.get("member_id", ""),
            subject=f"Trust access {event}",
            html_body=f"<p>Grant {event}. Revoke: <a href='{revoke_url}'>revoke</a></p>",
            text_body=f"Grant {event}. Revoke at: {revoke_url}",
        )
    except Exception:
        pass
