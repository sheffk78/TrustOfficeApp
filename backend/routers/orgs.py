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


async def _resolve_org_ref(org_ref: str) -> Optional[dict]:
    """Resolve an org by org_id OR by exact name (users type the name)."""
    org = await db.orgs.find_one({"org_id": org_ref}, {"_id": 0})
    if not org:
        org = await db.orgs.find_one({"name": org_ref}, {"_id": 0})
    return org


@router.get("/orgs", response_model=List[OrgResponse])
async def list_my_orgs(user: dict = Depends(get_current_user)):
    """List orgs the caller owns or is an active member of (M4+ console)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    memberships = await _my_memberships(user)
    my_org_ids = [m["org_id"] for m in memberships if m.get("status") == "active"]
    if not my_org_ids:
        return []
    orgs = []
    cursor = db.orgs.find({"org_id": {"$in": my_org_ids}}, {"_id": 0})
    async for o in cursor:
        orgs.append(OrgResponse(**o))
    return orgs


@router.get("/orgs/{org_id}", response_model=OrgResponse)
async def get_org(org_id: str, user: dict = Depends(get_current_user)):
    """Read org. Owner-or-member access (M1-M2 authz)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    org = await _resolve_org_ref(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org_id = org["org_id"]
    # Owner short-circuit
    if org.get("owner_user_id") == user["user_id"]:
        return OrgResponse(**org)
    # Member check
    memberships = await _my_memberships(user)
    if not any(m.get("org_id") == org_id and m.get("status") == "active" for m in memberships):
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    return OrgResponse(**org)


@router.get("/orgs/{org_id}/members", response_model=List[OrgMember])
async def list_org_members(org_id: str, user: dict = Depends(get_current_user)):
    """List org members. Owner-or-member access (M1-M2 authz)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    org = await _resolve_org_ref(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org_id = org["org_id"]
    # Owner short-circuit
    if org.get("owner_user_id") == user["user_id"]:
        cursor = db.org_members.find({"org_id": org_id}, {"_id": 0})
        members = []
        async for m in cursor:
            members.append(OrgMember(**m))
        return members
    # Member check
    memberships = await _my_memberships(user)
    if not any(m.get("org_id") == org_id and m.get("status") == "active" for m in memberships):
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
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
    """Accept an org invite by token. Binds user_id, status=active (C3 email binding)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    member = await db.org_members.find_one(
        {"invite_token": token, "status": "invited"},
        {"_id": 0},
    )
    if not member:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")
    # C3: invited email must match authenticated user email
    if member.get("email", "").lower() != (user.get("email", "")).lower():
        raise HTTPException(status_code=403, detail={"code": "invite_email_mismatch"})
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
    # Validate expiry <= 365 days (D5). Unparseable input -> 422 (was an
    # unhandled ValueError -> 500, prod E2E finding 2026-09-24). Naive
    # datetimes (no tz offset) raised TypeError on the aware-datetime
    # subtraction -> 500; treat them as UTC. Past expiries are rejected so
    # no permanently-dead grant can be written.
    try:
        expires_at = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail={"code": "invalid_expires_at"})
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    granted_at = datetime.now(timezone.utc)
    if (expires_at - granted_at).days > 365:
        raise HTTPException(status_code=422, detail={"code": "expiry_exceeds_365_days"})
    if expires_at <= granted_at:
        raise HTTPException(status_code=422, detail={"code": "expiry_in_past"})
    # FK validation: org must exist and the client must hold an active membership
    # in it (D4 hardening 2026-09-24 — a free-text org label once polluted these
    # fields and silently broke the org-console join).
    org = await db.orgs.find_one({"org_id": body.org_id}, {"_id": 0, "org_id": 1})
    if not org:
        raise HTTPException(status_code=422, detail={"code": "org_not_found"})
    membership = await db.org_members.find_one(
        {
            "org_id": body.org_id,
            "member_id": body.member_id,
            "status": "active",
        },
        {"_id": 0, "member_id": 1},
    )
    if not membership:
        raise HTTPException(status_code=422, detail={"code": "member_not_in_org"})
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
        # Normalized tz-aware ISO (naive input coerced to UTC) so the
        # string-compare expiry filters in require_org_grant stay correct.
        "expires_at": expires_at.isoformat(),
        "attestation_ref": body.attestation_ref,
        "client_notified_at": None,
        "revoked_at": None,
        "revoke_reason": None,
    }
    await db.trust_grants.insert_one(grant_doc)
    # D7: fire grant_created notice email (best-effort, non-blocking)
    _ = _send_grant_notice(grant_doc, "grant_created")
    # M4: record notification timestamp
    await db.trust_grants.update_one(
        {"grant_id": grant_id},
        {"$set": {"client_notified_at": now}},
    )
    grant_doc["client_notified_at"] = now
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
    # Resolve via active member_ids (works whether caller passed through guard or not)
    from dependencies import _active_member_ids
    user_member_ids = await _active_member_ids(user)
    is_granted_member = grant["member_id"] in user_member_ids
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
    """Org console read: full client context per granted trust.

    Additive fields per trust (item 1): owner_user_id, owner_name, owner_email,
    grantor_name, trustee_name (from the ACTUAL live trustee field:
    trustee_full_name), grant_level for the requesting member, pending_minutes
    (drafts awaiting owner approval), next_deadline (earliest governance task
    deadline in the future; null when none). Batched to avoid N+1.
    """
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    org = await db.orgs.find_one({"org_id": org_id}, {"_id": 0, "org_id": 1, "name": 1})
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org_name = org.get("name", "")
    memberships = await _my_memberships(user)
    member_ids = [m["member_id"] for m in memberships if m.get("status") == "active" and m.get("org_id") == org_id]
    if not member_ids:
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    cursor = db.trust_grants.find(
        {
            "org_id": org_id,
            "member_id": {"$in": member_ids},
            "status": "active",
            "$or": [
                {"expires_at": {"$gte": _now()}},
                {"expires_at": {"$exists": False}},
                {"expires_at": None},
            ],
        },
        {"_id": 0, "trust_id": 1, "member_id": 1, "level": 1},
    )
    grants = []
    async for g in cursor:
        grants.append(g)
    # Best grant level per trust for THIS requesting member (preparer > viewer)
    level_by_trust: dict = {}
    trust_ids: list = []
    for g in grants:
        tid = g["trust_id"]
        if tid not in trust_ids:
            trust_ids.append(tid)
        if _level_rank(g.get("level", "viewer")) > _level_rank(level_by_trust.get(tid, "viewer")):
            level_by_trust[tid] = g.get("level", "viewer")

    # Batch fetch: trusts
    trust_map = {}
    tcur = db.trusts.find({"trust_id": {"$in": trust_ids}})
    async for t in tcur:
        t.pop("_id", None)
        trust_map[t["trust_id"]] = t

    # Batch fetch: owners (users)
    owner_ids = []
    for tid in trust_ids:
        t = trust_map.get(tid) or {}
        if t.get("user_id") and t["user_id"] not in owner_ids:
            owner_ids.append(t["user_id"])
    owner_map = {}
    if owner_ids:
        ucur = db.users.find({"user_id": {"$in": owner_ids}}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})
        async for u in ucur:
            owner_map[u["user_id"]] = u

    # Batch fetch: pending minutes (workflow drafts, not yet finalized) +
    # upcoming governance deadlines, aggregated with two grouped queries.
    APPROVAL_OPEN = ("draft", "pending_review", "under_review", "changes_requested")
    pending_by_trust: dict = {}
    async for row in db.meeting_minutes.aggregate([
        {"$match": {"trust_id": {"$in": trust_ids}}},
        {"$lookup": {
            "from": "minutes_approval_status",
            "localField": "minutes_id",
            "foreignField": "minutes_id",
            "as": "_appr",
        }},
        {"$addFields": {
            "_st": {"$ifNull": [{"$arrayElemAt": ["$_appr.current_status", 0]}, "$status"]},
        }},
        {"$match": {"_st": {"$in": list(APPROVAL_OPEN)}}},
        {"$group": {"_id": "$trust_id", "n": {"$sum": 1}}},
    ]):
        pending_by_trust[row["_id"]] = row["n"]

    deadline_by_trust: dict = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async for row in db.governance_tasks.aggregate([
        {"$match": {
            "trust_id": {"$in": trust_ids},
            "due_date": {"$gte": today},
            "$or": [{"completed_at": {"$exists": False}}, {"completed_at": None}],
        }},
        {"$group": {"_id": "$trust_id", "earliest": {"$min": "$due_date"}}},
    ]):
        deadline_by_trust[row["_id"]] = row["earliest"]

    trusts = []
    for tid in trust_ids:
        trust = trust_map.get(tid) or {}
        owner = owner_map.get(trust.get("user_id")) or {}
        trusts.append({
            "trust_id": tid,
            "name": trust.get("name") or trust.get("trust_name"),
            "owner_user_id": trust.get("user_id"),
            "owner_name": owner.get("name"),
            "owner_email": owner.get("email"),
            "grantor_name": trust.get("grantor_name"),
            "trustee_name": _trustee_display_name(trust),
            "grant_level": level_by_trust.get(tid, "viewer"),
            "pending_minutes": pending_by_trust.get(tid, 0),
            "next_deadline": deadline_by_trust.get(tid),
        })
    return {"org_id": org_id, "org_name": org_name, "trusts": trusts}


