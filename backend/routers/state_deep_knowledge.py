# State deep-knowledge router — surfaces the 10 per-state deep guides
# (backend/KNOWLEDGE/18-state-compliance-<state>.md) that ship with the app
# image via the Dockerfile COPY but were not served by any endpoint.
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user

router = APIRouter(prefix="/state-compliance", tags=["state_deep_knowledge"])

# Same pattern as routers/knowledge_retrieval.py: in Railway this file lives
# at /app/routers/state_deep_knowledge.py, so parent.parent = /app.
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "KNOWLEDGE"

# <filename stem> -> state metadata (canonical state names for the 50 states
# that have deep-knowledge guides; anything else 404s on the detail route).
STATE_META = {
    "arizona": ("AZ", "Arizona"),
    "california": ("CA", "California"),
    "delaware": ("DE", "Delaware"),
    "florida": ("FL", "Florida"),
    "illinois": ("IL", "Illinois"),
    "nevada": ("NV", "Nevada"),
    "new-york": ("NY", "New York"),
    "south-dakota": ("SD", "South Dakota"),
    "texas": ("TX", "Texas"),
    "washington": ("WA", "Washington"),
}

SUMMARY_CHARS = 300


def _slug_for_state_code(state_code: str) -> str:
    """Reverse lookup: 'NY' -> 'new-york'."""
    for slug, (code, _name) in STATE_META.items():
        if code == state_code.upper():
            return slug
    return ""


@lru_cache(maxsize=1)
def _list_knowledge_files() -> tuple:
    """Cached listing of the 18-state-compliance-*.md guides."""
    if not KNOWLEDGE_DIR.exists():
        return ()
    return tuple(sorted(KNOWLEDGE_DIR.glob("18-state-compliance-*.md")))


def _parse_guide(path: Path) -> dict:
    """Extract title (first H1) and a plain-ish summary from a guide file."""
    text = path.read_text(encoding="utf-8")
    h1_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = h1_match.group(1).strip() if h1_match else path.stem

    body = text
    if h1_match:
        body = text[h1_match.end():]
    summary = re.sub(r"^#+\s+.*$", "", body, flags=re.MULTILINE)
    summary = re.sub(r"\s+", " ", summary).strip()

    return {
        "text": text,
        "title": title,
        "summary": summary[:SUMMARY_CHARS],
    }


@router.get("/deep-knowledge")
async def list_deep_knowledge(user: dict = Depends(get_current_user)):
    """List the available per-state deep-knowledge guides, sorted by state_name."""
    items = []
    for path in _list_knowledge_files():
        slug = path.stem.replace("18-state-compliance-", "", 1)
        meta = STATE_META.get(slug)
        if not meta:
            continue
        state_code, state_name = meta
        parsed = _parse_guide(path)
        items.append({
            "id": path.stem,
            "state_code": state_code,
            "state_name": state_name,
            "title": parsed["title"],
            "summary": parsed["summary"],
        })
    items.sort(key=lambda i: i["state_name"])
    return items


@router.get("/deep-knowledge/{state_code}")
async def get_deep_knowledge(state_code: str, user: dict = Depends(get_current_user)):
    """Full markdown for one state's deep-knowledge guide; 404 if not covered."""
    slug = _slug_for_state_code(state_code)
    if not slug:
        raise HTTPException(status_code=404, detail="State not covered")

    path = KNOWLEDGE_DIR / f"18-state-compliance-{slug}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="State not covered")

    _code, state_name = STATE_META[slug]
    parsed = _parse_guide(path)
    return {
        "id": path.stem,
        "state_code": state_code.upper(),
        "state_name": state_name,
        "title": parsed["title"],
        "markdown": parsed["text"],
    }