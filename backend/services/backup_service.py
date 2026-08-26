"""
Core backup service — orchestrates vault document backups to cloud providers.
"""
import logging
import asyncio
from datetime import datetime, timezone

from database import db
from services.backup_providers import get_provider

logger = logging.getLogger(__name__)

# Category folder mapping — converts internal category keys to human-readable folder names
CATEGORY_FOLDER_MAP = {
    "trust_instrument": "Trust-Instruments",
    "amendment": "Amendments",
    "schedule_a": "Schedule-A",
    "minutes": "Minutes",
    "tax_return": "Tax-Returns",
    "k1": "Schedule-K1",
    "ein_letter": "EIN-Letters",
    "irs_determination": "IRS-Determination",
    "financial_statement": "Financial-Statements",
    "appraisal": "Appraisals",
    "notice": "Beneficiary-Notices",
    "insurance": "Insurance",
    "deed": "Deeds",
    "bank_statement": "Bank-Statements",
    "legal_opinion": "Legal-Opinions",
    "court_order": "Court-Orders",
    "other": "Other",
}

MAX_RETRIES = 3
RETRY_DELAYS = [60, 300, 900]  # 1 min, 5 min, 15 min


async def run_scheduled_backups():
    """Run weekly backup for all users with active connections."""
    cursor = db.cloud_backup_connections.find({"is_active": True})
    async for conn in cursor:
        try:
            await backup_user_vault(conn["user_id"], conn)
        except Exception as e:
            logger.error(f"Backup failed for user {conn['user_id']}: {e}")
            await db.cloud_backup_connections.update_one(
                {"_id": conn["_id"]},
                {"$set": {
                    "last_backup_status": "failed",
                    "last_backup_error": str(e),
                    "last_backup_at": datetime.now(timezone.utc).isoformat(),
                }}
            )


async def backup_user_vault(user_id: str, conn: dict):
    """Back up all changed vault documents for a user."""
    provider = get_provider(conn["provider"])

    # Refresh token if needed
    access_token = await provider.refresh_token_if_needed(conn)

    # Ensure backup folder exists
    folder_ref = await provider.ensure_backup_folder(access_token, conn)

    # Store folder ref for future use
    if folder_ref and folder_ref != conn.get("backup_folder_id"):
        await db.cloud_backup_connections.update_one(
            {"_id": conn["_id"]},
            {"$set": {"backup_folder_id": folder_ref}}
        )

    # Mark backup as in progress
    await db.cloud_backup_connections.update_one(
        {"_id": conn["_id"]},
        {"$set": {"last_backup_status": "in_progress", "last_backup_error": None}}
    )

    # Find documents that need backup
    cursor = db.vault_documents.find({
        "user_id": user_id,
        "file_content": {"$ne": None},
        "$or": [
            {"last_backup_at": None},
            {"$expr": {"$gt": ["$updated_at", {"$ifNull": ["$last_backup_at", ""]}]}}
        ]
    })

    backed_up = 0
    failed = 0
    manifest_docs = []

    async for doc in cursor:
        try:
            category = doc.get("category", "other")
            category_folder = CATEGORY_FOLDER_MAP.get(category, "Other")
            file_name = doc.get("file_name", f"{doc['doc_id']}.bin")
            backup_path = f"TrustOffice-Backup/{category_folder}/{file_name}"

            # Upload with retry
            success = await _upload_with_retry(
                provider, access_token, folder_ref, backup_path,
                doc["file_content"],
                doc.get("file_content_type", "application/octet-stream")
            )

            if success:
                now_iso = datetime.now(timezone.utc).isoformat()
                await db.vault_documents.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "last_backup_at": now_iso,
                        "backup_path": backup_path,
                    }}
                )
                manifest_docs.append({
                    "doc_id": doc["doc_id"],
                    "title": doc.get("title", ""),
                    "category": category,
                    "file_name": file_name,
                    "backup_path": backup_path,
                    "backup_date": now_iso,
                })
                backed_up += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Failed to back up doc {doc.get('doc_id')}: {e}")
            failed += 1

    # Update manifest
    manifest = {
        "backup_date": datetime.now(timezone.utc).isoformat(),
        "total_documents": backed_up,
        "documents": manifest_docs,
    }
    try:
        await provider.update_manifest(access_token, folder_ref, manifest)
    except Exception as e:
        logger.warning(f"Manifest upload failed: {e}")

    # Update connection status
    status = "success" if failed == 0 else ("partial" if backed_up > 0 else "failed")
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.cloud_backup_connections.update_one(
        {"_id": conn["_id"]},
        {"$set": {
            "last_backup_at": now_iso,
            "last_backup_status": status,
            "last_backup_error": None if status == "success" else f"{failed} files failed",
            "last_backup_doc_count": backed_up,
            "backup_folder_id": folder_ref,
        }}
    )

    # Send notification
    await _send_backup_notification(user_id, status, backed_up, failed)

    logger.info(f"Backup complete for user {user_id}: {backed_up} backed up, {failed} failed")
    return {"backed_up": backed_up, "failed": failed, "status": status}


async def _upload_with_retry(provider, access_token, folder_ref, path, content, content_type):
    """Upload a file with exponential backoff retry."""
    for attempt in range(MAX_RETRIES):
        try:
            await provider.upload_file(access_token, folder_ref, path, content, content_type)
            return True
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Upload attempt {attempt+1} failed for {path}: {e}. Retrying in {RETRY_DELAYS[attempt]}s")
                await asyncio.sleep(RETRY_DELAYS[attempt])
            else:
                logger.error(f"Upload failed after {MAX_RETRIES} attempts for {path}: {e}")
                return False


async def _send_backup_notification(user_id: str, status: str, backed_up: int, failed: int):
    """Send in-app notification about backup result."""
    if status == "success":
        message = f"Cloud backup complete: {backed_up} document(s) backed up successfully."
    elif status == "partial":
        message = f"Cloud backup partially complete: {backed_up} backed up, {failed} failed. We'll retry failed files next time."
    else:
        message = "Cloud backup failed. We'll retry automatically. Please check your cloud connection in Settings."

    await db.notifications.insert_one({
        "user_id": user_id,
        "type": "backup_status",
        "message": message,
        "status": status,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })