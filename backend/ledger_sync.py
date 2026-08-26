"""
Ledger sync — auto-write transactions to the ledger when money moves.

When a distribution is approved, a compensation payment is recorded, or an
expense is approved, this module creates a corresponding outflow transaction in
db.transactions so the ledger stays in sync without manual double-entry.

All writes are idempotent: if a transaction with the same linked_*_id already
exists, the insert is skipped. This makes it safe to call on re-approval or
retries.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
import logging

from database import db

logger = logging.getLogger(__name__)


async def _resolve_default_entity_id(trust_id: str, user_id: str) -> Optional[str]:
    """Find the first entity for a trust so we can attach the ledger entry.

    The transaction ledger requires an entity_id. When auto-creating from a
    distribution/compensation/expense that doesn't carry one, we fall back to
    the first entity registered for the trust.
    """
    entity = await db.entities.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "entity_id": 1}
    )
    return entity["entity_id"] if entity else None


async def _linked_txn_exists(linked_field: str, linked_id: str) -> bool:
    """Check if a transaction already exists for this linked record (idempotency)."""
    existing = await db.transactions.find_one({linked_field: linked_id}, {"_id": 1})
    return existing is not None


async def auto_write_ledger_transaction(
    trust_id: str,
    user_id: str,
    amount: float,
    date: str,
    governance_classification: str,
    purpose_memo: str = "",
    linked_distribution_id: Optional[str] = None,
    linked_compensation_payment_id: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> Optional[str]:
    """Create a ledger transaction from a money event.

    Returns the transaction_id, or None if:
      - No entity can be resolved (the trust has no entities set up)
      - A transaction with the same linked ID already exists (idempotent skip)

    This function NEVER raises — ledger sync is best-effort. If it fails, the
    originating operation (distribution approval, expense creation, etc.) still
    succeeds. The error is logged.
    """
    try:
        # Idempotency check
        if linked_distribution_id:
            if await _linked_txn_exists("linked_distribution_id", linked_distribution_id):
                logger.info(f"Ledger txn already exists for distribution {linked_distribution_id}, skipping")
                return None
        if linked_compensation_payment_id:
            if await _linked_txn_exists("linked_compensation_payment_id", linked_compensation_payment_id):
                logger.info(f"Ledger txn already exists for compensation payment {linked_compensation_payment_id}, skipping")
                return None

        # Resolve entity
        if not entity_id:
            entity_id = await _resolve_default_entity_id(trust_id, user_id)
        if not entity_id:
            logger.warning(f"Cannot auto-write ledger txn: no entity found for trust {trust_id}")
            return None

        txn_id = f"txn_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        txn_doc = {
            "transaction_id": txn_id,
            "trust_id": trust_id,
            "entity_id": entity_id,
            "user_id": user_id,
            "date": date,
            "amount": amount,
            "direction": "outflow",
            "source_account": "",
            "destination_account": "",
            "governance_classification": governance_classification,
            "purpose_memo": purpose_memo,
            "other_note": "",
            "linked_distribution_id": linked_distribution_id,
            "linked_compensation_payment_id": linked_compensation_payment_id,
            "linked_minutes_id": None,
            "document_name": None,
            "import_batch_id": None,
            "created_at": now,
            "updated_at": None,
        }

        await db.transactions.insert_one(txn_doc)

        # Audit log
        await db.transaction_audit_log.insert_one({
            "audit_id": f"txn_audit_{uuid.uuid4().hex[:12]}",
            "transaction_id": txn_id,
            "user_id": user_id,
            "action": "auto_created",
            "changes": txn_doc,
            "timestamp": now,
        })

        # Run alert detection (best-effort)
        try:
            from alert_detection import check_transaction_alerts
            await check_transaction_alerts(txn_doc)
        except Exception as e:
            logger.warning(f"Alert detection failed for auto-txn {txn_id}: {e}")

        logger.info(f"Auto-created ledger txn {txn_id} ({governance_classification}, ${amount})")
        return txn_id

    except Exception as e:
        logger.exception(f"Failed to auto-write ledger transaction: {e}")
        return None