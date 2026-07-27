"""
Enhanced exports router — one-click export tools for trust data.

Phase 4 (Enhanced Features) of the TrustOffice plan.
"""
import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from database import db
from dependencies import get_current_user, require_write_access
from services import export_service

router = APIRouter(tags=["exports-enhanced"])


# ==================== HELPERS ====================

async def _require_owned_trust(trust_id: str, user: dict) -> dict:
    trust = await export_service.get_owned_trust(trust_id, user["user_id"])
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return trust


# ==================== REQUEST BODIES ====================

class ExportBody(BaseModel):
    format: str = "json"  # "json" | "zip"


# ==================== TRUST EXPORT ====================

@router.post("/exports/trust/{trust_id}")
async def export_trust(
    trust_id: str,
    body: ExportBody,
    user: dict = Depends(get_current_user),
):
    """Export all trust data as JSON or ZIP."""
    await _require_owned_trust(trust_id, user)
    if body.format not in ("json", "zip"):
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'zip'.")

    try:
        result = await export_service.export_trust_data(
            trust_id, user["user_id"], format=body.format
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if body.format == "zip":
        zip_bytes = result.pop("zip_bytes")
        filename = result.pop("filename")
        safe_filename = re.sub(r'[\r\n"\\]', "", filename)
        encoded_filename = quote(safe_filename, safe="")
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{safe_filename}\""
                    f"; filename*=UTF-8''{encoded_filename}"
                )
            },
        )

    return result


@router.get("/exports/trust/{trust_id}/download")
async def download_last_export(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    """Download the most recent export/archive for a trust as a ZIP."""
    await _require_owned_trust(trust_id, user)

    # Find the most recent archive backup
    doc = await db.vault_documents.find_one(
        {
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "category": "archive_backup",
        },
        sort=[("created_at", -1)],
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="No export found. Create an archive backup first.",
        )

    file_content = doc.get("file_content")
    if not file_content:
        raise HTTPException(status_code=400, detail="Export file content not available.")

    filename = doc.get("file_name", "export.zip")
    safe_filename = re.sub(r'[\r\n"\\]', "", filename)
    encoded_filename = quote(safe_filename, safe="")

    return Response(
        content=file_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{safe_filename}\""
                f"; filename*=UTF-8''{encoded_filename}"
            )
        },
    )


# ==================== CLIENT EXPORT ====================

@router.post("/exports/client/{client_id}")
async def export_client(
    client_id: str,
    body: ExportBody,
    user: dict = Depends(get_current_user),
):
    """Export all client data across trusts as JSON or ZIP."""
    if body.format not in ("json", "zip"):
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'zip'.")

    try:
        result = await export_service.export_client_data(
            client_id, user["user_id"], format=body.format
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if body.format == "zip":
        zip_bytes = result.pop("zip_bytes")
        filename = result.pop("filename")
        safe_filename = re.sub(r'[\r\n"\\]', "", filename)
        encoded_filename = quote(safe_filename, safe="")
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"{safe_filename}\""
                    f"; filename*=UTF-8''{encoded_filename}"
                )
            },
        )

    return result


# ==================== ARCHIVE BACKUP ====================

@router.post("/exports/trust/{trust_id}/archive", status_code=201)
async def create_archive(
    trust_id: str,
    user: dict = Depends(require_write_access),
):
    """Create comprehensive ZIP archive (data + vault files)."""
    await _require_owned_trust(trust_id, user)
    try:
        return await export_service.create_archive_backup(
            trust_id, user["user_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/exports/archive/{archive_id}/download")
async def download_archive(
    archive_id: str,
    user: dict = Depends(get_current_user),
):
    """Download an archive ZIP."""
    doc = await db.vault_documents.find_one(
        {
            "user_id": user["user_id"],
            "category": "archive_backup",
            "$or": [{"archive_id": archive_id}, {"doc_id": archive_id}],
        },
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Archive not found.")

    file_content = doc.get("file_content")
    if not file_content:
        raise HTTPException(status_code=400, detail="Archive file content not available.")

    filename = doc.get("file_name", "archive.zip")
    safe_filename = re.sub(r'[\r\n"\\]', "", filename)
    encoded_filename = quote(safe_filename, safe="")

    return Response(
        content=file_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{safe_filename}\""
                f"; filename*=UTF-8''{encoded_filename}"
            )
        },
    )


@router.get("/exports/trust/{trust_id}/archives")
async def list_archives(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    """List all archive backups for a trust."""
    await _require_owned_trust(trust_id, user)

    docs = await db.vault_documents.find(
        {
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "category": "archive_backup",
        },
        {"_id": 0, "file_content": 0},
    ).sort("created_at", -1).to_list(50)

    trust = await export_service.get_owned_trust(trust_id, user["user_id"])
    trust_name = (trust or {}).get("name", "Unnamed Trust")

    results = []
    for d in docs:
        results.append({
            "archive_id": d.get("archive_id", d["doc_id"]),
            "doc_id": d["doc_id"],
            "created_at": d.get("created_at", ""),
            "trust_name": trust_name,
            "file_size": d.get("file_size", ""),
            "file_size_bytes": d.get("file_size_bytes", 0),
            "description": d.get("description", ""),
        })
    return results
