"""
Knowledge Base Retrieval router — compatibility wrapper.

Preserves the original public API of this endpoint (GET /knowledge-retrieval/search
with q, limit, category params and the get_current_user auth dependency) and its
response shape (query, count, results with id/title/category/summary/content_snippet),
but now answers from the consolidated SQLite FTS5 index (services/trust_knowledge.py)
instead of doing a Mongo regex scan.

Build-on-first-use: if the index database does not exist, it is built from the
canonical registry + knowledge markdown before the first query.
"""
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from dependencies import get_current_user

from services import trust_knowledge

router = APIRouter(prefix="/knowledge-retrieval", tags=["knowledge_retrieval"])

# Canonical registry + knowledge source (single source of truth).
# File: .../TrustOffice/projects/TrustOfficeApp/backend/routers/knowledge_retrieval.py
# parents[0]=routers [1]=backend [2]=TrustOfficeApp [3]=projects [4]=TrustOffice (brand root)
BRAND_ROOT = Path(__file__).resolve().parents[4]
REGISTRY_PATH = os.environ.get(
    "TRUST_KNOWLEDGE_REGISTRY",
    str(BRAND_ROOT / "KNOWLEDGE" / "trustoffice-registry.yaml"),
)
KNOWLEDGE_DIR = os.environ.get(
    "TRUST_KNOWLEDGE_DIR",
    str(Path(__file__).resolve().parent.parent / "knowledge"),
)
DB_PATH = os.environ.get(
    "TRUST_KNOWLEDGE_DB",
    str(Path(__file__).resolve().parent.parent / "data" / "trust_knowledge.db"),
)

# Content snippet length (kept for compatibility with the original response shape).
CONTENT_SNIPPET_LENGTH = 500


def _ensure_index() -> str:
    """Return the index db path, building it if it does not yet exist."""
    if not Path(DB_PATH).exists():
        trust_knowledge.build_index(REGISTRY_PATH, KNOWLEDGE_DIR, DB_PATH)
    return DB_PATH


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., min_length=1, description="Free-text query."),
    limit: int = Query(5, ge=1, le=10, description="Maximum number of articles to return (default 5, max 10)."),
    category: Optional[str] = Query(None, description="Optional category filter."),
    user: dict = Depends(get_current_user),
):
    """
    Search the GLOBAL knowledge base for published articles matching `q`.

    Compatibility wrapper: preserves the original endpoint signature and response
    shape, but answers from the consolidated SQLite FTS5 index. Only live, public
    records are surfaced to this public endpoint (private partner offers such as
    WingPoint Annual are never returned).
    """
    db_path = _ensure_index()
    retrieved = trust_knowledge.retrieve(
        q,
        {"db_path": db_path, "limit": limit, "status": "live", "visibility": "public"},
    )

    results = []
    for item in retrieved.get("results", [])[:limit]:
        # Map the new index envelope into the legacy response shape.
        results.append({
            "id": item.get("item_id", ""),
            "title": item.get("title", ""),
            "category": item.get("kind", item.get("category", "")),
            "summary": (item.get("snippet") or "")[:CONTENT_SNIPPET_LENGTH],
            "content_snippet": (item.get("snippet") or "")[:CONTENT_SNIPPET_LENGTH],
        })

    return {"query": q, "count": len(results), "results": results}
