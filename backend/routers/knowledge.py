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
import json
import asyncio
import logging

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)

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


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class KnowledgeArticleListResponse(BaseModel):
    articles: List[KnowledgeArticleResponse]
    pagination: PaginationMeta


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


@router.get("", response_model=KnowledgeArticleListResponse)
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


# ==================== MARKETING SITE SYNC ====================

MARKETING_BASE = "https://trustoffice.app"

# Map marketing-site categories → app knowledge base categories
CATEGORY_MAP = {
    "fiduciary duty": "trust_basics",
    "compliance": "compliance",
    "compliance | accounting": "compliance",
    "governance": "governance",
    "trust administration": "trust_basics",
    "trust technology": "best_practices",
    "software": "best_practices",
    "tax": "tax",
    "distributions": "distributions",
    "compensation": "compensation",
    "onboarding": "onboarding",
    "structures": "structures",
}


def _map_category(marketing_cat: str) -> str:
    """Map a marketing-site category string to an app category."""
    if not marketing_cat:
        return "trust_basics"
    key = marketing_cat.lower().strip()
    if key in CATEGORY_MAP:
        return CATEGORY_MAP[key]
    # Try partial match
    for mk, ak in CATEGORY_MAP.items():
        if mk in key or key in mk:
            return ak
    return "trust_basics"


