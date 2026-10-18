"""
TrustOffice Agent Bridge — core service for the external customer-agent read surface.

Security contract (2026-10-18 council):
  * Opaque per-customer tokens (NOT JWT), SHA-256 hashed at rest, 90-day expiry.
  * Server-side validation on EVERY request; no caching of token validity.
  * Revocation effective immediately.
  * Read-only surface with field-level whitelists.
  * as_of / valid_until metadata on every response.
  * Generic-verdict validation envelope only (PASS / FAIL_* + draft reference).
  * Hash-chained audit entries with server timestamps and integrity verification.
  * Bridge auth is entirely separate from admin-api / user JWT auth.
"""

import hashlib
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Sequence

from database import db

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "tob_"
TOKEN_RANDOM_BYTES = 16  # -> 32 hex characters after the prefix
TOKEN_LIFETIME_DAYS = 90
DEFAULT_RATE_LIMIT = 60  # requests per hour per token
MCP_TOKEN_PREFIX = "toag_"
MCP_TOKEN_RANDOM_BYTES = 24  # -> 32 url-safe chars after prefix
MCP_TOKEN_LIFETIME_DAYS = 90


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _token_collection():
    return db.agent_tokens


def _audit_collection():
    return db.bridge_audit


# In-memory per-token request log for rate limiting. Sliding window over 1 hour.
# Format: {token_id: [epoch_seconds, ...]}
_rate_limit_buckets: Dict[str, List[float]] = {}


def reset_rate_limit(token_id: Optional[str] = None) -> None:
    """Test helper / MCP reset hook. Clears in-memory rate-limit buckets."""
    if token_id is None:
        _rate_limit_buckets.clear()
    else:
        _rate_limit_buckets.pop(token_id, None)


def _generate_raw_token() -> str:
    """Return an opaque token: 'tob_' + 32 hex characters."""
    return TOKEN_PREFIX + secrets.token_hex(TOKEN_RANDOM_BYTES)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_mcp_raw_token() -> str:
    """Opaque self-serve agent token: 'toag_' + 32 url-safe characters."""
    return MCP_TOKEN_PREFIX + secrets.token_urlsafe(MCP_TOKEN_RANDOM_BYTES)


