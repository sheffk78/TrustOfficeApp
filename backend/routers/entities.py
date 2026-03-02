# Entities router - handles entity CRUD and relationships
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List
import uuid

from database import db
from dependencies import get_current_user
from models import EntityCreate, EntityResponse, EntityRelationshipCreate, EntityRelationshipResponse

router = APIRouter(tags=["entities"])


@router.post("/entities", response_model=EntityResponse)
async def create_entity(entity: EntityCreate, user: dict = Depends(get_current_user)):
    entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    entity_doc = {
        "entity_id": entity_id,
        "user_id": user["user_id"],
        **entity.model_dump(),
        "entity_type": entity.entity_type.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.entities.insert_one(entity_doc)
    return EntityResponse(**{k: v for k, v in entity_doc.items() if k != "_id"})


@router.get("/entities", response_model=List[EntityResponse])
async def get_entities(trust_id: str, user: dict = Depends(get_current_user)):
    entities = await db.entities.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    return [EntityResponse(**e) for e in entities]


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(entity_id: str, user: dict = Depends(get_current_user)):
    entity = await db.entities.find_one(
        {"entity_id": entity_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return EntityResponse(**entity)


@router.patch("/entities/{entity_id}", response_model=EntityResponse)
async def update_entity(entity_id: str, updates: dict, user: dict = Depends(get_current_user)):
    existing = await db.entities.find_one(
        {"entity_id": entity_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Filter out None values and _id
    update_fields = {k: v for k, v in updates.items() if v is not None and k != "_id"}
    
    if update_fields:
        await db.entities.update_one(
            {"entity_id": entity_id},
            {"$set": update_fields}
        )
    
    updated = await db.entities.find_one({"entity_id": entity_id}, {"_id": 0})
    return EntityResponse(**updated)


@router.delete("/entities/{entity_id}")
async def delete_entity(entity_id: str, user: dict = Depends(get_current_user)):
    result = await db.entities.delete_one(
        {"entity_id": entity_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    await db.entity_relationships.delete_many({
        "$or": [
            {"parent_entity_id": entity_id},
            {"child_entity_id": entity_id}
        ]
    })
    
    return {"message": "Entity deleted"}


# Entity Relationships
@router.post("/entity-relationships", response_model=EntityRelationshipResponse)
async def create_relationship(rel: EntityRelationshipCreate, user: dict = Depends(get_current_user)):
    rel_id = f"rel_{uuid.uuid4().hex[:12]}"
    rel_doc = {
        "relationship_id": rel_id,
        "user_id": user["user_id"],
        **rel.model_dump(),
        "relationship_type": rel.relationship_type.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.entity_relationships.insert_one(rel_doc)
    return EntityRelationshipResponse(**{k: v for k, v in rel_doc.items() if k != "_id"})


@router.get("/entity-relationships", response_model=List[EntityRelationshipResponse])
async def get_relationships(trust_id: str, user: dict = Depends(get_current_user)):
    rels = await db.entity_relationships.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    return [EntityRelationshipResponse(**r) for r in rels]


@router.delete("/entity-relationships/{relationship_id}")
async def delete_relationship(relationship_id: str, user: dict = Depends(get_current_user)):
    result = await db.entity_relationships.delete_one(
        {"relationship_id": relationship_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return {"message": "Relationship deleted"}
