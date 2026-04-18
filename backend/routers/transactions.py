# Transactions router - Trust Transaction Ledger for structural separation tracking
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, require_write_access
from models import (
    TransactionCreate, TransactionUpdate, TransactionResponse,
    TransactionSummary, CsvImportRequest, BulkClassifyRequest,
    GovernanceClassification
)

router = APIRouter(tags=["transactions"])


# ==================== TRANSACTION CRUD ====================

@router.post("/transactions", response_model=TransactionResponse)
async def create_transaction(txn: TransactionCreate, user: dict = Depends(require_write_access)):
    """Create a new transaction in the ledger"""
    # Verify trust ownership
    trust = await db.trusts.find_one({"trust_id": txn.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Verify entity belongs to trust
    entity = await db.entities.find_one(
        {"entity_id": txn.entity_id, "trust_id": txn.trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Require other_note when classification is "Other"
    if txn.governance_classification == GovernanceClassification.other and not txn.other_note.strip():
        raise HTTPException(status_code=400, detail="A note is required when classification is 'Other'")

    txn_id = f"txn_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    txn_doc = {
        "transaction_id": txn_id,
        "trust_id": txn.trust_id,
        "entity_id": txn.entity_id,
        "user_id": user["user_id"],
        "date": txn.date,
        "amount": txn.amount,
        "direction": txn.direction.value,
        "source_account": txn.source_account,
        "destination_account": txn.destination_account,
        "governance_classification": txn.governance_classification.value,
        "purpose_memo": txn.purpose_memo,
        "other_note": txn.other_note,
        "linked_distribution_id": txn.linked_distribution_id,
        "linked_compensation_payment_id": txn.linked_compensation_payment_id,
        "document_name": txn.document_name,
        "import_batch_id": None,
        "created_at": now,
        "updated_at": None
    }

    await db.transactions.insert_one(txn_doc)

    # Add audit log entry
    await db.transaction_audit_log.insert_one({
        "audit_id": f"txn_audit_{uuid.uuid4().hex[:12]}",
        "transaction_id": txn_id,
        "user_id": user["user_id"],
        "action": "created",
        "changes": txn_doc,
        "timestamp": now
    })

    txn_doc["entity_name"] = entity.get("name", "")
    return TransactionResponse(**txn_doc)


@router.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(
    trust_id: str,
    entity_id: Optional[str] = None,
    classification: Optional[str] = None,
    direction: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    unclassified_only: bool = False,
    limit: int = 200,
    skip: int = 0,
    user: dict = Depends(get_current_user)
):
    """Get transactions for a trust, optionally filtered by entity"""
    query = {"trust_id": trust_id, "user_id": user["user_id"]}

    if entity_id:
        query["entity_id"] = entity_id
    if classification:
        query["governance_classification"] = classification
    if direction:
        query["direction"] = direction
    if date_from:
        query.setdefault("date", {})["$gte"] = date_from
    if date_to:
        query.setdefault("date", {})["$lte"] = date_to
    if unclassified_only:
        query["governance_classification"] = {"$exists": False}

    txns = await db.transactions.find(query, {"_id": 0}).sort("date", -1).skip(skip).limit(limit).to_list(limit)

    # Enrich with entity names
    entity_ids = list(set(t["entity_id"] for t in txns))
    entities = await db.entities.find(
        {"entity_id": {"$in": entity_ids}, "user_id": user["user_id"]},
        {"_id": 0, "entity_id": 1, "name": 1}
    ).to_list(100)
    entity_map = {e["entity_id"]: e["name"] for e in entities}

    for t in txns:
        t["entity_name"] = entity_map.get(t["entity_id"], "")

    return [TransactionResponse(**t) for t in txns]


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(transaction_id: str, updates: TransactionUpdate, user: dict = Depends(require_write_access)):
    """Update a transaction — all changes are audit-logged"""
    txn = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    update_data = {}
    for field, value in updates.model_dump(exclude_unset=True).items():
        if hasattr(value, 'value'):
            update_data[field] = value.value
        else:
            update_data[field] = value

    # Validate other_note when switching to "Other" classification
    new_class = update_data.get("governance_classification", txn.get("governance_classification"))
    new_note = update_data.get("other_note", txn.get("other_note", ""))
    if new_class == "Other" and not new_note.strip():
        raise HTTPException(status_code=400, detail="A note is required when classification is 'Other'")

    if update_data:
        now = datetime.now(timezone.utc).isoformat()
        update_data["updated_at"] = now
        await db.transactions.update_one({"transaction_id": transaction_id}, {"$set": update_data})

        # Immutable audit log
        await db.transaction_audit_log.insert_one({
            "audit_id": f"txn_audit_{uuid.uuid4().hex[:12]}",
            "transaction_id": transaction_id,
            "user_id": user["user_id"],
            "action": "updated",
            "changes": update_data,
            "previous": {k: txn.get(k) for k in update_data.keys()},
            "timestamp": now
        })

    updated = await db.transactions.find_one({"transaction_id": transaction_id}, {"_id": 0})
    entity = await db.entities.find_one({"entity_id": updated["entity_id"]}, {"_id": 0, "name": 1})
    updated["entity_name"] = entity.get("name", "") if entity else ""
    return TransactionResponse(**updated)


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str, user: dict = Depends(require_write_access)):
    """Delete a transaction (audit log entry preserved)"""
    txn = await db.transactions.find_one(
        {"transaction_id": transaction_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    await db.transactions.delete_one({"transaction_id": transaction_id})

    # Log deletion in audit trail (immutable)
    await db.transaction_audit_log.insert_one({
        "audit_id": f"txn_audit_{uuid.uuid4().hex[:12]}",
        "transaction_id": transaction_id,
        "user_id": user["user_id"],
        "action": "deleted",
        "changes": txn,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {"message": "Transaction deleted"}


# ==================== CSV IMPORT ====================

@router.post("/transactions/import", response_model=List[TransactionResponse])
async def import_transactions(req: CsvImportRequest, user: dict = Depends(require_write_access)):
    """Import multiple transactions from a CSV upload (pre-parsed by frontend)"""
    trust = await db.trusts.find_one({"trust_id": req.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    entity = await db.entities.find_one(
        {"entity_id": req.entity_id, "trust_id": req.trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if not req.rows:
        raise HTTPException(status_code=400, detail="No rows to import")

    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    created_txns = []

    for row in req.rows:
        txn_id = f"txn_{uuid.uuid4().hex[:12]}"
        classification = row.governance_classification.value if row.governance_classification else None

        txn_doc = {
            "transaction_id": txn_id,
            "trust_id": req.trust_id,
            "entity_id": req.entity_id,
            "user_id": user["user_id"],
            "date": row.date,
            "amount": row.amount,
            "direction": row.direction.value,
            "source_account": "",
            "destination_account": "",
            "governance_classification": classification or "Other",
            "purpose_memo": row.purpose_memo or row.description,
            "other_note": row.description if not classification else "",
            "linked_distribution_id": None,
            "linked_compensation_payment_id": None,
            "document_name": None,
            "import_batch_id": batch_id,
            "created_at": now,
            "updated_at": None
        }
        created_txns.append(txn_doc)

    if created_txns:
        await db.transactions.insert_many(created_txns)

    for t in created_txns:
        t["entity_name"] = entity.get("name", "")

    return [TransactionResponse(**t) for t in created_txns]


# ==================== BULK CLASSIFY ====================

@router.post("/transactions/bulk-classify")
async def bulk_classify_transactions(req: BulkClassifyRequest, user: dict = Depends(require_write_access)):
    """Bulk-classify multiple transactions with the same governance classification"""
    if not req.transaction_ids:
        raise HTTPException(status_code=400, detail="No transactions selected")

    if req.governance_classification == GovernanceClassification.other and not req.other_note.strip():
        raise HTTPException(status_code=400, detail="A note is required when classification is 'Other'")

    now = datetime.now(timezone.utc).isoformat()
    update_data = {
        "governance_classification": req.governance_classification.value,
        "purpose_memo": req.purpose_memo,
        "other_note": req.other_note,
        "updated_at": now
    }

    result = await db.transactions.update_many(
        {"transaction_id": {"$in": req.transaction_ids}, "user_id": user["user_id"]},
        {"$set": update_data}
    )

    # Audit log for bulk action
    await db.transaction_audit_log.insert_one({
        "audit_id": f"txn_audit_{uuid.uuid4().hex[:12]}",
        "transaction_id": None,
        "user_id": user["user_id"],
        "action": "bulk_classified",
        "changes": {
            "transaction_ids": req.transaction_ids,
            "classification": req.governance_classification.value,
            "purpose_memo": req.purpose_memo
        },
        "timestamp": now
    })

    return {"message": f"{result.modified_count} transactions classified", "modified": result.modified_count}


# ==================== SUMMARY / ANALYTICS ====================

@router.get("/transactions/summary")
async def get_transaction_summary(trust_id: str, days: int = 90, user: dict = Depends(get_current_user)):
    """Get transaction summary per entity for a trust"""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Get all entities for trust
    entities = await db.entities.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0, "entity_id": 1, "name": 1}
    ).to_list(100)

    txns = await db.transactions.find(
        {"trust_id": trust_id, "user_id": user["user_id"], "date": {"$gte": cutoff}},
        {"_id": 0}
    ).to_list(10000)

    # Aggregate per entity
    summaries = []
    for entity in entities:
        eid = entity["entity_id"]
        entity_txns = [t for t in txns if t["entity_id"] == eid]

        total_in = sum(t["amount"] for t in entity_txns if t.get("direction") == "inflow")
        total_out = sum(t["amount"] for t in entity_txns if t.get("direction") == "outflow")

        by_class = {}
        for t in entity_txns:
            cls = t.get("governance_classification", "Unclassified")
            by_class.setdefault(cls, {"inflows": 0, "outflows": 0, "count": 0})
            if t.get("direction") == "inflow":
                by_class[cls]["inflows"] += t["amount"]
            else:
                by_class[cls]["outflows"] += t["amount"]
            by_class[cls]["count"] += 1

        summaries.append({
            "entity_id": eid,
            "entity_name": entity["name"],
            "total_inflows": round(total_in, 2),
            "total_outflows": round(total_out, 2),
            "net_flow": round(total_in - total_out, 2),
            "transaction_count": len(entity_txns),
            "unclassified_count": sum(1 for t in entity_txns if t.get("governance_classification") == "Other"),
            "by_classification": by_class
        })

    return summaries
