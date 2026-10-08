"""
Beneficiaries router - Beneficiary dashboard for trust unit allocations
Migrated from server.py
"""
import re
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from pymongo.errors import OperationFailure

from dependencies import get_current_user, require_write_access, auto_update_onboarding
from database import db
from models import (
    BeneficiaryDashboardResponse, BeneficiaryAllocation,
    ClassBeneficiaryCreate, ClassBeneficiaryResponse, ClassBeneficiaryType,
    BeneficiaryCreate, BeneficiaryUpdate, SendCertificateRequest,
    TrustUnitCertificateCreate,
    ClassMemberCreate, ClassMemberStatusUpdate, ClassMemberRename, ClassBeneficiaryPatch,
)
import share_math
from routers.trust_units import create_unit_certificate as _create_cert, get_or_create_units_settings, get_next_certificate_number

router = APIRouter(prefix="/beneficiaries", tags=["beneficiaries"])


# ========== CLASS BENEFICIARY LABELS ==========
CLASS_BENEFICIARY_LABELS = {
    "children": "Children (including after-born)",
    "descendants": "Descendants",
    "issue": "Issue (lineal descendants)",
    "heirs": "Heirs",
    "heirs_at_law": "Heirs at Law",
    "blood_relatives": "Blood Relatives",
    "per_stirpes": "Per Stirpes (by branch)",
    "per_capita": "Per Capita (by head)",
    "custom": "Custom Class",
}


# ========== CLASS BENEFICIARY ENDPOINTS ==========

