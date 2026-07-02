# Vault router — trust document organization, reference tracking, and file upload
# File uploads stored as BSON binary in vault_documents (max 16MB per file)
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.responses import Response
from datetime import datetime, timezone
from typing import Optional, List
import re
import uuid
import base64
import logging
from urllib.parse import quote

from pydantic import BaseModel, field_validator

from database import db
from dependencies import get_current_user
from routers.compensation import auto_update_onboarding

logger = logging.getLogger(__name__)
router = APIRouter(tags=["vault"])

DOC_CATEGORIES = {
    "trust_instrument": "Trust Instrument / Governing Document",
    "amendment": "Trust Amendment / Restatement",
    "schedule_a": "Schedule A (Assets)",
    "minutes": "Minutes of Meetings",
    "tax_return": "Tax Return (Form 1041)",
    "k1": "Schedule K-1",
    "ein_letter": "EIN Confirmation Letter (CP575)",
    "financial_statement": "Financial Statement / Accounting",
    "appraisal": "Asset Appraisal / Valuation",
    "notice": "Beneficiary Notice / Communication",
    "insurance": "Insurance Policy / Rider",
    "deed": "Deed / Property Document",
    "bank_statement": "Bank / Investment Statement",
    "legal_opinion": "Legal Opinion / Attorney Letter",
    "court_order": "Court Order / Judgment",
    "other": "Other",
}

STORAGE_PROVIDERS = ["google_drive", "dropbox", "onedrive", "local_server", "cloud_url", "physical"]

ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "image/tiff": "tiff",
}

MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB BSON limit


# --- Pydantic models for request validation ---


class DocumentCreate(BaseModel):
    """Validated payload for adding a document reference to the vault."""
    title: str
    category: str = "other"
    date: Optional[str] = None
    description: Optional[str] = None
    storage_provider: str = "google_drive"
    storage_url: Optional[str] = None
    storage_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[str] = None
    tags: List[str] = []
    expiration_date: Optional[str] = None
    needs_renewal: bool = False

    @field_validator("storage_provider")
    @classmethod
    def validate_storage_provider(cls, v: str) -> str:
        if v not in STORAGE_PROVIDERS:
            raise ValueError(f"Invalid storage provider. Must be one of: {', '.join(STORAGE_PROVIDERS)}")
        return v

    @field_validator("storage_url")
    @classmethod
    def validate_storage_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith("https://"):
            raise ValueError("storage_url must start with 'https://'")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in DOC_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(DOC_CATEGORIES.keys())}")
        return v


class DocumentUpdate(BaseModel):
    """Validated payload for updating a vault document record. Only allowlisted fields are accepted."""
    title: Optional[str] = None
    category: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    expiration_date: Optional[str] = None
    needs_renewal: Optional[bool] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in DOC_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(DOC_CATEGORIES.keys())}")
        return v


@router.post("/trusts/{trust_id}/vault/documents")
async def add_document(trust_id: str, doc: DocumentCreate, user: dict = Depends(get_current_user)):
    """Add a document reference to the vault."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "doc_id": f"doc_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "title": doc.title,
        "category": doc.category,
        "category_label": DOC_CATEGORIES.get(doc.category, "Other"),
        "date": doc.date,
        "description": doc.description,
        "storage_provider": doc.storage_provider,
        "storage_url": doc.storage_url,
        "storage_path": doc.storage_path,
        "file_name": doc.file_name,
        "file_size": doc.file_size,
        "tags": doc.tags,
        "expiration_date": doc.expiration_date,
        "needs_renewal": doc.needs_renewal,
        "created_at": now,
        "updated_at": now,
    }
    await db.vault_documents.insert_one(record)
    try:
        await auto_update_onboarding(user["user_id"], trust_id)
    except Exception:
        pass
    return {"doc_id": record["doc_id"], "message": "Document added to vault"}


@router.post("/trusts/{trust_id}/vault/upload")
async def upload_document(
    trust_id: str,
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("trust_instrument"),
    date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(""),
    expiration_date: Optional[str] = Form(None),
    needs_renewal: Optional[str] = Form("false"),
    user: dict = Depends(get_current_user),
):
    """Upload a file to the vault. Stores file content as BSON binary."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Validate MIME type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIME_TYPES and not content_type.startswith("image/"):
        # Accept any image type even if not in our explicit list
        if not content_type.startswith(("image/", "application/pdf", "application/msword", "application/vnd.", "text/")):
            raise HTTPException(
                status_code=400,
                detail=f"File type '{content_type}' is not supported. Supported types: PDF, images, Word docs, Excel, and text files."
            )

    # Read and validate file size
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 16MB. Your file is {len(file_content) / (1024*1024):.1f}MB."
        )

    # Parse tags
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    # Format file size for display
    size_bytes = len(file_content)
    if size_bytes < 1024:
        size_display = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_display = f"{size_bytes / 1024:.1f} KB"
    else:
        size_display = f"{size_bytes / (1024 * 1024):.1f} MB"

    now = datetime.now(timezone.utc).isoformat()
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"

    record = {
        "doc_id": doc_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "title": title,
        "category": category,
        "category_label": DOC_CATEGORIES.get(category, "Other"),
        "date": date,
        "description": description,
        "storage_provider": "trustoffice",
        "storage_url": None,
        "storage_path": None,
        "file_name": file.filename or "document",
        "file_size": size_display,
        "file_size_bytes": size_bytes,
        "file_content_type": content_type,
        "file_content": file_content,  # BSON binary — stored directly
        "tags": tag_list,
        "expiration_date": expiration_date,
        "needs_renewal": needs_renewal.lower() == "true",
        "created_at": now,
        "updated_at": now,
    }

    await db.vault_documents.insert_one(record)

    # Update onboarding checklist (non-blocking — don't fail the upload if this errors)
    try:
        await auto_update_onboarding(user["user_id"], trust_id)
    except Exception:
        pass

    # Trigger trust document analysis if this is a trust instrument or amendment
    if category in ("trust_instrument", "amendment") and file_content:
        try:
            from trust_doc_analyzer import analyze_trust_document
            import asyncio
            asyncio.create_task(
                analyze_trust_document(
                    trust_id, user["user_id"], doc_id, file_content,
                    is_amendment=(category == "amendment")
                )
            )
            logger.info(f"Triggered trust doc analysis for trust {trust_id}, doc {doc_id}")
        except Exception as e:
            logger.warning(f"Failed to trigger trust doc analysis: {e}")

    # Return without file_content in the response
    response = {k: v for k, v in record.items() if k != "file_content"}
    response["message"] = "File uploaded to vault"
    return response


