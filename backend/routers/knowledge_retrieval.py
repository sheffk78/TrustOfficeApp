"""
Knowledge Base Retrieval router — read-only search of the GLOBAL knowledge base
for support agents grounding their replies. This is the retrieval source agents
call to fetch relevant published articles from the knowledge_articles
collection (product docs, FAQs, policy). It does NOT surface per-contact data.

Pair with the customer-memory layer (contacts, support_interactions,
contact_profile_summary) for the full agent context pipeline.
"""
from typing import List, Optional
import re

from fastapi import APIRouter, Depends, Query

from database import db
from dependencies import get_current_user

router = APIRouter(prefix="/knowledge-retrieval", tags=["knowledge_retrieval"])

# Maximum content snippet length returned in compact search results.
CONTENT_SNIPPET_LENGTH = 500


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., min_length=1, description="Free-text query matched against title, summary, tags, and content (case-insensitive)."),
    limit: int = Query(5, ge=1, le=10, description="Maximum number of articles to return (default 5, max 10)."),
    category: Optional[str] = Query(None, description="Optional category filter (e.g. compliance, tax)."),
    user: dict = Depends(get_current_user),
):
    """
    Search the GLOBAL knowledge base for published articles matching `q`.

    Returns a compact list of {id, title, category, summary, content_snippet}
    where content_snippet is the first ~500 characters of the article content.
    Only published articles are returned. This endpoint is read-only and does
    not increment view counts — it is optimized for retrieval, not browsing.
    """
    # Escape user input for safe regex matching (case-insensitive).
    pattern = re.escape(q)

    match_clauses = [
        {"title": {"$regex": pattern, "$options": "i"}},
        {"summary": {"$regex": pattern, "$options": "i"}},
        {"content": {"$regex": pattern, "$options": "i"}},
        {"tags": {"$regex": pattern, "$options": "i"}},
    ]

    query = {
        "published": True,
        "$or": match_clauses,
    }
    if category:
        query["category"] = category

    cursor = db.knowledge_articles.find(query, {
        "id": 1,
        "title": 1,
        "category": 1,
        "summary": 1,
        "content": 1,
        "_id": 0,
    }).limit(limit)

    results: List[dict] = []
    async for article in cursor:
        content = article.get("content", "") or ""
        summary = article.get("summary", "") or ""
        results.append({
            "id": article.get("id", ""),
            "title": article.get("title", ""),
            "category": article.get("category", ""),
            "summary": summary,
            "content_snippet": content[:CONTENT_SNIPPET_LENGTH],
        })

    return {"query": q, "count": len(results), "results": results}