@router.post("/class-beneficiaries", response_model=ClassBeneficiaryResponse)
async def create_class_beneficiary(
    data: ClassBeneficiaryCreate,
    user: dict = Depends(require_write_access)
):
    """Add a class beneficiary designation to a trust"""
    user_id = user["user_id"]
    
    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": data.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    settings = await get_or_create_units_settings(data.trust_id, user_id)
    convention = data.distribution_convention or settings.get("class_distribution_convention", "per_capita")
    if convention not in {"per_capita", "per_stirpes"}:
        raise HTTPException(status_code=400, detail="Unsupported class distribution convention.")
    if settings.get("allocation_mode", "percentage") == "percentage":
        existing_pools = await db.class_beneficiaries.aggregate([
            {"$match": {"trust_id": data.trust_id, "user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$percentage"}}},
        ]).to_list(1)
        current_pct = existing_pools[0]["total"] if existing_pools else 0
        if current_pct + data.percentage > 100:
            raise HTTPException(status_code=400, detail="Class-beneficiary pools cannot exceed 100% combined.")

    class_beneficiary = {
        "class_beneficiary_id": f"cb_{uuid.uuid4().hex[:16]}",
        "trust_id": data.trust_id,
        "user_id": user_id,
        "class_type": data.class_type.value,
        "class_type_label": CLASS_BENEFICIARY_LABELS.get(data.class_type.value, data.class_type.value),
        "description": data.description,
        "percentage": data.percentage,
        "notes": data.notes,
        "distribution_convention": convention,
        "reserved_units": round(settings.get("total_authorized_units", 100) * data.percentage / 100, 4),
        "member_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.class_beneficiaries.insert_one(class_beneficiary)
    class_beneficiary.pop("_id", None)
    return class_beneficiary


@router.get("/class-beneficiaries")
async def list_class_beneficiaries(
    trust_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """List all class beneficiaries for a trust (paginated). READ endpoint — available to all authenticated users."""
    user_id = user["user_id"]
    
    query = {"user_id": user_id}
    if trust_id:
        query["trust_id"] = trust_id
    
    total = await db.class_beneficiaries.count_documents(query)
    class_beneficiaries = await db.class_beneficiaries.find(
        query, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "items": class_beneficiaries,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.delete("/class-beneficiaries/{class_beneficiary_id}")
async def delete_class_beneficiary(
    class_beneficiary_id: str,
    user: dict = Depends(require_write_access)
):
    """
    Remove a class beneficiary designation.

    Session-2 cascade fix (council defect): class deletion also deletes its
    class_beneficiary_members docs and writes a member_removed event per doc —
    member rows were previously ORPHANED, still scanning in aggregate queries.
    Classes (the pool container) are hard-deletable; NAMED MEMBERS are not —
    their audit trail lands in the append-only ledger before the docs go.
    Route signature and response contract unchanged ({status: deleted}).
    """
    user_id = user["user_id"]

    class_doc = await db.class_beneficiaries.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    )
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")

    members = await db.class_beneficiary_members.find(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0, "class_member_id": 1, "name": 1, "member_status": 1}
    ).to_list(500)
    now = _utc_now_iso()
    events = [
        _make_member_event(
            trust_id=class_doc["trust_id"], user_id=user_id,
            class_beneficiary_id=class_beneficiary_id,
            class_member_id=m.get("class_member_id"),
            event_type="member_removed",
            before={"name": m.get("name"), "member_status": m.get("member_status", "active")},
            after=None,
            reason="Class removed — member cascade deleted with its class",
            now=now,
        )
        for m in members
    ]

    async def _cascade_delete_ops(session):
        if events:
            await db.class_member_events.insert_many(events, session=session)
        await db.class_beneficiary_members.delete_many(
            {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id},
            session=session,
        )
        await db.class_beneficiaries.delete_one(
            {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id},
            session=session,
        )

    await _run_with_txn(db.client, _cascade_delete_ops)

    return {"status": "deleted"}


VALID_MEMBER_STATUSES = ("active", "deceased", "removed", "inactive")
# Statuses whose members drop out of the pool division but whose rows remain.
_SHARE_EXCLUDED_STATUSES = ("deceased", "removed", "inactive")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_member_event(
    trust_id: str, user_id: str, class_beneficiary_id: str, class_member_id,
    event_type: str, before, after, reason: str,
    minutes_record_id=None, now: Optional[str] = None,
) -> dict:
    """
    Append-only class_member_events ledger entry (council design #4).
    user_id is ALWAYS the authenticated owner — the ledger is owner-scoped,
    never written with anyone else's identity.
    """
    return {
        "event_id": f"cme_{uuid.uuid4().hex[:16]}",
        "trust_id": trust_id,
        "user_id": user_id,
        "class_beneficiary_id": class_beneficiary_id,
        "class_member_id": class_member_id,  # null for class_updated events
        "event_type": event_type,  # member_added | member_status_changed | member_updated | class_updated
        "before": before,
        "after": after,
        "reason": reason,
        "minutes_record_id": minutes_record_id,
        "created_at": now or _utc_now_iso(),
    }


async def _txn_supported(client) -> bool:
    """
    Probe ONCE per client whether the deployment supports multi-document
    transactions (replica set). Standalone mongod raises OperationFailure at
    start_transaction — cached False thereafter. Distinguishing initiation
    failures from mid-transaction failures by exception shape is unreliable,
    so fallback happens ONLY at the boundary: once a transaction is known
    supported, mid-transaction errors propagate and roll back (never a
    partially-applied fallback double-write).
    """
    cached = getattr(client, "_trustoffice_txn_supported", None)
    if cached is not None:
        return cached
    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                pass
        supported = True
    except OperationFailure:
        supported = False
    except Exception:
        supported = False
    try:
        client._trustoffice_txn_supported = supported
    except Exception:
        pass
    return supported


async def _run_with_txn(client, ops):
    """
    Run a member-mutation write set atomically when possible.

    ops(session_or_none): the same ordered writes either way — collection
    calls accept session=None. With a replica set they run inside
    client.start_session + start_transaction (council: insert + event write +
    member_version bump + member_count recompute all-or-nothing). Without one
    (standalone mongod), start_transaction raises OperationFailure, so we
    fall back to the same ordered sequential writes — degraded atomicity,
    documented here, because refusing every write on standalone deploys would
    take the subsystem offline.
    """
    if await _txn_supported(client):
        async with await client.start_session() as session:
            async with session.start_transaction():
                await ops(session)
    else:
        await ops(None)


async def _bump_class_version_and_count(user_id: str, class_beneficiary_id: str, session=None):
    """
    Advisory-cache recompute + member_version bump for every member mutation
    (council: member_version monotonic, member_count self-healing derived value).
    member_count = total roster rows (incl. deceased/removed — their rows remain);
    active_member_count = share-eligible members. Runs inside the caller's
    transaction session when provided.
    """
    base = {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}
    total = await db.class_beneficiary_members.count_documents(base, session=session)
    active = await db.class_beneficiary_members.count_documents(
        {**base, "member_status": {"$nin": list(_SHARE_EXCLUDED_STATUSES)}}, session=session
    )
    await db.class_beneficiaries.update_one(
        base,
        {
            "$inc": {"member_version": 1},
            "$set": {"member_count": total, "active_member_count": active},
        },
        session=session,
    )


def _active_member_orders(members: list, roster_order: list = None) -> List[int]:
    """Share-eligible member order-keys, in creation order.

    roster_order is the id-keyed creation order (share_math.member_sort_key)
    computed once by the caller; members without member_order (legacy docs)
    get their POSITION in that order as a stable stand-in — they must never
    collapse onto order-key 0 (which would hand several members the first
    member's share). Kept list-based for the legacy math path.
    """
    order_lookup = {}
    if roster_order:
        order_lookup = {mid: idx for idx, mid in enumerate(roster_order)}
    def _key(m):
        if m.get("member_order") is not None:
            return m["member_order"]
        mid = m.get("class_member_id")
        return order_lookup.get(mid, 0) if order_lookup else 0
    return [
        _key(m)
        for m in sorted(members, key=lambda x: (_key(x), x.get("created_at", "")))
        if m.get("member_status", "active") not in _SHARE_EXCLUDED_STATUSES
    ]


def _class_share_payload(class_doc: dict, active_orders: List[int], class_member_ids=None) -> dict:
    """
    Derived per-member shares (NEVER stored): pool ppm split by largest
    remainder with roster-order tie-break. Visible-formula fields per council
    legibility rule (pool ÷ members, sum pinned to pool).
    """
    pool_pct = float(class_doc.get("percentage", 0) or 0)
    pool_ppm = share_math.percent_to_ppm(pool_pct)
    split_ppm = share_math.largest_remainder_share_ppm(pool_ppm, active_orders)
    if class_member_ids is None:
        per_member_ppm = {order: ppm for order, ppm in zip(active_orders, split_ppm)}
    else:
        # Id-keyed form: shares belong to class_member_ids (same creation
        # order as active_orders), never to a possibly-colliding order value.
        per_member_ppm = {mid: ppm for mid, ppm in zip(class_member_ids, split_ppm)}
    return {
        "pool_percentage": pool_pct,
        "pool_percentage_ppm": pool_ppm,
        "active_member_count": len(active_orders),
        "per_member_share_ppm": per_member_ppm,
        "per_member_share_percent": {
            order: share_math.ppm_to_percent(ppm) for order, ppm in per_member_ppm.items()
        },
        "sum_check": share_math.shares_sum_check(pool_ppm, split_ppm),
    }


def _member_share_preview(pool_pct: float, active_before: int, active_after: int) -> dict:
    """Before/after split preview for status-change responses (share_math)."""
    preview = share_math.share_preview_ppm(
        share_math.percent_to_ppm(pool_pct), active_before, active_after
    )
    return {
        "pool_percentage": pool_pct,
        "active_members_before": active_before,
        "active_members_after": active_after,
        "per_member_share_percent_before": preview["per_member_share_percent_before"],
        "per_member_share_percent_after": preview["per_member_share_percent_after"],
        "sum_check": preview["sum_check"],
    }


async def _attach_share_preview(class_doc: dict, member_doc: dict) -> None:
    """
    Attach the new member's DERIVED share + a live (n-1 → n) split preview to
    a freshly-added member doc — the council's visible-math requirement.
    Shares are computed, never stored.
    """
    roster = await db.class_beneficiary_members.find(
        {"class_beneficiary_id": class_doc["class_beneficiary_id"], "user_id": class_doc["user_id"]},
        {"_id": 0, "class_member_id": 1, "member_status": 1, "member_order": 1,
         "confirmed_at": 1},
    ).to_list(500)
    # id-keyed creation order (legacy docs rank by confirmed_at, then id)
    ordered_ids = share_math.sort_members_in_creation_order(roster)
    ordered_ids = [m.get("class_member_id") for m in ordered_ids if share_math.doc_is_active(m)]
    active_orders = _active_member_orders(roster, roster_order=ordered_ids)
    shares = _class_share_payload(class_doc, active_orders, class_member_ids=ordered_ids)
    member_doc["member_share_ppm"] = shares["per_member_share_ppm"].get(
        member_doc.get("class_member_id"), 0)
    member_doc["member_share_percent"] = share_math.ppm_to_percent(
        member_doc["member_share_ppm"])
    member_doc["share_preview"] = _member_share_preview(
        float(class_doc.get("percentage", 0) or 0),
        max(len(active_orders) - 1, 0),
        len(active_orders),
    )


@router.post("/class-beneficiaries/{class_beneficiary_id}/members")
async def add_class_member(
    class_beneficiary_id: str,
    member: ClassMemberCreate,
    user: dict = Depends(require_write_access),
):
    """
    Record a trustee-confirmed class member without inferring eligibility.

    Session-2 hardening (council design 2026-10-07):
    - Structured ClassMemberCreate body (name required/trimmed ≤200; optional
      date_of_birth, notes, minutes_record_id).
    - member_order = next free rank; member_status='active', share_weight=1.
    - Insert + member_added event + member_version bump + member_count
      recompute wrapped in a Mongo transaction (client.start_session).
      Fallback to sequential ops on OperationFailure — standalone mongod
      (no replica set) cannot run transactions, so atomicity degrades to
      ordered sequential writes rather than refusing the write entirely.
    """
    user_id = user["user_id"]
    class_doc = await db.class_beneficiaries.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    )
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")

    name = (member.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Member name is required")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="Member name must be 200 characters or fewer")

    now = datetime.now(timezone.utc).isoformat()
    member_id = f"cm_{uuid.uuid4().hex[:12]}"

    # member_order = next free rank (no unique index violation on concurrent adds)
    last = await db.class_beneficiary_members.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id},
        sort=[("member_order", -1)],
    )
    member_order = (last.get("member_order", 0) + 1) if last else 1

    doc = {
        "class_member_id": member_id,
        "class_beneficiary_id": class_beneficiary_id,
        "trust_id": class_doc["trust_id"], "user_id": user_id,
        "name": name, "confirmed_by_user_id": user_id,
        "confirmed_at": now, "created_at": now,
        "member_status": "active",
        "status_reason": None, "status_changed_at": None,
        "share_weight": 1,
        "member_order": member_order,
        "minutes_record_id": member.minutes_record_id,
        "date_of_birth": member.date_of_birth,
        "notes": member.notes,
        "name_history": [],
    }
    event = _make_member_event(
        trust_id=class_doc["trust_id"], user_id=user_id,
        class_beneficiary_id=class_beneficiary_id, class_member_id=member_id,
        event_type="member_added", before=None, after=doc,
        reason=f"Member added: {name}",
        minutes_record_id=member.minutes_record_id, now=now,
    )

    # member_version bump + member_count recompute (advisory cache) ride in the
    # same transaction so a crash can never leave class/member disagreeing.

    async def _member_add_ops(session):
        await db.class_beneficiary_members.insert_one(doc, session=session)
        await _bump_class_version_and_count(user_id, class_beneficiary_id, session=session)
        await db.class_member_events.insert_one(event, session=session)

    await _run_with_txn(db.client, _member_add_ops)

    doc.pop("_id", None)
    await _attach_share_preview(class_doc, doc)
    return doc