def _html_to_markdown(html_content: str) -> str:
    """Convert simple HTML article content to Markdown."""
    soup = BeautifulSoup(html_content, "html.parser")

    lines = []

    def process_element(el, depth=0):
        if isinstance(el, NavigableString):
            text = str(el).strip()
            if text:
                lines.append(text)
            return

        if not isinstance(el, Tag):
            return

        tag = el.name

        # Skip non-content elements
        if tag in ("script", "style", "nav", "footer", "header", "form", "button"):
            return

        if tag == "h1":
            lines.append(f"\n# {el.get_text(strip=True)}\n")
        elif tag == "h2":
            lines.append(f"\n## {el.get_text(strip=True)}\n")
        elif tag == "h3":
            lines.append(f"\n### {el.get_text(strip=True)}\n")
        elif tag == "h4":
            lines.append(f"\n#### {el.get_text(strip=True)}\n")
        elif tag == "p":
            lines.append(f"\n{el.get_text(strip=True)}\n")
        elif tag == "ul":
            lines.append("")
            for li in el.find_all("li", recursive=False):
                lines.append(f"- {li.get_text(strip=True)}")
            lines.append("")
        elif tag == "ol":
            lines.append("")
            for i, li in enumerate(el.find_all("li", recursive=False), 1):
                lines.append(f"{i}. {li.get_text(strip=True)}")
            lines.append("")
        elif tag == "blockquote":
            lines.append("")
            for bq_line in el.get_text(strip=True).split("\n"):
                lines.append(f"> {bq_line}")
            lines.append("")
        elif tag == "strong" or tag == "b":
            lines.append(f"**{el.get_text(strip=True)}**")
        elif tag == "em" or tag == "i":
            lines.append(f"*{el.get_text(strip=True)}*")
        elif tag == "a":
            href = el.get("href", "")
            text = el.get_text(strip=True)
            if href and text:
                lines.append(f"[{text}]({href})")
            elif text:
                lines.append(text)
        elif tag == "br":
            lines.append("")
        elif tag == "hr":
            lines.append("\n---\n")
        elif tag in ("div", "section", "article", "span"):
            for child in el.children:
                process_element(child, depth + 1)
        else:
            text = el.get_text(strip=True)
            if text:
                lines.append(text)

    for child in soup.children:
        process_element(child)

    # Clean up excessive blank lines
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a page with timeout and retry."""
    for attempt in range(3):
        try:
            resp = await client.get(url, timeout=15.0)
            if resp.status_code == 200:
                return resp.text
            logger.warning(f"Fetch {url} returned {resp.status_code} (attempt {attempt+1})")
        except Exception as e:
            logger.warning(f"Fetch {url} failed: {e} (attempt {attempt+1})")
        if attempt < 2:
            await asyncio.sleep(1)
    return ""


async def _extract_article_from_page(html: str, url: str) -> dict | None:
    """Extract article metadata and content from a marketing-site page."""
    soup = BeautifulSoup(html, "html.parser")

    # Extract JSON-LD — BlogPosting for blog, Article for resource guides
    title = ""
    date_published = ""
    description = ""
    category = ""
    word_count = 0

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            script_text = script.string or ""
            data = json.loads(script_text)
            if isinstance(data, dict) and data.get("@type") in ("BlogPosting", "Article"):
                title = data.get("headline", "")
                date_published = data.get("datePublished", "")
                description = data.get("description", "")
                word_count = data.get("wordCount", 0)
                break
        except (json.JSONDecodeError, TypeError):
            continue

    # Extract category from the badge in the header (blog posts only)
    badge_span = soup.find("span", class_=re.compile(r"bg-gold/10.*text-navy"))
    if badge_span:
        category = badge_span.get_text(strip=True)

    # If no JSON-LD, try to get title from h1
    if not title:
        main = soup.find("main", id="main-content")
        if main:
            h1 = main.find("h1")
            if h1:
                title = h1.get_text(strip=True)

    if not title:
        return None

    # Extract article content from main-content
    main = soup.find("main", id="main-content")
    if not main:
        return None

    # Blog posts have <article> tags; resource pages use <section> tags
    article_tag = main.find("article")
    if article_tag:
        content_element = article_tag
    else:
        # Resource pages: collect all sections, then filter out CTAs
        # Create a wrapper from all sections' content
        sections = main.find_all("section")
        if not sections:
            # Fallback: try max-w-4xl div
            content_div = main.find("div", class_=re.compile(r"max-w-4xl"))
            if content_div:
                content_element = content_div
            else:
                return None
        else:
            # Build a composite element from sections
            from bs4 import BeautifulSoup as _BS
            wrapper = _BS("<div></div>", "html.parser").div
            for s in sections:
                # Skip sections that are primarily CTA/capture forms
                if s.find(class_=re.compile(r"capture|lead-capture|cta|newsletter|subscribe")):
                    continue
                # Skip sections with CTA-style headings
                h2 = s.find("h2")
                if h2:
                    h2_text = h2.get_text(strip=True).lower()
                    if any(kw in h2_text for kw in [
                        "ready to", "get started", "subscribe", "sign up",
                        "try trust", "simplify your", "document your",
                    ]):
                        continue
                # Skip "Related Resources" sections
                if h2 and "related" in h2.get_text(strip=True).lower():
                    continue
                # Copy section content into wrapper
                for child in list(s.children):
                    wrapper.append(child.__copy__())
            content_element = wrapper

    # Strip out capture forms, CTAs, and other non-article content
    for el in content_element.find_all(class_=re.compile(r"capture|lead-capture|btn-|cta|newsletter|subscribe")):
        el.decompose()
    for el in content_element.find_all(["form", "script", "style"]):
        el.decompose()

    content_md = _html_to_markdown(str(content_element))

    if not content_md or len(content_md) < 50:
        return None

    # Use description as summary if available
    summary = description or content_md[:200].rsplit(" ", 1)[0] + "…"

    # Generate slug from URL
    path = url.replace(MARKETING_BASE, "").strip("/")
    slug = path.rstrip("/").split("/")[-1] if path else _slugify(title)

    # Map category
    app_category = _map_category(category)

    return {
        "title": title,
        "slug": slug,
        "category": app_category,
        "content": content_md,
        "summary": summary,
        "source_url": url,
        "date_published": date_published,
        "marketing_category": category,
        "word_count": word_count,
    }


async def _discover_article_urls(client: httpx.AsyncClient) -> tuple[list[str], list[str]]:
    """Discover all blog and resource article URLs from the sitemap."""
    sitemap_xml = await _fetch_page(client, f"{MARKETING_BASE}/sitemap.xml")

    blog_urls = []
    resource_urls = []

    # Extract all URLs from sitemap
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap_xml)

    # Skip utility pages (exact match, not prefix — so /blog/ doesn't skip /blog/post-slug/)
    skip_exact = {
        "/terms-of-service", "/privacy-policy", "/dmca-policy", "/security",
        "/faq", "/contact", "/about", "/features", "/pricing", "/how-it-works",
        "/get-started", "/for-professionals", "/advisors", "/book-a-call",
        "/resources", "/blog", "/trust-governance-offer", "/trust-governance-system",
        "/fiduciary-assessment", "/wingpoint", "/trust-administration-service",
        "/trustee-101",
    }

    # Skip pages by prefix (catches /compare/ sub-pages)
    skip_prefix = {
        "/compare/",
    }

    for url in urls:
        path = url.replace(MARKETING_BASE, "").rstrip("/")
        # Skip root and utility pages
        if not path or path in skip_exact or any(path.startswith(sp) for sp in skip_prefix):
            continue
        if path.startswith("/blog/"):
            blog_urls.append(url.rstrip("/"))
        else:
            # Resource/guide pages
            resource_urls.append(url.rstrip("/"))

    return blog_urls, resource_urls


@router.post("/sync")
async def sync_from_marketing_site(
    user: dict = Depends(get_current_user),
):
    """
    Sync articles from the marketing site (trustoffice.app) into the knowledge base.
    Admin only. Discovers all blog posts + resource guides, extracts content,
    and upserts into MongoDB using the source URL as the unique key.
    """
    await _require_admin(user)

    results = {
        "discovered": 0,
        "synced": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "articles": [],
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Discover URLs
        blog_urls, resource_urls = await _discover_article_urls(client)
        all_urls = blog_urls + resource_urls
        results["discovered"] = len(all_urls)

        logger.info(f"Knowledge sync: discovered {len(blog_urls)} blog + {len(resource_urls)} resource URLs")

        # Fetch and process pages concurrently (limit to 5 at a time)
        semaphore = asyncio.Semaphore(5)

        async def process_url(url: str):
            async with semaphore:
                html = await _fetch_page(client, url)
                if not html:
                    results["errors"].append(f"Failed to fetch: {url}")
                    return None

                article_data = await _extract_article_from_page(html, url)
                if not article_data:
                    results["errors"].append(f"No article content found: {url}")
                    return None
                return article_data

        tasks = [process_url(url) for url in all_urls]
        articles_data = await asyncio.gather(*tasks, return_exceptions=True)

    # Upsert into MongoDB
    now = datetime.now(timezone.utc).isoformat()

    for result_item in articles_data:
        if isinstance(result_item, Exception):
            results["errors"].append(str(result_item))
            continue
        if result_item is None:
            results["skipped"] += 1
            continue

        article = result_item  # type: dict

        try:
            # Check if article with this source_url already exists
            existing = await db.knowledge_articles.find_one({
                "$or": [
                    {"source_url": article["source_url"]},
                    {"slug": article["slug"]},
                ]
            })

            if existing:
                # Update existing article
                update_data = {
                    "title": article["title"],
                    "category": article["category"],
                    "content": article["content"],
                    "summary": article["summary"],
                    "marketing_category": article["marketing_category"],
                    "source_url": article["source_url"],
                    "updated_at": now,
                    "synced_at": now,
                }
                await db.knowledge_articles.update_one(
                    {"id": existing["id"]},
                    {"$set": update_data}
                )
                results["updated"] += 1
                results["articles"].append({
                    "title": article["title"],
                    "action": "updated",
                    "slug": article["slug"],
                })
            else:
                # Create new article
                article_id = f"ka_{uuid.uuid4().hex[:12]}"
                article_doc = {
                    "id": article_id,
                    "title": article["title"],
                    "slug": article["slug"],
                    "category": article["category"],
                    "content": article["content"],
                    "summary": article["summary"],
                    "author": "Kenneth Kohler",
                    "tags": [],
                    "published": True,
                    "views": 0,
                    "created_at": article["date_published"] or now,
                    "updated_at": now,
                    "synced_at": now,
                    "source_url": article["source_url"],
                    "marketing_category": article["marketing_category"],
                }
                await db.knowledge_articles.insert_one(article_doc)
                results["created"] += 1
                results["articles"].append({
                    "title": article["title"],
                    "action": "created",
                    "slug": article["slug"],
                })

            results["synced"] += 1
        except Exception as e:
            results["errors"].append(f"DB error for {article.get('title', 'unknown')}: {str(e)}")

    logger.info(
        f"Knowledge sync complete: {results['synced']} synced "
        f"({results['created']} created, {results['updated']} updated, "
        f"{results['skipped']} skipped, {len(results['errors'])} errors)"
    )

    return results