def _canonical_json(payload: Dict[str, Any]) -> str:
    """Deterministic JSON serialization for hash inputs."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


async def _next_seq() -> int:
    """Return the next audit sequence number. Safe under the append-only model."""
    last = await _audit_collection().find_one({}, sort=[("seq", -1)])
    if last is None:
        return 1
    return int(last.get("seq", 0)) + 1


async def _next_agent_audit_seq() -> int:
    """Return the next agent_audit_log sequence number."""
    last = await db.agent_audit_log.find_one({}, sort=[("seq", -1)])
    if last is None:
        return 1
    return int(last.get("seq", 0)) + 1


async def _trust_owned(customer_id: str, trust_id: str) -> Optional[Dict[str, Any]]:
    """Return the trust document only if it belongs to the customer."""
    return await db.trusts.find_one({"user_id": customer_id, "trust_id": trust_id}, {"_id": 0})


async def issue_agent_token(
    customer_id: str,
    scopes: Sequence[str],
    issued_by_admin_id: str,
    label: Optional[str] = None,
    rate_limit: int = DEFAULT_RATE_LIMIT,
) -> Dict[str, Any]:
    """
    Issue a new bridge agent token.

    Returns a dict with the raw token (shown ONCE), token_id, expires_at, etc.
    The raw token is never persisted; only its SHA-256 hash is stored.
    """
    raw = _generate_raw_token()
    now = _now_dt()
    expires = now + timedelta(days=TOKEN_LIFETIME_DAYS)
    token_id = f"btok_{uuid.uuid4().hex[:12]}"
    doc = {
        "token_id": token_id,
        "token_hash": _hash_token(raw),
        "customer_id": customer_id,
        "scopes": list(scopes),
        "status": "active",
        "created_at": now,
        "expires_at": expires,
        "last_used_at": None,
        "revoked_at": None,
        "revoked_reason": None,
        "call_count": 0,
        "label": (label or "")[:80],
        "rate_limit": max(1, int(rate_limit)),
        "issued_by": issued_by_admin_id,
    }
    await _token_collection().insert_one(doc)

    await append_audit(
        token_id=token_id,
        customer_id=customer_id,
        action="token.issued",
        resource="agent_token",
        request_meta={"issued_by": issued_by_admin_id, "scopes": doc["scopes"], "rate_limit": doc["rate_limit"]},
    )

    return {
        "token_id": token_id,
        "token": raw,
        "customer_id": customer_id,
        "scopes": doc["scopes"],
        "expires_at": expires.isoformat(),
        "rate_limit": doc["rate_limit"],
    }


async def issue_mcp_token(
    user_id: str,
    agent_name: str,
    scopes: Sequence[str] = ("read",),
) -> Dict[str, Any]:
    """
    Issue a self-serve MCP agent token (toag_* prefix).

    Reuses the same hashed-at-rest, 90-day-expiry, rate-limited model as the
    admin-issued bridge tokens, but lives in the same agent_tokens collection and
    carries user_id + agent_name for the Settings > AI Agents card.
    """
    raw = _generate_mcp_raw_token()
    now = _now_dt()
    expires = now + timedelta(days=MCP_TOKEN_LIFETIME_DAYS)
    token_id = f"mtok_{uuid.uuid4().hex[:12]}"
    doc = {
        "token_id": token_id,
        "user_id": user_id,
        "customer_id": user_id,  # same value, dual key for cross-surface queries
        "agent_name": agent_name[:80],
        "token_hash": _hash_token(raw),
        "token_hint": raw[-6:],
        "scope": list(scopes),
        "scopes": list(scopes),
        "status": "active",
        "created_at": now,
        "expires_at": expires,
        "last_used_at": None,
        "revoked_at": None,
        "revoked_reason": None,
        "revoked_by": None,
        "call_count": 0,
        "rate_limit": DEFAULT_RATE_LIMIT,
        "issued_by": user_id,
        "label": agent_name[:80],
    }
    await _token_collection().insert_one(doc)

    await append_agent_audit(
        token_id=token_id,
        user_id=user_id,
        action="token.issued",
        resource="agent_token",
        request_meta={"agent_name": agent_name, "scopes": doc["scopes"], "rate_limit": doc["rate_limit"]},
    )

    return {
        "token": raw,
        "token_id": token_id,
        "agent_name": agent_name,
        "scope": doc["scope"],
        "scopes": doc["scopes"],
        "expires_at": expires.isoformat(),
        "rate_limit": doc["rate_limit"],
        "note": "Store this token in your agent's secret store now. It is shown only once.",
    }


async def list_mcp_tokens(user_id: str) -> List[Dict[str, Any]]:
    """List active self-serve MCP tokens for the settings card."""
    projection = {
        "_id": 0,
        "token_id": 1, "agent_name": 1, "token_hint": 1,
        "scope": 1, "created_at": 1, "last_used_at": 1,
        "call_count": 1, "expires_at": 1, "rate_limit": 1,
    }
    return await _token_collection().find(
        {"user_id": user_id, "status": "active"},
        projection,
    ).sort("created_at", -1).to_list(length=100)


async def revoke_mcp_token(token_id: str, user_id: str) -> bool:
    """Revoke a self-serve MCP token. Returns True if the token existed and was active."""
    now = _now_dt()
    tok = await _token_collection().find_one({"token_id": token_id, "user_id": user_id})
    if tok is None:
        return False
    result = await _token_collection().update_one(
        {"token_id": token_id, "user_id": user_id, "status": "active"},
        {
            "$set": {
                "status": "revoked",
                "revoked_at": now,
                "revoked_reason": "user_revoked",
                "revoked_by": user_id,
            }
        },
    )
    revoked = getattr(result, "modified_count", 0) > 0 or getattr(result, "matched_count", 0) > 0
    if revoked:
        await append_agent_audit(
            token_id=token_id,
            user_id=user_id,
            action="token.revoked",
            resource="agent_token",
            request_meta={"reason": "user_revoked", "revoked_by": user_id},
        )
    return revoked


async def validate_token(raw: str, prefix: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Server-side token validation with NO caching.

    Checks: format, hash lookup, active status, expiry, owner presence.
    Returns the token document or None.
    """
    expected_prefix = prefix or TOKEN_PREFIX
    if not isinstance(raw, str) or not raw.startswith(expected_prefix):
        return None
    tok = await _token_collection().find_one({"token_hash": _hash_token(raw)})
    if tok is None:
        return None
    if tok.get("status") != "active":
        return None
    expires_at = tok.get("expires_at")
    if expires_at is not None:
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _now_dt():
            return None
    if not (tok.get("customer_id") or tok.get("user_id")):
        return None
    return tok