@router.get("/class-beneficiaries/{class_beneficiary_id}/members")
async def list_class_members(class_beneficiary_id: str, user: dict = Depends(get_current_user)):
    """
    Roster read with DERIVED per-member shares (session 2):
    pool ppm split across share-eligible members via share_math — never stored
    per member. Every query filters by the AUTHENTICATED user's user_id.
    """
    user_id = user["user_id"]
    items = await db.class_beneficiary_members.find(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    ).sort("member_order", 1).to_list(500)
    class_doc = await db.class_beneficiaries.find_one({"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")
    # Creation order in id terms (member_order, confirmed_at, id — legacy docs
    # fall back to confirmed_at/id). Drives BOTH share paths so legacy docs
    # without member_order can never collapse onto order-key 0.
    derived = share_math.derive_class_member_shares(
        class_doc.get("percentage", 0) or 0, items
    )
    roster_order = derived["ordered_active_member_ids"]
    active_orders = _active_member_orders(items, roster_order=roster_order)
    active_ids_in_order = [
        m.get("class_member_id") for m in
        sorted(
            (m for m in items if m.get("member_status", "active") not in _SHARE_EXCLUDED_STATUSES),
            key=lambda x: share_math.member_sort_key(x),
        )
    ]
    shares = _class_share_payload(class_doc, active_orders, class_member_ids=active_ids_in_order)
    share_by_id = shares["per_member_share_ppm"]
    for item in items:
        mid = item.get("class_member_id")
        ppm = share_by_id.get(mid, 0)
        item["member_share_ppm"] = ppm
        item["member_share_percent"] = share_math.ppm_to_percent(ppm)
    # ===== Derived-share contract keys (council 2026-10-07, additive) =====
    # id-keyed computation via share_math.derive_class_member_shares: split
    # over ACTIVE members (missing member_status treated active), sorted in
    # creation order (member_order, then confirmed_at, then id). Legacy docs
    # that all lack member_order must never collapse onto order-key 0.
    # (derived also feeds roster_order above — one creation order everywhere.)
    return {
        "items": items,
        "member_count": len(items),
        "active_member_count": len(active_orders),
        "pool_percentage": shares["pool_percentage"],
        "pool_percentage_ppm": shares["pool_percentage_ppm"],
        "per_member_percentage": (
            shares["per_member_share_percent"].get(active_orders[0], 0.0)
            if active_orders else 0.0
        ),
        "per_member_share_percent": shares["per_member_share_percent"],
        "sum_check": shares["sum_check"],
        # Contract extension: per_member_shares (class_member_id, share_ppm,
        # share_pct) over ACTIVE members, integer pool shadow + integer
        # sum-check. active_member_count above already carries the contract
        # value (same roster), so no duplicate key is added here.
        "per_member_shares": derived["per_member_shares"],
        "share_mode": "per_capita_equal",
        "sum_check_ppm": derived["sum_check_ppm"],
    }


# ========== MEMBER MUTATION ENDPOINTS (session 2 — council design) ==========

@router.post("/class-beneficiaries/{class_beneficiary_id}/members/{class_member_id}/status")
async def set_class_member_status(
    class_beneficiary_id: str,
    class_member_id: str,
    body: ClassMemberStatusUpdate,
    user: dict = Depends(require_write_access),
):
    """
    Status transition — NO hard delete of members, ever (council design #3).
    deceased/removed/inactive drop out of the pool division; rows and history
    remain. Reason REQUIRED. Writes before/after event, bumps member_version,
    recomputes member_count, and returns a before/after per-member share
    preview (pool split old n vs new n via share_math).
    """
    user_id = user["user_id"]
    if body.status not in VALID_MEMBER_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {', '.join(VALID_MEMBER_STATUSES)}",
        )
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")

    class_doc = await db.class_beneficiaries.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    )
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")

    member_doc = await db.class_beneficiary_members.find_one(
        {
            "class_member_id": class_member_id,
            "class_beneficiary_id": class_beneficiary_id,
            "user_id": user_id,  # owner-only — member id alone is never trusted
        },
        {"_id": 0},
    )
    if not member_doc:
        raise HTTPException(status_code=404, detail="Class member not found")

    before_status = member_doc.get("member_status", "active")
    if before_status == body.status:
        raise HTTPException(status_code=400, detail=f"Member is already {body.status}")

    now = _utc_now_iso()
    event = _make_member_event(
        trust_id=member_doc["trust_id"], user_id=user_id,
        class_beneficiary_id=class_beneficiary_id, class_member_id=class_member_id,
        event_type="member_status_changed",
        before={"member_status": before_status},
        after={"member_status": body.status},
        reason=reason, minutes_record_id=body.minutes_record_id, now=now,
    )

    set_body = {
        "member_status": body.status,
        "status_reason": reason,
        "status_changed_at": now,
        **({"minutes_record_id": body.minutes_record_id}
           if body.minutes_record_id else {}),
    }

    async def _status_ops(session):
        await db.class_beneficiary_members.update_one(
            {"class_member_id": class_member_id, "user_id": user_id},
            {"$set": set_body},
            session=session,
        )
        await _bump_class_version_and_count(user_id, class_beneficiary_id, session=session)
        await db.class_member_events.insert_one(event, session=session)

    await _run_with_txn(db.client, _status_ops)

    # Before/after share preview: pool split across old n vs new n actives.
    roster = await db.class_beneficiary_members.find(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id},
        {"_id": 0, "class_member_id": 1, "member_status": 1, "member_order": 1,
         "confirmed_at": 1},
    ).to_list(500)
    ordered_ids = [
        m.get("class_member_id") for m in share_math.sort_members_in_creation_order(roster)
        if share_math.doc_is_active(m)
    ]
    active_now_n = len(_active_member_orders(roster, roster_order=ordered_ids))
    before_excluded = before_status in _SHARE_EXCLUDED_STATUSES
    after_excluded = body.status in _SHARE_EXCLUDED_STATUSES
    if not before_excluded and after_excluded:
        active_before_n, active_after_n = active_now_n + 1, active_now_n
    elif before_excluded and not after_excluded:
        active_before_n, active_after_n = active_now_n - 1, active_now_n
    else:
        # excluded → excluded transition: neither state counts toward the split
        active_before_n = active_after_n = active_now_n
    share_preview = _member_share_preview(
        float(class_doc.get("percentage", 0) or 0), active_before_n, active_after_n
    )

    updated = await db.class_beneficiary_members.find_one(
        {"class_member_id": class_member_id, "user_id": user_id}, {"_id": 0}
    )
    return {
        "member": updated,
        "before_status": before_status,
        "after_status": body.status,
        "reason": reason,
        "event_id": event["event_id"],
        "share_preview": share_preview,
    }


