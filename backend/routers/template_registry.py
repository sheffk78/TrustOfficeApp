"""
Template Registry - Centralized definition of all minutes templates,
their display metadata, form fields, and AI prompt templates.

This module is the single source of truth for what templates exist,
how they're organized, and what fields each template requires.
"""
from typing import List, Optional, Dict, Any


# ==================== CATEGORY DISPLAY ORDER ====================

CATEGORY_DISPLAY_ORDER = [
    "first_meeting",
    "quick_minutes",
    "trustee_changes",
    "property_assets",
    "financial",
    "distributions",
    "legal_governance",
    "admin",
    "benevolence",
]


# ==================== TEMPLATE REGISTRY ====================

TEMPLATE_REGISTRY: Dict[str, Dict[str, Any]] = {
    # ─── First Meeting ───────────────────────────────────────
    "initial_trustee_meeting": {
        "display_name": "Initial Trustee Meeting",
        "description": "Your trust's first organizational meeting — accept trusteeship, open bank accounts, confirm EIN, set fiscal year, adopt governance standards, and more",
        "icon": "gavel",
        "category": "first_meeting",
        "priority": True,
        "special_form": True,  # Has its own dedicated form, not generic fields
        "fields": [],
        "ai_prompt_template": (
            "Generate first organizational meeting minutes for {trust_name}. "
            "The meeting was held on {meeting_date}. Trustees present: {participants}. "
            "This is the trust's first meeting after formation. Include: acceptance of trusteeship, "
            "adoption of declaration of trust, acknowledgment of fiduciary duties, "
            "authorization of bank accounts, fiscal year election, EIN confirmation, "
            "adoption of governance standards, and ratification of prior actions. "
            "Additional context: {additional_context}"
        ),
    },

    # ─── Quick Minutes (AI-assisted, bullet-point input) ─────
    "annual_review": {
        "display_name": "Annual Review Meeting",
        "description": "Year-end financial and governance review with comprehensive report",
        "icon": "calendar-check",
        "category": "quick_minutes",
        "fields": [
            {"name": "agenda_items", "label": "Agenda Items", "type": "textarea", "required": False,
             "placeholder": "• Financial review\n• Asset performance\n• Trustee compensation review"},
            {"name": "key_decisions", "label": "Key Decisions", "type": "textarea", "required": False,
             "placeholder": "• Approved annual budget\n• Renewed insurance policies"},
            {"name": "additional_notes", "label": "Additional Notes", "type": "textarea", "required": False,
             "placeholder": "Any additional context for the AI…"},
        ],
        "ai_prompt_template": (
            "Generate annual review meeting minutes for {trust_name} held on {meeting_date}. "
            "Trustees present: {participants}. "
            "Agenda items: {agenda_items}. "
            "Key decisions: {key_decisions}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED structure with comprehensive annual review language."
        ),
    },

    "quarterly_review": {
        "display_name": "Quarterly Review Meeting",
        "description": "Routine quarterly trustee meeting and financial review",
        "icon": "calendar-days",
        "category": "quick_minutes",
        "fields": [
            {"name": "agenda_items", "label": "Agenda Items", "type": "textarea", "required": False,
             "placeholder": "• Quarterly financial review\n• Distribution review"},
            {"name": "key_decisions", "label": "Key Decisions", "type": "textarea", "required": False,
             "placeholder": "• Approved quarterly distribution"},
            {"name": "additional_notes", "label": "Additional Notes", "type": "textarea", "required": False,
             "placeholder": "Any additional context for the AI…"},
        ],
        "ai_prompt_template": (
            "Generate quarterly review meeting minutes for {trust_name} held on {meeting_date}. "
            "Trustees present: {participants}. "
            "Agenda items: {agenda_items}. "
            "Key decisions: {key_decisions}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED structure with professional quarterly review language."
        ),
    },

    "general_meeting": {
        "display_name": "General Meeting",
        "description": "Record a general trustee meeting with multiple resolutions",
        "icon": "users",
        "category": "quick_minutes",
        "fields": [
            {"name": "agenda_items", "label": "Agenda Items", "type": "textarea", "required": False,
             "placeholder": "• General trust business\n• Any resolutions"},
            {"name": "key_decisions", "label": "Key Decisions", "type": "textarea", "required": False,
             "placeholder": "• Resolutions adopted at this meeting"},
            {"name": "additional_notes", "label": "Additional Notes", "type": "textarea", "required": False,
             "placeholder": "Any additional context for the AI…"},
        ],
        "ai_prompt_template": (
            "Generate general meeting minutes for {trust_name} held on {meeting_date}. "
            "Trustees present: {participants}. "
            "Agenda items: {agenda_items}. "
            "Key decisions: {key_decisions}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED structure with professional meeting minutes language."
        ),
    },

    # ─── Trustee Changes ──────────────────────────────────────
    "appointment_additional_trustee": {
        "display_name": "Appoint Additional Trustee",
        "description": "Appoint a new trustee to serve alongside existing trustees",
        "icon": "user-plus",
        "category": "trustee_changes",
        "fields": [
            {"name": "new_trustee_name", "label": "New Trustee Name", "type": "text", "required": True},
            {"name": "new_trustee_address", "label": "New Trustee Address", "type": "text", "required": False},
            {"name": "effective_date", "label": "Effective Date", "type": "date", "required": True},
        ],
        "ai_prompt_template": (
            "Generate minutes for appointing an additional trustee to {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "New trustee: {new_trustee_name}. Address: {new_trustee_address}. "
            "Effective date: {effective_date}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS clauses about trust authority and RESOLVED clauses for appointment."
        ),
    },

    "appointment_successor_trustee": {
        "display_name": "Appoint Successor Trustee",
        "description": "Appoint a replacement trustee due to resignation, death, or removal",
        "icon": "user-check",
        "category": "trustee_changes",
        "fields": [
            {"name": "departing_trustee_name", "label": "Departing Trustee Name", "type": "text", "required": True},
            {"name": "reason", "label": "Reason for Departure", "type": "select", "required": True,
             "options": ["resignation", "death", "removal"]},
            {"name": "new_trustee_name", "label": "New Trustee Name", "type": "text", "required": True},
            {"name": "effective_date", "label": "Effective Date", "type": "date", "required": True},
        ],
        "ai_prompt_template": (
            "Generate minutes for appointing a successor trustee to {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Departing trustee: {departing_trustee_name}. Reason: {reason}. "
            "New trustee: {new_trustee_name}. Effective date: {effective_date}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS clauses about trust authority and vacancy, RESOLVED clauses for appointment."
        ),
    },

    "trustee_resignation": {
        "display_name": "Trustee Resignation/Removal",
        "description": "Document a trustee's departure from office",
        "icon": "user-minus",
        "category": "trustee_changes",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes documenting trustee resignation/removal from {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include formal WHEREAS/RESOLVED language for the departure."
        ),
    },

    "trustee_compensation": {
        "display_name": "Trustee Compensation",
        "description": "Approve trustee fee arrangements and compensation",
        "icon": "wallet",
        "category": "trustee_changes",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for trustee compensation approval for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for compensation approval with proper recusal acknowledgment."
        ),
    },

    # ─── Property & Assets ───────────────────────────────────
    "real_estate_purchase": {
        "display_name": "Real Estate Purchase",
        "description": "Authorize acquisition of real property for the trust",
        "icon": "home",
        "category": "property_assets",
        "fields": [
            {"name": "property_address", "label": "Property Address", "type": "text", "required": True},
            {"name": "purchase_price", "label": "Purchase Price", "type": "currency", "required": True},
            {"name": "funding_source", "label": "Funding Source", "type": "text", "required": False,
             "placeholder": "e.g., Trust checking account at XYZ Bank"},
            {"name": "closing_date", "label": "Closing Date", "type": "date", "required": True},
        ],
        "ai_prompt_template": (
            "Generate minutes authorizing real estate purchase for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Property address: {property_address}. Purchase price: {purchase_price}. "
            "Funding source: {funding_source}. Closing date: {closing_date}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS clauses about investment prudence and RESOLVED for purchase authorization."
        ),
    },

    "acceptance_of_property": {
        "display_name": "Accept Property into Trust",
        "description": "Accept additional property into the trust corpus and update Schedule A",
        "icon": "plus-circle",
        "category": "property_assets",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for acceptance of property into {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for property acceptance and Schedule A update."
        ),
    },

    "disposition_of_asset": {
        "display_name": "Dispose / Sell Asset",
        "description": "Record the sale, transfer, or removal of an asset from Schedule A",
        "icon": "minus-circle",
        "category": "property_assets",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for asset disposition from {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for disposition and Schedule A update."
        ),
    },

    "business_interest_acquisition": {
        "display_name": "Business Interest Acquisition",
        "description": "Authorize purchase of LLC, partnership, or corporate interest",
        "icon": "building-2",
        "category": "property_assets",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for business interest acquisition by {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for acquisition authorization."
        ),
    },

    "real_estate_lease": {
        "display_name": "Real Estate Lease",
        "description": "Authorize leasing of trust real property to third parties",
        "icon": "key",
        "category": "property_assets",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes authorizing real estate lease for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for lease authorization."
        ),
    },

    # ─── Financial ────────────────────────────────────────────
    "bank_account_authorization": {
        "display_name": "Open Bank Account",
        "description": "Authorize opening a bank or investment account for the trust",
        "icon": "landmark",
        "category": "financial",
        "fields": [
            {"name": "bank_name", "label": "Bank Name", "type": "text", "required": True},
            {"name": "account_type", "label": "Account Type", "type": "select", "required": True,
             "options": ["checking", "savings", "investment"]},
            {"name": "initial_deposit", "label": "Initial Deposit", "type": "currency", "required": False},
            {"name": "authorized_signers", "label": "Authorized Signers", "type": "trusteelist", "required": True},
        ],
        "ai_prompt_template": (
            "Generate minutes authorizing a bank account for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Bank name: {bank_name}. Account type: {account_type}. "
            "Initial deposit: {initial_deposit}. Authorized signers: {authorized_signers}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for banking authorization with signature powers."
        ),
    },

    "investment_policy": {
        "display_name": "Investment Policy",
        "description": "Adopt, amend, or review the trust's investment policy statement",
        "icon": "trending-up",
        "category": "financial",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for investment policy adoption/amendment for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for investment policy with prudence standards."
        ),
    },

    "loan_authorization": {
        "display_name": "Loan Authorization",
        "description": "Authorize the trust to make or receive a loan",
        "icon": "banknote",
        "category": "financial",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for loan authorization by {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for loan terms and authorization."
        ),
    },

    "insurance_authorization": {
        "display_name": "Insurance Authorization",
        "description": "Approve trust insurance policies and coverage",
        "icon": "shield-check",
        "category": "financial",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for insurance authorization for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for insurance coverage authorization."
        ),
    },

    # ─── Distributions ───────────────────────────────────────
    "distribution_to_beneficiaries": {
        "display_name": "Distribution to Beneficiaries",
        "description": "Document a distribution of trust proceeds to beneficiaries",
        "icon": "dollar-sign",
        "category": "distributions",
        "fields": [
            {"name": "distribution_total", "label": "Total Amount", "type": "currency", "required": True},
            {"name": "distribution_recipient", "label": "Recipient", "type": "text", "required": True},
            {"name": "distribution_date", "label": "Distribution Date", "type": "date", "required": True},
            {"name": "distribution_characterization", "label": "Characterization", "type": "select", "required": True,
             "options": ["income", "principal", "both"]},
            {"name": "distribution_purpose", "label": "Purpose/Notes", "type": "textarea", "required": False},
        ],
        "ai_prompt_template": (
            "Generate minutes for a distribution to beneficiaries from {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Distribution total: {distribution_total}. Recipient: {distribution_recipient}. "
            "Distribution date: {distribution_date}. Characterization: {distribution_characterization}. "
            "Purpose: {distribution_purpose}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for distribution with solvency confirmation."
        ),
    },

    "hems_distribution": {
        "display_name": "HEMS Distribution",
        "description": "Health, Education, Maintenance, Support distribution with standard compliance",
        "icon": "heart-pulse",
        "category": "distributions",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for a HEMS distribution from {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for HEMS distribution with beneficiary standard reference."
        ),
    },

    "beneficiary_loan": {
        "display_name": "Loan to Beneficiary",
        "description": "Authorize an intra-family loan to a beneficiary",
        "icon": "hand-coins",
        "category": "distributions",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for beneficiary loan from {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for loan terms, repayment schedule, and authorization."
        ),
    },

    # ─── Legal & Governance ──────────────────────────────────
    "trust_amendment": {
        "display_name": "Trust Amendment",
        "description": "Modify specific provisions of the trust instrument",
        "icon": "file-edit",
        "category": "legal_governance",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for trust amendment for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for amendment with specific provision references."
        ),
    },

    "conflict_of_interest": {
        "display_name": "Conflict of Interest Disclosure",
        "description": "Document trustee's disclosure and waiver of conflict",
        "icon": "scale",
        "category": "legal_governance",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for conflict of interest disclosure for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for disclosure, recusal process, and approval."
        ),
    },

    "emergency_ratification": {
        "display_name": "Emergency Action Ratification",
        "description": "Ratify trustee actions taken during an emergency",
        "icon": "alert-triangle",
        "category": "legal_governance",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for emergency action ratification for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language describing the emergency, actions taken, and ratification."
        ),
    },

    "power_of_attorney": {
        "display_name": "Power of Attorney",
        "description": "Grant limited power of attorney to a trustee or agent",
        "icon": "stamp",
        "category": "legal_governance",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for power of attorney authorization for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for POA scope, limitations, and duration."
        ),
    },

    "trust_termination": {
        "display_name": "Trust Termination",
        "description": "Document trust dissolution and final distribution",
        "icon": "file-x",
        "category": "legal_governance",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for trust termination of {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for termination, final distribution, and winding down."
        ),
    },

    "change_of_situs": {
        "display_name": "Change Trust Situs",
        "description": "Change the jurisdiction and principal place of administration",
        "icon": "map-pin",
        "category": "legal_governance",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for change of situs for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for jurisdiction change with governing law update."
        ),
    },

    # ─── Admin ───────────────────────────────────────────────
    "fiscal_year_election": {
        "display_name": "Fiscal Year Election",
        "description": "Document the trust's fiscal year choice for tax purposes",
        "icon": "calendar-range",
        "category": "admin",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for fiscal year election for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for fiscal year election with tax purpose reference."
        ),
    },

    "tax_filing_authorization": {
        "display_name": "Tax Filing Authorization",
        "description": "Authorize preparation and filing of trust tax returns",
        "icon": "receipt",
        "category": "admin",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for tax filing authorization for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for authorization of tax preparer and filing."
        ),
    },

    "designation_of_beneficiaries": {
        "display_name": "Designate Beneficiaries",
        "description": "Establish or amend beneficiary designations and units of beneficial interest",
        "icon": "users-round",
        "category": "admin",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for beneficiary designation for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for designation with units of beneficial interest."
        ),
    },

    "beneficiary_request_denial": {
        "display_name": "Beneficiary Request Denial",
        "description": "Document denial of a beneficiary request with proper reasoning",
        "icon": "x-circle",
        "category": "admin",
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for beneficiary request denial by {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for denial with fiduciary duty reasoning."
        ),
    },

    "beneficiary_distribution_notice": {
        "display_name": "Beneficiary Distribution Notice",
        "description": "Notify a beneficiary of an approved distribution with formal documentation",
        "icon": "mail",
        "category": "distributions",
        "fields": [
            {"name": "beneficiary_name", "label": "Beneficiary Name", "type": "text", "required": True,
             "placeholder": "Jane Smith"},
            {"name": "distribution_amount", "label": "Distribution Amount", "type": "text", "required": True,
             "placeholder": "$15,000"},
            {"name": "distribution_purpose", "label": "Purpose", "type": "textarea", "required": True,
             "placeholder": "Education expenses for fall semester tuition"},
            {"name": "distribution_date", "label": "Distribution Date", "type": "text", "required": False,
             "placeholder": "YYYY-MM-DD"},
            {"name": "trustee_name", "label": "Trustee Name", "type": "text", "required": False,
             "placeholder": "Your name"},
        ],
        "ai_prompt_template": (
            "Generate a formal beneficiary distribution notice for {trust_name}. "
            "Beneficiary: {beneficiary_name}. Amount: {distribution_amount}. "
            "Purpose: {distribution_purpose}. Date: {distribution_date}. "
            "Trustee: {trustee_name}. Meeting date: {meeting_date}. "
            "Additional context: {additional_context}. "
            "This is a formal notification to the beneficiary documenting the approved distribution. "
            "Include the trust name, distribution amount, purpose, HEMS category reference if applicable, "
            "and a statement that this distribution was made in accordance with the trust's distribution "
            "standards and the trustee's fiduciary duty. Format as a formal letter."
        ),
    },

    "evaluate_distribution": {
        "display_name": "Evaluate Distribution Request",
        "description": "Get an AI evaluation of whether a distribution request complies with your trust document and trust law",
        "icon": "scale",
        "category": "distributions",
        "fields": [
            {"name": "beneficiary_name", "label": "Beneficiary Name", "type": "text", "required": True,
             "placeholder": "John Smith Jr."},
            {"name": "requested_amount", "label": "Requested Amount", "type": "text", "required": True,
             "placeholder": "$50,000"},
            {"name": "request_purpose", "label": "Purpose", "type": "textarea", "required": False,
             "placeholder": "Fall semester tuition"},
            {"name": "hems_category", "label": "HEMS Category", "type": "select", "required": True,
             "placeholder": "education"},
            {"name": "beneficiary_financial_situation", "label": "Beneficiary Financial Situation", "type": "textarea", "required": False,
             "placeholder": "Annual income, savings, other assets"},
            {"name": "beneficiary_other_resources", "label": "Other Resources", "type": "text", "required": False,
             "placeholder": "Scholarships, parental support"},
            {"name": "past_distributions_note", "label": "Past Distributions Notes", "type": "textarea", "required": False,
             "placeholder": "Previous distributions for equity reference"},
        ],
        "ai_prompt_template": (
            "Evaluate a distribution request for {trust_name}. "
            "Beneficiary: {beneficiary_name}. Requested amount: {requested_amount}. "
            "Purpose: {request_purpose}. HEMS category: {hems_category}. "
            "Beneficiary financial situation: {beneficiary_financial_situation}. "
            "Other resources: {beneficiary_other_resources}. "
            "Past distributions: {past_distributions_note}. "
            "Additional context: {additional_context}."
        ),
    },

    # ─── Benevolence ─────────────────────────────────────────
    "benevolence_approval": {
        "display_name": "Benevolence Assistance",
        "description": "Approve and document a benevolence grant for charitable assistance",
        "icon": "heart-handshake",
        "category": "benevolence",
        "requires_benevolence": True,
        "fields": [],
        "ai_prompt_template": (
            "Generate minutes for benevolence approval for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language for benevolence with purpose and amount."
        ),
    },
}


