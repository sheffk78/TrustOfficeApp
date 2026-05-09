# Document Vault router — trust document organization and reference tracking
# NO file upload (no S3). Users store files externally and reference them here.
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Optional
import uuid

from database import db
from dependencies import get_current_user

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


@router.post("/trusts/{trust_id}/vault/documents")
async def add_document(trust_id: str, doc: dict, user: dict = Depends(get_current_user)):
    """Add a document reference to the vault."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "doc_id": f"doc_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "title": doc["title"],
        "category": doc.get("category", "other"),
        "category_label": DOC_CATEGORIES.get(doc.get("category", "other"), "Other"),
        "date": doc.get("date"),
        "description": doc.get("description"),
        "storage_provider": doc.get("storage_provider", "google_drive"),
        "storage_url": doc.get("storage_url"),     # external link
        "storage_path": doc.get("storage_path"),   # path or identifier
        "file_name": doc.get("file_name"),
        "file_size": doc.get("file_size"),
        "tags": doc.get("tags", []),
        "expiration_date": doc.get("expiration_date"),
        "needs_renewal": doc.get("needs_renewal", False),
        "tags": doc.get("tags", []),
        "created_at": now,
        "updated_at": now,
    }
    await db.vault_documents.insert_one(record)
    return {"doc_id": record["doc_id"], "message": "Document added to vault"}


@router.get("/trusts/{trust_id}/vault/documents")
async def list_documents(
    trust_id: str,
    category: Optional[str] = None,
    search: Optional[str] = None,
    provider: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List vault documents with filtering."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    query = {"trust_id": trust_id}
    if category:
        query["category"] = category
    if provider:
        query["storage_provider"] = provider
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    docs = await db.vault_documents.find(query, {"_id": 0}).sort("date", -1).to_list(200)

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
async def update_document(doc_id: str, update: dict, user: dict = Depends(get_current_user)):
    """Update a vault document record."""
    doc = await db.vault_documents.find_one({"doc_id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    trust = await db.trusts.find_one({"trust_id": doc["trust_id"], "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    update_data = {k: v for k, v in update.items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.vault_documents.update_one({"doc_id": doc_id}, {"$set": update_data})
    return {"message": "Document updated"}


@router.delete("/vault/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    """Remove a document reference from vault."""
    doc = await db.vault_documents.find_one({"doc_id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    trust = await db.trusts.find_one({"trust_id": doc["trust_id"], "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    await db.vault_documents.delete_one({"doc_id": doc_id})
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
