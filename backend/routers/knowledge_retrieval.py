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
from database import db

from services import trust_knowledge

router = APIRouter(prefix="/knowledge-retrieval", tags=["knowledge_retrieval"])

# Canonical registry + knowledge source (single source of truth).
# In Railway this file lives at /app/routers/knowledge_retrieval.py, so
# parents[0]=routers [1]=app. The repository root is not a brand monorepo
# checkout in the deployed image; keep the path calculation within the app.
BRAND_ROOT = Path(__file__).resolve().parents[1]
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
    shape, but answers from the consolidated SQLite FTS5 index.

    AUDIENCE ALLOWLIST (WingPoint isolation, 2026-10-30): this is a POSITIVE
    gate now. The authenticated caller's trust grants knowledge audiences;
    grants come only from a WP-provisioned trust in the caller's own account.
    No grant → universal-audience documents only (fail closed). The legacy
    negative filter (visibility!='public') plus the internal:true bypass are
    gone — a WP-tier document can only surface when the caller's own trust
    context grants the wingpoint audience.
    """
    db_path = _ensure_index()

    # Resolve the audience grant from the caller's OWN account: their
    # WingPoint-provisioned trust(s) grant the wingpoint audience. This is a
    # single indexed query on user_id — never request-derived, never
    # client-controlled.
    allowed_audiences: list = []
    try:
        wp_trust = await db.trusts.find_one(
            {
                "user_id": user["user_id"],
                "$or": [{"source": "wingpoint"}, {"wingpoint_ref": {"$exists": True, "$ne": None}}],
            },
            {"_id": 0, "trust_id": 1},
        )
        if wp_trust:
            allowed_audiences = ["wingpoint"]
    except Exception:
        allowed_audiences = []  # fail closed on lookup failure

    retrieved = trust_knowledge.retrieve(
        q,
        {
            "db_path": db_path,
            "limit": limit,
            "status": "live",
            "visibility": "public",
            "allowed_audiences": allowed_audiences,
        },
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