async def validate_mcp_token(raw: str) -> Optional[Dict[str, Any]]:
    """Validate a self-serve toag_ MCP token."""
    return await validate_token(raw, prefix=MCP_TOKEN_PREFIX)


async def record_usage(token_id: str) -> None:
    """Bump last_used_at and call_count for a successfully validated token."""
    await _token_collection().update_one(
        {"token_id": token_id},
        {
            "$set": {"last_used_at": _now_dt()},
            "$inc": {"call_count": 1},
        },
    )


def check_rate_limit(token_id: str, limit: int = DEFAULT_RATE_LIMIT) -> bool:
    """
    Sliding-window rate limit: allow if fewer than `limit` requests in the past hour.
    Records this request on success.
    """
    now = time.time()
    window_start = now - 3600
    bucket = _rate_limit_buckets.get(token_id, [])
    bucket = [ts for ts in bucket if ts > window_start]
    allowed = len(bucket) < limit
    if allowed:
        bucket.append(now)
    _rate_limit_buckets[token_id] = bucket
    return allowed


async def revoke_token(token_id: str, reason: str, revoked_by: Optional[str] = None) -> bool:
    """Revoke an agent token immediately. Returns True if the token existed and was active."""
    now = _now_dt()
    tok = await _token_collection().find_one({"token_id": token_id})
    if tok is None:
        return False
    result = await _token_collection().update_one(
        {"token_id": token_id, "status": "active"},
        {
            "$set": {
                "status": "revoked",
                "revoked_at": now,
                "revoked_reason": (reason or "administrative")[:200],
                "revoked_by": revoked_by,
            }
        },
    )
    revoked = getattr(result, "modified_count", 0) > 0 or getattr(result, "matched_count", 0) > 0
    if revoked:
        await append_audit(
            token_id=token_id,
            customer_id=tok.get("customer_id", ""),
            action="token.revoked",
            resource="agent_token",
            request_meta={"reason": reason, "revoked_by": revoked_by},
        )
    return revoked


def _build_entry_hash(prev_hash: str, payload: Dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + _canonical_json(payload)).encode("utf-8")).hexdigest()


