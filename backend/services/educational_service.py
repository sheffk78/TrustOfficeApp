"""
Educational service — curated educational resources for trust administration.

Phase 4 (Enhanced Features) of the TrustOffice plan.

Aggregates Trustee 101 course data, WingPoint knowledge base links,
and in-app governance guides based on trust type and health score.
"""
from datetime import datetime, timezone
from typing import List, Optional

from database import db
from routers.courses import CURRICULUM


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_owned_trust(trust_id: str, user_id: str) -> Optional[dict]:
    """Fetch a trust only if owned by this user (mirrors meeting_service pattern)."""
    return await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )


# ==================== STATIC RESOURCE MAPS ====================

# WingPoint knowledge base links mapped by trust type
_WINGPOINT_RESOURCES = {
    "revocable_living": [
        {
            "title": "Revocable Living Trust Guide",
            "description": "Complete guide to administering a revocable living trust, including funding, management, and distribution.",
            "url": "https://wingpoint.com/kb/revocable-living-trust-guide",
            "type": "article",
            "relevance": "trust_type",
        },
        {
            "title": "Successor Trustee Checklist",
            "description": "Step-by-step checklist for successor trustees taking over a revocable living trust.",
            "url": "https://wingpoint.com/kb/successor-trustee-checklist",
            "type": "guide",
            "relevance": "trust_type",
        },
    ],
    "irrevocable": [
        {
            "title": "Irrevocable Trust Administration",
            "description": "Key differences in administering irrevocable trusts — tax filings, distribution standards, and fiduciary duties.",
            "url": "https://wingpoint.com/kb/irrevocable-trust-administration",
            "type": "article",
            "relevance": "trust_type",
        },
        {
            "title": "HEMS Distribution Standard Explained",
            "description": "Understanding Health, Education, Maintenance, and Support distribution standards for irrevocable trusts.",
            "url": "https://wingpoint.com/kb/hems-distribution-standard",
            "type": "guide",
            "relevance": "trust_type",
        },
    ],
    "special_needs": [
        {
            "title": "Special Needs Trust Administration",
            "description": "Administering a special needs trust without jeopardizing government benefits — SSI, Medicaid, and SSDI rules.",
            "url": "https://wingpoint.com/kb/special-needs-trust-guide",
            "type": "article",
            "relevance": "trust_type",
        },
    ],
    "charitable": [
        {
            "title": "Charitable Trust Compliance",
            "description": "Annual compliance requirements for charitable remainder and charitable lead trusts.",
            "url": "https://wingpoint.com/kb/charitable-trust-compliance",
            "type": "article",
            "relevance": "trust_type",
        },
    ],
}

# Default resources for any trust type
_DEFAULT_WINGPOINT_RESOURCES = [
    {
        "title": "Trust Administration Fundamentals",
        "description": "Core concepts every trustee should understand — fiduciary duty, record-keeping, and beneficiary communication.",
        "url": "https://wingpoint.com/kb/trust-administration-fundamentals",
        "type": "article",
        "relevance": "general",
    },
    {
        "title": "Trust Tax Filing Calendar",
        "description": "Key dates and deadlines for trust tax filings including Form 1041 and Schedule K-1.",
        "url": "https://wingpoint.com/kb/trust-tax-calendar",
        "type": "guide",
        "relevance": "general",
    },
]

# Health criterion → educational resource mapping
_HEALTH_RESOURCE_MAP = {
    "Quarterly Minutes": {
        "title": "Meeting Minutes Are Not Optional (Trustee 101, Lesson 3)",
        "description": "Learn why regular minutes are critical for trust governance and how to create them efficiently.",
        "url": "/courses/trustee-101/lesson/3",
        "type": "course",
        "relevance": "health_score",
    },
    "Task Compliance": {
        "title": "Trustee Task Management",
        "description": "Best practices for staying on top of governance tasks and deadlines.",
        "url": "/guides/task-management",
        "type": "guide",
        "relevance": "health_score",
    },
    "Compensation Alignment": {
        "title": "Trustee Compensation Guidelines",
        "description": "How to set and document reasonable trustee compensation that aligns with the trust instrument.",
        "url": "/guides/trustee-compensation",
        "type": "guide",
        "relevance": "health_score",
    },
    "Distribution Documentation": {
        "title": "Documenting Trust Distributions",
        "description": "Proper documentation for trust distributions — HEMS standards, beneficiary receipts, and court-ready records.",
        "url": "/guides/distribution-documentation",
        "type": "guide",
        "relevance": "health_score",
    },
    "Annual Review": {
        "title": "Annual Trust Review Checklist",
        "description": "A comprehensive checklist for conducting and documenting the annual trust review.",
        "url": "/guides/annual-review-checklist",
        "type": "guide",
        "relevance": "health_score",
    },
    "Asset Valuation Freshness": {
        "title": "Asset Valuation Best Practices",
        "description": "When and how to update asset valuations on Schedule A to maintain accurate records.",
        "url": "/guides/asset-valuation",
        "type": "guide",
        "relevance": "health_score",
    },
    "Transaction Classification": {
        "title": "Classifying Trust Transactions",
        "description": "How to properly classify trust income, principal, and expense transactions.",
        "url": "/guides/transaction-classification",
        "type": "guide",
        "relevance": "health_score",
    },
    "Separation Alert Health": {
        "title": "Trust Asset Separation",
        "description": "Why commingling is dangerous and how to maintain proper separation of trust and personal assets.",
        "url": "/guides/asset-separation",
        "type": "guide",
        "relevance": "health_score",
    },
}


