# Tasks router - handles governance task management
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, require_write_access, get_task_status, auto_update_onboarding
from models import GovernanceTaskCreate, GovernanceTaskResponse

router = APIRouter(tags=["tasks"])


# ==================== GOVERNANCE TASK ENDPOINTS ====================

@router.post("/tasks", response_model=GovernanceTaskResponse)
async def create_task(task: GovernanceTaskCreate, user: dict = Depends(require_write_access)):
    """Create a new governance task"""
    trust = await db.trusts.find_one({"trust_id": task.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task_doc = {
        "task_id": task_id,
        "trust_id": task.trust_id,
        "user_id": user["user_id"],
        "task_type": task.task_type.value,
        "due_date": task.due_date,
        "completed_at": None,
        "description": task.description,
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
        result.append(GovernanceTaskResponse(**t, status=status))
    
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