@router.patch("/class-beneficiaries/{class_beneficiary_id}/members/{class_member_id}")
async def rename_class_member(
    class_beneficiary_id: str,
    class_member_id: str,
    body: ClassMemberRename,
    user: dict = Depends(require_write_access),
):
    """
    Rename only — every rename appends a name_history entry
    {previous_name, changed_at, changed_by_user_id} and a member_updated
    event; never a silent overwrite (council design).
    """
    user_id = user["user_id"]
    class_doc = await db.class_beneficiaries.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    )
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")

    member_doc = await db.class_beneficiary_members.find_one(
        {
            "class_member_id": class_member_id,
            "class_beneficiary_id": class_beneficiary_id,
            "user_id": user_id,
        },
        {"_id": 0},
    )
    if not member_doc:
        raise HTTPException(status_code=404, detail="Class member not found")

    new_name = (body.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Member name is required")
    if len(new_name) > 200:
        raise HTTPException(status_code=400, detail="Member name must be 200 characters or fewer")
    old_name = member_doc.get("name", "")
    if new_name == old_name:
        raise HTTPException(status_code=400, detail="New name is identical to the current name")

    now = _utc_now_iso()
    history_entry = {
        "previous_name": old_name,
        "changed_at": now,
        "changed_by_user_id": user_id,
    }

    async def _rename_ops(session):
        await db.class_beneficiary_members.update_one(
            {"class_member_id": class_member_id, "user_id": user_id},
            {"$set": {"name": new_name}, "$push": {"name_history": history_entry}},
            session=session,
        )
        await _bump_class_version_and_count(user_id, class_beneficiary_id, session=session)
        await db.class_member_events.insert_one(
            _make_member_event(
                trust_id=member_doc["trust_id"], user_id=user_id,
                class_beneficiary_id=class_beneficiary_id,
                class_member_id=class_member_id,
                event_type="member_updated",
                before={"name": old_name}, after={"name": new_name},
                reason="Member renamed", now=now,
            ),
            session=session,
        )

    await _run_with_txn(db.client, _rename_ops)

    updated = await db.class_beneficiary_members.find_one(
        {"class_member_id": class_member_id, "user_id": user_id}, {"_id": 0}
    )
    return updated


@router.patch("/class-beneficiaries/{class_beneficiary_id}")
async def patch_class_beneficiary(
    class_beneficiary_id: str,
    body: ClassBeneficiaryPatch,
    user: dict = Depends(require_write_access),
):
    """
    Patch description/notes/percentage/distribution_convention on the class —
    replaces delete+recreate churn (council defect fix). Percentage changes
    pass the same 100%-cap aggregate check the create path uses. Returns the
    recomputed share preview and writes a class_updated event
    (class_member_id null). member_version bumps on percentage change because
    it alters every derived member share.
    """
    user_id = user["user_id"]
    class_doc = await db.class_beneficiaries.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    )
    if not class_doc:
        raise HTTPException(status_code=404, detail="Class beneficiary not found")

    updates = {}
    if body.description is not None:
        updates["description"] = body.description
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.distribution_convention is not None:
        if body.distribution_convention not in {"per_capita", "per_stirpes"}:
            raise HTTPException(status_code=400, detail="Unsupported class distribution convention.")
        updates["distribution_convention"] = body.distribution_convention
    if body.percentage is not None:
        updates["percentage"] = body.percentage
        settings = await get_or_create_units_settings(class_doc["trust_id"], user_id)
        if settings.get("allocation_mode", "percentage") == "percentage":
            existing_pools = await db.class_beneficiaries.aggregate([
                {"$match": {"trust_id": class_doc["trust_id"], "user_id": user_id}},
                {"$group": {"_id": None, "total": {"$sum": "$percentage"}}},
            ]).to_list(1)
            current_pct = existing_pools[0]["total"] if existing_pools else 0
            if current_pct - class_doc.get("percentage", 0) + body.percentage > 100:
                raise HTTPException(status_code=400, detail="Class-beneficiary pools cannot exceed 100% combined.")

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    now = _utc_now_iso()
    before_snapshot = {k: class_doc.get(k) for k in updates}
    event = _make_member_event(
        trust_id=class_doc["trust_id"], user_id=user_id,
        class_beneficiary_id=class_beneficiary_id, class_member_id=None,
        event_type="class_updated", before=before_snapshot, after=updates,
        reason="Class updated", now=now,
    )

    async def _class_patch_ops(session):
        await db.class_beneficiaries.update_one(
            {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id},
            {"$set": updates, "$inc": {"member_version": 1}},
            session=session,
        )
        await db.class_member_events.insert_one(event, session=session)

    await _run_with_txn(db.client, _class_patch_ops)

    updated_class = await db.class_beneficiaries.find_one(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id}, {"_id": 0}
    )
    roster = await db.class_beneficiary_members.find(
        {"class_beneficiary_id": class_beneficiary_id, "user_id": user_id},
        {"_id": 0, "class_member_id": 1, "member_status": 1, "member_order": 1,
         "confirmed_at": 1},
    ).to_list(500)
    ordered_ids = [
        m.get("class_member_id") for m in share_math.sort_members_in_creation_order(roster)
        if share_math.doc_is_active(m)
    ]
    share_preview = _class_share_payload(
        updated_class,
        _active_member_orders(roster, roster_order=ordered_ids),
        class_member_ids=ordered_ids,
    )
    return {"class": updated_class, "share_preview": share_preview, "event_id": event["event_id"]}


