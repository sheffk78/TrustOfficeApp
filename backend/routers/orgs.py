# Orgs router â Institution skeleton (M1, TrustOffice)
# Gated on TOGGLE_INSTITUTION: returns 404 when flag is off.
# All endpoints are additive; no existing collection or endpoint is modified.

import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, List

from database import db
from dependencies import (
    get_current_user, _toggle_institution, _level_rank,
    require_org_grant, _active_member_ids,
)
from services.security_events import record_security_event
from models import (
    OrgCreate, OrgResponse, OrgMemberRole, OrgMember,
    GrantLevel, TrustGrantCreate, TrustGrant,
)

router = APIRouter(tags=["orgs"])

logger = logging.getLogger("orgs")


# ==================== HELPERS ====================

# RFC-5322-lite: local@domain.tld — blocks the "Invite sent to not-an-email."
# class of bugs (P0-1, 2026-10-01). Full RFC validation stays with EmailStr.
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_members(raw: list) -> list:
    """Defensive read-side filter (P0-1 fix, 2026-10-01): skip rows that fail
    OrgMember validation (e.g. legacy malformed emails) instead of letting one
    bad row 500 the whole members list."""
    members = []
    for m in raw:
        try:
            members.append(OrgMember(**m))
        except Exception:
            logging.warning("org_members: skipping malformed row org=%s email=%r",
                            m.get("org_id"), m.get("email"))
    return members


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
        raw = []
        async for m in cursor:
            raw.append(m)
        return _sanitize_members(raw)
    # Member check
    memberships = await _my_memberships(user)
    if not any(m.get("org_id") == org_id and m.get("status") == "active" for m in memberships):
        raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
    cursor = db.org_members.find({"org_id": org_id}, {"_id": 0})
    raw = []
    async for m in cursor:
        raw.append(m)
    return _sanitize_members(raw)


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
    email = (body.get("email") or "").strip()
    name = body.get("name", "")
    # P0 fix 2026-10-01: invite used to store ANY string as email with zero
    # validation; the members-list endpoint then fails its EmailStr
    # validation on read -> HTTP 500 for the whole org (org card degrades to
    # Members (0)). Validate BEFORE insert and return a proper 422.
    if not email or not EMAIL_RE.match(email):
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_email", "message": "Enter a valid email address to invite."},
        )
    member_id = f"mem_{uuid.uuid4().hex[:12]}"
    # D6 (T2 MED-8): real 256-bit token with a true 72h expiry the accept
    # path enforces — the old 16-char uuid4 hex "token" was guessable and
    # the advertised "72h" was never real.
    invite_token = secrets.token_urlsafe(32)
    now = _now()
    invite_expires_at = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
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
        # Stored in the same doc (single source of truth, no second roundtrip)
        "invite_token": invite_token,
        "invite_expires_at": invite_expires_at,
    })
    return {"member_id": member_id, "invite_token": invite_token, "expires_in": "72h"}


