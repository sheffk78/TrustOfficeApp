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
            "Use formal WHEREAS/RESOLVED structure for each action. "
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

    "successor_trustee_acceptance": {
        "display_name": "Successor Trustee Acceptance & Qualification",
        "description": "Record a successor trustee's formal acceptance of trusteeship and qualification to serve",
        "icon": "user-check-circle",
        "category": "trustee_changes",
        "fields": [
            {"name": "successor_trustee_name", "label": "Successor Trustee Name", "type": "text", "required": True},
            {"name": "qualifying_event", "label": "Qualifying Event", "type": "select", "required": True,
             "options": ["prior trustee resignation", "prior trustee death", "prior trustee removal", "incapacity of prior trustee"]},
            {"name": "acceptance_date", "label": "Date of Acceptance", "type": "date", "required": True},
            {"name": "bonding_notes", "label": "Bonding / Qualification Notes", "type": "textarea", "required": False,
             "placeholder": "e.g., bond requirement waived per trust instrument; letters of acceptance filed"},
        ],
        "ai_prompt_template": (
            "Generate minutes recording the acceptance of trusteeship by {successor_trustee_name} for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Qualifying event: {qualifying_event}. Acceptance date: {acceptance_date}. "
            "Bonding/qualification notes: {bonding_notes}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language: WHEREAS clauses recite the succession event under the trust "
            "instrument and that {successor_trustee_name} accepts the office and qualifies to serve (including any "
            "bonding notes as recorded); RESOLVED clauses record the acceptance, the commencement of authority "
            "as of the acceptance date, and ratification of prior-trustee acts properly taken. "
            "The minutes record the process and facts of succession; they do not determine any legal right."
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

    # ─── Conveyance Documents ────────────────────────────────
    "bill_of_sale": {
        "display_name": "Bill of Sale (Vehicle/Equipment)",
        "description": "Generate a bill of sale transferring tangible personal property to the trust",
        "icon": "file-text",
        "category": "property_assets",
        "fields": [
            {"name": "grantor_name", "label": "Grantor/Seller Name", "type": "text", "required": True},
            {"name": "property_description", "label": "Property Description", "type": "textarea", "required": True},
            {"name": "property_identifier", "label": "Identifier (VIN, Serial #, etc.)", "type": "text", "required": False},
            {"name": "property_location", "label": "Property Location", "type": "text", "required": False},
            {"name": "property_value", "label": "Sale Price / Approximate Value", "type": "currency", "required": False},
            {"name": "conveyance_date", "label": "Date of Sale/Transfer", "type": "date", "required": True},
            {"name": "add_to_schedule_a", "label": "Auto-add to Schedule A", "type": "boolean", "required": False},
            {"name": "schedule_a_category", "label": "Schedule A Category", "type": "select", "required": False,
             "options": ["personal_property", "real_property", "other_property"]},
        ],
        "ai_prompt_template": (
            "Generate a bill of sale for transfer of tangible personal property to {trust_name}. "
            "The meeting was held on {meeting_date}. Trustees present: {participants}. "
            "Grantor: {grantor_name}. Property: {property_description}. Identifier: {property_identifier}. "
            "Value: {property_value}. Date: {conveyance_date}. Trustee: {trustee_name}. EIN: {ein}. "
            "Include conveyance language, consideration statement, 'as-is' clause, and notary acknowledgment block "
            "for {state_code}. Output formal bill of sale document text."
        ),
    },
    "assignment_of_personal_property": {
        "display_name": "Assignment of Personal Property (Art/Jewelry/Collectibles)",
        "description": "Assign artwork, antiques, jewelry, or collectibles to the trust",
        "icon": "gem",
        "category": "property_assets",
        "fields": [
            {"name": "grantor_name", "label": "Grantor/Assignor Name", "type": "text", "required": True},
            {"name": "property_description", "label": "Property Description", "type": "textarea", "required": True},
            {"name": "property_identifier", "label": "Identifier (Serial #, Provenance Ref, etc.)", "type": "text", "required": False},
            {"name": "property_location", "label": "Property Location", "type": "text", "required": False},
            {"name": "property_value", "label": "Appraised Value", "type": "currency", "required": False},
            {"name": "appraiser_name", "label": "Appraiser Name (if appraised)", "type": "text", "required": False},
            {"name": "conveyance_date", "label": "Date of Assignment", "type": "date", "required": True},
            {"name": "add_to_schedule_a", "label": "Auto-add to Schedule A", "type": "boolean", "required": False},
            {"name": "schedule_a_category", "label": "Schedule A Category", "type": "select", "required": False,
             "options": ["personal_property", "real_property", "other_property"]},
        ],
        "ai_prompt_template": (
            "Generate an assignment of personal property for transfer of artwork, jewelry, or collectibles to {trust_name}. "
            "The meeting was held on {meeting_date}. Trustees present: {participants}. "
            "Grantor: {grantor_name}. Property: {property_description}. Appraised value: {property_value}. "
            "Appraiser: {appraiser_name}. Date: {conveyance_date}. Trustee: {trustee_name}. EIN: {ein}. "
            "Include assignment and conveyance language, consideration statement, warranty of title, "
            "and notary acknowledgment block for {state_code}. Output formal assignment document text."
        ),
    },
    "general_assignment": {
        "display_name": "General Assignment (Intangible Assets)",
        "description": "Assign intangible assets (notes, IP, business interests, digital assets) to the trust",
        "icon": "briefcase",
        "category": "property_assets",
        "fields": [
            {"name": "grantor_name", "label": "Grantor/Assignor Name", "type": "text", "required": True},
            {"name": "property_description", "label": "Asset Description", "type": "textarea", "required": True},
            {"name": "property_identifier", "label": "Identifier (Account #, Patent #, etc.)", "type": "text", "required": False},
            {"name": "property_value", "label": "Approximate Value", "type": "currency", "required": False},
            {"name": "conveyance_date", "label": "Date of Assignment", "type": "date", "required": True},
            {"name": "add_to_schedule_a", "label": "Auto-add to Schedule A", "type": "boolean", "required": False},
            {"name": "schedule_a_category", "label": "Schedule A Category", "type": "select", "required": False,
             "options": ["personal_property", "real_property", "other_property"]},
        ],
        "ai_prompt_template": (
            "Generate a general assignment of intangible assets to {trust_name}. "
            "The meeting was held on {meeting_date}. Trustees present: {participants}. "
            "Grantor: {grantor_name}. Asset: {property_description}. Identifier: {property_identifier}. "
            "Value: {property_value}. Date: {conveyance_date}. Trustee: {trustee_name}. EIN: {ein}. "
            "Include general assignment language, consideration statement, warranty of title, "
            "and notary acknowledgment block for {state_code}. Output formal general assignment document text."
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
            "Include WHEREAS/RESOLVED language for the distribution. State explicitly that the distribution is made for the beneficiary's health, education, maintenance, or support (the HEMS standard), identify which HEMS prong applies, and reference the standard objectively — the minutes record the trustees' process, they do not determine legal rights."
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
            "Include WHEREAS/RESOLVED language for loan terms, repayment schedule, and authorization."
        ),
    },

    "beneficiary_receipt_release": {
        "display_name": "Beneficiary Receipt & Release",
        "description": "Record a beneficiary's written acknowledgment of a distribution received",
        "icon": "file-check",
        "category": "distributions",
        "fields": [
            {"name": "beneficiary_name", "label": "Beneficiary Name", "type": "text", "required": True},
            {"name": "distribution_amount", "label": "Amount Received", "type": "currency", "required": True},
            {"name": "distribution_date", "label": "Date of Distribution", "type": "date", "required": True},
            {"name": "distribution_form", "label": "Form of Distribution", "type": "select", "required": True,
             "options": ["check", "ACH transfer", "wire", "in-kind asset"]},
            {"name": "release_scope", "label": "Scope of Acknowledgment", "type": "textarea", "required": False,
             "placeholder": "e.g., acknowledges receipt of the distribution described; no general release of trustee claims"},
        ],
        "ai_prompt_template": (
            "Generate minutes recording the beneficiary receipt acknowledgment for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Beneficiary: {beneficiary_name}. Amount: {distribution_amount}. "
            "Distribution date: {distribution_date}. Form: {distribution_form}. "
            "Scope acknowledged: {release_scope}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language: WHEREAS clauses recite the distribution made under the trust's "
            "distribution process and that the beneficiary acknowledges receipt of the stated property; RESOLVED "
            "clauses record the acknowledgment for the trust's permanent records and direct its filing with the "
            "trust's books. Keep the scope exactly as entered — the acknowledgment records receipt, and the "
            "minutes do not determine any legal right or release beyond the scope stated."
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

    "trustee_indemnification_release": {
        "display_name": "Trustee Indemnification & Release",
        "description": "Document the trust's indemnification of a trustee and the scope of any release after a matter closes",
        "icon": "shield",
        "category": "legal_governance",
        "fields": [
            {"name": "affected_trustee_name", "label": "Trustee Name", "type": "text", "required": True},
            {"name": "matter_summary", "label": "Matter Summary", "type": "textarea", "required": True,
             "placeholder": "e.g., third-party claim regarding property repairs; matter concluded without finding of breach"},
            {"name": "indemnification_scope", "label": "Indemnification Scope", "type": "textarea", "required": False,
             "placeholder": "e.g., reasonable costs and expenses actually incurred, per the trust instrument's indemnification provision"},
            {"name": "release_scope", "label": "Release Scope", "type": "textarea", "required": False,
             "placeholder": "e.g., release limited to the matters described above; no release regarding future acts"},
        ],
        "ai_prompt_template": (
            "Generate minutes recording trustee indemnification and release for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Trustee: {affected_trustee_name}. Matter: {matter_summary}. "
            "Indemnification scope: {indemnification_scope}. Release scope: {release_scope}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language: WHEREAS clauses recite the matter, its conclusion, and the trust "
            "instrument's indemnification provision; RESOLVED clauses record indemnification limited to the scope "
            "as entered and any release limited to the matters described, and direct the resolution be filed with "
            "the trust's books. Keep both scopes exactly as entered; the trustee's own interest requires recusal "
            "acknowledgment, and the minutes record the trustees' process — they do not determine any legal right."
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

    "grantor_trust_election": {
        "display_name": "Grantor Trust / Entity Election",
        "description": "Record the trustees' adoption of a tax-election position for the trust (e.g., check-the-box or an S-corp election for a held entity)",
        "icon": "file-signature",
        "category": "admin",
        "fields": [
            {"name": "election_type", "label": "Election Type", "type": "select", "required": True,
             "options": ["grantor trust position (Rev. Rul. 85-13 framework)", "check-the-box entity classification (Form 8832)", "S-corporation election for a held entity (Form 2553)"]},
            {"name": "related_entity", "label": "Related Entity (if any)", "type": "text", "required": False,
             "placeholder": "e.g., ABC Holdings LLC, wholly owned by the trust"},
            {"name": "election_reason", "label": "Reason for Election", "type": "textarea", "required": True},
            {"name": "tax_advisor", "label": "Tax Advisor / Preparer", "type": "text", "required": False},
        ],
        "ai_prompt_template": (
            "Generate minutes recording the trustees' adoption of a tax election for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Election type: {election_type}. Related entity: {related_entity}. "
            "Reason: {election_reason}. Tax advisor: {tax_advisor}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language: WHEREAS clauses recite the trustees' duty to administer the "
            "trust's tax affairs and that the election was reviewed with the trust's tax advisor ({tax_advisor}); "
            "RESOLVED clauses record the trustees' adoption of the stated election position, authorize signature "
            "and filing of the associated form by the designated officer or preparer, and direct retention of the "
            "election records with the trust's tax files. Frame everything as the trustees' recorded "
            "administrative adoption of a tax position developed with their tax advisor — the minutes record the "
            "process; they do not determine the trust's tax treatment, and no tax advice is given in the minutes."
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
            "Trustees present: {participants}. "
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

    "beneficiary_periodic_notice": {
        "display_name": "Beneficiary Periodic Notice",
        "description": "Send the periodic beneficiary notice your state requires and record it against the compliance deadline",
        "icon": "mail-check",
        "category": "distributions",
        "fields": [
            {"name": "notice_date", "label": "Notice Date", "type": "date", "required": False,
             "placeholder": "YYYY-MM-DD"},
            {"name": "trustee_name", "label": "Trustee Name(s)", "type": "text", "required": False,
             "placeholder": "Defaults to the trustees on the trust"},
            {"name": "trustee_contact", "label": "Trustee Contact (phone/email/address)", "type": "text", "required": False,
             "placeholder": "How beneficiaries can reach you with questions"},
            {"name": "additional_context", "label": "Additional Context", "type": "textarea", "required": False,
             "placeholder": "Any extra information to include in the notice"},
        ],
        "ai_prompt_template": (
            "Generate a formal periodic beneficiary notice letter for {trust_name}. "
            "Notice date: {notice_date}. Trustee: {trustee_name}. "
            "Trustee contact: {trustee_contact}. Additional context: {additional_context}. "
            "This letter informs beneficiaries that the trustee is providing the periodic "
            "notice required by the trust's state law, states the notice window, and invites "
            "beneficiaries to submit questions or objections to the trustee. Format as a professional letter."
        ),
    },

    "evaluate_distribution": {
        "display_name": "Evaluate Distribution Request",
        "description": "Structure the facts the trustees should consider when evaluating a distribution request — a record-keeping aid, not legal advice",
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
            "Summarize for the trustees' evaluation record a distribution request before {trust_name}. "
            "The meeting was held on {meeting_date}. Trustees present: {participants}. "
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

    # ─── Financial: Spending Authorization ──────────────────
    "spending_authorization": {
        "display_name": "Spending Authorization",
        "description": "Document trustee approval of an expenditure that exceeds the spending threshold",
        "icon": "shield-check",
        "category": "financial",
        "fields": [
            {"name": "expenditure_amount", "label": "Expenditure Amount", "type": "currency", "required": True},
            {"name": "expenditure_date", "label": "Expenditure Date", "type": "date", "required": True},
            {"name": "expenditure_purpose", "label": "Purpose of Expenditure", "type": "textarea", "required": True},
            {"name": "expenditure_vendor", "label": "Vendor/Payee", "type": "text", "required": False},
            {"name": "expenditure_source_account", "label": "Source Account", "type": "text", "required": False},
        ],
        "ai_prompt_template": (
            "Generate minutes documenting trustee approval of an expenditure for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Expenditure amount: {expenditure_amount}. Date: {expenditure_date}. "
            "Purpose: {expenditure_purpose}. Vendor/Payee: {expenditure_vendor}. "
            "Source account: {expenditure_source_account}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language. The WHEREAS clause should reference that "
            "this expenditure exceeds the trust's spending threshold and requires documented "
            "trustee approval per the trust's governance policy. The RESOLVED clause should "
            "authorize the expenditure and confirm it is in the best interest of the trust "
            "and its beneficiaries."
        ),
    },

    "reserve_account_resolution": {
        "display_name": "Reserve Account / Corpus Preservation",
        "description": "Establish or adjust a reserve policy preserving trust corpus against anticipated obligations",
        "icon": "piggy-bank",
        "category": "financial",
        "fields": [
            {"name": "reserve_purpose", "label": "Reserve Purpose", "type": "textarea", "required": True,
             "placeholder": "e.g., property tax and insurance obligations on the Elm Street parcel; anticipated capital repairs"},
            {"name": "reserve_amount", "label": "Reserve Amount / Target", "type": "currency", "required": True},
            {"name": "reserve_source", "label": "Funded From", "type": "text", "required": False,
             "placeholder": "e.g., trust checking account; monthly allocation from rental income"},
            {"name": "review_cadence", "label": "Review Cadence", "type": "select", "required": False,
             "options": ["quarterly", "semi-annual", "annual", "at each regular meeting"]},
        ],
        "ai_prompt_template": (
            "Generate minutes establishing or adjusting the reserve policy for {trust_name}. "
            "Meeting date: {meeting_date}. Trustees present: {participants}. "
            "Reserve purpose: {reserve_purpose}. Amount/target: {reserve_amount}. "
            "Funded from: {reserve_source}. Review cadence: {review_cadence}. "
            "Additional context: {additional_context}. "
            "Include WHEREAS/RESOLVED language: WHEREAS clauses recite the trustees' duty to preserve trust "
            "corpus and administer the trust for the benefit of its beneficiaries, and the identified "
            "obligations the reserve addresses; RESOLVED clauses record the reserve amount and funding source, "
            "set the review cadence, and direct the reserve's accounting treatment be recorded in the trust's "
            "books. The minutes record the trustees' preservation policy — corpus preservation serves the "
            "beneficiaries; the minutes do not determine any legal right."
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