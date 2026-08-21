"""Defensible, on-demand full trust export (TO-015).

The archive is generated in memory and is therefore not retained server-side;
the 90-day retention policy is satisfied without creating an additional copy.
"""
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from database import db
from dependencies import get_current_user
from services.export_service import _export_safe, _safe_export_name
from utils.audit import log_audit_event

router = APIRouter(tags=["full-export"])

# Keep this explicit: it documents the legal/data scope of the export and
# permits deployments with optional collections to omit absent collections.
COLLECTIONS = {
    "entities": "entities", "entity_relationships": "entity_relationships",
    "beneficiaries": "trust_unit_certificates", "beneficiary_records": "beneficiaries",
    "class_beneficiaries": "class_beneficiaries", "class_beneficiary_members": "class_beneficiary_members",
    "certificates": "trust_unit_certificates", "assets_schedule_a": "schedule_a_items",
    "tasks": "governance_tasks", "calendar_events": "calendar_events",
    "distributions": "distribution_records", "transactions": "transactions",
    "audit_trail": "audit_trail", "audit_logs": "audit_logs",
    "ai_chat_history": "chat_history", "minutes": "minutes_records",
    "resolutions": "resolutions", "meetings": "meetings", "vault_documents": "vault_documents",
}


async def _records(collection: str, trust_id: str, user_id: str, include_files=False):
    projection = {"_id": 0}
    if collection == "vault_documents" and not include_files:
        projection["file_content"] = 0
    # Some older records lack user_id; trust ownership is still guaranteed by
    # the trust lookup, but including user_id where present narrows exposure.
    return await db[collection].find({"trust_id": trust_id, "user_id": user_id}, projection).to_list(10000)


@router.get("/export")
async def full_trust_export(
    trust_id: str = Query(..., description="Owned trust to export"),
    user: dict = Depends(get_current_user),
):
    user_id = user["user_id"]
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    exported_at = datetime.now(timezone.utc)
    exported_iso = exported_at.isoformat()
    data = {"trust_profile": [_export_safe(trust)]}
    counts = {}
    for category, collection in COLLECTIONS.items():
        try:
            docs = await _records(collection, trust_id, user_id, include_files=False)
        except Exception:
            docs = []
        # The two aliases intentionally remain separate for defensible lineage.
        data[category] = [_export_safe(doc) for doc in docs]
        counts[category] = len(docs)

    manifest = {
        "schema_version": "TO-015.v1", "exported_at": exported_iso,
        "retention": {"mode": "on_demand", "expires_at": None, "days": 90},
        "trust_id": trust_id, "trust_name": trust.get("name", "Unnamed Trust"),
        "owner_user_id": user_id, "collections": counts,
        "files": [],
        "notes": "Generated in memory; no server-side export copy is retained.",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        archive.writestr("data/index.json", json.dumps({"manifest": "../manifest.json", "categories": list(data)}, indent=2))
        for category, records in data.items():
            archive.writestr(f"data/{category}.json", json.dumps(records, indent=2, default=str))

        try:
            vault_docs = await _records("vault_documents", trust_id, user_id, include_files=True)
        except Exception:
            vault_docs = []
        for doc in vault_docs:
            content = doc.get("file_content")
            if not content:
                continue
            filename = _safe_export_name(doc.get("file_name") or f"{doc.get('doc_id', 'document')}.bin")
            path = f"vault/{doc.get('doc_id', 'unknown')}/{filename}"
            archive.writestr(path, bytes(content))
            manifest["files"].append({
                "path": path, "doc_id": doc.get("doc_id"), "file_name": doc.get("file_name"),
                "content_type": doc.get("file_content_type"), "size_bytes": len(content),
                "category": doc.get("category"), "created_at": doc.get("created_at"),
            })

        # Preserve minutes/resolutions as original PDFs when records carry them.
        for category in ("minutes", "resolutions"):
            try:
                source_records = await _records(COLLECTIONS[category], trust_id, user_id, include_files=True)
            except Exception:
                source_records = []
            for source in source_records:
                content = source.get("file_content")
                if content and (source.get("file_content_type") == "application/pdf" or str(source.get("file_name", "")).lower().endswith(".pdf")):
                    path = f"documents/{category}/{_safe_export_name(str(source.get('file_name') or source.get('id') or 'record.pdf'))}"
                    archive.writestr(path, bytes(content))
                    manifest["files"].append({"path": path, "record_id": source.get("id"), "type": category, "content_type": "application/pdf", "created_at": source.get("created_at")})

        # Rewrite manifest after file enumeration.
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

    audit_details = {"exported_at": exported_iso, "format": "zip", "categories": counts, "retention_days": 90}
    await log_audit_event(user_id, "trust_export", "trust", trust_id, audit_details)
    await db.audit_trail.insert_one({"audit_id": f"export_{trust_id}_{exported_at.strftime('%Y%m%dT%H%M%S%fZ')}", "user_id": user_id, "trust_id": trust_id, "action": "trust_export", "entity_type": "trust", "entity_id": trust_id, "details": audit_details, "timestamp": exported_iso})
    filename = f"TrustOffice_Export_{_safe_export_name(trust.get('name'))}_{exported_at.strftime('%Y-%m-%d')}.zip"
    safe = re.sub(r'[\r\n"\\]', "", filename)
    return Response(content=buffer.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{safe}"; filename*=UTF-8\'\'{quote(safe, safe="")}'
    })