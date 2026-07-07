"""
Banking router — bank account CRUD and bank statement management.
Bank accounts are tied to trust entities. Statements are linked to vault documents.
"""
import uuid
import re
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from database import db
from dependencies import get_current_user, require_write_access
from models import (
    BankAccountCreate, BankAccountUpdate, BankAccountResponse,
    BankStatementResponse,
)
from routers.compensation import auto_update_onboarding

logger = logging.getLogger(__name__)
router = APIRouter(tags=["banking"])


# ==================== BANK ACCOUNT ENDPOINTS ====================

@router.post("/trusts/{trust_id}/bank-accounts", response_model=BankAccountResponse)
async def create_bank_account(
    trust_id: str,
    account: BankAccountCreate,
    user: dict = Depends(require_write_access),
):
    """Create a bank account for a trust entity."""
    if account.trust_id != trust_id:
        raise HTTPException(status_code=400, detail="Trust ID mismatch")

    # Verify trust belongs to user
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Verify entity belongs to this trust
    entity = await db.entities.find_one(
        {"entity_id": account.entity_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0, "name": 1}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found in this trust")

    account_id = f"bac_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "account_id": account_id,
        "trust_id": trust_id,
        "entity_id": account.entity_id,
        "user_id": user["user_id"],
        "nickname": account.nickname,
        "institution_name": account.institution_name,
        "account_type": account.account_type.value,
        "last_four": account.last_four,
        "is_archived": False,
        "created_at": now,
        "updated_at": now,
    }

    await db.bank_accounts.insert_one(doc)

    # Auto-update onboarding
    try:
        await auto_update_onboarding(user["user_id"], trust_id)
    except Exception:
        pass

    doc.pop("_id", None)
    return BankAccountResponse(**doc)


@router.get("/trusts/{trust_id}/bank-accounts", response_model=List[BankAccountResponse])
async def list_bank_accounts(
    trust_id: str,
    include_archived: bool = False,
    user: dict = Depends(get_current_user),
):
    """List bank accounts for a trust."""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    if not include_archived:
        query["is_archived"] = {"$ne": True}

    accounts = await db.bank_accounts.find(query, {"_id": 0}).sort("created_at", 1).to_list(100)
    return [BankAccountResponse(**a) for a in accounts]


@router.get("/trusts/{trust_id}/entities/{entity_id}/bank-accounts", response_model=List[BankAccountResponse])
async def list_bank_accounts_by_entity(
    trust_id: str,
    entity_id: str,
    user: dict = Depends(get_current_user),
):
    """List bank accounts for a specific entity within a trust."""
    query = {
        "trust_id": trust_id,
        "entity_id": entity_id,
        "user_id": user["user_id"],
        "is_archived": {"$ne": True},
    }
    accounts = await db.bank_accounts.find(query, {"_id": 0}).sort("created_at", 1).to_list(50)
    return [BankAccountResponse(**a) for a in accounts]