def get_template_registry(trust_id: Optional[str] = None, benevolence_enabled: bool = False) -> List[Dict[str, Any]]:
    """
    Get the list of available templates in display order.

    Returns templates grouped by category in CATEGORY_DISPLAY_ORDER,
    with fields included for each template.

    If the trust does not have benevolence_enabled, the benevolence template is filtered out.
    """
    templates = []

    for template_type, definition in TEMPLATE_REGISTRY.items():
        # Filter out benevolence if not enabled
        if definition.get("requires_benevolence") and not benevolence_enabled:
            continue

        entry = {
            "type": template_type,
            "name": definition["display_name"],
            "description": definition["description"],
            "icon": definition["icon"],
            "category": definition["category"],
            "fields": definition.get("fields", []),
        }

        # Include special flags
        if definition.get("priority"):
            entry["priority"] = True
        if definition.get("requires_benevolence"):
            entry["requires_benevolence"] = True
        if definition.get("special_form"):
            entry["special_form"] = True

        templates.append(entry)

    # Sort by category display order
    category_rank = {cat: i for i, cat in enumerate(CATEGORY_DISPLAY_ORDER)}
    templates.sort(key=lambda t: category_rank.get(t["category"], 99))

    return templates


def get_template_definition(template_type: str) -> Optional[Dict[str, Any]]:
    """Get a single template definition by type, or None if not found."""
    return TEMPLATE_REGISTRY.get(template_type)


