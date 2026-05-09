# Binder router — cover sheet data endpoint
from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from typing import List, Optional

from database import db
from dependencies import get_current_user
from pydantic import BaseModel

router = APIRouter(tags=["binder"])


# Trust type enum value → human-readable label
TRUST_TYPE_LABELS = {
    "family": "Family Trust",
    "charitable": "Charitable Trust",
    "business": "Business Trust",
    "ecclesiastical": "Ecclesiastical Trust",
    "institutional": "Institutional Trust",
}

# US state code → full name (for jurisdiction display)
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


class BinderCoverSheetResponse(BaseModel):
    trust_name: str = ""
    ein: str = ""
    formation_date: str = ""
    trustees: List[str] = []
    trust_type: str = ""
    jurisdiction: str = ""


def format_formation_date(raw: Optional[str]) -> str:
    """Convert ISO date string to 'Month Day, Year' format. Return empty string on failure."""
    if not raw:
        return ""
    try:
        # Handle ISO format (e.g. "2024-01-15" or "2024-01-15T00:00:00")
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y").replace(" 0", " ")  # strip leading zero on day
    except (ValueError, TypeError, AttributeError):
        # Try common formats
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.strftime("%B %d, %Y").replace(" 0", " ")
            except ValueError:
                continue
        return ""


def format_trust_type(raw: Optional[str]) -> str:
    """Convert trust_type enum value to human-readable label."""
    if not raw:
        return ""
    return TRUST_TYPE_LABELS.get(raw, raw.replace("_", " ").title() if isinstance(raw, str) else "")


def format_jurisdiction(jurisdiction: Optional[str], state_code: Optional[str]) -> str:
    """Return the most readable jurisdiction string available."""
    # Prefer state_code for US states (full name)
    if state_code and state_code.upper() in US_STATES:
        return US_STATES[state_code.upper()]
    # If jurisdiction is a 2-letter code, expand it
    if jurisdiction and len(jurisdiction) == 2 and jurisdiction.upper() in US_STATES:
        return US_STATES[jurisdiction.upper()]
    # Otherwise return what we have
    if jurisdiction:
        return jurisdiction
    if state_code:
        return state_code
    return ""


def parse_trustees(raw: Optional[str]) -> List[str]:
    """Parse comma-separated trustee names into a list."""
    if not raw:
        return []
    return [name.strip() for name in raw.split(",") if name.strip()]


@router.get("/binder/cover-sheet-data", response_model=BinderCoverSheetResponse)
async def get_binder_cover_sheet_data(user: dict = Depends(get_current_user)):
    """
    Return the primary trust's data formatted for the binder cover sheet.
    Returns empty strings/arrays if no trust exists, so the frontend can
    display placeholder text.
    """
    # Fetch the user's first (primary) trust
    trust = await db.trusts.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0}
        # Default MongoDB sort is natural order ≈ insertion order,
        # so first document = the user's first/primary trust
    )

    if not trust:
        return BinderCoverSheetResponse()

    return BinderCoverSheetResponse(
        trust_name=trust.get("name", ""),
        ein=trust.get("ein") or "",
        formation_date=format_formation_date(trust.get("start_date")),
        trustees=parse_trustees(trust.get("trustees")),
        trust_type=format_trust_type(trust.get("trust_type")),
        jurisdiction=format_jurisdiction(trust.get("jurisdiction"), trust.get("state_code")),
    )