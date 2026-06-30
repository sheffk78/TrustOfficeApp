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
        "api_endpoint": "POST /api/minutes",
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
        "api_endpoint": "POST /api/schedule-a",
        "fields": [
            {"name": "asset_type", "type": "string", "required": True, "description": "Category of asset (real_property, financial_accounts, tangible_property, business_interests, intellectual_property, other)"},
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
        "api_endpoint": "POST /api/distributions",
        "fields": [
            {"name": "beneficiary_name", "type": "string", "required": True, "description": "Name of the beneficiary receiving the distribution"},
            {"name": "amount", "type": "number", "required": True, "description": "Distribution amount"},
            {"name": "purpose", "type": "string", "required": True, "description": "Purpose classification (HEMS category: health, education, maintenance, support, medical_expenses, education_expenses, housing, emergency, or other)"},
            {"name": "date", "type": "string", "required": True, "description": "Date of the distribution"},
            {"name": "from_account", "type": "string", "required": False, "description": "Source account if known"},
        ],
    },
    "create_beneficiary": {
        "type": "beneficiary_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Add a new beneficiary",
        "api_endpoint": "POST /api/beneficiaries/create",
        "fields": [
            {"name": "name", "type": "string", "required": True, "description": "Beneficiary full name"},
            {"name": "email", "type": "string", "required": False, "description": "Beneficiary email address"},
            {"name": "phone", "type": "string", "required": False, "description": "Beneficiary phone number"},
            {"name": "notes", "type": "string", "required": False, "description": "Any additional notes about the beneficiary"},
        ],
    },
    "create_class_beneficiary": {
        "type": "class_beneficiary_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Add a class beneficiary designation (e.g., children, descendants, blood relatives) that automatically covers future members",
        "api_endpoint": "POST /api/beneficiaries/class-beneficiaries",
        "fields": [
            {"name": "class_type", "type": "string", "required": True, "description": "Class type: children, descendants, issue, heirs, heirs_at_law, blood_relatives, per_stirpes, per_capita, or custom"},
            {"name": "description", "type": "string", "required": False, "description": "Description of the class and how it's defined"},
            {"name": "percentage", "type": "number", "required": False, "description": "Allocation percentage for this class (0-100)"},
            {"name": "notes", "type": "string", "required": False, "description": "Additional notes about the class beneficiary designation"},
        ],
    },
    "remove_class_beneficiary": {
        "type": "class_beneficiary_removal_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Remove a class beneficiary designation",
        "api_endpoint": "DELETE /api/beneficiaries/class-beneficiaries/{class_beneficiary_id}",
        "fields": [
            {"name": "class_type", "type": "string", "required": True, "description": "The class type to remove (e.g., children, descendants, blood_relatives)"},
            {"name": "reason", "type": "string", "required": False, "description": "Reason for removal"},
        ],
    },
    "update_beneficiary": {
        "type": "beneficiary_update_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Update existing beneficiary contact or allocation information",
        "api_endpoint": "PATCH /api/beneficiaries/{beneficiary_id}",
        "fields": [
            {"name": "beneficiary_name", "type": "string", "required": True, "description": "Name of the beneficiary to update (used to look up their record)"},
            {"name": "email", "type": "string", "required": False, "description": "New email address"},
            {"name": "phone", "type": "string", "required": False, "description": "New phone number"},
            {"name": "notes", "type": "string", "required": False, "description": "Updated notes"},
        ],
    },
    "remove_beneficiary": {
        "type": "beneficiary_removal_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Remove a beneficiary from the trust",
        "api_endpoint": "DELETE /api/beneficiaries/{beneficiary_id}",
        "fields": [
            {"name": "beneficiary_name", "type": "string", "required": True, "description": "Name of the beneficiary to remove"},
            {"name": "reason", "type": "string", "required": False, "description": "Reason for removal"},
        ],
    },
    "send_certificate": {
        "type": "certificate_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Email a beneficiary their certificate showing trust unit allocation",
        "api_endpoint": "POST /api/beneficiaries/send-certificate",
        "fields": [
            {"name": "beneficiary_name", "type": "string", "required": True, "description": "Name of the beneficiary to email (used to look up their certificate record)"},
            {"name": "email", "type": "string", "required": False, "description": "Override email address; if not provided, uses the email on file for the beneficiary"},
            {"name": "notes", "type": "string", "required": False, "description": "Optional personal note to include in the certificate email"},
        ],
    },
    "cancel_distribution": {
        "type": "distribution_cancel_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Cancel or delete a distribution record",
        "api_endpoint": "DELETE /api/distributions/{distribution_id}",
        "fields": [
            {"name": "beneficiary_name", "type": "string", "required": True, "description": "Name of the beneficiary on the distribution to cancel"},
            {"name": "amount", "type": "number", "required": False, "description": "Amount of the distribution (to help identify the correct one)"},
            {"name": "date", "type": "string", "required": False, "description": "Date of the distribution to cancel"},
        ],
    },
    "upload_document": {
        "type": "document_upload_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Upload a document to the vault",
        "api_endpoint": "POST /api/trusts/{trust_id}/vault/upload",
        "fields": [
            {"name": "title", "type": "string", "required": True, "description": "Document title or name"},
            {"name": "category", "type": "string", "required": False, "description": "Document category (trust_document, court_filing, tax_return, correspondence, financial_statement, legal, insurance, property, beneficiary_doc, other)"},
            {"name": "notes", "type": "string", "required": False, "description": "Any notes about the document"},
        ],
    },
    "review_document": {
        "type": "document_search",
        "requires_write": False,
        "confirmation_required": False,
        "description": "Search and retrieve documents from the vault",
        "fields": [],
    },
    "setup_compensation": {
        "type": "compensation_plan_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Create a trustee compensation plan",
        "api_endpoint": "POST /api/compensation-plans",
        "fields": [
            {"name": "trustee_name", "type": "string", "required": True, "description": "Name of the trustee being compensated"},
            {"name": "amount", "type": "number", "required": True, "description": "Compensation amount"},
            {"name": "frequency", "type": "string", "required": True, "description": "Payment frequency (monthly, quarterly, annually, per_meeting)"},
            {"name": "effective_date", "type": "string", "required": True, "description": "Date compensation takes effect"},
            {"name": "role", "type": "string", "required": False, "description": "Trustee role or title"},
        ],
    },
    "dismiss_alert": {
        "type": "alert_dismiss",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Dismiss a governance insight or alert",
        "api_endpoint": "POST /api/insights/dismiss",
        "fields": [
            {"name": "criterion_name", "type": "string", "required": True, "description": "Name of the insight or criterion to dismiss (e.g. 'Quarterly Minutes', 'Task Compliance')"},
        ],
    },
    "schedule_task": {
        "type": "task_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Create a new governance task",
        "api_endpoint": "POST /api/tasks",
        "fields": [
            {"name": "task_type", "type": "string", "required": True, "description": "Type of task (annual_review, quarterly_review, compensation_review, distribution_review, insurance_compliance, transaction_review, tax_filing_1041, tax_filing_k1, custom)"},
            {"name": "description", "type": "string", "required": True, "description": "Description of the task"},
            {"name": "due_date", "type": "string", "required": True, "description": "ISO date when the task is due"},
            {"name": "priority", "type": "string", "required": False, "description": "Priority level (normal, high, critical)"},
        ],
    },
    "add_transaction": {
        "type": "transaction_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Log a trust income or expense transaction",
        "api_endpoint": "POST /api/transactions",
        "fields": [
            {"name": "type", "type": "string", "required": True, "description": "Transaction type (income, expense, transfer)"},
            {"name": "amount", "type": "number", "required": True, "description": "Transaction amount"},
            {"name": "category", "type": "string", "required": True, "description": "Category (rental_income, interest, dividends, capital_gains, business_income, other_income, legal_fees, accounting_fees, trustee_fees, insurance, property_taxes, maintenance, utilities, distributions, investments, other_expense)"},
            {"name": "date", "type": "string", "required": True, "description": "Date of the transaction"},
            {"name": "description", "type": "string", "required": False, "description": "Optional description or memo"},
        ],
    },
    "change_settings": {
        "type": "settings_update_preview",
        "requires_write": True,
        "confirmation_required": True,
        "description": "Update trust profile settings",
        "api_endpoint": "PUT /api/trusts/{trust_id}",
        "fields": [
            {"name": "field", "type": "string", "required": True, "description": "Field to update (name, trust_type, formation_date, ein, jurisdiction, state_code)"},
            {"name": "value", "type": "string", "required": True, "description": "New value for the field"},
        ],
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


def get_write_intents() -> list:
    """Return list of all intents that require write access."""
    return [
        intent for intent, config in ACTION_REGISTRY.items()
        if config.get("requires_write", False)
    ]