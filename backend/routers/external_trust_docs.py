# External Trust Documents API — WingPoint → TrustOffice Document Delivery
# Provision endpoint is in routers/external.py (Emergent-built). This module handles
# document delivery and health check only.

import os
import re
import hmac
import ipaddress
import socket
import uuid
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional, List
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator, EmailStr

from database import db
from dependencies import auto_update_onboarding

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external"])

# ─── Config ───────────────────────────────────────────────────────────────
TRUSTOFFICE_EXTERNAL_API_KEY = os.environ.get("TRUSTOFFICE_EXTERNAL_API_KEY", "")

# Use the same auth as the provision endpoint (EXTERNAL_API_KEY env var)
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


# ─── Models ───────────────────────────────────────────────────────────────
class TrustDocumentInput(BaseModel):
    type: str
    url: str
    filename: str
    title: str
    category: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"ein_confirmation", "declaration", "certification", "certification_general",
                    "certification_banking", "binder_kit", "declaration_signed"}
        if v not in allowed:
            raise ValueError(
                f"Unknown document type: '{v}'. Allowed: {', '.join(sorted(allowed))}"
            )
        return v


class DeliverDocumentsRequest(BaseModel):
    wingpoint_ref: str
    customer_email: EmailStr
    trust_name: str
    ein: Optional[str] = None
    trust_id: Optional[str] = None  # From provision response — preferred for multi-trust
    documents: List[TrustDocumentInput]


class DocumentStored(BaseModel):
    doc_id: str
    type: str
    category: str
    title: str
    stored: bool


class TrustDocumentsResponse(BaseModel):
    status: str
    documents_stored: int
    documents: List[DocumentStored]
    ein_updated: bool
    trust_name: str


# ─── Constants ─────────────────────────────────────────────────────────────
DOC_CATEGORIES = {
    "ein_confirmation": "ein_letter",
    "declaration": "trust_instrument",
    "declaration_signed": "trust_instrument",
    "certification": "trust_instrument",
    "certification_general": "trust_instrument",
    "certification_banking": "banking",
    "binder_kit": "other",
}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB BSON limit


# ─── Helpers ───────────────────────────────────────────────────────────────
def _build_failed_stored(doc) -> DocumentStored:
    """Construct a DocumentStored marking the doc as not stored."""
    return DocumentStored(
        doc_id="",
        type=doc.type,
        category=doc.category,
        title=doc.title,
        stored=False,
    )


def _build_success_stored(doc, doc_id: str) -> DocumentStored:
    """Construct a DocumentStored marking the doc as stored with its id."""
    return DocumentStored(
        doc_id=doc_id,
        type=doc.type,
        category=doc.category,
        title=doc.title,
        stored=True,
    )


def _is_unsafe_ip(ip) -> bool:
    """True if an IP is private/loopback/link-local/reserved (SSRF risk)."""
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def _hostname_resolves_to_unsafe_ip(hostname: str) -> bool:
    """Return True if hostname resolves to any private/loopback/etc IP."""
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, ValueError):
        # Unresolvable — let httpx handle the error downstream.
        return False
    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        if _is_unsafe_ip(ip):
            logger.warning(f"Rejected SSRF attempt: {hostname} resolves to private IP {ip}")
            return True
    return False


def _url_is_safe(url: str) -> bool:
    """Validate that the URL's hostname doesn't resolve to private IPs (scheme checked separately)."""
    hostname = urlparse(url).hostname
    if not hostname:
        return False
    return not _hostname_resolves_to_unsafe_ip(hostname)


def _format_file_size(num_bytes: int) -> str:
    """Human-readable file size string."""
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


async def _resolve_trust(user_id: str, payload: DeliverDocumentsRequest):
    """Find the trust record, preferring explicit trust_id → name match → any."""
    if payload.trust_id:
        trust = await db.trusts.find_one({"trust_id": payload.trust_id, "user_id": user_id})
        if trust:
            return trust

    trust = await db.trusts.find_one(
        {"user_id": user_id, "name": {"$regex": f"^{re.escape(payload.trust_name)}$", "$options": "i"}}
    )
    if trust:
        return trust

    return await db.trusts.find_one({"user_id": user_id})


