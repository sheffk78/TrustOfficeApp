"""
TrustOffice Agent Bridge Router — external customer-agent read surface.

All routes under /api/bridge/* use opaque agent tokens (NOT JWT) issued via the
admin-only /api/bridge/admin/tokens endpoints. The bridge auth dependency
validates the token on every request with no caching.

Security conditions from the 2026-10-18 council:
  - opaque per-customer tokens, SHA-256 hashed at rest, 90-day expiry
  - server-side validation on every request
  - revocation effective immediately
  - read-only surface with field-level whitelists
  - as_of / valid_until on every response
  - generic-verdict validation envelope only
  - hash-chained audit entries with integrity verification
  - bridge auth entirely separate from admin-api auth
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from database import db
from dependencies import get_current_user
from routers.admin import require_admin
from services import bridge_service

router = APIRouter(prefix="/bridge", tags=["agent_bridge"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(data: Dict[str, Any], tok: Dict[str, Any], ttl_minutes: int = 1) -> Dict[str, Any]:
    """Wrap every bridge response with as_of and valid_until metadata."""
    now = datetime.now(timezone.utc)
    return {
        "as_of": now.isoformat(),
        "valid_until": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        "token_id": tok.get("token_id"),
        **data,
    }


# ==================== ADMIN TOKEN ISSUANCE (internal JWT auth only) ====================

class TokenIssueRequest(BaseModel):
    customer_id: str = Field(..., min_length=1)
    scopes: List[str] = Field(default=["read"])
    label: Optional[str] = None
    rate_limit: int = Field(default=bridge_service.DEFAULT_RATE_LIMIT, ge=1, le=10000)


class TokenRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=1)


@router.post("/admin/tokens", status_code=201)
async def admin_issue_token(
    payload: TokenIssueRequest,
    admin: dict = Depends(require_admin),
):
    """Issue an opaque bridge agent token for a customer. Admin JWT only."""
    result = await bridge_service.issue_agent_token(
        customer_id=payload.customer_id,
        scopes=payload.scopes,
        issued_by_admin_id=admin["user_id"],
        label=payload.label,
        rate_limit=payload.rate_limit,
    )
    return result


@router.get("/admin/tokens")
async def admin_list_tokens(
    customer_id: Optional[str] = None,
    admin: dict = Depends(require_admin),
):
    """List active bridge agent tokens (optionally filtered by customer)."""
    query: Dict[str, Any] = {"status": "active"}
    if customer_id:
        query["customer_id"] = customer_id
    projection = {
        "_id": 0,
        "token_hash": 0,  # never expose the hash
    }
    docs = await db.agent_tokens.find(query, projection).sort("created_at", -1).to_list(length=200)
    return {"tokens": docs}


@router.post("/admin/tokens/{token_id}/revoke")
async def admin_revoke_token(
    token_id: str,
    payload: TokenRevokeRequest,
    admin: dict = Depends(require_admin),
):
    """Revoke a bridge agent token immediately."""
    revoked = await bridge_service.revoke_token(
        token_id=token_id,
        reason=payload.reason,
        revoked_by=admin.get("user_id"),
    )
    if not revoked:
        raise HTTPException(404, "token not found or already revoked")
    return {"revoked": True, "token_id": token_id}


# ==================== BRIDGE AUTH MIDDLEWARE ====================

async def require_bridge_token(
    request: Request,
    x_agent_token: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    Bridge auth dependency: validates the opaque agent token on every request.
    No caching. Sets request.state.bridge_token for downstream use.
    """
    raw = x_agent_token
    if not raw:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            raw = auth[7:].strip()
    if not raw:
        raise HTTPException(401, "agent token required")

    tok = await bridge_service.validate_token(raw)
    if tok is None:
        raise HTTPException(401, "agent token invalid, expired, or revoked")

    limit = tok.get("rate_limit", bridge_service.DEFAULT_RATE_LIMIT)
    if not bridge_service.check_rate_limit(tok["token_id"], limit):
        raise HTTPException(429, "rate limit exceeded")

    await bridge_service.record_usage(tok["token_id"])

    await bridge_service.append_audit(
        token_id=tok["token_id"],
        customer_id=tok["customer_id"],
        action="request.authorized",
        resource=request.url.path,
        request_meta={"method": request.method, "client_ip": request.client.host if request.client else None},
    )

    request.state.bridge_token = tok
    return tok


# ==================== READ-ONLY BRIDGE ENDPOINTS ====================

@router.get("/trust-calendar")
async def get_trust_calendar(
    request: Request,
    trust_id: Optional[str] = None,
    tok: dict = Depends(require_bridge_token),
):
    """Deadlines and obligations for the token's customer (single trust or all)."""
    if "read" not in tok.get("scopes", []):
        raise HTTPException(403, "token scope denied")
    items = await bridge_service.fetch_trust_calendar(tok["customer_id"], trust_id)
    return _envelope({"deadlines": items}, tok)


@router.get("/trust-facts")
async def get_trust_facts(
    request: Request,
    trust_id: Optional[str] = None,
    tok: dict = Depends(require_bridge_token),
):
    """Trust facts (name/type/key dates) excluding SSN, asset values, beneficiary contacts."""
    if "read" not in tok.get("scopes", []):
        raise HTTPException(403, "token scope denied")
    items = await bridge_service.fetch_trust_facts(tok["customer_id"], trust_id)
    return _envelope({"trusts": items}, tok)


@router.get("/document-status")
async def get_document_status(
    request: Request,
    trust_id: Optional[str] = None,
    tok: dict = Depends(require_bridge_token),
):
    """Vault document and minutes status list for the token's customer."""
    if "read" not in tok.get("scopes", []):
        raise HTTPException(403, "token scope denied")
    items = await bridge_service.fetch_document_status(tok["customer_id"], trust_id)
    return _envelope({"documents": items}, tok)


# ==================== GENERIC-VERDICT VALIDATION ====================

class ValidateDocumentRequest(BaseModel):
    trust_id: str
    document_id: str
    draft_reference: Optional[str] = None


@router.post("/validate-document")
async def validate_document(
    request: Request,
    payload: ValidateDocumentRequest,
    tok: dict = Depends(require_bridge_token),
):
    """
    Return a generic validation verdict + draft reference only.
    No rulebook detail is exposed over this API.
    """
    if "read" not in tok.get("scopes", []):
        raise HTTPException(403, "token scope denied")
    result = await bridge_service.generic_validate_document(
        customer_id=tok["customer_id"],
        trust_id=payload.trust_id,
        document_id=payload.document_id,
        draft_reference=payload.draft_reference,
    )
    if result["verdict"] not in bridge_service.VALID_VERDICTS:
        raise HTTPException(500, "invalid verdict generated")
    return _envelope({"validation": result}, tok)


# ==================== AUDIT INTEGRITY ====================

@router.get("/audit/verify")
async def verify_audit_chain(
    request: Request,
    tok: dict = Depends(require_bridge_token),
):
    """Verify the bridge audit chain integrity for this token's customer trail."""
    if "read" not in tok.get("scopes", []):
        raise HTTPException(403, "token scope denied")
    errors = await bridge_service.verify_audit_chain()
    return _envelope({"verified": len(errors) == 0, "errors": errors}, tok)
