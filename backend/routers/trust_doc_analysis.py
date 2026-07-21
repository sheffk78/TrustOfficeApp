"""
Trust Document Analysis API — endpoints for retrieving and triggering
trust document intelligence extraction.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import logging
from typing import Optional
import asyncio

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trust_doc_analysis"])


@router.get("/trusts/{trust_id}/document-analysis")
async def get_analysis(trust_id: str, user: dict = Depends(get_current_user)):
    """Get the latest completed trust document analysis for a trust."""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Try to find a complete analysis
    analysis = await db.trust_document_analysis.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"], "status": "complete"},
        {"_id": 0},
        sort=[("created_at", -1)]
    )

    if analysis:
        return {
            "status": "complete",
            "extracted_fields": analysis.get("extracted_fields", {}),
            "vault_document_id": analysis.get("vault_document_id"),
            "created_at": analysis.get("created_at"),
        }

    # Check if there's a pending/analyzing one
    pending = await db.trust_document_analysis.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"], "status": {"$in": ["pending", "analyzing"]}},
        {"_id": 0, "status": 1, "created_at": 1},
        sort=[("created_at", -1)]
    )
    if pending:
        return {
            "status": pending["status"],
            "extracted_fields": None,
            "created_at": pending.get("created_at"),
        }

    # Check if there's a failed one (so frontend can show retry)
    failed = await db.trust_document_analysis.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"], "status": "failed"},
        {"_id": 0, "status": 1, "error_message": 1, "created_at": 1},
        sort=[("created_at", -1)]
    )
    if failed:
        return {
            "status": "failed",
            "error_message": failed.get("error_message"),
            "extracted_fields": None,
            "created_at": failed.get("created_at"),
        }

    return {"status": "none", "extracted_fields": None}


@router.get("/trusts/{trust_id}/document-analysis/status")
async def get_analysis_status(
    trust_id: str,
    doc_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Lightweight status check for polling. Filters by doc_id if provided."""
    # Verify trust ownership
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    query = {"trust_id": trust_id}
    if doc_id:
        query["vault_document_id"] = doc_id

    analysis = await db.trust_document_analysis.find_one(
        query,
        {"_id": 0, "status": 1, "error_message": 1, "vault_document_id": 1},
        sort=[("created_at", -1)]
    )
    if not analysis:
        return {"status": "none"}
    return {
        "status": analysis["status"],
        "error_message": analysis.get("error_message"),
        "vault_document_id": analysis.get("vault_document_id"),
    }


@router.get("/trusts/{trust_id}/vault/analysis-status")
async def get_vault_analysis_status(trust_id: str, user: dict = Depends(get_current_user)):
    """Combined vault + analysis status for onboarding polling.
    Returns vault document existence and analysis status/fields in one call."""
    # Verify trust ownership
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Check for trust instrument in vault
    doc = await db.vault_documents.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"], "category": {"$in": ["trust_instrument", "amendment"]}},
        sort=[("created_at", -1)]
    )

    if not doc:
        return {"vault_status": "empty", "analysis_status": "none", "extracted_fields": None, "doc_id": None}

    # Get completed analysis
    analysis = await db.trust_document_analysis.find_one(
        {"trust_id": trust_id, "vault_document_id": doc["doc_id"], "status": "complete"},
        {"_id": 0},
        sort=[("created_at", -1)]
    )

    if analysis:
        return {
            "vault_status": "uploaded",
            "analysis_status": "complete",
            "extracted_fields": analysis.get("extracted_fields", {}),
            "doc_id": doc["doc_id"]
        }

    # Check for pending/analyzing
    pending = await db.trust_document_analysis.find_one(
        {"trust_id": trust_id, "vault_document_id": doc["doc_id"], "status": {"$in": ["pending", "analyzing"]}},
        {"_id": 0, "status": 1},
        sort=[("created_at", -1)]
    )

    if pending:
        return {"vault_status": "uploaded", "analysis_status": pending["status"], "extracted_fields": None, "doc_id": doc["doc_id"]}

    # Check for failed
    failed = await db.trust_document_analysis.find_one(
        {"trust_id": trust_id, "vault_document_id": doc["doc_id"], "status": "failed"},
        {"_id": 0, "status": 1, "error_message": 1},
        sort=[("created_at", -1)]
    )

    if failed:
        return {"vault_status": "uploaded", "analysis_status": "failed", "error_message": failed.get("error_message"), "extracted_fields": None, "doc_id": doc["doc_id"]}

    return {"vault_status": "uploaded", "analysis_status": "none", "extracted_fields": None, "doc_id": doc["doc_id"]}


@router.post("/trusts/{trust_id}/document-analysis/reanalyze")
async def reanalyze(trust_id: str, user: dict = Depends(get_current_user)):
    """
    Re-trigger analysis from the existing trust instrument in the vault.
    Used by the "Re-analyze" button in the UI, or by users who want to
    retry after a failure.
    """
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Find the most recent trust instrument in the vault with file content
    doc = await db.vault_documents.find_one(
        {
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "category": {"$in": ["trust_instrument", "amendment"]},
            "file_content": {"$exists": True, "$ne": None},
        },
        sort=[("created_at", -1)]
    )

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="No trust instrument found in vault. Please upload your trust document first."
        )

    file_content = doc.get("file_content")
    if not file_content:
        raise HTTPException(
            status_code=400,
            detail="Trust instrument has no file content. The document may be a reference-only entry."
        )

    is_amendment = doc.get("category") == "amendment"

    # Trigger analysis async (non-blocking)
    from trust_doc_analyzer import analyze_trust_document
    asyncio.create_task(
        analyze_trust_document(
            trust_id, user["user_id"], doc["doc_id"], file_content,
            is_amendment=is_amendment
        )
    )

    return {
        "message": "Re-analysis started",
        "status": "pending",
        "doc_id": doc["doc_id"],
    }