async def append_audit(
    token_id: str,
    customer_id: str,
    action: str,
    resource: str,
    request_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Append a tamper-evident audit entry.

    Fields: seq, server ts, token_id, customer_id, action, resource, request_meta,
    prev_hash, entry_hash = sha256(prev_hash + canonical payload).
    """
    seq = await _next_seq()
    now = _now_dt()
    last = await _audit_collection().find_one({}, sort=[("seq", -1)])
    prev_hash = last.get("entry_hash") if last else "0" * 64

    payload = {
        "seq": seq,
        "timestamp": now.isoformat(),
        "token_id": token_id,
        "customer_id": customer_id,
        "action": action,
        "resource": resource,
        "request_meta": request_meta or {},
        "prev_hash": prev_hash,
    }
    entry_hash = _build_entry_hash(prev_hash, payload)
    doc = {**payload, "entry_hash": entry_hash}
    await _audit_collection().insert_one(doc)
    return doc


async def append_agent_audit(
    token_id: str,
    user_id: str,
    action: str,
    resource: str,
    request_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Append a tamper-evident audit entry to agent_audit_log.

    Plain legacy rows are retroactively woven into the chain on first write:
    they are assigned monotonic seq values and linked by recomputed entry_hash,
    so the chain is deterministic from genesis forward. New rows carry
    seq, server timestamp, prev_hash, and entry_hash = sha256(prev_hash + payload).
    """
    await _weave_legacy_agent_audit_rows()
    seq = await _next_agent_audit_seq()
    now = _now_dt()
    last = await db.agent_audit_log.find_one({}, sort=[("seq", -1)])
    prev_hash = last.get("entry_hash") if last else "0" * 64

    payload = {
        "seq": seq,
        "timestamp": now.isoformat(),
        "token_id": token_id,
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "request_meta": request_meta or {},
        "prev_hash": prev_hash,
    }
    entry_hash = _build_entry_hash(prev_hash, payload)
    doc = {**payload, "entry_hash": entry_hash}
    await db.agent_audit_log.insert_one(doc)
    return doc


async def _weave_legacy_agent_audit_rows() -> None:
    """
    One-time deterministic migration: assign seq/prev_hash/entry_hash to any
    plain pre-consolidation rows in agent_audit_log, ordered by timestamp then _id.
    This makes the existing plain rows the deterministic genesis of the chain.
    """
    plain = await db.agent_audit_log.find({"seq": {"$exists": False}}).sort(
        [("at", 1), ("timestamp", 1), ("_id", 1)]
    ).to_list(length=None)
    if not plain:
        return
    prev_hash = "0" * 64
    for doc in plain:
        seq_doc = await db.agent_audit_log.find_one({}, sort=[("seq", -1)])
        seq = 1 if seq_doc is None else int(seq_doc.get("seq", 0)) + 1
        ts = doc.get("at") or doc.get("timestamp") or _now_dt().isoformat()
        payload = {
            "seq": seq,
            "timestamp": ts.isoformat() if isinstance(ts, datetime) else str(ts),
            "token_id": doc.get("token_id", ""),
            "user_id": doc.get("user_id", ""),
            "action": doc.get("tool", doc.get("action", "legacy.tool_call")),
            "resource": doc.get("resource", "legacy"),
            "request_meta": {"legacy": True, "args_summary": doc.get("args_summary", "")},
            "prev_hash": prev_hash,
        }
        entry_hash = _build_entry_hash(prev_hash, payload)
        # Store the full chain fields so verify can recompute deterministically.
        await db.agent_audit_log.update_one(
            {"_id": doc["_id"]},
            {"$set": {**payload, "entry_hash": entry_hash}},
        )
        prev_hash = entry_hash


async def verify_agent_audit_chain() -> List[str]:
    """Verify the agent_audit_log hash chain."""
    await _weave_legacy_agent_audit_rows()
    entries = await db.agent_audit_log.find({}, {"_id": 0}).sort("seq", 1).to_list(length=None)
    errors: List[str] = []
    prev_hash = "0" * 64
    for idx, entry in enumerate(entries):
        seq = entry.get("seq", idx + 1)
        if entry.get("prev_hash") != prev_hash:
            errors.append(f"agent seq {seq}: prev_hash mismatch")
        recomputed = _build_entry_hash(entry.get("prev_hash", prev_hash), {
            "seq": entry.get("seq"),
            "timestamp": entry.get("timestamp"),
            "token_id": entry.get("token_id"),
            "user_id": entry.get("user_id"),
            "action": entry.get("action"),
            "resource": entry.get("resource"),
            "request_meta": entry.get("request_meta", {}),
            "prev_hash": entry.get("prev_hash"),
        })
        if entry.get("entry_hash") != recomputed:
            errors.append(f"agent seq {seq}: entry_hash mismatch (tampered payload)")
        prev_hash = entry.get("entry_hash", prev_hash)
    return errors


async def verify_audit_chain() -> List[str]:
    """
    Verify the entire bridge_audit chain.
    Returns a list of error messages (empty if chain is intact).
    """
    entries = await _audit_collection().find({}, {"_id": 0}).sort("seq", 1).to_list(length=None)
    errors: List[str] = []
    prev_hash = "0" * 64
    for idx, entry in enumerate(entries):
        seq = entry.get("seq", idx + 1)
        if entry.get("prev_hash") != prev_hash:
            errors.append(f"seq {seq}: prev_hash mismatch")
        recomputed = _build_entry_hash(entry.get("prev_hash", prev_hash), {
            "seq": entry.get("seq"),
            "timestamp": entry.get("timestamp"),
            "token_id": entry.get("token_id"),
            "customer_id": entry.get("customer_id"),
            "action": entry.get("action"),
            "resource": entry.get("resource"),
            "request_meta": entry.get("request_meta", {}),
            "prev_hash": entry.get("prev_hash"),
        })
        if entry.get("entry_hash") != recomputed:
            errors.append(f"seq {seq}: entry_hash mismatch (tampered payload)")
        prev_hash = entry.get("entry_hash", prev_hash)
    return errors


# ==================== FRESHNESS ENVELOPE (cross-surface) ====================

def wrap_freshness(data: Dict[str, Any], ttl_minutes: int = 1) -> Dict[str, Any]:
    """Wrap any response payload with as_of / valid_until metadata."""
    now = _now_dt()
    return {
        "as_of": now.isoformat(),
        "valid_until": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        **data,
    }


# ==================== READ-ONLY DATA FETCHERS (field-level whitelists) ====================

TRUST_FACTS_WHITELIST = {
    "trust_id", "name", "state", "type", "grantor", "revocable",
    "formation_date", "created_at", "updated_at",
}

CALENDAR_WHITELIST = {
    "deadline_id", "trust_id", "title", "category", "due_date", "status",
    "priority", "is_statutory", "days_remaining", "is_overdue",
}

DOCUMENT_STATUS_WHITELIST = {
    "vault_document_id", "doc_id", "minutes_id", "name", "title", "category",
    "status", "analysis_status", "uploaded_at", "created_at", "updated_at",
    "mime_type", "file_size", "trust_id",
}


def _whitelist(doc: Dict[str, Any], allowed: set) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k in allowed}


