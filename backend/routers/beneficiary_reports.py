"""
Beneficiary reports router — PDF report generation, listing, download, deletion.

Phase 4 (Enhanced Features) of the TrustOffice plan.
"""
import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from database import db
from dependencies import get_current_user, require_write_access
from services import beneficiary_report_service

router = APIRouter(tags=["beneficiary-reports"])


# ==================== HELPERS ====================

async def _require_owned_trust(trust_id: str, user: dict) -> dict:
    trust = await beneficiary_report_service.get_owned_trust(
        trust_id, user["user_id"]
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return trust


# ==================== ENDPOINTS ====================

@router.post("/beneficiary-reports/{trust_id}/generate", status_code=201)
async def generate_report(
    trust_id: str,
    user: dict = Depends(require_write_access),
):
    """Generate a new PDF beneficiary report for a trust."""
    await _require_owned_trust(trust_id, user)
    try:
        result = await beneficiary_report_service.generate_beneficiary_report(
            trust_id, user["user_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.get("/beneficiary-reports/{trust_id}")
async def list_reports(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    """List all generated beneficiary reports for a trust."""
    await _require_owned_trust(trust_id, user)
    try:
        return await beneficiary_report_service.list_reports(
            trust_id, user["user_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/beneficiary-reports/{trust_id}/{report_id}/download")
async def download_report(
    trust_id: str,
    report_id: str,
    user: dict = Depends(get_current_user),
):
    """Download a specific beneficiary report PDF."""
    await _require_owned_trust(trust_id, user)

    # Look up by report_id or doc_id
    doc = await db.vault_documents.find_one(
        {
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "category": "beneficiary_report",
            "$or": [{"report_id": report_id}, {"doc_id": report_id}],
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Report not found.")

    file_content = doc.get("file_content")
    if not file_content:
        raise HTTPException(status_code=400, detail="Report file content not available.")

    trust_name = doc.get("title", "report").split("—")[1].strip() if "—" in doc.get("title", "") else "report"
    date_str = doc.get("date", doc.get("created_at", ""))[:10].replace("-", "")
    safe_name = re.sub(r"[^\w\s-]", "", trust_name).strip().replace(" ", "_")
    filename = f"beneficiary_report_{safe_name}_{date_str}.pdf"
    safe_filename = re.sub(r'[\r\n"\\]', "", filename)
    encoded_filename = quote(safe_filename, safe="")

    return Response(
        content=file_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{safe_filename}\""
                f"; filename*=UTF-8''{encoded_filename}"
            )
        },
    )


@router.delete("/beneficiary-reports/{report_id}", status_code=204)
async def delete_report(
    report_id: str,
    user: dict = Depends(require_write_access),
):
    """Delete a beneficiary report from the vault."""
    result = await db.vault_documents.delete_one(
        {
            "user_id": user["user_id"],
            "category": "beneficiary_report",
            "$or": [{"report_id": report_id}, {"doc_id": report_id}],
        }
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Report not found.")
    return None
