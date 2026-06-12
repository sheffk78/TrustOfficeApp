"""
Action Registry — Maps intent types to TrustOffice API endpoints

Each action entry defines:
- The intent that triggers it
- The API endpoint to call
- Required fields and their types
- Preview template for the Action Card UI
- Whether user confirmation is required before execution
"""

from typing import Optional

# ==================== INTENT → ACTION MAPPING ====================

ACTION_REGISTRY = {
    "ask_knowledge": {
        "type": "knowledge_response",
        "requires_write": False,
        "confirmation_required": False,
        "description": "Answer a general trust administration question",
        "fields": [],
    },
    "check_deadlines": {
        "type": "deadlines_summary",
        "requires_write": False,
        "confirmation_required": False,
        "description": "Return upcoming deadlines and pending tasks",
        "fields": [],
    },
    "health_check": {
        "type": "health_status",
        "requires_write": False,
        "confirmation_required": False,
        "description": "Return defensibility score and trust health status",
        "fields": [],
    },
    "recommend_action": {
        "type": "action_recommendations",
        "requires_write": False,
        "confirmation_required": False,
        "description": "Recommend prioritized next steps",
        "fields": [],
    },
    "log_minutes": {
        "type": "minutes_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Draft meeting minutes for review and approval",
        "api_endpoint": "POST /api/minutes/create",
        "fields": [
            {"name": "minutes_type", "type": "string", "required": True, "description": "Type of minutes (annual, quarterly, distribution, etc.)"},
            {"name": "meeting_date", "type": "string", "required": True, "description": "ISO date of the meeting"},
            {"name": "participants", "type": "list", "required": True, "description": "List of meeting participants"},
            {"name": "decisions", "type": "list", "required": True, "description": "List of decisions or agenda items"},
            {"name": "trust_name", "type": "string", "required": False, "description": "Name of the trust"},
        ],
    },
    "add_asset": {
        "type": "asset_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Log a new asset on Schedule A",
        "api_endpoint": "POST /api/schedule-a/create",
        "fields": [
            {"name": "asset_type", "type": "string", "required": True, "description": "Category of asset (real_property, financial_accounts, etc.)"},
            {"name": "description", "type": "string", "required": True, "description": "Description of the asset"},
            {"name": "value", "type": "number", "required": False, "description": "Estimated value of the asset"},
            {"name": "date_acquired", "type": "string", "required": True, "description": "Date the asset was acquired or contributed"},
            {"name": "ownership_pct", "type": "number", "required": False, "description": "Trust's ownership percentage"},
        ],
    },
    "create_distribution": {
        "type": "distribution_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Create a distribution record to a beneficiary",
        "api_endpoint": "POST /api/distributions/create",
        "fields": [
            {"name": "beneficiary_name", "type": "string", "required": True, "description": "Name of the beneficiary receiving the distribution"},
            {"name": "amount", "type": "number", "required": True, "description": "Distribution amount"},
            {"name": "purpose", "type": "string", "required": True, "description": "Purpose classification (HEMS category or description)"},
            {"name": "date", "type": "string", "required": True, "description": "Date of the distribution"},
            {"name": "from_account", "type": "string", "required": False, "description": "Source account if known"},
        ],
    },
    "add_beneficiary": {
        "type": "beneficiary_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Add or update beneficiary information",
        "api_endpoint": "POST /api/beneficiaries/create",
        "fields": [
            {"name": "name", "type": "string", "required": True, "description": "Beneficiary full name"},
            {"name": "email", "type": "string", "required": False, "description": "Beneficiary email address"},
            {"name": "phone", "type": "string", "required": False, "description": "Beneficiary phone number"},
            {"name": "allocation_pct", "type": "number", "required": False, "description": "Allocation percentage if relevant"},
        ],
    },
    "review_document": {
        "type": "document_search",
        "requires_write": False,
        "confirmation_required": False,
        "description": "Search and retrieve documents from the vault",
        "fields": [],
    },
    "general_chat": {
        "type": "general_response",
        "requires_write": False,
        "confirmation_required": False,
        "description": "General conversation or greeting",
        "fields": [],
    },
    "emergency": {
        "type": "emergency_response",
        "requires_write": False,
        "confirmation_required": False,
        "description": "Fiduciary concern or distress — provide reassurance and guidance",
        "fields": [],
    },
}


def get_action(intent: str) -> Optional[dict]:
    """Get the action definition for a given intent type."""
    return ACTION_REGISTRY.get(intent)


def requires_confirmation(intent: str) -> bool:
    """Check if this intent requires user confirmation before execution."""
    action = get_action(intent)
    if action:
        return action.get("confirmation_required", False)
    return False


def get_required_fields(intent: str) -> list:
    """Get the list of required fields for this intent's action."""
    action = get_action(intent)
    if action:
        return [f for f in action.get("fields", []) if f.get("required")]
    return []


def get_field_descriptions(intent: str) -> dict:
    """Get a dict of field_name -> description for all fields in this action."""
    action = get_action(intent)
    if action:
        return {f["name"]: f["description"] for f in action.get("fields", [])}
    return {}