# Expenses router — CRUD for trust expense records
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid

from database import db
from dependencies import get_current_user, require_write_access
from ledger_sync import auto_write_ledger_transaction

router = APIRouter(tags=["expenses"])


# ==================== EXPENSES CRUD ====================

@router.get("/expenses")
async def get_expenses(
    trust_id: str = Query(..., description="Trust ID to fetch expenses for"),
    user: dict = Depends(get_current_user)
):
    """Get all expenses for a trust"""
    expenses = await db.expenses.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("date", -1).to_list(10000)
    return expenses


@router.post("/expenses")
async def create_expense(
    data: dict,
    user: dict = Depends(require_write_access)
):
    """Create a new expense record"""
    trust_id = data.get("trust_id")
    if not trust_id:
        raise HTTPException(status_code=400, detail="trust_id is required")

    # Verify trust ownership
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Validate amount
    raw_amount = data.get("amount", 0)
    try:
        amount = float(raw_amount)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="amount must be a valid number")
    if amount < 0:
        raise HTTPException(status_code=400, detail="amount must not be negative")

    # Validate status if provided
    valid_statuses = {"review", "approved", "rejected", "pending"}
    status = data.get("status", "review")
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(valid_statuses))}")

    expense_id = f"exp_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    expense_doc = {
        "expense_id": expense_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "date": data.get("date", now),
        "amount": amount,
        "payee": data.get("payee", ""),
        "category": data.get("category", ""),
        "notes": data.get("notes") or "",
        "status": status,
        "created_at": now,
    }

    await db.expenses.insert_one(expense_doc)
    expense_doc.pop("_id", None)

    # Auto-write to ledger if expense is created as approved
    if status == "approved":
        await auto_write_ledger_transaction(
            trust_id=trust_id,
            user_id=user["user_id"],
            amount=amount,
            date=expense_doc.get("date", now),
            governance_classification="Operational Expense",
            purpose_memo=f"Expense — {expense_doc.get('payee', '')} ({expense_doc.get('category', 'Uncategorized')})" + (f" — {expense_doc.get('notes', '')}" if expense_doc.get('notes') else ""),
        )

    return expense_doc


@router.put("/expenses/{expense_id}")
async def update_expense(
    expense_id: str,
    status: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    user: dict = Depends(require_write_access)
):
    """Update an expense record (e.g., change status).

    Status can be passed either as a query parameter (?status=approved) or
    in the JSON body ({"status": "approved"}).
    """
    expense = await db.expenses.find_one(
        {"expense_id": expense_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    # Build update fields from the request body and/or query params
    update_fields = {}
    if data:
        for field in ("date", "amount", "payee", "category", "notes", "status"):
            if field in data:
                update_fields[field] = data[field]

    # Query param status takes effect if body didn't include it
    if status and "status" not in update_fields:
        update_fields["status"] = status

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Track if status changed to "approved" for ledger sync
    old_status = expense.get("status", "")
    new_status = update_fields.get("status", old_status)
    status_changed_to_approved = old_status != "approved" and new_status == "approved"

    await db.expenses.update_one(
        {"expense_id": expense_id, "user_id": user["user_id"]},
        {"$set": update_fields}
    )

    updated = await db.expenses.find_one(
        {"expense_id": expense_id, "user_id": user["user_id"]},
        {"_id": 0}
    )

    # Auto-write to ledger when expense transitions to "approved"
    if status_changed_to_approved and updated:
        await auto_write_ledger_transaction(
            trust_id=updated.get("trust_id", ""),
            user_id=user["user_id"],
            amount=updated.get("amount", 0),
            date=updated.get("date", datetime.now(timezone.utc).isoformat()),
            governance_classification="Operational Expense",
            purpose_memo=f"Expense — {updated.get('payee', '')} ({updated.get('category', 'Uncategorized')})" + (f" — {updated.get('notes', '')}" if updated.get('notes') else ""),
        )

    return updated


@router.delete("/expenses/{expense_id}")
async def delete_expense(
    expense_id: str,
    user: dict = Depends(require_write_access)
):
    """Delete an expense record"""
    expense = await db.expenses.find_one(
        {"expense_id": expense_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    await db.expenses.delete_one(
        {"expense_id": expense_id, "user_id": user["user_id"]}
    )
    return {"deleted": True, "expense_id": expense_id}