def build_ai_prompt(template_type: str, context: Dict[str, str]) -> str:
    """
    Build an AI prompt string from a template type and a context dict.

    Context dict keys map to the {placeholder} names in ai_prompt_template.
    Missing keys are replaced with "Not specified".
    """
    definition = TEMPLATE_REGISTRY.get(template_type)
    if not definition:
        # Fallback for unknown template types
        return (
            "Generate meeting minutes for {trust_name} held on {meeting_date}. "
            "Trustees present: {participants}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED structure with professional trust minutes language."
        ).format(**{k: context.get(k, "Not specified") for k in ["trust_name", "meeting_date", "participants", "additional_context"]})

    template_str = definition["ai_prompt_template"]

    # Get all placeholders from the template
    import re
    placeholders = re.findall(r'\{(\w+)\}', template_str)

    # Build a filled context with defaults for missing keys
    filled = {}
    for key in placeholders:
        filled[key] = context.get(key, "Not specified")

    try:
        return template_str.format(**filled)
    except KeyError:
        # If formatting fails, return a basic prompt
        return (
            f"Generate {definition['display_name']} minutes for {context.get('trust_name', 'the trust')} "
            f"held on {context.get('meeting_date', 'the meeting date')}. "
            f"Trustees present: {context.get('participants', 'Not specified')}. "
            f"Additional context: {context.get('additional_context', 'None')}. "
            f"Include WHEREAS/RESOLVED structure with professional trust minutes language."
        )