@router.get("/vault/documents/{doc_id}/download")
async def download_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Download a file from the vault."""
    doc = await db.vault_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_content = doc.get("file_content")
    if not file_content:
        # This is a reference-only doc (no uploaded file) — redirect to external URL
        storage_url = doc.get("storage_url")
        if storage_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=storage_url)
        raise HTTPException(status_code=404, detail="No file content available")

    content_type = doc.get("file_content_type", "application/octet-stream")
    filename = doc.get("file_name", "document")

    # Sanitize filename to prevent header injection — strip CR/LF and quotes
    safe_filename = re.sub(r'[\r\n"\\]', '', filename)
    # RFC 5987 encoded filename for non-ASCII / special characters
    encoded_filename = quote(safe_filename, safe='')

    return Response(
        content=file_content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/trusts/{trust_id}/vault/documents")
async def list_documents(
    trust_id: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    provider: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List vault documents with filtering. Excludes file_content from responses."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    query = {"trust_id": trust_id}
    if category:
        query["category"] = category
    if provider:
        query["storage_provider"] = provider
    if search:
        escaped_search = re.escape(search)
        query["$or"] = [
            {"title": {"$regex": escaped_search, "$options": "i"}},
            {"description": {"$regex": escaped_search, "$options": "i"}},
            {"tags": {"$regex": escaped_search, "$options": "i"}},
        ]

    # Exclude file_content from list responses (it can be huge)
    docs = await db.vault_documents.find(query, {"_id": 0, "file_content": 0}).sort("date", -1).to_list(200)

    # Group by category
    by_category = {}
    for d in docs:
        cat = d.get("category", "other")
        if cat not in by_category:
            by_category[cat] = {"label": DOC_CATEGORIES.get(cat, "Other"), "documents": []}
        by_category[cat]["documents"].append(d)

    # Upcoming renewals
    renewals = [d for d in docs if d.get("needs_renewal") and d.get("expiration_date")]

    return {
        "trust_id": trust_id,
        "documents": docs,
        "by_category": by_category,
        "count": len(docs),
        "categories": DOC_CATEGORIES,
        "upcoming_renewals": renewals[:5],
    }


@router.patch("/vault/documents/{doc_id}")
async def update_document(doc_id: str, update: DocumentUpdate, user: dict = Depends(get_current_user)):
    """Update a vault document record."""
    doc = await db.vault_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Update category_label if category changed
    if "category" in update_data:
        update_data["category_label"] = DOC_CATEGORIES.get(update_data["category"], "Other")

    await db.vault_documents.update_one({"doc_id": doc_id}, {"$set": update_data})
    return {"message": "Document updated"}


@router.delete("/vault/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Remove a document from vault (and its file content)."""
    doc = await db.vault_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.vault_documents.delete_one({"doc_id": doc_id, "user_id": user["user_id"]})
    return {"message": "Document removed from vault"}


@router.get("/trusts/{trust_id}/vault/summary")
async def vault_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """Dashboard summary for Trust Document Vault."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    total = await db.vault_documents.count_documents({"trust_id": trust_id})

    by_category = []
    pipeline = [
        {"$match": {"trust_id": trust_id}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ]
    async for doc in db.vault_documents.aggregate(pipeline):
        by_category.append({
            "category": doc["_id"],
            "label": DOC_CATEGORIES.get(doc["_id"], "Other"),
            "count": doc["count"],
        })

    missing_critical = []
    critical_cats = ["trust_instrument", "schedule_a", "tax_return", "minutes"]
    present_cats = {c["category"] for c in by_category}
    for cat in critical_cats:
        if cat not in present_cats:
            missing_critical.append({
                "category": cat,
                "label": DOC_CATEGORIES[cat],
                "severity": "high",
                "message": f"No {DOC_CATEGORIES[cat]} found in vault",
            })

    return {
        "trust_id": trust_id,
        "total_documents": total,
        "by_category": by_category,
        "missing_critical": missing_critical,
        "is_complete": len(missing_critical) == 0,
    }