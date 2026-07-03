# Entities router - handles entity and relationship management
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import List
import uuid

from database import db
from dependencies import get_current_user, require_write_access, auto_update_onboarding
from models import EntityCreate, EntityResponse, EntityRelationshipCreate, EntityRelationshipResponse

router = APIRouter(tags=["entities"])


# ==================== ENTITY CRUD ENDPOINTS ====================

@router.post("/entities", response_model=EntityResponse)
async def create_entity(entity: EntityCreate, user: dict = Depends(require_write_access)):
    """Create a new entity"""
    trust = await db.trusts.find_one({"trust_id": entity.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    entity_doc = {
        "entity_id": entity_id,
        "user_id": user["user_id"],
        **entity.model_dump(),
        "entity_type": entity.entity_type.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.entities.insert_one(entity_doc)
    await auto_update_onboarding(user["user_id"], entity.trust_id)
    
    return EntityResponse(**entity_doc)


@router.get("/entities", response_model=List[EntityResponse])
async def get_entities(trust_id: str, user: dict = Depends(get_current_user)):
    """Get all entities for a trust"""
    entities = await db.entities.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(100)
    
    return [EntityResponse(**e) for e in entities]


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(entity_id: str, user: dict = Depends(get_current_user)):
    """Get a single entity by ID"""
    entity = await db.entities.find_one(
        {"entity_id": entity_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found. It may have been deleted. Please refresh the page and try again.")
    
    return EntityResponse(**entity)


@router.patch("/entities/{entity_id}", response_model=EntityResponse)
async def update_entity(entity_id: str, updates: dict, user: dict = Depends(require_write_access)):
    """Update an entity"""
    entity = await db.entities.find_one(
        {"entity_id": entity_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found. It may have been deleted. Please refresh the page and try again.")
    
    # Filter only allowed fields
    allowed_fields = [
        "name", "legal_name", "formation_date", "governing_law", "ein",
        "trustee_names", "beneficiary_standard", "article_ref_distribution",
        "article_ref_compensation", "article_ref_amendment", "oversight_required",
        "member_names", "manager_names", "article_ref_authority", "article_ref_profit_distribution"
    ]
    update_data = {k: v for k, v in updates.items() if k in allowed_fields}
    
    if update_data:
        await db.entities.update_one({"entity_id": entity_id}, {"$set": update_data})
    
    updated = await db.entities.find_one({"entity_id": entity_id}, {"_id": 0})
    return EntityResponse(**updated)


@router.delete("/entities/{entity_id}")
async def delete_entity(entity_id: str, user: dict = Depends(require_write_access)):
    """Delete an entity and its relationships"""
    result = await db.entities.delete_one({"entity_id": entity_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entity not found. It may have been already deleted. Please refresh the page and try again.")
    
    # Delete related relationships
    await db.entity_relationships.delete_many({"$or": [
        {"parent_entity_id": entity_id},
        {"child_entity_id": entity_id}
    ]})
    
    return {"message": "Entity deleted"}


# ==================== ENTITY RELATIONSHIP ENDPOINTS ====================

@router.post("/entity-relationships", response_model=EntityRelationshipResponse)
async def create_relationship(rel: EntityRelationshipCreate, user: dict = Depends(require_write_access)):
    """Create an entity relationship"""
    rel_id = f"rel_{uuid.uuid4().hex[:12]}"
    rel_doc = {
        "relationship_id": rel_id,
        "user_id": user["user_id"],
        **rel.model_dump(),
        "relationship_type": rel.relationship_type.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.entity_relationships.insert_one(rel_doc)
    
    return EntityRelationshipResponse(**rel_doc)


@router.get("/entity-relationships", response_model=List[EntityRelationshipResponse])
async def get_relationships(trust_id: str, user: dict = Depends(get_current_user)):
    """Get all entity relationships for a trust"""
    rels = await db.entity_relationships.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(100)
    
    return [EntityRelationshipResponse(**r) for r in rels]


@router.delete("/entity-relationships/{relationship_id}")
async def delete_relationship(relationship_id: str, user: dict = Depends(require_write_access)):
    """Delete an entity relationship"""
    result = await db.entity_relationships.delete_one({
        "relationship_id": relationship_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Relationship not found. It may have been already deleted. Please refresh the page and try again.")
    
    return {"message": "Relationship deleted"}
