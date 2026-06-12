# Tasks router - handles governance task management
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, require_write_access, get_task_status, auto_update_onboarding
from models import GovernanceTaskCreate, GovernanceTaskResponse

router = APIRouter(tags=["tasks"])


# Checklist templates for each task type
CHECKLIST_TEMPLATES = {
    "annual_review": [
        {"text": "Review trust terms and provisions", "completed": False},
        {"text": "Verify beneficiary information is current", "completed": False},
        {"text": "Review investment performance", "completed": False},
        {"text": "Confirm compliance with state law", "completed": False},
        {"text": "Document meeting minutes", "completed": False},
    ],
    "quarterly_review": [
        {"text": "Review trust account statements", "completed": False},
        {"text": "Verify distributions are documented", "completed": False},
        {"text": "Check insurance coverage", "completed": False},
        {"text": "Review pending transactions", "completed": False},
    ],
    "compensation_review": [
        {"text": "Review current compensation plan", "completed": False},
        {"text": "Compare YTD payments against approved amount", "completed": False},
        {"text": "Document compensation decisions in minutes", "completed": False},
    ],
    "distribution_review": [
        {"text": "Verify trust solvency before distribution", "completed": False},
        {"text": "Confirm distribution authority per trust terms", "completed": False},
        {"text": "Document distribution in minutes", "completed": False},
        {"text": "Send beneficiary notification", "completed": False},
    ],
    "insurance_compliance": [
        {"text": "Verify current insurance policies", "completed": False},
        {"text": "Review coverage adequacy", "completed": False},
        {"text": "Update trust records with policy details", "completed": False},
    ],
    "transaction_review": [
        {"text": "Review all transactions for the period", "completed": False},
        {"text": "Classify any untagged transactions", "completed": False},
        {"text": "Review separation alerts", "completed": False},
        {"text": "Document review findings in minutes", "completed": False},
    ],
    "tax_filing_1041": [
        {"text": "Gather all income and deduction records", "completed": False},
        {"text": "Review estimated tax payments made", "completed": False},
        {"text": "Engage tax preparer/accountant", "completed": False},
        {"text": "Review draft Form 1041", "completed": False},
        {"text": "Sign and file Form 1041", "completed": False},
    ],
    "tax_filing_k1": [
        {"text": "Confirm all beneficiary allocations", "completed": False},
        {"text": "Prepare Schedule K-1 for each beneficiary", "completed": False},
        {"text": "Review K-1 drafts with tax preparer", "completed": False},
        {"text": "Distribute K-1s to beneficiaries", "completed": False},
    ],
}


# ==================== GOVERNANCE TASK ENDPOINTS ====================

@router.post("/tasks", response_model=GovernanceTaskResponse)
async def create_task(task: GovernanceTaskCreate, user: dict = Depends(require_write_access)):
    """Create a new governance task"""
    trust = await db.trusts.find_one({"trust_id": task.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    
    # Determine checklist items
    checklist_items = []
    if task.checklist_items:
        checklist_items = [{"text": item.text, "completed": item.completed} for item in task.checklist_items]
    elif task.task_type.value in CHECKLIST_TEMPLATES:
        checklist_items = [item.copy() for item in CHECKLIST_TEMPLATES[task.task_type.value]]
    
    task_doc = {
        "task_id": task_id,
        "trust_id": task.trust_id,
        "user_id": user["user_id"],
        "task_type": task.task_type.value,
        "due_date": task.due_date,
        "completed_at": None,
        "description": task.description,
        "checklist_items": checklist_items,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.governance_tasks.insert_one(task_doc)
    await auto_update_onboarding(user["user_id"], task.trust_id)
    
    status = get_task_status(task.due_date, None)
    return GovernanceTaskResponse(**task_doc, status=status)


@router.get("/tasks", response_model=List[GovernanceTaskResponse])
async def get_tasks(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Get all tasks, optionally filtered by trust"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    tasks = await db.governance_tasks.find(query, {"_id": 0}).sort("due_date", 1).to_list(1000)
    
    result = []
    for t in tasks:
        status = get_task_status(t["due_date"], t.get("completed_at"))
        t_copy = {k: v for k, v in t.items() if k != "status"}
        # Ensure checklist_items defaults to empty list
        if "checklist_items" not in t_copy:
            t_copy["checklist_items"] = []
        result.append(GovernanceTaskResponse(**t_copy, status=status))
    
    return result


@router.patch("/tasks/{task_id}/complete")
async def complete_task(task_id: str, user: dict = Depends(require_write_access)):
    """Mark a task as complete"""
    task = await db.governance_tasks.find_one(
        {"task_id": task_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    completed_at = datetime.now(timezone.utc).isoformat()
    await db.governance_tasks.update_one(
        {"task_id": task_id},
        {"$set": {"completed_at": completed_at}}
    )
    
    return {"message": "Task completed", "completed_at": completed_at}


@router.patch("/tasks/{task_id}/uncomplete")
async def uncomplete_task(task_id: str, user: dict = Depends(require_write_access)):
    """Mark a task as incomplete"""
    result = await db.governance_tasks.update_one(
        {"task_id": task_id, "user_id": user["user_id"]},
        {"$set": {"completed_at": None}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"message": "Task marked incomplete"}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: dict = Depends(require_write_access)):
    """Delete a task"""
    result = await db.governance_tasks.delete_one({"task_id": task_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"message": "Task deleted"}


@router.patch("/tasks/{task_id}/checklist/{item_index}")
async def update_checklist_item(
    task_id: str,
    item_index: int,
    update: dict,
    user: dict = Depends(require_write_access)
):
    """Update a specific checklist item's completed status"""
    task = await db.governance_tasks.find_one(
        {"task_id": task_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    checklist_items = task.get("checklist_items", [])
    if item_index < 0 or item_index >= len(checklist_items):
        raise HTTPException(status_code=404, detail="Checklist item index out of range")
    
    completed = update.get("completed")
    if completed is None:
        raise HTTPException(status_code=400, detail="completed field is required")
    
    checklist_items[item_index]["completed"] = completed
    
    await db.governance_tasks.update_one(
        {"task_id": task_id},
        {"$set": {"checklist_items": checklist_items}}
    )
    
    # If all checklist items are completed, optionally mark the task as complete
    all_completed = all(item.get("completed", False) for item in checklist_items)
    
    return {
        "message": "Checklist item updated",
        "item_index": item_index,
        "completed": completed,
        "all_completed": all_completed,
        "checklist_items": checklist_items
    }