def _all_types_already_stored(incoming_types: set, existing_by_type: dict) -> bool:
    """Idempotency check: every incoming doc type already exists in vault."""
    return bool(existing_by_type) and incoming_types.issubset(existing_by_type.keys())


def _build_existing_response(payload: DeliverDocumentsRequest, trust: dict, existing_by_type: dict) -> TrustDocumentsResponse:
    """Construct the idempotent response when all docs already exist."""
    stored_docs = [
        _build_success_stored(doc, existing_by_type[doc.type])
        for doc in payload.documents
        if doc.type in existing_by_type
    ]
    return TrustDocumentsResponse(
        status="delivered",
        documents_stored=len(stored_docs),
        documents=stored_docs,
        ein_updated=bool(payload.ein and trust.get("ein") != payload.ein),
        trust_name=trust.get("name", payload.trust_name),
    )


async def _download_document(http_client: httpx.AsyncClient, doc, filename: str):
    """Download a single doc, re-validating the final (post-redirect) URL for SSRF.

    Returns (content: bytes | None) — None means the download was rejected/failed.
    """
    try:
        response = await http_client.get(str(doc.url), follow_redirects=True)
    except httpx.HTTPError as e:
        logger.warning(f"Failed to download {doc.url}: {e}")
        return None

    # Re-validate the final URL after redirects
    final_url = str(response.url)
    if urlparse(final_url).scheme != "https":
        logger.warning(f"Redirected to non-HTTPS URL for {filename}: {final_url}")
        return None

    try:
        response.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning(f"Bad status downloading {doc.url}: {e}")
        return None

    return response.content


async def _store_one_document(
    http_client: httpx.AsyncClient,
    doc,
    wingpoint_ref: str,
    trust_id: str,
    user_id: str,
) -> DocumentStored:
    """Process a single document: validate, download, store. Always returns a DocumentStored."""
    # ── Validate URL scheme + SSRF ──
    parsed_url = urlparse(str(doc.url))
    if parsed_url.scheme != "https":
        logger.warning(f"Rejected non-HTTPS download URL for {doc.filename}: {parsed_url.scheme}://")
        return _build_failed_stored(doc)

    if not _url_is_safe(str(doc.url)):
        return _build_failed_stored(doc)

    # ── Download ──
    file_content = await _download_document(http_client, doc, doc.filename)
    if file_content is None:
        return _build_failed_stored(doc)

    # ── Validate size ──
    if len(file_content) > MAX_FILE_SIZE:
        logger.warning(f"Document {doc.filename} exceeds {MAX_FILE_SIZE} bytes, skipping")
        return _build_failed_stored(doc)

    # ── Build + insert record ──
    category_label = DOC_CATEGORIES.get(doc.category, "Other")
    now = datetime.now(timezone.utc).isoformat()
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"

    record = {
        "doc_id": doc_id,
        "trust_id": trust_id,
        "user_id": user_id,
        "title": doc.title,
        "category": doc.category,
        "category_label": category_label,
        "date": now[:10],
        "description": f"Uploaded from WingPoint (ref: {wingpoint_ref})",
        "storage_provider": "trustoffice",
        "storage_url": None,
        "storage_path": None,
        "file_name": doc.filename,
        "file_size": _format_file_size(len(file_content)),
        "file_size_bytes": len(file_content),
        "file_content_type": "application/pdf",
        "file_content": file_content,
        "tags": ["wingpoint", "auto-generated"],
        "expiration_date": None,
        "needs_renewal": False,
        "created_at": now,
        "updated_at": now,
        "wingpoint_ref": wingpoint_ref,
        "wingpoint_doc_type": doc.type,
        "source": "wingpoint",
    }
    await db.vault_documents.insert_one(record)

    return _build_success_stored(doc, doc_id)