# ========== DASHBOARD ENDPOINT (updated) ==========

@router.get("/dashboard", response_model=BeneficiaryDashboardResponse)
async def get_beneficiary_dashboard(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Beneficiary Dashboard showing current unit allocations per certificate holder.
    Also includes class beneficiary designations.

    READ endpoint — available to all authenticated users (free, expired, past-due).
    Users can view their beneficiary data regardless of subscription status.
    """
    user_id = user["user_id"]
    
    # Get trust
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
        if not trust:
            raise HTTPException(status_code=404, detail="Trust not found")
    else:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        if not trust:
            raise HTTPException(status_code=404, detail="No trust found")
    
    trust_id = trust["trust_id"]
    trust_name = trust.get("name", "Unnamed Trust")
    
    # Get unit settings
    settings = await get_or_create_units_settings(trust_id, user_id)
    total_authorized = settings["total_authorized_units"]
    unit_label = settings.get("unit_label", "Certificate Unit")
    
    # Aggregate certificates directly in MongoDB for correctness at any scale
    pipeline = [
        {"$match": {"trust_id": trust_id, "user_id": user_id, "status": "active"}},
        {
            "$group": {
                "_id": {
                    "holder_name": "$holder_name",
                    "holder_identifier": {"$ifNull": ["$holder_identifier", ""]},
                    "holder_type": {"$ifNull": ["$holder_type", "individual"]},
                },
                "holder_identifier": {"$first": "$holder_identifier"},
                "holder_type": {"$first": {"$ifNull": ["$holder_type", "individual"]}},
                "email": {"$first": "$email"},
                "phone": {"$first": "$phone"},
                "total_units": {"$sum": "$units"},
                "certificates": {
                    "$push": {
                        "certificate_id": "$certificate_id",
                        "certificate_number": "$certificate_number",
                        "holder_name": "$holder_name",
                        "holder_identifier": {"$ifNull": ["$holder_identifier", ""]},
                        "holder_type": {"$ifNull": ["$holder_type", "individual"]},
                        "units": "$units",
                        "issue_date": "$issue_date",
                        "notes": {"$ifNull": ["$notes", ""]},
                        "email": {"$ifNull": ["$email", ""]},
                        "phone": {"$ifNull": ["$phone", ""]},
                    }
                },
            }
        },
        {"$sort": {"total_units": -1}},
    ]
    agg_results = await db.trust_unit_certificates.aggregate(pipeline).to_list(None)

    # Build beneficiary allocations with percentages
    beneficiaries = []
    total_issued = 0
    for row in agg_results:
        holder_data = {
            "holder_name": row["_id"]["holder_name"],
            "holder_identifier": row["holder_identifier"],
            "holder_type": row["holder_type"],
            "email": row["email"],
            "phone": row["phone"],
            "total_units": row["total_units"],
            "certificates": row["certificates"],
        }
        percentage = (holder_data["total_units"] / total_authorized * 100) if total_authorized > 0 else 0
        total_issued += holder_data["total_units"]
        beneficiaries.append(BeneficiaryAllocation(
            holder_name=holder_data["holder_name"],
            holder_identifier=holder_data["holder_identifier"],
            holder_type=holder_data.get("holder_type", "individual"),
            email=holder_data.get("email"),
            phone=holder_data.get("phone"),
            total_units=holder_data["total_units"],
            percentage=round(percentage, 4),
            certificate_count=len(holder_data["certificates"]),
            certificates=holder_data["certificates"]
        ))
    
    # Get class beneficiaries
    class_beneficiaries = await db.class_beneficiaries.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    # ===== Derived-share extension (council 2026-10-07, additive) =====
    # One roster read for the whole trust (mirrors roster endpoint's 500-cap
    # per class); attaches members[] with computed shares + active_member_count
    # to each class. Existing keys/semantics untouched; roster-less classes
    # get members=[] (Harmony Haven case: "pool undistributed until members
    # are added" still renders with pool_percentage intact).
    if class_beneficiaries:
        roster_query = {"trust_id": trust_id, "user_id": user_id}
        class_ids = [cb["class_beneficiary_id"] for cb in class_beneficiaries]
        roster_query["class_beneficiary_id"] = {"$in": class_ids}
        rosters = await db.class_beneficiary_members.find(
            roster_query,
            {"_id": 0, "class_member_id": 1, "class_beneficiary_id": 1, "name": 1,
             "member_status": 1, "member_order": 1, "confirmed_at": 1,
             "created_at": 1, "share_weight": 1},
        ).limit(10000).to_list(10000)
        rosters_by_class = {}
        for m in rosters:
            rosters_by_class.setdefault(m.get("class_beneficiary_id"), []).append(m)
        for cb in class_beneficiaries:
            class_roster = rosters_by_class.get(cb["class_beneficiary_id"], [])
            derived = share_math.derive_class_member_shares(
                cb.get("percentage", 0) or 0,
                class_roster,
            )
            names = {m.get("class_member_id"): m.get("name") for m in class_roster}
            member_rows = []
            for share_row in derived["per_member_shares"]:
                row = dict(share_row)
                row["name"] = names.get(share_row["class_member_id"])
                member_rows.append(row)
            cb["members"] = member_rows
            cb["active_member_count"] = derived["active_member_count"]
            cb["pool_percentage_ppm"] = derived["pool_percentage_ppm"]
            cb["share_mode"] = "per_capita_equal"

    # Compute allocation totals.
    # Certificate percentages are ISSUED ownership (additive, capped at 100 by
    # create_unit_certificate). Class-beneficiary percentages are RESERVED
    # pools that may overlap with issued certificates (a descendant holding a
    # 15% certificate can also sit in a contingent descendants class), so they
    # are tracked separately and NOT summed into one "total allocated".
    # total_allocated_percentage is therefore max(certificates, classes) as a
    # conservative committed-allocation figure; cert/class totals let the UI
    # show each layer and flag when reserved pools exceed remaining capacity.
    certificate_percentage_total = round(
        sum(b.percentage for b in beneficiaries), 4
    )
    class_beneficiary_percentage_total = round(
        sum(cb.get("percentage", 0) for cb in class_beneficiaries), 4
    )
    total_allocated_percentage = round(
        max(certificate_percentage_total, class_beneficiary_percentage_total), 4
    )
    
    # Get recent transfers
    transfers = await db.trust_unit_transfers.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)

    # Total active certificate count for metadata
    active_cert_count = await db.trust_unit_certificates.count_documents(
        {"trust_id": trust_id, "user_id": user_id, "status": "active"}
    )

    return BeneficiaryDashboardResponse(
        trust_id=trust_id,
        trust_name=trust_name,
        total_authorized_units=total_authorized,
        total_issued_units=total_issued,
        remaining_units=total_authorized - total_issued,
        unit_label=unit_label,
        active_certificate_count=active_cert_count,
        beneficiaries=beneficiaries,
        class_beneficiaries=class_beneficiaries,
        recent_transfers=transfers,
        total_allocated_percentage=total_allocated_percentage,
        class_beneficiary_percentage_total=class_beneficiary_percentage_total,
        certificate_percentage_total=certificate_percentage_total,
    )


# ========== BENEFICIARY MANAGEMENT ENDPOINTS ==========
# These mirror the logic in routers/chat.py _execute_approved_action
# (lines 796-957) but exposed as proper REST handlers so the
# action_registry.py endpoints resolve to real HTTP routes.

@router.get("")
async def list_beneficiaries(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List beneficiaries for a trust.

    READ endpoint — available to all authenticated users.
    Returns {beneficiaries: [...]} with beneficiary_id, name, relationship,
    created_at, and date_added fields. Used by the Audit Trail page.
    """
    user_id = user["user_id"]

    query = {"user_id": user_id}
    if trust_id:
        query["trust_id"] = trust_id

    beneficiaries = await db.beneficiaries.find(
        query,
        {
            "_id": 0,
            "beneficiary_id": 1,
            "trust_id": 1,
            "user_id": 1,
            "name": 1,
            "relationship": 1,
            "created_at": 1,
            "date_added": 1,
        }
    ).sort("created_at", -1).to_list(1000)

    return {"beneficiaries": beneficiaries}


@router.post("/create")
async def create_beneficiary(
    data: BeneficiaryCreate,
    user: dict = Depends(require_write_access)
):
    """Add a beneficiary by issuing a trust unit certificate.

    Converts allocation_pct into a unit count using the trust's unit settings,
    then routes through the trust_units create_unit_certificate handler to
    ensure the same validation (units overflow, fractional, numbering) as a
    direct certificate issuance.
    """
    user_id = user["user_id"]

    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": data.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Get the trust's explicit allocation mode and ceiling.
    settings = await get_or_create_units_settings(data.trust_id, user_id)
    allocation_mode = settings.get("allocation_mode", "percentage")
    total_authorized = settings.get("total_authorized_units", 0)
    allow_fractional = settings.get("allow_fractional", False)

    if total_authorized <= 0:
        raise HTTPException(
            status_code=400,
            detail="Trust has no authorized units. Configure unit settings first."
        )

    allocation_pct = data.allocation_pct
    if allocation_mode == "units" and data.units is not None:
        raw_units = data.units
        allocation_pct = round(raw_units / total_authorized * 100, 4)
    else:
        if allocation_pct is None:
            raise HTTPException(status_code=400, detail="allocation_pct is required in percentage mode")
        if not isinstance(allocation_pct, (int, float)) or allocation_pct <= 0:
            raise HTTPException(status_code=400, detail="allocation_pct must be a positive number greater than 0")
        if allocation_mode == "percentage" and allocation_pct > 100:
            raise HTTPException(status_code=400, detail="Percentage allocations cannot exceed 100%.")
        # Percentage mode converts the requested share to the configured
        # certificate basis; unit mode never infers units from display values.
        raw_units = total_authorized * allocation_pct / 100.0

    if allow_fractional:
        units = round(raw_units, 4)
    else:
        units = round(raw_units)

    ceiling = settings.get("authorized_units_ceiling")
    if allocation_mode == "units" and not settings.get("unlimited_units") and ceiling and units > ceiling:
        raise HTTPException(status_code=400, detail="Allocation exceeds the configured authorized-unit ceiling.")
    if units <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"allocation_pct of {allocation_pct}% resolves to zero units "
                f"(raw={raw_units}, allow_fractional={allow_fractional}). "
                f"Increase the percentage or enable fractional units."
            )
        )

    # Effective percentage back-calculated from final units for the response
    effective_pct = round(units / total_authorized * 100, 4)

    cert_create = TrustUnitCertificateCreate(
        trust_id=data.trust_id,
        holder_name=data.name,
        holder_type=data.holder_type,
        units=float(units),
        issue_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        email=data.email,
        phone=data.phone,
        notes=data.notes or "",
    )

    # create_unit_certificate expects a user dict with user_id
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        user_doc = {"user_id": user_id, "email": "", "name": ""}

    try:
        result = await _create_cert(certificate=cert_create, user=user_doc)
        # Update onboarding checklist
        try:
            await auto_update_onboarding(user_id, data.trust_id)
        except Exception:
            pass
        # Enrich response with the effective values derived from allocation_pct
        response = dict(result) if hasattr(result, "__dict__") else dict(result)
        response["requested_allocation_pct"] = allocation_pct
        response["effective_pct"] = effective_pct
        response["effective_units"] = units
        return response
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create beneficiary: {str(e)}")


