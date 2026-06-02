# External Trust Documents API — WingPoint → TrustOffice Document Delivery
# Provision endpoint is in routers/external.py (Emergent-built). This module handles
# document delivery and health check only.

import os
import uuid
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends
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


async def verify_document_api_key(request: Request, authorization: str = Depends(api_key_header)) -> None:
    """Verify API key for document delivery. Uses TRUSTOFFICE_EXTERNAL_API_KEY or falls back to EXTERNAL_API_KEY."""
    key = (authorization or "").replace("Bearer ", "").strip() if authorization else ""
    
    if not key:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Use: Bearer <api_key>")
    
    # Accept either the dedicated doc key or the general external key
    valid_keys = [k for k in [TRUSTOFFICE_EXTERNAL_API_KEY, os.environ.get("EXTERNAL_API_KEY", "")] if k]
    if not valid_keys or key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")


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
        valid = {"ein_confirmation", "declaration", "certification", "binder_kit"}
        if v not in valid:
            raise ValueError(f"Invalid document type: {v}. Must be one of {valid}")
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
    "certification": "trust_instrument",
    "binder_kit": "other",
}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB BSON limit


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

    # ─── Main handler with error reporting ─────────────────────────────────
    try:
        # 1. Find user by email
        email_lower = payload.customer_email.lower()
        user = await db.users.find_one({"email": email_lower}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail=f"No TrustOffice user found for email: {payload.customer_email}")

        user_id = user["user_id"]

        # 2. Find the trust — prefer explicit trust_id, then name match, then any trust
        trust = None

        if payload.trust_id:
            trust = await db.trusts.find_one({"trust_id": payload.trust_id, "user_id": user_id})

        if not trust:
            trust = await db.trusts.find_one(
                {"user_id": user_id, "name": {"$regex": f"^{payload.trust_name}$", "$options": "i"}}
            )

        if not trust:
            trust = await db.trusts.find_one({"user_id": user_id})

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

        # If all doc types already exist, return existing (idempotent)
        incoming_types = {d.type for d in payload.documents}
        if existing_by_type and incoming_types.issubset(existing_by_type.keys()):
            stored_docs = []
            for doc in payload.documents:
                if doc.type in existing_by_type:
                    stored_docs.append(DocumentStored(
                        doc_id=existing_by_type[doc.type],
                        type=doc.type,
                        category=doc.category,
                        title=doc.title,
                        stored=True
                    ))
            return TrustDocumentsResponse(
                status="delivered",
                documents_stored=len(stored_docs),
                documents=stored_docs,
                ein_updated=bool(payload.ein and trust.get("ein") != payload.ein),
                trust_name=trust.get("name", payload.trust_name)
            )

        # 4. Download and store each document
        stored_docs = []
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            for doc in payload.documents:
                if doc.type in existing_by_type:
                    stored_docs.append(DocumentStored(
                        doc_id=existing_by_type[doc.type],
                        type=doc.type,
                        category=doc.category,
                        title=doc.title,
                        stored=True
                    ))
                    continue

                # Download the PDF from WingPoint
                try:
                    response = await http_client.get(str(doc.url))
                    response.raise_for_status()
                    file_content = response.content
                except httpx.HTTPError as e:
                    logger.warning(f"Failed to download {doc.url}: {e}")
                    stored_docs.append(DocumentStored(
                        doc_id="",
                        type=doc.type,
                        category=doc.category,
                        title=doc.title,
                        stored=False
                    ))
                    continue

                # Validate size
                if len(file_content) > MAX_FILE_SIZE:
                    logger.warning(f"Document {doc.filename} exceeds {MAX_FILE_SIZE} bytes, skipping")
                    stored_docs.append(DocumentStored(
                        doc_id="",
                        type=doc.type,
                        category=doc.category,
                        title=doc.title,
                        stored=False
                    ))
                    continue

                # Category label
                category_label = DOC_CATEGORIES.get(doc.category, "Other")

                # Create vault document record
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
                    "description": f"Uploaded from WingPoint (ref: {payload.wingpoint_ref})",
                    "storage_provider": "trustoffice",
                    "storage_url": None,
                    "storage_path": None,
                    "file_name": doc.filename,
                    "file_size": f"{len(file_content) / 1024:.1f} KB" if len(file_content) < 1024 * 1024 else f"{len(file_content) / (1024 * 1024):.1f} MB",
                    "file_size_bytes": len(file_content),
                    "file_content_type": "application/pdf",
                    "file_content": file_content,
                    "tags": ["wingpoint", "auto-generated"],
                    "expiration_date": None,
                    "needs_renewal": False,
                    "created_at": now,
                    "updated_at": now,
                    "wingpoint_ref": payload.wingpoint_ref,
                    "wingpoint_doc_type": doc.type,
                    "source": "wingpoint",
                }

                await db.vault_documents.insert_one(record)

                stored_docs.append(DocumentStored(
                    doc_id=doc_id,
                    type=doc.type,
                    category=doc.category,
                    title=doc.title,
                    stored=True
                ))

        # 5. Update EIN on trust record if provided
        ein_updated = False
        if payload.ein:
            current_ein = trust.get("ein")
            if current_ein != payload.ein:
                await db.trusts.update_one(
                    {"trust_id": trust_id, "user_id": user_id},
                    {"$set": {"ein": payload.ein, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                ein_updated = True

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
            trust_name=trust.get("name", payload.trust_name)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document delivery failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document delivery failed: {str(e)}")


# ─── Health Check ─────────────────────────────────────────────────────────
@router.get("/api/external/trust-documents/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "service": "trust-documents"}