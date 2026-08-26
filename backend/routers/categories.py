"""
Categories router - Enum values for dropdowns and selects
Migrated from server.py
"""
from fastapi import APIRouter

from models import (
    PurposeClassification, TaskType, MinutesType, 
    EntityType, RelationshipType
)

router = APIRouter(tags=["categories"])

# Trust expense categories — used by the Expenses page dropdown
EXPENSE_CATEGORIES = [
    "Administration",
    "Professional Fees",
    "Accounting / Legal",
    "Insurance",
    "Property / Maintenance",
    "Taxes",
    "Travel",
    "Marketing",
    "Technology",
    "Utilities",
    "Bank Fees",
    "Investment Management",
    "Education",
    "Healthcare",
    "Charitable / Benevolence",
    "Other",
]


@router.get("/categories")
async def get_categories():
    """Get all category/enum values for forms and dropdowns"""
    return {
        "purpose_classifications": [c.value for c in PurposeClassification],
        "task_types": [t.value for t in TaskType],
        "minutes_types": [m.value for m in MinutesType],
        "entity_types": [e.value for e in EntityType],
        "relationship_types": [r.value for r in RelationshipType],
        "expense_categories": EXPENSE_CATEGORIES,
    }