@router.put("/trusts/{trust_id}/bank-accounts/{account_id}", response_model=BankAccountResponse)
async def update_bank_account(
    trust_id: str,
    account_id: str,
    update: BankAccountUpdate,
    user: dict = Depends(require_write_access),
):
    """Update a bank account."""
    update_data = {k: v.value if isinstance(v, Enum) else v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.bank_accounts.update_one(
        {"account_id": account_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": update_data}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found")

    updated = await db.bank_accounts.find_one({"account_id": account_id}, {"_id": 0})
    return BankAccountResponse(**updated)


@router.delete("/trusts/{trust_id}/bank-accounts/{account_id}")
async def archive_bank_account(
    trust_id: str,
    account_id: str,
    user: dict = Depends(require_write_access),
):
    """Archive a bank account (soft delete — preserves statement history)."""
    result = await db.bank_accounts.update_one(
        {"account_id": account_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": {"is_archived": True, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return {"message": "Bank account archived"}


# ==================== BANK STATEMENT ENDPOINTS ====================

@router.get("/trusts/{trust_id}/bank-accounts/{account_id}/statements", response_model=List[BankStatementResponse])
async def list_statements(
    trust_id: str,
    account_id: str,
    user: dict = Depends(get_current_user),
):
    """List bank statements for a specific bank account, ordered by statement period."""
    account = await db.bank_accounts.find_one(
        {"account_id": account_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    statements = await db.bank_statements.find(
        {"account_id": account_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("statement_period_end", -1).to_list(100)

    return [BankStatementResponse(**s) for s in statements]


@router.get("/trusts/{trust_id}/bank-accounts/{account_id}/statements/summary")
async def get_account_summary(
    trust_id: str,
    account_id: str,
    user: dict = Depends(get_current_user),
):
    """Get a summary of an account's statement history including balance trend."""
    account = await db.bank_accounts.find_one(
        {"account_id": account_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    statements = await db.bank_statements.find(
        {
            "account_id": account_id,
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "extraction_status": {"$in": ["completed", "needs_review"]},
        },
        {"_id": 0}
    ).sort("statement_period_end", 1).to_list(100)

    if not statements:
        return {
            "account_id": account_id,
            "statement_count": 0,
            "latest_balance": None,
            "balance_trend": [],
        }

    return {
        "account_id": account_id,
        "statement_count": len(statements),
        "latest_balance": statements[-1].get("ending_balance"),
        "latest_period_end": statements[-1].get("statement_period_end"),
        "balance_trend": [
            {
                "date": s.get("statement_period_end"),
                "balance": s.get("ending_balance"),
            }
            for s in statements if s.get("ending_balance") is not None
        ],
    }


@router.put("/trusts/{trust_id}/bank-statements/{statement_id}")
async def update_statement(
    trust_id: str,
    statement_id: str,
    updates: dict,
    user: dict = Depends(require_write_access),
):
    """Manually correct extracted statement data (trustee review)."""
    allowed_fields = {
        "bank_name", "account_last_four", "statement_period_start",
        "statement_period_end", "beginning_balance", "ending_balance",
        "total_deposits", "total_withdrawals", "extraction_status", "needs_review",
        "account_id",
    }
    update_data = {k: v for k, v in updates.items() if k in allowed_fields}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.bank_statements.update_one(
        {"statement_id": statement_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": update_data}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    updated = await db.bank_statements.find_one({"statement_id": statement_id}, {"_id": 0})
    return BankStatementResponse(**updated)


@router.get("/trusts/{trust_id}/bank-statements")
async def list_all_statements(
    trust_id: str,
    vault_document_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List all bank statements across all accounts for a trust.
    Optionally filter by vault_document_id to find the statement for a specific vault doc.
    """
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    if vault_document_id:
        query["vault_document_id"] = vault_document_id

    statements = await db.bank_statements.find(
        query,
        {"_id": 0}
    ).sort("statement_period_end", -1).to_list(200)

    # Enrich with account nicknames
    account_ids = list(set(s["account_id"] for s in statements if s.get("account_id")))
    accounts = {}
    if account_ids:
        account_docs = await db.bank_accounts.find(
            {"account_id": {"$in": account_ids}}, {"_id": 0, "account_id": 1, "nickname": 1, "institution_name": 1}
        ).to_list(50)
        accounts = {a["account_id"]: a for a in account_docs}

    for s in statements:
        acct = accounts.get(s.get("account_id"), {})
        s["account_nickname"] = acct.get("nickname", "Unknown")
        s["institution_name"] = acct.get("institution_name", "")

    return {"statements": statements, "count": len(statements)}


@router.post("/trusts/{trust_id}/bank-statements/{statement_id}/reextract")
async def reextract_statement(
    trust_id: str,
    statement_id: str,
    user: dict = Depends(require_write_access),
):
    """Retry AI extraction for a bank statement (e.g., after extraction failure)."""
    statement = await db.bank_statements.find_one(
        {"statement_id": statement_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not statement:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    vault_doc = await db.vault_documents.find_one(
        {"doc_id": statement["vault_document_id"]}, {"_id": 0, "file_content": 1}
    )
    if not vault_doc or not vault_doc.get("file_content"):
        raise HTTPException(status_code=400, detail="Source document not available")

    import asyncio
    from trust_doc_analyzer import analyze_bank_statement

    # Update status to pending
    await db.bank_statements.update_one(
        {"statement_id": statement_id},
        {"$set": {"extraction_status": "pending", "extraction_error": None, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    # Fire extraction as background task
    asyncio.create_task(
        analyze_bank_statement(
            trust_id, user["user_id"], statement_id,
            vault_doc["file_content"],
            statement.get("account_id"),
        )
    )

    return {"message": "Re-extraction started", "statement_id": statement_id}


@router.put("/trusts/{trust_id}/bank-statements/{statement_id}/link")
async def link_statement_to_account(
    trust_id: str,
    statement_id: str,
    link: dict,
    user: dict = Depends(require_write_access),
):
    """Link a bank statement to a bank account (trustee selects which account)."""
    account_id = link.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")

    # Verify account belongs to this trust
    account = await db.bank_accounts.find_one(
        {"account_id": account_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0, "last_four": 1}
    )
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found in this trust")

    update_data = {
        "account_id": account_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    # If the extracted last_four matches the account's last_four, clear needs_review
    statement = await db.bank_statements.find_one(
        {"statement_id": statement_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0, "account_last_four": 1, "needs_review": 1}
    )
    if not statement:
        raise HTTPException(status_code=404, detail="Bank statement not found")

    if statement.get("account_last_four") and account.get("last_four"):
        if statement["account_last_four"] == account["last_four"]:
            update_data["needs_review"] = False
            update_data["extraction_status"] = "completed"

    await db.bank_statements.update_one(
        {"statement_id": statement_id, "trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": update_data}
    )

    return {"message": "Statement linked to account", "statement_id": statement_id, "account_id": account_id}


@router.get("/trusts/{trust_id}/bank-accounts/summary")
async def get_trust_banking_summary(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    """Get a trust-level banking summary: account count, total latest balance, balance trend."""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    accounts = await db.bank_accounts.find(
        {"trust_id": trust_id, "user_id": user["user_id"], "is_archived": {"$ne": True}},
        {"_id": 0}
    ).to_list(100)

    account_summaries = []
    total_latest_balance = 0
    accounts_with_balance = 0

    for acct in accounts:
        # Get latest statement for this account
        latest = await db.bank_statements.find_one(
            {
                "account_id": acct["account_id"],
                "trust_id": trust_id,
                "user_id": user["user_id"],
                "extraction_status": {"$in": ["completed", "needs_review"]},
                "ending_balance": {"$ne": None},
            },
            {"_id": 0, "ending_balance": 1, "statement_period_end": 1}
        )
        balance = latest.get("ending_balance") if latest else None
        if balance is not None:
            total_latest_balance += balance
            accounts_with_balance += 1
        account_summaries.append({
            "account_id": acct["account_id"],
            "nickname": acct.get("nickname", "Unknown"),
            "institution_name": acct.get("institution_name", ""),
            "last_four": acct.get("last_four", ""),
            "latest_balance": balance,
            "latest_period_end": latest.get("statement_period_end") if latest else None,
        })

    return {
        "account_count": len(accounts),
        "accounts_with_balance": accounts_with_balance,
        "total_latest_balance": total_latest_balance if accounts_with_balance > 0 else None,
        "accounts": account_summaries,
    }