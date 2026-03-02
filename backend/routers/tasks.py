# Tasks router - handles governance tasks
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from dependencies import get_current_user, get_task_status
from models import GovernanceTaskCreate, GovernanceTaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=GovernanceTaskResponse)
async def create_task(task: GovernanceTaskCreate, user: dict = Depends(get_current_user)):
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task_doc = {
        "task_id": task_id,
        "user_id": user["user_id"],
        "trust_id": task.trust_id,
        "task_type": task.task_type.value,
        "due_date": task.due_date,
        "completed_at": None,
        "description": task.description,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.governance_tasks.insert_one(task_doc)
    
    return GovernanceTaskResponse(
        **{k: v for k, v in task_doc.items() if k != "_id"},
        status=get_task_status(task_doc["due_date"], task_doc["completed_at"])
    )


@router.get("", response_model=List[GovernanceTaskResponse])
async def get_tasks(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    tasks = await db.governance_tasks.find(query, {"_id": 0}).to_list(1000)
    return [
        GovernanceTaskResponse(
            **t,
            status=get_task_status(t["due_date"], t.get("completed_at"))
        )
        for t in tasks
    ]


@router.patch("/{task_id}/complete")
async def complete_task(task_id: str, user: dict = Depends(get_current_user)):
    result = await db.governance_tasks.update_one(
        {"task_id": task_id, "user_id": user["user_id"]},
        {"$set": {"completed_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = await db.governance_tasks.find_one({"task_id": task_id}, {"_id": 0})
    return GovernanceTaskResponse(
        **task,
        status="completed"
    )


@router.patch("/{task_id}/uncomplete")
async def uncomplete_task(task_id: str, user: dict = Depends(get_current_user)):
    await db.governance_tasks.update_one(
        {"task_id": task_id, "user_id": user["user_id"]},
        {"$set": {"completed_at": None}}
    )
    task = await db.governance_tasks.find_one({"task_id": task_id}, {"_id": 0})
    return GovernanceTaskResponse(
        **task,
        status=get_task_status(task["due_date"], None)
    )


@router.delete("/{task_id}")
async def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    result = await db.governance_tasks.delete_one(
        {"task_id": task_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted"}
