"""
Knowledge Base / Resource Hub router — centralized educational content for trust administrators.

Feature 3.12 (P3 priority).
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import re

from database import db
from dependencies import get_current_user

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# ==================== CONSTANTS ====================

CATEGORIES = [
    "trust_basics",
    "compliance",
    "tax",
    "distributions",
    "compensation",
    "governance",
    "structures",
    "onboarding",
    "glossary",
    "best_practices",
]

CATEGORY_LABELS = {
    "trust_basics": "Trust Basics",
    "compliance": "Compliance",
    "tax": "Tax",
    "distributions": "Distributions",
    "compensation": "Compensation",
    "governance": "Governance",
    "structures": "Structures",
    "onboarding": "Onboarding",
    "glossary": "Glossary",
    "best_practices": "Best Practices",
}


def _slugify(text: str) -> str:
    """Generate a URL-safe slug from a title."""
    s = text.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[-\s]+', '-', s)
    return s[:80].rstrip('-')


# ==================== SCHEMAS ====================

class KnowledgeArticleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: str = Field(...)
    content: str = Field(..., min_length=1)
    summary: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = Field(None)
    published: bool = True

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(CATEGORIES)}")
        return v


class KnowledgeArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    published: Optional[bool] = None

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        if v is not None and v not in CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(CATEGORIES)}")
        return v


class KnowledgeArticleResponse(BaseModel):
    id: str
    title: str
    slug: str
    category: str
    content: str
    summary: Optional[str]
    author: str
    tags: List[str]
    published: bool
    views: int
    created_at: str
    updated_at: str


# ==================== HELPERS ====================

async def _require_admin(user: dict) -> dict:
    """Ensure the current user has admin privileges."""
    if not user.get("is_admin", False) and user.get("email", "").lower() != "contact@trustoffice.app":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


async def _get_article_or_404(article_id: str) -> dict:
    """Fetch an article by ID or raise 404."""
    article = await db.knowledge_articles.find_one({"id": article_id})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    return article


def _serialize_article(article: dict) -> dict:
    """Convert MongoDB document to API response format."""
    return {
        "id": article["id"],
        "title": article["title"],
        "slug": article["slug"],
        "category": article["category"],
        "content": article["content"],
        "summary": article.get("summary"),
        "author": article.get("author", ""),
        "tags": article.get("tags", []),
        "published": article.get("published", True),
        "views": article.get("views", 0),
        "created_at": article.get("created_at", ""),
        "updated_at": article.get("updated_at", ""),
    }


# ==================== ENDPOINTS ====================

@router.get("/categories")
async def list_categories():
    """Return the list of available knowledge base categories."""
    return {
        "categories": [
            {"id": c, "label": CATEGORY_LABELS.get(c, c)} for c in CATEGORIES
        ]
    }


@router.get("", response_model=List[KnowledgeArticleResponse])
async def list_articles(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search title/summary/tags"),
    published_only: bool = Query(True, description="Only show published articles"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_user),
):
    """List knowledge base articles with pagination, search, and category filter."""
    query = {}
    if published_only:
        query["published"] = True
    if category:
        if category not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"Invalid category. Valid: {', '.join(CATEGORIES)}")
        query["category"] = category
    if search:
        search_lower = search.lower()
        query["$or"] = [
            {"title": {"$regex": re.escape(search_lower), "$options": "i"}},
            {"summary": {"$regex": re.escape(search_lower), "$options": "i"}},
            {"tags": {"$in": [t for t in [search_lower] if t]}},
        ]

    skip = (page - 1) * limit
    # Get total count separately
    total = await db.knowledge_articles.count_documents(query)
    articles = await db.knowledge_articles.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)

    return {
        "articles": [_serialize_article(a) for a in articles],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1,
            "has_next": skip + limit < total,
            "has_prev": page > 1,
        },
    }


@router.get("/{article_id}", response_model=KnowledgeArticleResponse)
async def get_article(
    article_id: str,
    user: dict = Depends(get_current_user),
):
    """Get a single knowledge article by ID. Increments view count."""
    article = await _get_article_or_404(article_id)

    # Increment views
    await db.knowledge_articles.update_one(
        {"id": article_id},
        {"$inc": {"views": 1}}
    )

    return _serialize_article(article)


@router.post("", response_model=KnowledgeArticleResponse)
async def create_article(
    body: KnowledgeArticleCreate,
    user: dict = Depends(get_current_user),
):
    """Create a new knowledge article. Admin only."""
    await _require_admin(user)

    now = datetime.now(timezone.utc).isoformat()
    article_id = f"ka_{uuid.uuid4().hex[:12]}"
    slug = _slugify(body.title)

    # Ensure unique slug
    existing = await db.knowledge_articles.find_one({"slug": slug})
    if existing:
        slug = f"{slug}-{article_id[-6:]}"

    article = {
        "id": article_id,
        "title": body.title.strip(),
        "slug": slug,
        "category": body.category,
        "content": body.content,
        "summary": body.summary or "",
        "author": user.get("name", user.get("email", "")),
        "tags": body.tags or [],
        "published": body.published,
        "views": 0,
        "created_at": now,
        "updated_at": now,
    }

    await db.knowledge_articles.insert_one(article)
    return _serialize_article(article)


@router.patch("/{article_id}", response_model=KnowledgeArticleResponse)
async def update_article(
    article_id: str,
    body: KnowledgeArticleUpdate,
    user: dict = Depends(get_current_user),
):
    """Update an existing knowledge article. Admin only."""
    await _require_admin(user)
    await _get_article_or_404(article_id)

    now = datetime.now(timezone.utc).isoformat()
    update_data = {"updated_at": now}

    if body.title is not None:
        update_data["title"] = body.title.strip()
        update_data["slug"] = _slugify(body.title)
    if body.category is not None:
        update_data["category"] = body.category
    if body.content is not None:
        update_data["content"] = body.content
    if body.summary is not None:
        update_data["summary"] = body.summary
    if body.tags is not None:
        update_data["tags"] = body.tags
    if body.published is not None:
        update_data["published"] = body.published

    await db.knowledge_articles.update_one(
        {"id": article_id},
        {"$set": update_data}
    )

    updated = await _get_article_or_404(article_id)
    return _serialize_article(updated)


@router.delete("/{article_id}")
async def delete_article(
    article_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a knowledge article. Admin only."""
    await _require_admin(user)
    await _get_article_or_404(article_id)

    await db.knowledge_articles.delete_one({"id": article_id})
    return {"success": True, "message": "Article deleted successfully."}