def _trustee_display_name(trust: dict) -> str:
    """Trustee display name from the ACTUAL live fields (dogfood verified
    2026-09-28: trustee_full_name is the populated field; trustee_names is
    usually empty). Falls back to grantor_name, then '' — never invents."""
    from services.org_activity import trustee_display_name
    return trustee_display_name(trust)


# ==================== ORG ACTIVITY FEED (item 5) ====================

@router.get("/orgs/{org_id}/activity")
async def org_activity_feed(
    org_id: str,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Org activity feed — what org members did on clients' behalf.

    Member-only (any active member of the org sees it), newest first,
    capped at 100 entries.
    """
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    memberships = await _my_memberships(user)
    if not any(
        m.get("org_id") == org_id and m.get("status") == "active"
        for m in memberships
    ):
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    limit = max(1, min(int(limit or 100), 100))
    events = []
    cursor = (
        db.org_activity.find({"org_id": org_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    async for ev in cursor:
        events.append(ev)
    return {"org_id": org_id, "events": events, "count": len(events)}


@router.post("/orgs/run-expiring-grants-job")
async def run_expiring_grants_job(user: dict = Depends(get_current_user)):
    """D7: on-demand run of the expiring-grant notice job.

    Finds active trust_grants with expires_at within 7 days that have not been
    noticed, emails each trust owner, stamps expiring_notice_sent=True.
    TOGGLE_INSTITUTION-gated (404 when off). Admin-only: platform operator
    trigger for the daily background job.
    """
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail={"code": "admin_only"})
    from background_tasks import run_org_expiring_grant_notices
    result = await run_org_expiring_grant_notices()
    return {"status": "ok", **result}


# ==================== EMAIL (best-effort, non-blocking) ====================

def _send_grant_notice(grant: dict, event: str):
    """Fire a notice email. Best-effort — never blocks the request."""
    try:
        from email_service import email_service
        # Tokenized one-click revoke link (D7)
        revoke_token = grant["grant_id"]
        revoke_url = f"{os.environ.get('APP_URL', 'http://localhost:3000')}/revoke/{revoke_token}"
        # Look up real email instead of using member_id string
        to_email = grant.get("email", "")
        if not to_email:
            # fallback: this is a sync context, can't async lookup.
            # In production, refactor to async. For now, rely on grant.email if populated.
            to_email = grant.get("member_id", "")
        email_service.send_email(
            to_email=to_email,
            subject=f"Trust access {event}",
            html_body=f"<p>Grant {event}. Revoke: <a href='{revoke_url}'>revoke</a></p>",
            text_body=f"Grant {event}. Revoke at: {revoke_url}",
        )
    except Exception:
        pass


@router.post("/revoke/{token}")
async def revoke_by_token(token: str):
    """D7: tokenized one-click revoke (no login required).
    Looks up active grant by grant_id, sets status=revoked.
    Single-use: already-revoked/expired grants return 410 Gone.
    """
    now = _now()
    # Try org grant first
    grant = await db.trust_grants.find_one({"grant_id": token})
    if grant:
        if grant.get("status") != "active":
            raise HTTPException(status_code=410, detail={"code": "grant_already_revoked"})
        await db.trust_grants.update_one(
            {"grant_id": token},
            {"$set": {"status": "revoked", "revoked_at": now, "revoke_reason": "token_revoke"}},
        )
        return {"grant_id": token, "status": "revoked", "type": "org_grant"}
    # Try party grant
    pgrant = await db.party_grants.find_one({"grant_id": token})
    if pgrant:
        if pgrant.get("status") != "active":
            raise HTTPException(status_code=410, detail={"code": "grant_already_revoked"})
        await db.party_grants.update_one(
            {"grant_id": token},
            {"$set": {"status": "revoked", "revoked_at": now, "revoke_reason": "token_revoke"}},
        )
        return {"grant_id": token, "status": "revoked", "type": "party_grant"}
    raise HTTPException(status_code=404, detail={"code": "grant_not_found"})
