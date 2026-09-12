"""Account summary router — GET /account/exit-summary (Delta 1, 2026-09-12).

Drives the cancel-flow modal: cloud backup connection status + last backup
time (from cloud_backup data), document/vault counts, and subscription state
(subscriptions.py patterns). Read-only; no writes.
"""
import logging

from fastapi import APIRouter, Depends

from database import db
from dependencies import get_current_user
from models import ExitSummaryResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["account_summary"])


@router.get("/account/exit-summary", response_model=ExitSummaryResponse)
async def exit_summary(user: dict = Depends(get_current_user)):
    """Everything the cancel-flow modal needs in one read.

    backup:      cloud backup connection status + last backup time
                 (cloud_backup_connections — the same source /backup/status reads)
    counts:      document + vault-item counts for this account
    subscription: status + access_until (current_period_end — when access ends)
    """
    user_id = user["user_id"]

    # --- Backup status (reuse cloud_backup.py data source) ---
    conn = await db.cloud_backup_connections.find_one(
        {"user_id": user_id, "is_active": True},
        {"_id": 0, "provider": 1, "last_backup_at": 1, "last_backup_status": 1},
    )
    backup = {
        "connected": bool(conn),
        "last_backup_at": (conn or {}).get("last_backup_at"),
    }

    # --- Counts (documents = vault files with content; vault_items = all records) ---
    documents = await db.vault_documents.count_documents({
        "user_id": user_id,
        "file_content": {"$ne": None},
    })
    vault_items = await db.vault_documents.count_documents({"user_id": user_id})
    counts = {"documents": documents, "vault_items": vault_items}

    # --- Subscription state (reuse subscriptions.py source of truth) ---
    from dependencies import get_subscription_state
    state = await get_subscription_state(user_id)
    subscription = {
        "status": state.status,
        "access_until": state.current_period_end,
    }

    return ExitSummaryResponse(backup=backup, counts=counts, subscription=subscription)