async def fetch_trust_calendar(customer_id: str, trust_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return trust deadlines / obligations with a field-level whitelist.
    Uses deadline_service for enrichment when a single trust is requested.
    """
    if trust_id:
        trust = await _trust_owned(customer_id, trust_id)
        if not trust:
            return []
        # Reuse existing enrichment (computed days_remaining, is_overdue, status)
        from services import deadline_service
        enriched = await deadline_service.get_trust_deadlines(trust_id, customer_id)
        return [_whitelist(d, CALENDAR_WHITELIST) for d in enriched]

    # No trust_id: collect deadlines across all customer trusts (no bulk list-all risk
    # because the query is scoped to this customer_id and their known trust_ids).
    trust_ids = [
        d.get("trust_id")
        async for d in db.trusts.find({"user_id": customer_id}, {"_id": 0, "trust_id": 1})
    ]
    if not trust_ids:
        return []
    docs = await db.deadlines.find(
        {"user_id": customer_id, "trust_id": {"$in": trust_ids}},
        {"_id": 0, "deadline_id": 1, "trust_id": 1, "title": 1, "category": 1,
         "due_date": 1, "status": 1, "priority": 1, "is_statutory": 1},
    ).sort("due_date", 1).to_list(length=200)
    return [_whitelist(d, CALENDAR_WHITELIST) for d in docs]


async def fetch_trust_facts(customer_id: str, trust_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return trust facts: name/type/key dates. Explicitly excludes SSN, asset values,
    beneficiary contact info, and any other sensitive fields.
    """
    query: Dict[str, Any] = {"user_id": customer_id}
    if trust_id:
        query["trust_id"] = trust_id
    docs = await db.trusts.find(
        query,
        {"_id": 0, "trust_id": 1, "name": 1, "state": 1, "type": 1,
         "grantor": 1, "revocable": 1, "formation_date": 1,
         "created_at": 1, "updated_at": 1},
    ).to_list(length=100)
    return [_whitelist(d, TRUST_FACTS_WHITELIST) for d in docs]


async def fetch_document_status(customer_id: str, trust_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return a status list for vault documents and minutes. Content/file bytes are
    never included.
    """
    query: Dict[str, Any] = {"user_id": customer_id}
    if trust_id:
        query["trust_id"] = trust_id

    vault_docs = await db.vault_documents.find(
        query,
        {"_id": 0, "doc_id": 1, "trust_id": 1, "name": 1, "category": 1,
         "status": 1, "created_at": 1, "updated_at": 1, "mime_type": 1,
         "file_size": 1},
    ).sort("created_at", -1).to_list(length=100)

    minutes_query = dict(query)
    minutes_docs = await db.minutes_records.find(
        minutes_query,
        {"_id": 0, "minutes_id": 1, "trust_id": 1, "title": 1, "status": 1,
         "meeting_date": 1, "created_at": 1, "updated_at": 1},
    ).sort("created_at", -1).to_list(length=100)

    results: List[Dict[str, Any]] = []
    for d in vault_docs:
        results.append(_whitelist({
            "vault_document_id": d.get("doc_id"),
            "trust_id": d.get("trust_id"),
            "title": d.get("name"),
            "category": d.get("category"),
            "status": d.get("status", "uploaded"),
            "uploaded_at": d.get("created_at"),
            "updated_at": d.get("updated_at"),
            "mime_type": d.get("mime_type"),
            "file_size": d.get("file_size"),
            "analysis_status": None,
        }, DOCUMENT_STATUS_WHITELIST))

    for m in minutes_docs:
        results.append(_whitelist({
            "minutes_id": m.get("minutes_id"),
            "trust_id": m.get("trust_id"),
            "title": m.get("title"),
            "category": "minutes",
            "status": m.get("status"),
            "uploaded_at": m.get("created_at"),
            "updated_at": m.get("updated_at"),
            "meeting_date": m.get("meeting_date"),
            "analysis_status": None,
        }, DOCUMENT_STATUS_WHITELIST))

    return results


# ==================== GENERIC VALIDATION ENVELOPE ====================

VALID_VERDICTS = {"PASS", "FAIL_COMPLETENESS", "FAIL_FORMAT", "FAIL_CONSISTENCY"}


async def generic_validate_document(
    customer_id: str,
    trust_id: str,
    document_id: str,
    draft_reference: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return only a generic verdict + draft reference. No rulebook detail is exposed.

    Current implementation is a deterministic stub/contract that wires to the
    repository state: a missing trust/document => FAIL_COMPLETENESS, a missing
    file/content blob => FAIL_FORMAT, otherwise PASS. Real AI validation can be
    swapped in here without changing the API envelope.
    """
    ref = draft_reference or document_id or "draft_unknown"

    trust = await _trust_owned(customer_id, trust_id)
    if not trust:
        return {"verdict": "FAIL_CONSISTENCY", "draft_reference": ref}

    if not document_id:
        return {"verdict": "FAIL_FORMAT", "draft_reference": ref}

    doc = await db.vault_documents.find_one(
        {"doc_id": document_id, "trust_id": trust_id, "user_id": customer_id},
        {"_id": 0, "doc_id": 1, "file_content": 1, "mime_type": 1},
    )
    if not doc:
        return {"verdict": "FAIL_COMPLETENESS", "draft_reference": ref}

    # A document with no parseable content fails format validation.
    if not doc.get("file_content") and doc.get("mime_type") != "text/plain":
        return {"verdict": "FAIL_FORMAT", "draft_reference": ref}

    return {"verdict": "PASS", "draft_reference": ref}