async def get_educational_resources(trust_id: str, user_id: str) -> dict:
    """Return curated educational resources relevant to the trust.

    Structure: {courses, articles, guides, recommended}.
    Raises ValueError if trust not found.
    """
    trust = await get_owned_trust(trust_id, user_id)
    if not trust:
        raise ValueError("Trust not found")

    trust_type = trust.get("trust_type", "").lower().replace(" ", "_")

    # --- Courses (Trustee 101) ---
    # Check if user has any course enrollment/lead
    # We look up the user's email from the user record
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    user_email = (user_doc or {}).get("email", "")
    if user_email:
        enrollment = await db.course_leads.find_one(
            {"email": user_email.lower()}, {"_id": 0}
        )
    else:
        enrollment = None

    enrolled = enrollment is not None
    purchased = (enrollment or {}).get("course_purchased", False)

    courses = []
    for lesson in CURRICULUM:
        courses.append({
            "lesson": lesson["lesson"],
            "title": lesson["title"],
            "duration": lesson["duration"],
            "free": lesson["free"],
            "status": lesson["status"],
            "pdf_url": lesson.get("pdf_url"),
            "accessible": lesson["free"] or purchased,
            "enrolled": enrolled,
        })

    # --- WingPoint articles by trust type ---
    articles = _WINGPOINT_RESOURCES.get(trust_type, [])
    if not articles:
        articles = _DEFAULT_WINGPOINT_RESOURCES
    # Always include general resources too
    seen_urls = {a["url"] for a in articles}
    for res in _DEFAULT_WINGPOINT_RESOURCES:
        if res["url"] not in seen_urls:
            articles.append(res)

    # --- In-app guides ---
    guides = [
        {
            "title": "Getting Started with TrustOffice",
            "description": "Set up your trust, add beneficiaries, and configure governance tracking.",
            "url": "/guides/getting-started",
            "type": "guide",
            "relevance": "onboarding",
        },
        {
            "title": "Understanding Your Health Score",
            "description": "How the TrustOffice health score works and what each criterion measures.",
            "url": "/guides/health-score",
            "type": "guide",
            "relevance": "governance",
        },
        {
            "title": "Document Vault Best Practices",
            "description": "Organize trust documents for audit readiness and easy retrieval.",
            "url": "/guides/vault-organization",
            "type": "guide",
            "relevance": "documentation",
        },
    ]

    # --- Recommended (based on health score) ---
    recommended = await get_recommended_resources(trust_id, user_id)

    return {
        "courses": courses,
        "articles": articles,
        "guides": guides,
        "recommended": recommended,
    }


async def get_recommended_resources(trust_id: str, user_id: str) -> list:
    """Recommend educational content based on failing health score criteria.

    Queries the latest health_score_snapshot, finds criteria where
    achieved=False, and maps each to a relevant educational resource.
    """
    # Get latest health score snapshot
    snapshot = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("calculated_at", -1)],
    )

    if not snapshot or not snapshot.get("criteria_breakdown"):
        return []

    recommended = []
    seen_titles = set()

    for criterion in snapshot["criteria_breakdown"]:
        if criterion.get("achieved"):
            continue
        criterion_name = criterion.get("name", "")
        resource = _HEALTH_RESOURCE_MAP.get(criterion_name)
        if resource and resource["title"] not in seen_titles:
            seen_titles.add(resource["title"])
            recommended.append({
                **resource,
                "criterion": criterion_name,
                "points_lost": criterion.get("max_points", 0) - criterion.get("points", 0),
            })

    # Sort by points lost descending (biggest impact first)
    recommended.sort(key=lambda r: r.get("points_lost", 0), reverse=True)
    return recommended