async def _update_ein_if_needed(payload: DeliverDocumentsRequest, trust_id: str, user_id: str, trust: dict) -> bool:
    """Update trust EIN if a new one was provided. Returns whether it changed."""
    if not payload.ein:
        return False
    if trust.get("ein") == payload.ein:
        return False
    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"$set": {"ein": payload.ein, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return True


# ─── Auth ─────────────────────────────────────────────────────────────────
async def verify_document_api_key(request: Request) -> None:
    """Verify API key for document delivery. Uses TRUSTOFFICE_EXTERNAL_API_KEY or falls back to EXTERNAL_API_KEY."""
    authorization = request.headers.get("authorization", "")
    key = authorization.replace("Bearer ", "").strip()

    if not key:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Use: Bearer <api_key>")

    valid_keys = [k for k in [TRUSTOFFICE_EXTERNAL_API_KEY, os.environ.get("EXTERNAL_API_KEY", "")] if k]
    if not valid_keys or not any(hmac.compare_digest(key, k) for k in valid_keys):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ─── Document Delivery Endpoint ───────────────────────────────────────────
@router.post("/api/external/trust-documents")
async def receive_trust_documents(request: Request, payload: DeliverDocumentsRequest):
    """
    Receive trust documents from WingPoint and store them in the customer's TrustOffice vault.

    WingPoint calls this after a trust application has all documents generated.
    TrustOffice downloads each PDF from the provided URLs and stores them as BSON binary
    in the vault — same as the existing user upload flow. No URL dependency.

    Multi-trust: pass trust_id from provision response for accurate document placement.
    """
    # Auth check
    try:
        await verify_document_api_key(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth verification failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

    try:
        return await _deliver_documents(payload)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document delivery failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Document delivery failed. Check server logs.")


async def _deliver_documents(payload: DeliverDocumentsRequest) -> TrustDocumentsResponse:
    """Main delivery logic, separated from the endpoint for testability and shallow nesting."""
    # 1. Find user by email
    email_lower = payload.customer_email.lower()
    user = await db.users.find_one({"email": email_lower}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="Document delivery failed. User or trust not found.")

    user_id = user["user_id"]

    # 2. Find the trust
    trust = await _resolve_trust(user_id, payload)
    if not trust:
        raise HTTPException(
            status_code=404,
            detail=f"No trust found for user {payload.customer_email}. User may not have completed TrustOffice onboarding yet."
        )

    trust_id = trust["trust_id"]

    # 3. Check for duplicates (idempotency by wingpoint_ref + doc type)
    existing_docs = await db.vault_documents.find(
        {"user_id": user_id, "trust_id": trust_id, "wingpoint_ref": payload.wingpoint_ref},
        {"_id": 0, "doc_id": 1, "wingpoint_doc_type": 1}
    ).to_list(100)

    existing_by_type = {d["wingpoint_doc_type"]: d["doc_id"] for d in existing_docs}
    incoming_types = {d.type for d in payload.documents}

    # Idempotent short-circuit
    if _all_types_already_stored(incoming_types, existing_by_type):
        return _build_existing_response(payload, trust, existing_by_type)

    # 4. Download and store each document
    stored_docs: List[DocumentStored] = []
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        for doc in payload.documents:
            # Skip docs already in vault
            if doc.type in existing_by_type:
                stored_docs.append(_build_success_stored(doc, existing_by_type[doc.type]))
                continue
            stored_docs.append(
                await _store_one_document(http_client, doc, payload.wingpoint_ref, trust_id, user_id)
            )

    # 5. Update EIN on trust record if provided
    ein_updated = await _update_ein_if_needed(payload, trust_id, user_id, trust)

    # 6. Trigger onboarding checklist update (non-blocking)
    try:
        await auto_update_onboarding(user_id, trust_id)
    except Exception as e:
        logger.warning(f"Onboarding update failed for user {user_id} / trust {trust_id}: {e}")

    # 7. Return response
    successfully_stored = sum(1 for d in stored_docs if d.stored)
    return TrustDocumentsResponse(
        status="delivered" if successfully_stored > 0 else "partial_failure",
        documents_stored=successfully_stored,
        documents=stored_docs,
        ein_updated=ein_updated,
        trust_name=trust.get("name", payload.trust_name),
    )


# ─── Health Check ─────────────────────────────────────────────────────────
@router.get("/api/external/trust-documents/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "service": "trust-documents"}