@router.post("/orgs/invites/{token}/accept")
async def accept_org_invite(token: str, user: dict = Depends(get_current_user)):
    """Accept an org invite by token. Binds user_id, status=active (C3 email binding)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    now = _now()
    # D6: atomic accept — find_one_and_update keyed on token + status=invited
    # + expiry. Single-use by construction (second submit finds no invited
    # doc), so the C3-verified email binding below stays race-free too.
    member = await db.org_members.find_one_and_update(
        {
            "invite_token": token,
            "status": "invited",
            "$or": [
                {"invite_expires_at": {"$exists": False}},
                {"invite_expires_at": None},
                {"invite_expires_at": {"$gte": now}},
            ],
        },
        {"$set": {
            "user_id": user["user_id"],
            "status": "active",
            "joined_at": now,
            "invite_accepted_at": now,
        }},
        return_document=False,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Invite not found, expired, or already accepted")
    # C3: invited email must match authenticated user email — on mismatch the
    # accept is rolled back so the invite stays usable by the right person.
    if member.get("email", "").lower() != (user.get("email", "")).lower():
        await db.org_members.update_one(
            {"member_id": member["member_id"], "status": "active"},
            {"$set": {"user_id": None, "status": "invited"},
             "$unset": {"joined_at": "", "invite_accepted_at": ""}},
        )
        raise HTTPException(status_code=403, detail={"code": "invite_email_mismatch"})
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
        # E (MED-13): validate against the real role/status vocabulary —
        # a raw dict body could otherwise inject arbitrary role/status docs.
        if body["role"] not in ("member", "admin", "owner"):
            raise HTTPException(status_code=422, detail={"code": "invalid_role"})
        if body["role"] == "owner":
            raise HTTPException(status_code=422, detail={"code": "owner_role_transfer_not_supported"})
        update_fields["role"] = body["role"]
    if "status" in body:
        if body["status"] not in ("invited", "active", "suspended"):
            raise HTTPException(status_code=422, detail={"code": "invalid_status"})
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
        # D1 (T2 HIGH): one-click revoke now keys on an unguessable
        # 256-bit token, NOT the raw grant_id. Token expires with the grant.
        "revoke_token": secrets.token_urlsafe(32),
        "revoke_token_expires_at": expires_at.isoformat(),
    }
    await db.trust_grants.insert_one(grant_doc)
    # D7: fire grant_created notice email (best-effort, non-blocking)
    import asyncio
    _task_notice = asyncio.ensure_future(_send_grant_notice(grant_doc, "grant_created"))
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
    grant = await db.trust_grants.find_one({"grant_id": grant_id, "trust_id": trust_id})
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
    import asyncio
    _task_notice = asyncio.ensure_future(_send_grant_notice(grant, "grant_revoked"))
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

async def _send_grant_notice(grant: dict, event: str):
    """D2 (T2 HIGH-4): fire a notice email to the REAL member address.

    Grant docs carry member_id, not email — resolve via org_members. Best-effort:
    resolution or send failures are logged, never silently swallowed, and never
    block the request.
    """
    try:
        to_email = grant.get("email", "")
        if not to_email:
            member = await db.org_members.find_one(
                {"member_id": grant.get("member_id")}, {"_id": 0, "email": 1}
            )
            to_email = (member or {}).get("email", "")
        if not to_email or "@" not in to_email:
            logging.warning(
                "grant notice skipped: no resolvable email for member_id=%s event=%s",
                grant.get("member_id"), event,
            )
            return
        # Unauthenticated one-click revoke link (D7) — now the per-grant
        # unguessable token, never the raw grant_id (D1/T2 HIGH-6).
        revoke_token = grant.get("revoke_token") or ""
        base = os.environ.get("APP_URL", "http://localhost:3000")
        if revoke_token:
            revoke_url = f"{base}/revoke/{revoke_token}"
            revoke_line = f"Revoke: {revoke_url}"
        else:
            # Legacy grants created before token hardening: owner revoke via console.
            revoke_line = f"Revoke from your TrustOffice console: {base}/trust-access"
        email_html = (
            f"<p>Trust access was {event}.</p>"
            f"<p>{revoke_line}</p>"
        )
        from email_service import email_service
        await email_service.send_email(
            to_email=to_email,
            subject=f"Trust access {event}",
            html_body=email_html,
            text_body=f"Trust access was {event}. {revoke_line}",
        )
    except Exception as e:
        logging.warning("grant notice failed (member_id=%s, event=%s): %s",
                        grant.get("member_id"), event, e)


@router.post("/revoke/{token}")
async def revoke_by_token(token: str):
    """D7 one-click revoke, D1-hardened (T2 HIGH-6).

    The token is a per-grant 256-bit revoke_token — never a raw grant_id, so
    possession of a grant_id alone revokes nothing. Single-use (atomic
    find_one_and_update on status=active) and expiring; every successful
    revoke writes an audit row + org activity event.
    """
    now = _now()
    # Org grants: atomically flip active -> revoked keyed on the revoke token
    grant = await db.trust_grants.find_one_and_update(
        {
            "revoke_token": token,
            "status": "active",
            "$or": [
                {"revoke_token_expires_at": {"$exists": False}},
                {"revoke_token_expires_at": None},
                {"revoke_token_expires_at": {"$gte": now}},
            ],
        },
        {"$set": {"status": "revoked", "revoked_at": now, "revoke_reason": "token_revoke"}},
        return_document=False,
    )
    if grant:
        # Audit trail (T2 HIGH-6): every successful token revoke writes an org
        # activity row directly — log_org_activity's contract no-ops for
        # non-grant actors, and the one-click link is a system actor by design.
        try:
            await db.org_activity.insert_one({
                "event_id": f"act_{uuid.uuid4().hex[:12]}",
                "org_id": grant.get("org_id") or "",
                "trust_id": grant.get("trust_id") or "",
                "member_name": "One-click revoke",
                "org_name": "",
                "action": "grant_revoked_via_link",
                "attribution": None,
                "created_at": now,
            })
        except Exception as e:
            logging.warning("revoke audit write failed (grant=%s): %s", grant.get("grant_id"), e)
        return {"grant_id": grant["grant_id"], "status": "revoked", "type": "org_grant"}
    # Party grants (co-trustee invites) mirror the same token mechanics
    pgrant = await db.party_grants.find_one_and_update(
        {"revoke_token": token, "status": "active"},
        {"$set": {"status": "revoked", "revoked_at": now, "revoke_reason": "token_revoke"}},
        return_document=False,
    )
    if pgrant:
        return {"grant_id": pgrant["grant_id"], "status": "revoked", "type": "party_grant"}
    # Unknown or stale token: 404 (no enumeration of grant state)
    raise HTTPException(status_code=404, detail={"code": "grant_not_found"})


# ==================== ORG WORKSPACE ENTRY (M5, 2026-10-01) ====================
# Jeff's verdict on the org console: entering a client's workspace was a silent
# handoff (selectedTrust + navigate) — no "you're in their account" state, no
# back navigation, nothing audited. Option B (approved 2026-10-01): org entry
# rides the same state machinery as admin impersonation — an explicit, audited
# ENTER endpoint + an EXIT endpoint; the frontend swaps on the banner/exit UX.
# Scoping stays server-side: every trust data endpoint keeps enforcing
# require_org_grant (grant level, expiry, revocation) for member sessions.

@router.post("/orgs/enter-trust/{trust_id}")
async def enter_trust_workspace(
    trust_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Org member enters a granted trust's workspace (audited 'viewing as')."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    trust = await db.trusts.find_one(
        {"trust_id": trust_id},
        {"_id": 0, "trust_id": 1, "name": 1, "user_id": 1},
    )
    if not trust:
        raise HTTPException(status_code=404, detail={"code": "trust_not_found"})

    # Trust owner entering their own trust: allowed, marked as owner view.
    if trust.get("user_id") == user["user_id"]:
        view_level = "owner"
        grant = None
    else:
        member_ids = await _active_member_ids(user)
        now = datetime.now(timezone.utc).isoformat()
        grant = await db.trust_grants.find_one({
            "trust_id": trust_id,
            "status": "active",
            "member_id": {"$in": member_ids},
            "$or": [
                {"expires_at": {"$gte": now}},
                {"expires_at": {"$exists": False}},
                {"expires_at": None},
            ],
        })
        if not grant:
            raise HTTPException(status_code=403, detail={"code": "org_access_denied"})
        view_level = grant.get("level", "viewer")

    # Client-side lock consent (mirrors admin impersonation): a client who
    # locked admin access also keeps service-provider viewers out.
    locked_pref = await db.user_preferences.find_one(
        {"user_id": trust["user_id"]},
        {"_id": 0, "admin_access_locked": 1},
    )
    if locked_pref and locked_pref.get("admin_access_locked") is True and view_level != "owner":
        raise HTTPException(
            status_code=403,
            detail={"code": "workspace_locked_by_owner"},
        )

    client = await db.users.find_one(
        {"user_id": trust["user_id"]},
        {"_id": 0, "email": 1, "name": 1},
    )
    org_row = await db.orgs.find_one(
        {"org_id": (grant or {}).get("org_id", "")},
        {"_id": 0, "org_id": 1, "name": 1},
    )

    # Audit: both collections used by admin impersonation, org-specific actions.
    now = _now()
    await db.admin_audit_log.insert_one({
        "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
        "action": "org_enter_workspace",
        "admin_user_id": user["user_id"],
        "admin_email": user.get("email", ""),
        "target_user_id": trust["user_id"],
        "target_email": (client or {}).get("email", ""),
        "trust_id": trust_id,
        "org_id": (grant or {}).get("org_id"),
        "grant_id": (grant or {}).get("grant_id"),
        "view_level": view_level,
        "timestamp": now,
    })

    # Security event logging (best-effort, mirrors admin impersonation)
    try:
        ip = request.headers.get("X-Forwarded-For", "").split(",")[-1].strip() if request else None
        ua = request.headers.get("User-Agent") if request else None
        await record_security_event(
            user["user_id"], "org_enter_workspace",
            ip=ip, user_agent=ua,
            details={
                "trust_id": trust_id,
                "org_id": (grant or {}).get("org_id"),
                "grant_id": (grant or {}).get("grant_id"),
                "view_level": view_level,
            },
        )
    except Exception as sec_exc:
        logger.warning(f"Security event logging for org_enter_workspace failed (non-fatal): {sec_exc}")

    logger.info("Org member %s entered workspace of trust %s (level=%s)",
                user.get("email", ""), trust_id, view_level)

    return {
        "trust": {
            "trust_id": trust["trust_id"],
            "name": trust.get("name", ""),
        },
        "client": {
            "user_id": trust["user_id"],
            "email": (client or {}).get("email", ""),
            "name": (client or {}).get("name", ""),
        },
        "org": {"org_id": (org_row or {}).get("org_id", ""), "name": (org_row or {}).get("name", "")},
        "view_level": view_level,
        "expires_at": (grant or {}).get("expires_at"),
        "entered_at": now,
        "return_path": "/org-console",
    }


@router.post("/orgs/enter-trust/{trust_id}/log-exit")
async def log_org_workspace_exit(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    """Org member exits a granted trust's workspace (audited)."""
    if not _toggle_institution():
        raise HTTPException(status_code=404, detail={"code": "feature_disabled"})
    trust = await db.trusts.find_one(
        {"trust_id": trust_id},
        {"_id": 0, "user_id": 1},
    )
    if not trust:
        raise HTTPException(status_code=404, detail={"code": "trust_not_found"})
    member_ids = await _active_member_ids(user)
    owner_view = trust.get("user_id") == user["user_id"]
    if not owner_view:
        grant = await db.trust_grants.find_one(
            {"trust_id": trust_id, "member_id": {"$in": member_ids}},
            {"_id": 0, "grant_id": 1, "org_id": 1},
        )
        if not grant:
            # Never fail the exit itself — the member may still be in-session
            # from a revocation; log with unknown grant but do not 403-block
            # a legitimate exit path.
            grant = {}
    else:
        grant = {}
    await db.admin_audit_log.insert_one({
        "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
        "action": "org_exit_workspace",
        "admin_user_id": user["user_id"],
        "admin_email": user.get("email", ""),
        "target_user_id": trust["user_id"],
        "trust_id": trust_id,
        "org_id": grant.get("org_id"),
        "grant_id": grant.get("grant_id"),
        "timestamp": _now(),
    })
    logger.info("Org member %s exited workspace of trust %s", user.get("email", ""), trust_id)
    return {"message": "Org workspace session ended"}
