# Trusts router - handles trust CRUD operations
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List
import uuid

from database import db
from dependencies import get_current_user, create_initial_governance_tasks
from models import TrustCreate, TrustUpdate, TrustResponse

router = APIRouter(prefix="/trusts", tags=["trusts"])


@router.post("", response_model=TrustResponse)
async def create_trust(trust: TrustCreate, user: dict = Depends(get_current_user)):
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"
    trust_doc = {
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "name": trust.name,
        "trust_type": trust.trust_type.value,
        "jurisdiction": trust.jurisdiction,
        "benevolence_enabled": False,
        "tax_status": "private",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.trusts.insert_one(trust_doc)
    await create_initial_governance_tasks(trust_id, user["user_id"])
    return TrustResponse(**{k: v for k, v in trust_doc.items() if k != "_id"})


@router.get("", response_model=List[TrustResponse])
async def get_trusts(user: dict = Depends(get_current_user)):
    trusts = await db.trusts.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    return [TrustResponse(**t) for t in trusts]


@router.get("/{trust_id}", response_model=TrustResponse)
async def get_trust(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    return TrustResponse(**trust)


@router.put("/{trust_id}", response_model=TrustResponse)
async def update_trust(trust_id: str, update: TrustUpdate, user: dict = Depends(get_current_user)):
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    if "trust_type" in update_dict:
        update_dict["trust_type"] = update_dict["trust_type"].value
    
    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": update_dict}
    )
    trust = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0})
    return TrustResponse(**trust)


@router.delete("/{trust_id}")
async def delete_trust(trust_id: str, user: dict = Depends(get_current_user)):
    result = await db.trusts.delete_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Cascade delete related data
    await db.entities.delete_many({"trust_id": trust_id})
    await db.entity_relationships.delete_many({"trust_id": trust_id})
    await db.governance_tasks.delete_many({"trust_id": trust_id})
    await db.minutes_records.delete_many({"trust_id": trust_id})
    await db.distribution_records.delete_many({"trust_id": trust_id})
    
    return {"message": "Trust deleted"}