@router.patch("/{beneficiary_id}")
async def update_beneficiary(
    beneficiary_id: str,
    data: BeneficiaryUpdate,
    user: dict = Depends(require_write_access)
):
    """Update a beneficiary's contact info (email/phone/notes).

    The beneficiary_id path param is the certificate_id of an active
    trust unit certificate. The trust_id is derived from the certificate
    record itself, so callers don't need to pass it separately.
    """
    user_id = user["user_id"]

    existing = await db.trust_unit_certificates.find_one(
        {
            "certificate_id": beneficiary_id,
            "user_id": user_id,
            "status": "active",
        },
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Beneficiary certificate not found")

    trust_id = existing.get("trust_id")

    update_fields = {}
    if data.email is not None:
        update_fields["email"] = data.email
    if data.phone is not None:
        update_fields["phone"] = data.phone
    if data.notes is not None:
        update_fields["notes"] = data.notes

    # Allocation edits are replacements, not in-place mutations. Validate the
    # replacement against the same canonical trust allocation rules before
    # superseding the prior certificate.
    if data.allocation_pct is not None or data.units is not None:
        settings = await get_or_create_units_settings(trust_id, user_id)
        total_authorized = settings.get("total_authorized_units", 0)
        allocation_mode = settings.get("allocation_mode", "percentage")
        if data.allocation_pct is not None:
            if allocation_mode == "percentage" and data.allocation_pct > 100:
                raise HTTPException(status_code=400, detail="Percentage allocations cannot exceed 100%.")
            replacement_units = total_authorized * data.allocation_pct / 100.0
        else:
            replacement_units = float(data.units or 0)
        if settings.get("allow_fractional"):
            replacement_units = round(replacement_units, 4)
        else:
            replacement_units = round(replacement_units)
        if replacement_units <= 0:
            raise HTTPException(status_code=400, detail="Allocation must resolve to a positive number of units.")
        active_total = await db.trust_unit_certificates.aggregate([
            {"$match": {"trust_id": trust_id, "user_id": user_id, "status": "active", "certificate_id": {"$ne": beneficiary_id}}},
            {"$group": {"_id": None, "total": {"$sum": "$units"}}},
        ]).to_list(1)
        issued_elsewhere = active_total[0]["total"] if active_total else 0
        if issued_elsewhere + replacement_units > total_authorized:
            raise HTTPException(status_code=400, detail="Replacement allocation exceeds the trust's remaining authorized units.")
        now = datetime.now(timezone.utc).isoformat()
        replacement = dict(existing)
        replacement.pop("_id", None)
        replacement["certificate_id"] = f"cert_{uuid.uuid4().hex[:12]}"
        replacement["certificate_number"] = await get_next_certificate_number(trust_id, user_id)
        replacement["units"] = float(replacement.get("units", 0))
        if data.units is not None:
            replacement["units"] = data.units
        elif data.allocation_pct is not None:
            settings = await get_or_create_units_settings(trust_id, user_id)
            replacement["units"] = round(settings["total_authorized_units"] * data.allocation_pct / 100.0, 4 if settings.get("allow_fractional") else 0)
        replacement["supersedes_certificate_id"] = beneficiary_id
        replacement["version"] = int(existing.get("version", 1)) + 1
        replacement["created_at"] = now
        replacement["updated_at"] = now
        replacement["effective_date"] = data.effective_date or now[:10]
        replacement["status"] = "active"
        await db.trust_unit_certificates.update_one(
            {"certificate_id": beneficiary_id, "user_id": user_id, "trust_id": trust_id},
            {"$set": {"status": "superseded", "superseded_at": now, "updated_at": now}},
        )
        await db.trust_unit_certificates.insert_one(replacement)
        await db.beneficiary_allocation_audit.insert_one({
            "audit_id": f"baa_{uuid.uuid4().hex[:12]}", "trust_id": trust_id,
            "user_id": user_id, "action": "replacement_created",
            "prior_certificate_id": beneficiary_id, "replacement_certificate_id": replacement["certificate_id"],
            "created_at": now,
            "reason": data.replacement_reason or "Allocation updated",
            "effective_date": replacement["effective_date"],
        })
        update_fields = {k: v for k, v in update_fields.items() if k in {"email", "phone", "notes"}}
        if update_fields:
            await db.trust_unit_certificates.update_one({"certificate_id": replacement["certificate_id"]}, {"$set": update_fields})
        return replacement

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.trust_unit_certificates.update_one({"certificate_id": beneficiary_id, "user_id": user_id, "trust_id": trust_id}, {"$set": update_fields})

    updated = await db.trust_unit_certificates.find_one(
        {"certificate_id": beneficiary_id, "user_id": user_id},
        {"_id": 0}
    )
    return updated


@router.delete("/{beneficiary_id}")
async def delete_beneficiary(
    beneficiary_id: str,
    user: dict = Depends(require_write_access)
):
    """Remove (deactivate) a beneficiary.

    Marks the underlying trust unit certificate as inactive rather than
    deleting the record, preserving an audit trail. The trust_id is
    derived from the certificate record itself.
    """
    user_id = user["user_id"]

    existing = await db.trust_unit_certificates.find_one(
        {
            "certificate_id": beneficiary_id,
            "user_id": user_id,
            "status": "active",
        },
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Beneficiary certificate not found")

    trust_id = existing.get("trust_id")

    await db.trust_unit_certificates.update_one(
        {"certificate_id": beneficiary_id, "user_id": user_id, "trust_id": trust_id},
        {"$set": {
            "status": "inactive",
            "deactivated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    # 2026-09-23: releasing reserved capacity — this deactivate path skipped
    # the counter decrement, so removing a beneficiary permanently burned its
    # units. Mirrors the revoke path.
    await db.trust_unit_counters.update_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"$inc": {"reserved_units": -existing["units"]}}
    )

    return {"status": "deleted", "certificate_id": beneficiary_id}


@router.post("/send-certificate")
async def send_beneficiary_certificate(
    data: SendCertificateRequest,
    user: dict = Depends(require_write_access)
):
    """Email a beneficiary their certificate notice.

    Looks up all active certificates for the named holder, aggregates the
    unit total, and sends a templated certificate notice email. The
    optional email field overrides the address on file.
    """
    user_id = user["user_id"]

    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": data.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Find active certificates for this holder (case-insensitive exact match)
    holder_name = data.beneficiary_name
    certs = await db.trust_unit_certificates.find(
        {
            "trust_id": data.trust_id,
            "user_id": user_id,
            "holder_name": {"$regex": f"^{re.escape(holder_name)}$", "$options": "i"},
            "status": "active",
        },
        {"_id": 0}
    ).to_list(5000)

    if not certs:
        raise HTTPException(
            status_code=404,
            detail=f"No active certificate found for beneficiary '{holder_name}'. Add them as a beneficiary first."
        )

    # Aggregate units across all certificates for this holder
    total_units = sum(c.get("units", 0) for c in certs)
    first_cert = certs[0]
    cert_number = first_cert.get("certificate_number", "N/A")
    cert_email = data.email or first_cert.get("email", "")

    if not cert_email:
        raise HTTPException(
            status_code=400,
            detail=f"No email address on file for '{holder_name}'. Provide an email address or update the beneficiary record first."
        )

    # Get trust name and unit settings
    trust_name = trust.get("name", "Your Trust")
    settings = await get_or_create_units_settings(data.trust_id, user_id)
    total_authorized = settings.get("total_authorized_units", 0)
    unit_label = settings.get("unit_label", "Certificate Unit")
    percentage = (total_units / total_authorized * 100) if total_authorized > 0 else 0

    # Get trustee name (the user's name)
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "email": 1})
    from_name = user_doc.get("name", "Trustee") if user_doc else "Trustee"

    # Send the certificate email
    # 2026-09-23: `import email_service` bound the MODULE, not the singleton,
    # so .send_certificate_notice raised AttributeError on every send
    # ("module 'email_service' has no attribute 'send_certificate_notice'").
    # Every other router imports the instance directly.
    from email_service import email_service
    result = await email_service.send_certificate_notice(
        to_email=cert_email,
        beneficiary_name=holder_name,
        trust_name=trust_name,
        certificate_number=cert_number,
        units=total_units,
        unit_label=unit_label,
        percentage=percentage,
        issue_date=first_cert.get("issue_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        notes=data.notes,
        from_user_name=from_name,
    )

    # Log the communication
    comm_doc = {
        "communication_id": f"comm_{uuid.uuid4().hex[:12]}",
        "trust_id": data.trust_id,
        "user_id": user_id,
        "type": "email",
        "subject": f"Certificate of Trust Units — {trust_name}",
        "participants": [holder_name],
        "notes": f"Certificate notice emailed to {holder_name} at {cert_email}. Certificate #{cert_number}, {total_units} units ({percentage:.2f}%).",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.communications.insert_one(comm_doc)

    return {
        "success": True,
        "email_sent_to": cert_email,
        "units": total_units,
        "percentage": round(percentage, 2),
        "certificate_id": first_cert.get("certificate_id"),
    }
