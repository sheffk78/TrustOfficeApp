# External Provision + Trust Management API — WingPoint → TrustOffice

import os
import uuid
import hashlib
import hmac
import httpx
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, field_validator, EmailStr

import logging

from database import db
from dependencies import create_initial_governance_tasks

logger = logging.getLogger(__name__)

router = APIRouter(tags=["external"])

# ─── Config ───────────────────────────────────────────────────────────────
EXTERNAL_API_KEY = os.environ.get("TRUSTOFFICE_EXTERNAL_API_KEY", "")
TRUST_TYPE_MAP = {
    "IRREVOCABLE_TRUST": "irrevocable",
    "REVOCABLE_TRUST": "revocable",
    "BUSINESS_TRUST": "business",
    "FAMILY_TRUST": "family",
    "CHARITABLE_TRUST": "charitable",
    "ECCLESIASTICAL_TRUST": "ecclesiastical",
}


# ─── Auth ──────────────────────────────────────────────────────────────────
def verify_external_api_key(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header[len("Bearer "):]
    if not EXTERNAL_API_KEY or token != EXTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ─── Models ───────────────────────────────────────────────────────────────
class ProvisionTrustOfficeRequest(BaseModel):
    wingpoint_ref: str
    customer_email: EmailStr
    customer_first_name: str
    customer_last_name: str
    trust_name: str
    trust_type: str = "IRREVOCABLE_TRUST"
    formation_state: Optional[str] = None
    trustee_first_name: Optional[str] = None
    trustee_last_name: Optional[str] = None
    idempotency_key: Optional[str] = None

    @field_validator("trust_type")
    @classmethod
    def validate_trust_type(cls, v: str) -> str:
        v = v.upper()
        if v not in TRUST_TYPE_MAP and v not in TRUST_TYPE_MAP.values():
            raise ValueError(f"Invalid trust type: {v}")
        return v


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


class ProvisionResponse(BaseModel):
    status: str
    user_id: str
    trust_id: str
    email: str
    trust_name: str
    is_new_user: bool
    is_new_trust: bool


# ─── Provision Endpoint ────────────────────────────────────────────────────
@router.post("/api/external/provision-trustoffice")
async def provision_trustoffice(request: Request, payload: ProvisionTrustOfficeRequest):
    """
    Create or link a TrustOffice account + trust for a WingPoint customer.
    
    Handles three scenarios:
    1. New user, first trust → create account + trust
    2. Existing user, new trust → link to existing account, create new trust
    3. Existing user, existing trust → return existing account + trust (idempotent)
    """
    verify_external_api_key(request)

    # Idempotency: check by wingpoint_ref first
    existing_provision = await db.wingpoint_provisions.find_one(
        {"wingpoint_ref": payload.wingpoint_ref},
        {"_id": 0}
    )
    if existing_provision:
        # Already provisioned — return existing state
        return ProvisionResponse(
            status="already_provisioned",
            user_id=existing_provision["user_id"],
            trust_id=existing_provision["trust_id"],
            email=existing_provision["email"],
            trust_name=existing_provision["trust_name"],
            is_new_user=False,
            is_new_trust=False,
        )

    # Also check idempotency by email + idempotency_key if provided
    if payload.idempotency_key:
        idempotent = await db.wingpoint_provisions.find_one(
            {"customer_email": payload.customer_email.lower(), "idempotency_key": payload.idempotency_key},
            {"_id": 0}
        )
        if idempotent:
            return ProvisionResponse(
                status="already_provisioned",
                user_id=idempotent["user_id"],
                trust_id=idempotent["trust_id"],
                email=idempotent["email"],
                trust_name=idempotent["trust_name"],
                is_new_user=False,
                is_new_trust=False,
            )

    # 1. Find or create user
    email_lower = payload.customer_email.lower()
    user = await db.users.find_one({"email": email_lower}, {"_id": 0})
    is_new_user = user is None

    if user:
        user_id = user["user_id"]
    else:
        # Create new user account (no password — they'll set it via WingPoint webhook)
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        user_doc = {
            "user_id": user_id,
            "email": email_lower,
            "name": f"{payload.customer_first_name} {payload.customer_last_name}",
            "first_name": payload.customer_first_name,
            "last_name": payload.customer_last_name,
            "is_admin": False,
            "created_at": now,
            "updated_at": now,
            "source": "wingpoint",
            "wingpoint_ref": payload.wingpoint_ref,
        }
        await db.users.insert_one(user_doc)

        # Create free subscription
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        await db.subscriptions.insert_one({
            "subscription_id": sub_id,
            "user_id": user_id,
            "plan_type": "free",
            "status": "active",
            "trial_start_date": None,
            "trial_end_date": None,
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "created_at": now,
            "updated_at": now,
            "notes": "Free individual trustee account — provisioned from WingPoint",
        })

        # Create onboarding record
        await db.user_onboarding.insert_one({
            "user_id": user_id,
            "email": email_lower,
            "onboarding_completed": False,
            "created_at": now,
            "updated_at": now,
        })

    # 2. Find or create trust for this user
    trust_type = TRUST_TYPE_MAP.get(payload.trust_type.upper(), "irrevocable")
    jurisdiction = payload.formation_state or ""

    # Check if this user already has a trust with this name
    existing_trust = await db.trusts.find_one(
        {"user_id": user_id, "name": {"$regex": f"^{payload.trust_name}$", "$options": "i"}},
        {"_id": 0}
    )

    # Also check by wingpoint_ref
    if not existing_trust:
        existing_trust = await db.trusts.find_one(
            {"user_id": user_id, "wingpoint_ref": payload.wingpoint_ref},
            {"_id": 0}
        )

    if existing_trust:
        trust_id = existing_trust["trust_id"]
        is_new_trust = False
    else:
        # Create new trust
        trust_id = f"trust_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        trustee_name = None
        if payload.trustee_first_name or payload.trustee_last_name:
            trustee_name = f"{payload.trustee_first_name or ''} {payload.trustee_last_name or ''}".strip()

        trust_doc = {
            "trust_id": trust_id,
            "user_id": user_id,
            "name": payload.trust_name,
            "trust_type": trust_type,
            "jurisdiction": jurisdiction,
            "state_code": jurisdiction,
            "role": "trustee",
            "start_date": "",
            "trustees": trustee_name,
            "authority_clause": None,
            "ein": None,
            "tax_year_end_month": 12,
            "tax_year_end_day": 31,
            "is_fiscal_year": False,
            "wingpoint_ref": payload.wingpoint_ref,
            "created_at": now,
            "updated_at": now,
        }
        await db.trusts.insert_one(trust_doc)
        is_new_trust = True

        # Create initial governance tasks
        await create_initial_governance_tasks(trust_id, user_id)

    # 3. Record provision for idempotency
    provision_record = {
        "wingpoint_ref": payload.wingpoint_ref,
        "idempotency_key": payload.idempotency_key,
        "user_id": user_id,
        "trust_id": trust_id,
        "customer_email": email_lower,
        "trust_name": payload.trust_name,
        "is_new_user": is_new_user,
        "is_new_trust": is_new_trust,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.wingpoint_provisions.insert_one(provision_record)

    return ProvisionResponse(
        status="provisioned",
        user_id=user_id,
        trust_id=trust_id,
        email=email_lower,
        trust_name=payload.trust_name,
        is_new_user=is_new_user,
        is_new_trust=is_new_trust,
    )


# ─── Document Delivery Endpoint ───────────────────────────────────────────
VALID_DOC_TYPES = {"ein_confirmation", "declaration", "certification", "binder_kit"}
DOC_CATEGORIES = {
    "ein_confirmation": "ein_letter",
    "declaration": "trust_instrument",
    "certification": "trust_instrument",
    "binder_kit": "other",
}
ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB BSON limit


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


@router.post("/api/external/trust-documents")
async def receive_trust_documents(request: Request, payload: DeliverDocumentsRequest):
    """
    Receive trust documents from WingPoint and store them in the customer's TrustOffice vault.
    
    WingPoint calls this after a trust application has all documents generated.
    TrustOffice downloads each PDF from the provided URLs and stores them as BSON binary
    in the vault — same as the existing user upload flow.
    """
    verify_external_api_key(request)

    # 1. Find user by email
    email_lower = payload.customer_email.lower()
    user = await db.users.find_one({"email": email_lower}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail=f"No TrustOffice user found for email: {payload.customer_email}")

    user_id = user["user_id"]

    # 2. Find the trust — prefer explicit trust_id, then wingpoint_ref, then name match
    trust = None

    if payload.trust_id:
        # Explicit trust_id from provision response (best for multi-trust)
        trust = await db.trusts.find_one({"trust_id": payload.trust_id, "user_id": user_id})

    if not trust:
        # Try wingpoint_ref
        trust = await db.trusts.find_one({"user_id": user_id, "wingpoint_ref": payload.wingpoint_ref})

    if not trust:
        # Try name match
        trust = await db.trusts.find_one(
            {"user_id": user_id, "name": {"$regex": f"^{payload.trust_name}$", "$options": "i"}}
        )

    if not trust:
        # Fallback: any trust for this user
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
            # Skip if already stored for this wingpoint_ref + type
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

            # Create vault document record (same structure as user uploads)
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
                "file_content": file_content,  # BSON binary — stored directly
                "tags": ["wingpoint", "auto-generated"],
                "expiration_date": None,
                "needs_renewal": False,
                "created_at": now,
                "updated_at": now,
                # WingPoint tracking fields
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
    from dependencies import auto_update_onboarding
    try:
        await auto_update_onboarding(user_id, trust_id)
    except Exception:
        pass

    # 7. Return response
    successfully_stored = sum(1 for d in stored_docs if d.stored)

    return TrustDocumentsResponse(
        status="delivered" if successfully_stored > 0 else "partial_failure",
        documents_stored=successfully_stored,
        documents=stored_docs,
        ein_updated=ein_updated,
        trust_name=trust.get("name", payload.trust_name)
    )


# ─── Health Check ─────────────────────────────────────────────────────────
@router.get("/api/external/trust-documents/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "service": "trust-documents"}