# Shared Pydantic models and enums for TrustOffice API
from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import List, Optional, Literal, Union
from enum import Enum
import calendar
import re


# ==================== ENUMS ====================

class TrustType(str, Enum):
    # Legacy values (kept for backward compatibility with existing records)
    family = "family"
    institutional = "institutional"
    # Current options
    revocable_living = "revocable_living"
    irrevocable_family = "irrevocable_family"
    charitable = "charitable"
    charitable_remainder = "charitable_remainder"
    business = "business"
    ecclesiastical = "ecclesiastical"
    special_needs = "special_needs"
    spendthrift = "spendthrift"
    testamentary = "testamentary"
    life_insurance = "life_insurance"
    land = "land"
    other = "other"

class EntityType(str, Enum):
    trust = "Trust"
    holding_llc = "Holding LLC"
    operating_llc = "Operating LLC"

class RelationshipType(str, Enum):
    owns = "owns"
    controls = "controls"
    receives_distributions_from = "receives_distributions_from"
    pays_compensation_to = "pays_compensation_to"

class TaskType(str, Enum):
    annual_review = "annual_review"
    quarterly_review = "quarterly_review"
    compensation_review = "compensation_review"
    distribution_review = "distribution_review"
    insurance_compliance = "insurance_compliance"
    transaction_review = "transaction_review"
    custom = "custom"
    tax_filing_1041 = "tax_filing_1041"
    tax_filing_k1 = "tax_filing_k1"

class MinutesType(str, Enum):
    annual = "annual"
    quarterly = "quarterly"
    compensation = "compensation"
    distribution = "distribution"
    solvency = "solvency"
    general = "general"

class GuidedMinutesType(str, Enum):
    annual = "annual"
    quarterly = "quarterly"
    general = "general"

class PurposeClassification(str, Enum):
    distribution = "distribution"
    compensation = "compensation"
    expense = "expense"
    other = "other"

class HealthColor(str, Enum):
    red = "red"
    yellow = "yellow"
    green = "green"

class PlanType(str, Enum):
    # New 3-tier system
    trustee = "trustee"
    estate = "estate"
    advisor = "advisor"
    wingpoint = "wingpoint"  # WingPoint exclusive annual plan
    free = "free"
    forever_free = "forever_free"
    # Legacy (for migration compatibility)
    trial = "trial"
    monthly = "monthly"
    annual = "annual"

class SubscriptionStatus(str, Enum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    expired = "expired"

class AssetCategory(str, Enum):
    real_property = "real_property"
    personal_property = "personal_property"
    financial_accounts = "financial_accounts"
    business_interests = "business_interests"
    digital_assets = "digital_assets"
    intellectual_property = "intellectual_property"
    notes_receivable = "notes_receivable"
    other_property = "other_property"

class MinutesTemplateType(str, Enum):
    blank = "blank"
    initial_trustee_meeting = "initial_trustee_meeting"
    general_meeting = "general_meeting"
    distribution_to_beneficiaries = "distribution_to_beneficiaries"
    acceptance_of_property = "acceptance_of_property"
    disposition_of_asset = "disposition_of_asset"
    appointment_additional_trustee = "appointment_additional_trustee"
    appointment_successor_trustee = "appointment_successor_trustee"
    designation_of_beneficiaries = "designation_of_beneficiaries"
    bank_account_authorization = "bank_account_authorization"
    change_of_situs = "change_of_situs"
    benevolence_approval = "benevolence_approval"
    beneficiary_distribution_notice = "beneficiary_distribution_notice"
    evaluate_distribution = "evaluate_distribution"
    # New templates added (batch 1)
    investment_policy = "investment_policy"
    loan_authorization = "loan_authorization"
    insurance_authorization = "insurance_authorization"
    annual_review = "annual_review"
    quarterly_review = "quarterly_review"
    trustee_compensation = "trustee_compensation"
    trustee_resignation = "trustee_resignation"
    beneficiary_request_denial = "beneficiary_request_denial"
    hems_distribution = "hems_distribution"
    beneficiary_loan = "beneficiary_loan"
    # New templates added (batch 2)
    trust_amendment = "trust_amendment"
    power_of_attorney = "power_of_attorney"
    trust_termination = "trust_termination"
    real_estate_purchase = "real_estate_purchase"
    business_interest_acquisition = "business_interest_acquisition"
    real_estate_lease = "real_estate_lease"
    fiscal_year_election = "fiscal_year_election"
    tax_filing_authorization = "tax_filing_authorization"
    emergency_ratification = "emergency_ratification"
    conflict_of_interest = "conflict_of_interest"
    # Conveyance documents
    bill_of_sale = "bill_of_sale"
    assignment_of_personal_property = "assignment_of_personal_property"
    general_assignment = "general_assignment"

class AssetStatus(str, Enum):
    active = "active"
    disposed = "disposed"

class BenevolencePurpose(str, Enum):
    medical = "medical"
    housing = "housing"
    education = "education"
    food_necessities = "food_necessities"
    utilities = "utilities"
    transportation = "transportation"
    emergency = "emergency"
    spiritual = "spiritual"
    other = "other"

class CertificateStatus(str, Enum):
    active = "active"
    cancelled = "cancelled"
    replaced = "replaced"


class ClassBeneficiaryType(str, Enum):
    """Standard trust class beneficiary designations"""
    children = "children"
    descendants = "descendants"
    issue = "issue"
    heirs = "heirs"
    heirs_at_law = "heirs_at_law"
    blood_relatives = "blood_relatives"
    per_stirpes = "per_stirpes"
    per_capita = "per_capita"
    custom = "custom"


# ==================== USER MODELS ====================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    referral_code: Optional[str] = None  # Optional referral code from friend
    wp_ref: Optional[str] = None  # WingPoint reference ID for attribution
    wp_trust_name: Optional[str] = None  # WingPoint trust name (pre-fill)
    utm_source: Optional[str] = None  # Marketing attribution (ad campaign, etc.)
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    referrer: Optional[str] = None  # document.referrer from the browser

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: str
    is_admin: bool = False
    is_stats_user: bool = False
    wp_ref: Optional[str] = None
    is_wingpoint: bool = False

class ProfileUpdate(BaseModel):
    name: Optional[str] = None

class NotificationPreferences(BaseModel):
    minutes_created: bool = True
    distribution_created: bool = True
    distribution_approved: bool = True
    task_reminders: bool = True
    task_overdue: bool = True
    subscription_updates: bool = True
    weekly_digest: bool = False

class NotificationPreferencesUpdate(BaseModel):
    minutes_created: Optional[bool] = None
    distribution_created: Optional[bool] = None
    distribution_approved: Optional[bool] = None
    task_reminders: Optional[bool] = None
    task_overdue: Optional[bool] = None
    subscription_updates: Optional[bool] = None
    weekly_digest: Optional[bool] = None

class UserPreferences(BaseModel):
    hide_watermark: bool = False
    admin_access_locked: bool = False

class UserPreferencesUpdate(BaseModel):
    hide_watermark: Optional[bool] = None
    admin_access_locked: Optional[bool] = None


# ==================== PASSWORD RESET MODELS ====================

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


# ==================== TRUST MODELS ====================

class TrustCreate(BaseModel):
    name: str
    trust_type: TrustType = TrustType.family
    jurisdiction: str = ""
    role: Optional[str] = "Trustee"
    start_date: Optional[str] = None
    trustees: Optional[Union[str, List[str]]] = None
    authority_clause: Optional[str] = None
    successor_trustee_name: Optional[str] = None
    successor_trustee_email: Optional[str] = None
    successor_trustee_phone: Optional[str] = None
    successor_trustee_relationship: Optional[str] = None
    successor_trustee_notes: Optional[str] = None
    secondary_successor_trustee_name: Optional[str] = None
    secondary_successor_trustee_email: Optional[str] = None
    secondary_successor_trustee_phone: Optional[str] = None
    secondary_successor_trustee_relationship: Optional[str] = None
    trust_protector_name: Optional[str] = None
    trust_protector_email: Optional[str] = None
    trust_protector_phone: Optional[str] = None
    trust_protector_relationship: Optional[str] = None
    trust_protector_powers: List[str] = []
    trust_protector_status: Optional[str] = None
    grantor_name: Optional[str] = None
    attorney_name: Optional[str] = None
    attorney_phone: Optional[str] = None
    attorney_email: Optional[str] = None
    cpa_name: Optional[str] = None
    cpa_phone: Optional[str] = None
    cpa_email: Optional[str] = None
    financial_advisor_name: Optional[str] = None
    financial_advisor_phone: Optional[str] = None
    financial_advisor_email: Optional[str] = None
    successor_instructions: Optional[str] = None
    document_location: Optional[str] = None
    ein: Optional[str] = None
    state_code: Optional[str] = None
    tax_year_end_month: Optional[int] = Field(None, ge=1, le=12)
    tax_year_end_day: Optional[int] = Field(None, ge=1, le=31)
    is_fiscal_year: Optional[bool] = None
    description: Optional[str] = None
    review_cadence: Optional[str] = "quarterly"
    benevolence_mission: Optional[str] = None
    determination_letter_date: Optional[str] = None

    @model_validator(mode="after")
    def validate_tax_fields(self):
        # Coerce state_code to uppercase if present
        if self.state_code is not None:
            self.state_code = self.state_code.upper()
        # Validate EIN format
        if self.ein is not None and self.ein:
            cleaned = self.ein.replace("-", "")
            if not re.match(r"^\d{9}$", cleaned):
                raise ValueError("EIN must be 9 digits (format: XX-XXXXXXX)")
            self.ein = f"{cleaned[:2]}-{cleaned[2:]}"
        # Validate month/day coherence
        if self.tax_year_end_month is not None and self.tax_year_end_day is not None:
            max_day = calendar.monthrange(2024, self.tax_year_end_month)[1]
            if self.tax_year_end_day > max_day:
                raise ValueError(f"Invalid day {self.tax_year_end_day} for month {self.tax_year_end_month} (max {max_day})")
        # Require month/day when fiscal year is set
        if self.is_fiscal_year is True:
            if self.tax_year_end_month is None or self.tax_year_end_day is None:
                raise ValueError("tax_year_end_month and tax_year_end_day are required for fiscal year trusts")
        return self


class TrustUpdate(BaseModel):
    name: Optional[str] = None
    trust_type: Optional[TrustType] = None
    jurisdiction: Optional[str] = None
    benevolence_enabled: Optional[bool] = None
    governance_settings: Optional[dict] = None
    tax_status: Optional[str] = None
    start_date: Optional[str] = None
    trustees: Optional[Union[str, List[str]]] = None
    authority_clause: Optional[str] = None
    successor_trustee_name: Optional[str] = None
    successor_trustee_email: Optional[str] = None
    successor_trustee_phone: Optional[str] = None
    successor_trustee_relationship: Optional[str] = None
    successor_trustee_notes: Optional[str] = None
    secondary_successor_trustee_name: Optional[str] = None
    secondary_successor_trustee_email: Optional[str] = None
    secondary_successor_trustee_phone: Optional[str] = None
    secondary_successor_trustee_relationship: Optional[str] = None
    trust_protector_name: Optional[str] = None
    trust_protector_email: Optional[str] = None
    trust_protector_phone: Optional[str] = None
    trust_protector_relationship: Optional[str] = None
    trust_protector_powers: Optional[List[str]] = None
    trust_protector_status: Optional[str] = None
    grantor_name: Optional[str] = None
    attorney_name: Optional[str] = None
    attorney_phone: Optional[str] = None
    attorney_email: Optional[str] = None
    cpa_name: Optional[str] = None
    cpa_phone: Optional[str] = None
    cpa_email: Optional[str] = None
    financial_advisor_name: Optional[str] = None
    financial_advisor_phone: Optional[str] = None
    financial_advisor_email: Optional[str] = None
    successor_instructions: Optional[str] = None
    document_location: Optional[str] = None
    ein: Optional[str] = None
    state_code: Optional[str] = None
    tax_year_end_month: Optional[int] = Field(None, ge=1, le=12)
    tax_year_end_day: Optional[int] = Field(None, ge=1, le=31)
    is_fiscal_year: Optional[bool] = None
    description: Optional[str] = None
    review_cadence: Optional[str] = None
    benevolence_mission: Optional[str] = None
    determination_letter_date: Optional[str] = None

    @model_validator(mode="after")
    def validate_tax_fields(self):
        if self.state_code is not None:
            self.state_code = self.state_code.upper()
        if self.ein is not None and self.ein:
            cleaned = self.ein.replace("-", "")
            if not re.match(r"^\d{9}$", cleaned):
                raise ValueError("EIN must be 9 digits (format: XX-XXXXXXX)")
            self.ein = f"{cleaned[:2]}-{cleaned[2:]}"
        if self.tax_year_end_month is not None and self.tax_year_end_day is not None:
            max_day = calendar.monthrange(2024, self.tax_year_end_month)[1]
            if self.tax_year_end_day > max_day:
                raise ValueError(f"Invalid day {self.tax_year_end_day} for month {self.tax_year_end_month} (max {max_day})")
        if self.is_fiscal_year is True:
            if self.tax_year_end_month is None or self.tax_year_end_day is None:
                raise ValueError("tax_year_end_month and tax_year_end_day are required for fiscal year trusts")
        return self


class TrustResponse(BaseModel):
    trust_id: str
    user_id: str
    name: str
    trust_type: Optional[str] = "irrevocable"
    jurisdiction: Optional[str] = ""
    benevolence_enabled: Optional[bool] = False
    governance_settings: Optional[dict] = None
    tax_status: Optional[str] = "private"
    created_at: str
    governance_score: int = 0
    trustees: Optional[Union[str, List[str]]] = None
    start_date: Optional[str] = None
    authority_clause: Optional[str] = None
    successor_trustee_name: Optional[str] = None
    successor_trustee_email: Optional[str] = None
    successor_trustee_phone: Optional[str] = None
    successor_trustee_relationship: Optional[str] = None
    successor_trustee_notes: Optional[str] = None
    secondary_successor_trustee_name: Optional[str] = None
    secondary_successor_trustee_email: Optional[str] = None
    secondary_successor_trustee_phone: Optional[str] = None
    secondary_successor_trustee_relationship: Optional[str] = None
    trust_protector_name: Optional[str] = None
    trust_protector_email: Optional[str] = None
    trust_protector_phone: Optional[str] = None
    trust_protector_relationship: Optional[str] = None
    trust_protector_powers: Optional[List[str]] = None
    trust_protector_status: Optional[str] = None
    grantor_name: Optional[str] = None
    attorney_name: Optional[str] = None
    attorney_phone: Optional[str] = None
    attorney_email: Optional[str] = None
    cpa_name: Optional[str] = None
    cpa_phone: Optional[str] = None
    cpa_email: Optional[str] = None
    financial_advisor_name: Optional[str] = None
    financial_advisor_phone: Optional[str] = None
    financial_advisor_email: Optional[str] = None
    successor_instructions: Optional[str] = None
    document_location: Optional[str] = None
    role: Optional[str] = "Trustee"
    # Additional fields for tax and state compliance
    ein: Optional[str] = None
    state_code: Optional[str] = None
    tax_year_end_month: Optional[int] = Field(None, ge=1, le=12)
    tax_year_end_day: Optional[int] = Field(None, ge=1, le=31)
    is_fiscal_year: Optional[bool] = None
    description: Optional[str] = None
    review_cadence: Optional[str] = "quarterly"
    benevolence_mission: Optional[str] = None
    determination_letter_date: Optional[str] = None


# ==================== ENTITY MODELS ====================

class EntityCreate(BaseModel):
    trust_id: str
    name: str
    entity_type: EntityType
    legal_name: str = ""
    formation_date: Optional[str] = None
    governing_law: str = ""
    ein: Optional[str] = None
    trustee_names: str = ""
    beneficiary_standard: str = ""
    article_ref_distribution: str = ""
    article_ref_compensation: str = ""
    article_ref_amendment: str = ""
    oversight_required: bool = False
    member_names: str = ""
    manager_names: str = ""
    article_ref_authority: str = ""
    article_ref_profit_distribution: str = ""

class EntityResponse(BaseModel):
    entity_id: str
    trust_id: str
    name: str
    entity_type: str
    legal_name: str
    formation_date: Optional[str] = None
    governing_law: str
    ein: Optional[str] = None
    trustee_names: str
    beneficiary_standard: str
    article_ref_distribution: str
    article_ref_compensation: str
    article_ref_amendment: str
    oversight_required: bool
    member_names: str
    manager_names: str
    article_ref_authority: str
    article_ref_profit_distribution: str
    created_at: str

class EntityRelationshipCreate(BaseModel):
    trust_id: str
    parent_entity_id: str
    child_entity_id: str
    relationship_type: RelationshipType
    ownership_percentage: Optional[float] = Field(None, ge=0, le=100)
    notes: str = ""

class EntityRelationshipResponse(BaseModel):
    relationship_id: str
    trust_id: str
    parent_entity_id: str
    child_entity_id: str
    relationship_type: str
    ownership_percentage: Optional[float] = None
    notes: str
    source: Optional[str] = None
    certificate_id: Optional[str] = None
    created_at: str


# ==================== TRUST UNITS MODELS ====================

class TrustUnitsSettingsCreate(BaseModel):
    trust_id: str
    total_authorized_units: int = 100
    unit_label: str = "Certificate Unit"
    allow_fractional: bool = False

class TrustUnitsSettingsUpdate(BaseModel):
    total_authorized_units: Optional[int] = None
    unit_label: Optional[str] = None
    allow_fractional: Optional[bool] = None
    allocation_mode: Optional[str] = None
    authorized_units_ceiling: Optional[int] = None
    unlimited_units: Optional[bool] = None
    class_distribution_convention: Optional[str] = None

class TrustUnitsSettingsResponse(BaseModel):
    trust_id: str
    total_authorized_units: int
    unit_label: str
    allow_fractional: bool
    allocation_mode: str = "percentage"
    authorized_units_ceiling: Optional[int] = 100
    unlimited_units: bool = False
    class_distribution_convention: str = "per_capita"
    created_at: str
    updated_at: Optional[str] = None

class TrustUnitCertificateCreate(BaseModel):
    trust_id: str
    holder_name: str
    holder_identifier: Optional[str] = None
    holder_type: str = "individual"  # "individual", "trust", "llc", "corporation", "charity", "estate", "other"
    holder_trust_id: Optional[str] = None  # When holder_type="trust", links to an actual trust record
    units: float
    issue_date: str
    notes: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None

class TrustUnitCertificateUpdate(BaseModel):
    holder_name: Optional[str] = None
    holder_identifier: Optional[str] = None
    holder_type: Optional[str] = None
    holder_trust_id: Optional[str] = None
    units: Optional[float] = None
    status: Optional[CertificateStatus] = None
    notes: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    replacement_reason: Optional[str] = Field(None, max_length=1000)
    effective_date: Optional[str] = None

class TrustUnitCertificateResponse(BaseModel):
    certificate_id: str
    trust_id: str
    holder_name: str
    holder_identifier: Optional[str]
    holder_type: str = "individual"
    holder_trust_id: Optional[str] = None
    units: float
    percentage: float
    issue_date: str
    certificate_number: str
    status: str
    replaced_by_certificate_id: Optional[str] = None
    supersedes_certificate_id: Optional[str] = None
    version: int = 1
    notes: str
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    replacement_reason: Optional[str] = None
    effective_date: Optional[str] = None

class TrustUnitTransferCreate(BaseModel):
    trust_id: str
    from_holder: Optional[str] = None
    from_certificate_id: Optional[str] = None
    to_holder: str
    to_certificate_id: Optional[str] = None
    units: float
    reason: str
    minutes_record_id: Optional[str] = None

class TrustUnitTransferResponse(BaseModel):
    transfer_id: str
    trust_id: str
    from_holder: Optional[str]
    to_holder: str
    units: float
    reason: str
    minutes_record_id: Optional[str]
    created_at: str

class TrustUnitsSummaryResponse(BaseModel):
    settings: TrustUnitsSettingsResponse
    certificates: List[TrustUnitCertificateResponse]
    total_issued_units: float
    remaining_units: float
    active_certificate_count: int

class BootstrapFromMinutesResponse(BaseModel):
    success: bool
    message: str
    certificates_created: int
    certificates: List[TrustUnitCertificateResponse]


# ==================== GOVERNANCE TASK MODELS ====================

class ChecklistItem(BaseModel):
    text: str
    completed: bool = False

class GovernanceTaskCreate(BaseModel):
    trust_id: str
    task_type: TaskType
    due_date: str
    description: str = ""
    checklist_items: Optional[List[ChecklistItem]] = None

class GovernanceTaskResponse(BaseModel):
    task_id: str
    trust_id: str
    task_type: str
    due_date: str
    completed_at: Optional[str] = None
    status: str
    description: str
    checklist_items: List[dict] = []
    created_at: str


# ==================== MINUTES MODELS ====================

class MinutesCreate(BaseModel):
    trust_id: str
    minutes_type: MinutesType
    meeting_date: str
    participants_text: str
    decisions_text: str
    distribution_id: Optional[str] = None
    compensation_payment_id: Optional[str] = None
    # New fields for minutes redesign
    template_type: Optional[str] = None
    sections: Optional[List[dict]] = None
    template_data: Optional[dict] = None
    status: str = "finalized"
    is_retroactive: bool = False
    retroactive_reason: Optional[str] = None
    retroactive_trustees_aware: Optional[str] = None
    retroactive_type: Optional[str] = None
    manually_edited: bool = False

class MinutesResponse(BaseModel):
    minutes_id: str
    trust_id: str
    minutes_type: str
    meeting_date: str
    participants_text: str
    decisions_text: str
    created_at: str
    other_attendees_text: Optional[str] = None
    source: Optional[str] = None
    updated_at: Optional[str] = None
    # New fields for minutes redesign
    template_type: Optional[str] = None
    sections: List[dict] = []
    template_data: Optional[dict] = None
    status: str = "finalized"
    is_retroactive: bool = False
    retroactive_reason: Optional[str] = None
    retroactive_trustees_aware: Optional[str] = None
    retroactive_type: Optional[str] = None
    manually_edited: bool = False

class MinutesResolution(BaseModel):
    title: str
    whereas_clauses: List[str]
    resolved_clauses: List[str]
    vote: str = "Unanimous approval"
    effective_date: str = "Immediately upon adoption"

class MinutesTemplateData(BaseModel):
    minute_number: str = ""
    meeting_date: str = ""
    meeting_time: str = ""
    meeting_location: str = ""
    meeting_type: str = "unanimous_written_consent"
    trustees_present: List[str] = []
    protector_present: Optional[str] = None
    quorum_met: bool = True
    trust_formation_date: str = ""
    # Backward compat: accept old field name from existing data
    trust_indenture_date: Optional[str] = None
    resolutions: List[dict] = []
    distribution_total: Optional[float] = None
    distribution_items: List[dict] = []
    distribution_date: Optional[str] = None
    distribution_characterization: str = "income"
    property_description: str = ""
    property_value: Optional[float] = None
    grantor_name: str = ""
    conveyance_date: str = ""
    add_to_schedule_a: bool = True
    schedule_a_category: Optional[str] = None
    property_identifier: str = ""
    property_location: str = ""
    disposition_asset_id: Optional[str] = None
    disposition_asset_description: str = ""
    disposition_reason: str = ""
    disposition_date: str = ""
    disposition_value: Optional[float] = None
    disposition_recipient: str = ""
    disposition_notes: str = ""
    update_schedule_a: bool = True
    appointment_type: str = ""
    departing_trustee_name: str = ""
    departing_reason: str = ""
    new_trustee_name: str = ""
    new_trustee_gender: str = "man"
    signature_requirement: str = "any_one"
    signature_threshold: Optional[float] = None
    banking_powers_granted: bool = True
    executive_trustee: str = ""
    secretary_trustee: str = ""
    treasurer_trustee: str = ""

    @model_validator(mode='after')
    def map_legacy_indenture_date(self):
        """Map trust_indenture_date (legacy) → trust_formation_date (current)."""
        if self.trust_indenture_date and not self.trust_formation_date:
            self.trust_formation_date = self.trust_indenture_date
        return self


class MinutesTemplateCreate(BaseModel):
    trust_id: str
    template_type: MinutesTemplateType
    template_data: dict = {}

class MinutesTemplateUpdate(BaseModel):
    generated_document: Optional[str] = None
    status: Optional[str] = None
    template_data: Optional[dict] = None

class MinutesTemplateResponse(BaseModel):
    minutes_id: str
    trust_id: str
    template_type: str
    template_data: dict
    generated_document: str
    original_document: str
    meeting_date: str
    status: str
    created_at: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


# ==================== UNIFIED MINUTES REDESIGN MODELS ====================

class MinutesSection(BaseModel):
    """A single section within a multi-section minutes document"""
    section_id: str
    template_type: str
    title: str
    template_data: dict = {}
    generated_text: str = ""

class MinutesDraftRequest(BaseModel):
    """Unified AI minutes draft request — merges GuidedMinutesDraftRequest + /ai/minutes-draft"""
    trust_id: str
    template_type: Optional[str] = None  # MinutesTemplateType value
    minutes_type: Optional[str] = None   # MinutesType for backward compat
    meeting_date: str
    participants: List[str] = []
    other_attendees: List[str] = []
    # Quick minutes mode (bullets)
    agenda_items: List[str] = []
    key_decisions: List[str] = []
    additional_context: Optional[str] = None
    # Template mode (structured fields)
    template_data: Optional[dict] = None
    # Retroactive
    is_retroactive: bool = False
    retroactive_reason: Optional[str] = None
    # Section mode (for multi-section)
    section_context: Optional[str] = None

class MinutesDraftResponse(BaseModel):
    """Response model for unified AI minutes draft — same as GuidedMinutesDraftResponse + template_type"""
    suggested_title: str = Field(..., description="Suggested title for the minutes")
    draft_body: str = Field(..., description="The main minutes text body")
    cautions: List[str] = Field(default_factory=list, description="Warnings or notes for the trustee")
    minutes_type: str
    meeting_date: str
    participants_text: str
    template_type: Optional[str] = None

class MinutesAutosaveRequest(BaseModel):
    """Subset of MinutesCreate for autosave draft operations"""
    trust_id: str
    minutes_type: str
    template_type: Optional[str] = None
    meeting_date: str
    participants_text: str
    decisions_text: str
    sections: List[dict] = []
    template_data: Optional[dict] = None
    is_retroactive: bool = False
    retroactive_reason: Optional[str] = None
    retroactive_trustees_aware: Optional[str] = None
    retroactive_type: Optional[str] = None
    status: str = "draft"
    minutes_id: Optional[str] = None  # If provided, update existing draft; otherwise create new


# ==================== SCHEDULE A MODELS ====================

class ScheduleAItemCreate(BaseModel):
    trust_id: str
    category: AssetCategory
    description: str
    identifier: str = ""
    location: str = ""
    approximate_value: Optional[float] = Field(None, ge=0)
    date_conveyed: str
    notes: str = ""
    minutes_ref: Optional[str] = None

class ScheduleAItemUpdate(BaseModel):
    description: Optional[str] = None
    identifier: Optional[str] = None
    location: Optional[str] = None
    approximate_value: Optional[float] = Field(None, ge=0)
    date_conveyed: Optional[str] = None
    notes: Optional[str] = None
    minutes_ref: Optional[str] = None

class ScheduleAItemResponse(BaseModel):
    item_id: str
    trust_id: str
    category: str
    description: str
    identifier: str
    location: str
    approximate_value: Optional[float]
    date_conveyed: str
    notes: str
    created_at: str
    updated_at: Optional[str] = None
    status: str = "active"
    minutes_ref: Optional[str] = None
    disposition_minutes_ref: Optional[str] = None
    disposition_date: Optional[str] = None
    disposition_notes: Optional[str] = None


# ==================== DISTRIBUTION MODELS ====================

class DistributionCreate(BaseModel):
    trust_id: str
    beneficiary_name: str
    amount: float = Field(..., ge=0)
    date: str
    purpose_classification: PurposeClassification
    authority_clause_ref: str = ""
    notes: str = ""
    trustee_name: str = ""
    is_benevolence: bool = False
    benevolence_recipient_name: Optional[str] = None
    benevolence_need_description: Optional[str] = None
    benevolence_notes: Optional[str] = None
    policy_version_id: Optional[str] = None

class DistributionApprove(BaseModel):
    solvency_confirmed: bool
    recusal_acknowledged: bool

class DistributionResponse(BaseModel):
    distribution_id: str
    trust_id: str
    beneficiary_name: str
    amount: float
    date: str
    purpose_classification: str
    authority_clause_ref: str
    notes: str
    solvency_confirmed: bool
    recusal_acknowledged: bool
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    trustee_name: str = ""
    minutes_record_id: Optional[str] = None
    created_at: str
    is_benevolence: bool = False
    benevolence_recipient_name: Optional[str] = None
    benevolence_need_description: Optional[str] = None
    benevolence_notes: Optional[str] = None
    distribution_standard: Optional[str] = None
    beneficiary_not_verified: bool = False
    policy_version_id: Optional[str] = None
    policy_limit_warning: Optional[str] = None


class DistributionUpdate(BaseModel):
    beneficiary_name: Optional[str] = None
    amount: Optional[float] = Field(None, ge=0)
    date: Optional[str] = None
    purpose_classification: Optional[PurposeClassification] = None
    authority_clause_ref: Optional[str] = None
    notes: Optional[str] = None
    is_benevolence: Optional[bool] = None
    benevolence_recipient_name: Optional[str] = None
    benevolence_need_description: Optional[str] = None
    benevolence_notes: Optional[str] = None

class DistributionStatusUpdate(BaseModel):
    status: str

class BenevolenceMonthlyAggregate(BaseModel):
    month: str
    total_amount: float
    count: int

class BenevolenceYearlyAggregate(BaseModel):
    year: int
    total_amount: float
    count: int

class BenevolenceLogResponse(BaseModel):
    trust_id: str
    trust_name: str
    distributions: List[DistributionResponse]
    monthly_aggregates: List[BenevolenceMonthlyAggregate]
    yearly_aggregates: List[BenevolenceYearlyAggregate]
    total_all_time: float
    total_count: int
    incomplete_documentation_count: int


# ==================== BENEVOLENCE POLICY MODELS ====================

class AssistanceTypeConfig(BaseModel):
    """One allowable type of assistance within a policy"""
    purpose: BenevolencePurpose          # reuses existing enum
    label: str                            # display name, e.g. "Medical Expenses"
    is_allowed: bool = True               # True = covered, False = explicitly excluded
    per_recipient_limit: Optional[float] = None   # e.g. 500.00 (None = no limit)
    per_recipient_period: Optional[str] = None     # "annual" | "lifetime" | "per_request"
    notes: str = ""


class CommitteeMember(BaseModel):
    name: str
    role: str = "member"                   # "chair" | "secretary" | "member"
    email: Optional[str] = None


class EligibilityCriterion(BaseModel):
    criterion: str                         # e.g. "Must reside within 50 miles"
    is_required: bool = True               # hard requirement vs. preference


class DocumentationRequirement(BaseModel):
    item: str                              # e.g. "Receipt for medical bill"
    is_required: bool = True


class BenevolencePolicyCreate(BaseModel):
    trust_id: str
    version_label: str = "1.0"             # user-facing version, e.g. "1.0", "1.1", "2.0"
    charitable_class: str                  # IRS-required: who can receive
    charitable_class_description: str = "" # broader description
    eligibility_criteria: List[EligibilityCriterion] = []
    assistance_types: List[AssistanceTypeConfig] = []
    per_recipient_annual_limit: Optional[float] = None  # global cap across all types
    approval_process: str = ""             # free-text description of approval workflow
    approval_threshold: Optional[float] = None  # amounts below this = single approver; above = committee
    committee_members: List[CommitteeMember] = []
    documentation_requirements: List[DocumentationRequirement] = []
    designated_gift_prohibition: str = "No earmarked contributions for specific individuals will be accepted."
    employee_benevolence_note: str = ""    # IRC §102 / §139 taxability note
    board_approval_date: Optional[str] = None     # ISO date string
    board_approval_reference: Optional[str] = None  # minutes_id link to approving minutes
    effective_date: str                    # ISO date — when this version takes effect
    supersedes_version_id: Optional[str] = None   # policy_version_id of prior version
    notes: str = ""


class BenevolencePolicyUpdate(BaseModel):
    """Used for editing a DRAFT version only — published versions are immutable"""
    version_label: Optional[str] = None
    charitable_class: Optional[str] = None
    charitable_class_description: Optional[str] = None
    eligibility_criteria: Optional[List[EligibilityCriterion]] = None
    assistance_types: Optional[List[AssistanceTypeConfig]] = None
    per_recipient_annual_limit: Optional[float] = None
    approval_process: Optional[str] = None
    approval_threshold: Optional[float] = None
    committee_members: Optional[List[CommitteeMember]] = None
    documentation_requirements: Optional[List[DocumentationRequirement]] = None
    designated_gift_prohibition: Optional[str] = None
    employee_benevolence_note: Optional[str] = None
    board_approval_date: Optional[str] = None
    board_approval_reference: Optional[str] = None
    effective_date: Optional[str] = None
    notes: Optional[str] = None


class BenevolencePolicyResponse(BaseModel):
    policy_id: str                         # unique ID for the policy (one per trust)
    trust_id: str
    user_id: str
    current_version_id: str                # policy_version_id of the active version
    current_version_label: str
    current_version_status: str            # "draft" | "published" | "superseded"
    created_at: str
    updated_at: Optional[str] = None


class BenevolencePolicyVersionResponse(BaseModel):
    policy_version_id: str
    policy_id: str
    trust_id: str
    user_id: str
    version_label: str
    version_number: int                    # auto-incremented (1, 2, 3...)
    status: str                            # "draft" | "published" | "superseded"
    charitable_class: str
    charitable_class_description: str
    eligibility_criteria: List[dict]       # stored as list of dicts
    assistance_types: List[dict]           # stored as list of dicts
    per_recipient_annual_limit: Optional[float]
    approval_process: str
    approval_threshold: Optional[float]
    committee_members: List[dict]
    documentation_requirements: List[dict]
    designated_gift_prohibition: str
    employee_benevolence_note: str
    board_approval_date: Optional[str]
    board_approval_reference: Optional[str]
    effective_date: str
    supersedes_version_id: Optional[str]
    notes: str
    published_at: Optional[str] = None     # timestamp when status → "published"
    created_at: str
    updated_at: Optional[str] = None
    created_by: str                        # user_id of creator


# Patch BenevolenceRecord models to link to policy version
class BenevolenceRecordCreate(BaseModel):
    trust_id: str
    beneficiary_name: str
    beneficiary_type: str = "individual"
    purpose: BenevolencePurpose
    purpose_description: str
    amount: float
    date: str
    approved_by: List[str]
    approval_method: str = "unanimous"
    minutes_id: Optional[str] = None
    notes: str = ""
    status: str = "approved"
    policy_version_id: Optional[str] = None    # links to active policy at time of creation


class BenevolenceRecordUpdate(BaseModel):
    beneficiary_name: Optional[str] = None
    beneficiary_type: Optional[str] = None
    purpose: Optional[BenevolencePurpose] = None
    purpose_description: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    approved_by: Optional[List[str]] = None
    approval_method: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    policy_version_id: Optional[str] = None


class BenevolenceRecordResponse(BaseModel):
    record_id: str
    trust_id: str
    beneficiary_name: str
    beneficiary_type: str
    purpose: str
    purpose_description: str
    amount: float
    date: str
    approved_by: List[str]
    approval_method: str
    minutes_id: Optional[str]
    notes: str
    status: str
    created_at: str
    updated_at: Optional[str] = None
    policy_version_id: Optional[str] = None


# ==================== COMPENSATION MODELS ====================

class CompensationPlanCreate(BaseModel):
    trust_id: str
    trustee_name: str = ""
    role: str = ""
    annual_amount: float = Field(0, ge=0)
    annual_approved_amount: float = Field(0, ge=0)
    fee_type: str = "fixed"
    effective_date: str
    notes: str = ""
    is_primary: Optional[bool] = None  # If None, auto-determined based on context

class CompensationPlanResponse(BaseModel):
    plan_id: str
    trust_id: str
    trustee_name: str = ""
    role: str = ""
    annual_fee: Optional[float] = None
    annual_amount: Optional[float] = None
    annual_approved_amount: Optional[float] = None
    fee_type: str = "fixed"
    effective_date: str
    year: Optional[int] = None
    is_primary: Optional[bool] = None
    notes: str = ""
    created_at: str
    updated_at: Optional[str] = None

class CompensationPaymentCreate(BaseModel):
    trust_id: str
    amount: float = Field(..., ge=0)
    date: str
    classification_text: str = ""
    trustee_name: Optional[str] = None

class CompensationPaymentResponse(BaseModel):
    payment_id: str
    trust_id: str
    amount: float
    date: Optional[str] = None  # Optional for legacy payments
    classification_text: str = ""  # Default empty for legacy payments
    trustee_name: Optional[str] = None
    exceeds_plan_flag: bool = False  # Default false for legacy payments
    minutes_record_id: Optional[str] = None
    created_at: str


# ==================== HEALTH SCORE MODELS ====================

class HealthScoreCriterion(BaseModel):
    name: str
    description: str
    points: int
    max_points: int = 15
    achieved: bool
    no_data: bool = False  # True when there's nothing to measure yet

class RiskFinding(BaseModel):
    type: str
    severity: str  # critical, high, medium, low
    module: str
    title: str
    detail: str = ""
    action: str = ""
    deeplink: str = ""
    penalty: int = 0  # per-finding penalty (negative)

class RiskPenaltyBreakdown(BaseModel):
    critical: dict  # {"count": int, "penalty": int}
    high: dict
    medium: dict
    low: dict

class HealthScoreResponse(BaseModel):
    trust_id: str
    total_score: int
    max_score: int = 115
    color: str
    base_score: int = 0
    risk_penalty: int = 0
    has_critical_risk: bool = False
    criteria: List[HealthScoreCriterion]
    risk_findings: List[RiskFinding] = []
    risk_penalty_breakdown: Optional[RiskPenaltyBreakdown] = None
    calculated_at: str


# ==================== DASHBOARD MODELS ====================

class GovernanceInsight(BaseModel):
    type: str
    criterion_name: str
    title: str
    description: str
    action_path: str
    action_label: str
    points: int = 15

class DismissedInsightCreate(BaseModel):
    trust_id: str
    criterion_name: str

class DismissedInsightResponse(BaseModel):
    dismiss_id: str
    user_id: str
    trust_id: str
    criterion_name: str
    dismissed_at: str

class DashboardStats(BaseModel):
    total_decisions: int
    pending_reviews: int
    total_distributions: int
    ytd_distributions_amount: float

class DashboardResponse(BaseModel):
    trust_id: str
    trust_name: str
    health_score: HealthScoreResponse
    onboarding_state: "OnboardingState"
    recent_activity: List[dict]
    stats: DashboardStats
    governance_insights: List[GovernanceInsight]
    subscription: Optional["DashboardSubscriptionState"] = None
    pending_quarterly_draft: Optional[dict] = None

class OnboardingState(BaseModel):
    user_id: str
    # Profile completion steps
    formation_date_added: bool = False
    ein_entered: bool = False
    trust_doc_uploaded: bool = False
    ein_doc_uploaded: bool = False
    # Trust setup steps
    beneficiaries_added: bool = False
    assets_added: bool = False
    minutes_generated: bool = False
    calendar_set: bool = False
    checklist_dismissed: bool = False
    successor_trustee_added: bool = False
    trust_protector_added: bool = False
    # Manual overrides — tracks which steps the user manually toggled.
    # Auto-detection skips these fields, preserving the user's choice.
    manual_overrides: dict = {}


# ==================== BENEFICIARY DASHBOARD MODELS ====================

class BeneficiaryAllocation(BaseModel):
    holder_name: str
    holder_identifier: Optional[str] = None
    holder_type: str = "individual"
    email: Optional[str] = None
    phone: Optional[str] = None
    total_units: float
    percentage: float
    certificate_count: int
    certificates: List[dict]

class ClassBeneficiaryCreate(BaseModel):
    trust_id: str
    class_type: ClassBeneficiaryType
    description: str = Field("", max_length=500)
    percentage: float = Field(0.0, ge=0, le=100)
    notes: str = Field("", max_length=2000)
    distribution_convention: str = "per_capita"

class ClassBeneficiaryResponse(BaseModel):
    class_beneficiary_id: str
    trust_id: str
    class_type: str
    class_type_label: str
    description: str
    percentage: float
    notes: str
    distribution_convention: str = "per_capita"
    reserved_units: Optional[float] = None
    member_count: int = 0
    created_at: str


# ==================== BENEFICIARY MANAGEMENT MODELS ====================

class BeneficiaryCreate(BaseModel):
    trust_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    allocation_pct: Optional[float] = Field(None, ge=0, le=100)
    units: Optional[float] = Field(None, gt=0)
    holder_type: str = "individual"
    notes: Optional[str] = Field(None, max_length=2000)

class BeneficiaryUpdate(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)
    allocation_pct: Optional[float] = Field(None, ge=0, le=100)
    units: Optional[float] = Field(None, gt=0)
    replacement_reason: Optional[str] = Field(None, max_length=1000)
    effective_date: Optional[str] = None

class SendCertificateRequest(BaseModel):
    trust_id: str
    beneficiary_name: str
    email: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)

class BeneficiaryDashboardResponse(BaseModel):
    trust_id: str
    trust_name: str
    total_authorized_units: int
    total_issued_units: float
    remaining_units: float
    unit_label: str
    active_certificate_count: int
    beneficiaries: List[BeneficiaryAllocation]
    class_beneficiaries: List[ClassBeneficiaryResponse] = []
    recent_transfers: List[dict]
    # Combined allocation totals (persons + organizations + class beneficiaries)
    total_allocated_percentage: float = 0.0
    class_beneficiary_percentage_total: float = 0.0
    certificate_percentage_total: float = 0.0


# ==================== SUBSCRIPTION MODELS ====================

class SubscriptionState(BaseModel):
    """Normalized subscription state object for consistent access across modules"""
    user_id: str
    subscription_id: Optional[str] = None
    plan_type: str  # "trustee", "estate", "advisor", "free", "forever_free", legacy: "monthly", "annual"
    status: str  # "trialing", "active", "past_due", "canceled", "expired"
    billing_period: Optional[str] = None  # "monthly" | "annual" (new tiers)
    legacy_trust_limit: Optional[int] = None  # grandfathered users keep their old limit
    trial_start_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    trial_days_remaining: Optional[int] = None
    is_trial: bool = False
    is_active: bool = False
    is_read_only: bool = True
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None

class DashboardSubscriptionState(BaseModel):
    """Subscription state for dashboard - subset of full SubscriptionState"""
    plan_type: str
    status: str
    is_trial: bool
    is_active: bool
    is_read_only: bool
    trial_days_remaining: Optional[int] = None

class SubscriptionResponse(BaseModel):
    subscription_id: str
    user_id: str
    plan_type: str
    status: str
    billing_period: Optional[str] = None  # "monthly" | "annual" (new tiers)
    legacy_trust_limit: Optional[int] = None  # grandfathered users
    trial_start_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    days_remaining: Optional[int] = None
    is_active: bool
    current_period_end: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None

class CheckoutRequest(BaseModel):
    plan_type: str  # "trustee", "estate", "advisor" (legacy: "monthly", "annual")
    billing_period: Optional[str] = None  # "monthly" or "annual" (new tiers). Legacy plans infer from plan_type.
    success_url: str
    cancel_url: str
    promotion_code: Optional[str] = None
    coupon: Optional[str] = None  # Direct Stripe coupon ID (e.g., TRUST49)
    referral_id: Optional[str] = None  # Rewardful affiliate referral ID
    utm_source: Optional[str] = None  # Marketing attribution carried to Stripe metadata
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    referrer: Optional[str] = None


class ChangePlanRequest(BaseModel):
    """Request to change plan tier (upgrade/downgrade between trustee/estate/advisor)"""
    plan_type: str  # "trustee", "estate", "advisor"
    billing_period: str  # "monthly" or "annual"

class PortalRequest(BaseModel):
    return_url: str


# ==================== GUIDED MINUTES MODELS ====================

class GuidedMinutesContext(BaseModel):
    """Context data for the guided minutes wizard, pulled from trust/entity profile"""
    trust_id: str
    trust_name: str
    jurisdiction: Optional[str] = None
    trustees: List[str] = []
    beneficiary_standard: Optional[str] = None
    article_ref_distribution: Optional[str] = None
    article_ref_compensation: Optional[str] = None
    tax_status: Optional[str] = None
    start_date: Optional[str] = None

class GuidedMinutesDraftRequest(BaseModel):
    """Request model for guided minutes draft generation"""
    trust_id: str
    minutes_type: str = Field(..., description="Type: annual, quarterly, general")
    meeting_date: str = Field(..., description="ISO date of the meeting")
    participants: List[str] = Field(..., description="List of selected trustees")
    other_attendees: List[str] = Field(default_factory=list, description="List of other attendees (guests, advisors, beneficiaries)")
    agenda_items: List[str] = Field(default_factory=list, description="Short bullet points of agenda topics")
    key_decisions: List[str] = Field(default_factory=list, description="Short bullet points of decisions made")
    additional_context: Optional[str] = Field(None, description="Optional freeform notes")

class GuidedMinutesDraftResponse(BaseModel):
    """Response model for AI-generated guided minutes draft"""
    suggested_title: str = Field(..., description="Suggested title for the minutes")
    draft_body: str = Field(..., description="The main minutes text body")
    cautions: List[str] = Field(default_factory=list, description="Warnings or notes for the trustee")
    minutes_type: str
    meeting_date: str
    participants_text: str

class GuidedMinutesSaveRequest(BaseModel):
    """Request model for saving guided minutes as a minutes_records entry"""
    trust_id: str
    minutes_type: str
    meeting_date: str
    participants_text: str
    other_attendees_text: Optional[str] = None
    decisions_text: str


# ==================== MINUTES ↔ MONEY INTEGRATION MODELS ====================

class RecordFromMinutes(BaseModel):
    """A single money record to create from minutes"""
    record_type: str = Field(..., description="compensation, distribution, or benevolence")
    amount: float
    recipient: str
    date: str
    description: Optional[str] = None
    purpose_classification: Optional[str] = None  # For distributions
    benevolence_need: Optional[str] = None  # For benevolence

class GuidedMinutesSaveWithRecordsRequest(BaseModel):
    """Request model for saving guided minutes with linked money records"""
    trust_id: str
    minutes_type: str
    meeting_date: str
    participants_text: str
    other_attendees_text: Optional[str] = None
    decisions_text: str
    records_to_create: List[RecordFromMinutes] = Field(default_factory=list)

class GuidedMinutesSaveWithRecordsResponse(BaseModel):
    """Response after saving minutes with linked records"""
    minutes_id: str
    minutes_type: str
    meeting_date: str
    created_records: dict = Field(default_factory=dict, description="Count of created records by type")

class AttachMinutesRequest(BaseModel):
    """Request to attach existing minutes to a money record"""
    minutes_record_id: str

class MinutesSearchResult(BaseModel):
    """Search result for minutes"""
    minutes_id: str
    minutes_type: str
    meeting_date: str
    participants_text: Optional[str] = None
    preview: Optional[str] = None  # First 100 chars of decisions_text
    created_at: str


# ==================== TRANSACTION LEDGER MODELS ====================

class TransactionDirection(str, Enum):
    inflow = "inflow"
    outflow = "outflow"

class GovernanceClassification(str, Enum):
    distribution = "Distribution"
    compensation = "Compensation"
    inter_entity_transfer = "Inter-Entity Transfer"
    operational_expense = "Operational Expense"
    capital_contribution = "Capital Contribution"
    tax_payment = "Tax Payment"
    other = "Other"

class TransactionCreate(BaseModel):
    trust_id: str
    entity_id: str
    date: str
    amount: float = Field(..., ge=0)
    direction: TransactionDirection
    source_account: str = ""
    destination_account: str = ""
    governance_classification: GovernanceClassification
    purpose_memo: str = ""
    other_note: str = ""  # Required when classification is "Other"
    linked_distribution_id: Optional[str] = None
    linked_compensation_payment_id: Optional[str] = None
    linked_minutes_id: Optional[str] = None
    document_name: Optional[str] = None

class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    amount: Optional[float] = Field(None, ge=0)
    direction: Optional[TransactionDirection] = None
    source_account: Optional[str] = None
    destination_account: Optional[str] = None
    governance_classification: Optional[GovernanceClassification] = None
    purpose_memo: Optional[str] = None
    other_note: Optional[str] = None
    linked_distribution_id: Optional[str] = None
    linked_compensation_payment_id: Optional[str] = None
    linked_minutes_id: Optional[str] = None
    document_name: Optional[str] = None

class TransactionResponse(BaseModel):
    transaction_id: str
    trust_id: str
    entity_id: str
    entity_name: Optional[str] = None
    date: str
    amount: float
    direction: str
    source_account: str
    destination_account: str
    governance_classification: str
    purpose_memo: str
    other_note: str
    linked_distribution_id: Optional[str] = None
    linked_compensation_payment_id: Optional[str] = None
    linked_minutes_id: Optional[str] = None
    document_name: Optional[str] = None
    import_batch_id: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

class TransactionSummary(BaseModel):
    entity_id: str
    entity_name: str
    total_inflows: float
    total_outflows: float
    net_flow: float
    transaction_count: int
    unclassified_count: int
    by_classification: dict

class CsvImportRow(BaseModel):
    date: str
    amount: float
    direction: TransactionDirection
    description: str = ""
    governance_classification: Optional[GovernanceClassification] = None
    purpose_memo: str = ""

class CsvImportRequest(BaseModel):
    trust_id: str
    entity_id: str
    rows: List[CsvImportRow] = Field(..., max_length=1000)

class BulkClassifyRequest(BaseModel):
    transaction_ids: List[str] = Field(..., max_length=500)
    governance_classification: GovernanceClassification
    purpose_memo: str = ""
    other_note: str = ""



# ==================== SEPARATION ALERT MODELS ====================

class AlertSeverity(str, Enum):
    red = "red"
    yellow = "yellow"

class AlertType(str, Enum):
    personal_vendor = "personal_vendor"
    trust_paying_personal = "trust_paying_personal"
    large_unexplained = "large_unexplained"
    round_number_recurring = "round_number_recurring"
    same_day_reversal = "same_day_reversal"
    unclassified_aging = "unclassified_aging"
    unlinked_governance = "unlinked_governance"

class AlertStatus(str, Enum):
    active = "active"
    resolved = "resolved"

class AlertResponse(BaseModel):
    alert_id: str
    trust_id: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    transaction_id: Optional[str] = None
    alert_type: str
    severity: str
    title: str
    description: str
    status: str
    resolution_type: Optional[str] = None
    resolution_note: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str

class AlertResolveRequest(BaseModel):
    resolution_type: str  # "classified", "linked", "documented", "reviewed_no_issue"
    resolution_note: str  # Required — explains why this is not an issue

class AlertCountResponse(BaseModel):
    trust_id: str
    total_active: int
    red_count: int
    yellow_count: int
    by_entity: dict
    by_type: dict



# ==================== TAX CALENDAR MODELS ====================

class TaxDeadlineType(str, Enum):
    federal_1041 = "federal_1041"
    federal_1041_extension = "federal_1041_extension"
    k1_beneficiaries = "k1_beneficiaries"
    estimated_q1 = "estimated_q1"
    estimated_q2 = "estimated_q2"
    estimated_q3 = "estimated_q3"
    estimated_q4 = "estimated_q4"
    state_fiduciary = "state_fiduciary"
    state_fiduciary_extension = "state_fiduciary_extension"

class FilingStatus(str, Enum):
    pending = "pending"
    filed = "filed"
    extended = "extended"
    not_required = "not_required"

class TaxCalendarEntryCreate(BaseModel):
    tax_year: int
    deadline_type: TaxDeadlineType
    due_date: str
    description: Optional[str] = None
    notes: Optional[str] = None

class TaxCalendarEntryUpdate(BaseModel):
    due_date: Optional[str] = None
    filing_status: Optional[FilingStatus] = None
    filed_date: Optional[str] = None
    notes: Optional[str] = None
    accountant_engaged: Optional[bool] = None

class TaxCalendarEntryResponse(BaseModel):
    entry_id: str
    trust_id: str
    tax_year: int
    deadline_type: str
    due_date: str
    filing_status: str = "pending"
    filed_date: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    accountant_engaged: bool = False
    days_remaining: Optional[int] = None
    is_overdue: bool = False
    created_at: str
    updated_at: Optional[str] = None

class TaxCalendarSummaryResponse(BaseModel):
    trust_id: str
    tax_year: int
    total_entries: int
    filed_count: int
    pending_count: int
    overdue_count: int
    entries: List[TaxCalendarEntryResponse]

class TrustTaxProfile(BaseModel):
    """Trust profile fields for tax management"""
    ein: Optional[str] = None
    state_code: Optional[str] = None
    tax_year_end_month: Optional[int] = Field(None, ge=1, le=12)
    tax_year_end_day: Optional[int] = Field(None, ge=1, le=31)
    is_fiscal_year: Optional[bool] = None


# ==================== STATE COMPLIANCE MODELS ====================

class StateComplianceProfile(BaseModel):
    """Static seed data — state compliance rules"""
    state_code: str
    state_name: str
    utc_adopted: Optional[str] = None
    utc_adoption_date: Optional[str] = None
    notice_required: bool = False
    notice_timing_days: Optional[int] = None
    accounting_frequency: Optional[str] = None
    trustee_removal_standard: Optional[str] = None
    spendthrift_default: bool = True

class TrustStateCompliance(BaseModel):
    """Per-trust state compliance tracking"""
    trust_id: str
    state_code: str
    notice_last_sent: Optional[str] = None
    notice_next_due: Optional[str] = None
    accounting_last_sent: Optional[str] = None
    accounting_next_due: Optional[str] = None
    compliance_items: dict = {}
    compliance_score: int = Field(100, ge=0, le=100)
    alert_active: bool = False
    alert_reason: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

class TrustStateComplianceUpdate(BaseModel):
    notice_last_sent: Optional[str] = None
    notice_next_due: Optional[str] = None
    accounting_last_sent: Optional[str] = None
    accounting_next_due: Optional[str] = None
    compliance_items: Optional[dict] = None



# Fix forward reference
DashboardResponse.model_rebuild()


# ==================== CHAT / TRUST ASSISTANT MODELS ====================

class ChatAction(BaseModel):
    """An action card presented to the user for review/approval"""
    type: str = Field(..., description="Action type: minutes_preview, distribution_preview, asset_preview, beneficiary_preview")
    data: dict = Field(default_factory=dict, description="Action data payload")
    requires_confirmation: bool = Field(default=True, description="Whether user confirmation is required before execution")
    confirmation_status: Optional[str] = Field(None, description="Status: pending, approved, rejected")
    warning_summary: Optional[str] = Field(None, description="Brief warning about this action, if any")


class ChatMessage(BaseModel):
    """A single message in a conversation"""
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message text")
    action_card: Optional[dict] = Field(None, description="Action card attached to this message")
    citation_note: Optional[str] = Field(None, description="What the AI is basing this response on")
    unknown_note: Optional[str] = Field(None, description="What the AI doesn't know")
    caveat: Optional[str] = Field(None, description="Required caveat language")
    timestamp: str = Field(default_factory=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())


class ChatRequest(BaseModel):
    """Request to the chat endpoint"""
    message: str = Field(..., max_length=5000, description="User's message")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID")
    trust_id: Optional[str] = Field(None, description="Trust ID to scope the conversation")


class ChatResponse(BaseModel):
    """Non-streaming chat response"""
    message: dict
    conversation_id: str
    trust_context_summary: Optional[dict] = None
    has_pending_actions: bool = False


class Conversation(BaseModel):
    """A chat conversation document in MongoDB"""
    conversation_id: str
    user_id: str
    trust_id: str
    title: str
    messages: list = []
    created_at: str
    updated_at: str


class ConversationListItem(BaseModel):
    """Summary of a conversation for the history list"""
    conversation_id: str
    title: str
    message_count: int
    last_message_preview: str
    updated_at: str
    trust_id: Optional[str] = None


# ==================== BANKING MODELS ====================

class BankAccountType(str, Enum):
    checking = "checking"
    savings = "savings"
    investment = "investment"
    brokerage = "brokerage"
    cd = "cd"
    other = "other"

class BankAccountCreate(BaseModel):
    trust_id: str
    entity_id: str
    nickname: str
    institution_name: str
    account_type: BankAccountType = BankAccountType.checking
    last_four: str = Field(..., min_length=4, max_length=4)

class BankAccountUpdate(BaseModel):
    nickname: Optional[str] = None
    institution_name: Optional[str] = None
    account_type: Optional[BankAccountType] = None
    last_four: Optional[str] = Field(None, min_length=4, max_length=4)
    is_archived: Optional[bool] = None

class BankAccountResponse(BaseModel):
    account_id: str
    trust_id: str
    entity_id: str
    user_id: str
    nickname: str
    institution_name: str
    account_type: str
    last_four: str
    is_archived: bool = False
    created_at: str
    updated_at: Optional[str] = None

class BankStatementResponse(BaseModel):
    statement_id: str
    trust_id: str
    account_id: str
    user_id: str
    vault_document_id: str
    bank_name: Optional[str] = None
    account_last_four: Optional[str] = None
    statement_period_start: Optional[str] = None
    statement_period_end: Optional[str] = None
    beginning_balance: Optional[float] = None
    ending_balance: Optional[float] = None
    total_deposits: Optional[float] = None
    total_withdrawals: Optional[float] = None
    extraction_status: str = "pending"
    extraction_confidence: float = 0.0
    extraction_error: Optional[str] = None
    needs_review: bool = False
    created_at: str
    updated_at: Optional[str] = None


# ==================== GOVERNANCE SETTINGS ====================

class SpendingThresholdConfig(BaseModel):
    amount: float = Field(..., gt=0, description="Dollar threshold (e.g., 10000.00)")
    requires_minutes: bool = True
    scope_classifications: List[str] = Field(
        default=["Operational Expense", "Other"],
        description="Governance classifications that trigger the threshold check"
    )

class GovernanceSettings(BaseModel):
    spending_threshold: Optional[SpendingThresholdConfig] = None


# ==================== CLIENT MODELS ====================

class ClientCreate(BaseModel):
    """Create a client profile (denormalized aggregated view from trusts)"""
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    wingpoint_ref: Optional[str] = None  # WingPoint reference ID

class ClientUpdate(BaseModel):
    """Update client profile"""
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    wingpoint_ref: Optional[str] = None

class ClientResponse(BaseModel):
    """Client profile response with aggregated trust data"""
    client_id: str
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    wingpoint_ref: Optional[str] = None
    trust_count: int = 0
    created_at: str
    updated_at: Optional[str] = None

class ClientTrustSummary(BaseModel):
    """Summary of a trust within a client's portfolio"""
    trust_id: str
    trust_name: str
    trust_type: str
    jurisdiction: Optional[str] = None
    governance_score: Optional[int] = None
    health_color: Optional[str] = None
    created_at: str

class ClientDetailResponse(BaseModel):
    """Detailed client view with all trusts"""
    client_id: str
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    wingpoint_ref: Optional[str] = None
    trusts: List[ClientTrustSummary] = []
    created_at: str
    updated_at: Optional[str] = None

class ClientHealthSummary(BaseModel):
    """Client-level health score aggregation"""
    client_id: str
    trust_count: int
    average_health_score: Optional[float] = None
    trusts_by_health_color: dict = {}  # {"red": 2, "yellow": 1, "green": 3}
    total_overdue_tasks: int = 0
    upcoming_deadlines_count: int = 0
    calculated_at: str


# ==================== MEETING & AGENDA MODELS ====================

class AgendaItemType(str, Enum):
    """Types of agenda items"""
    review_financials = "review_financials"
    review_distributions = "review_distributions"
    review_compensation = "review_compensation"
    review_beneficiaries = "review_beneficiaries"
    compliance_check = "compliance_check"
    asset_review = "asset_review"
    tax_planning = "tax_planning"
    strategy_discussion = "strategy_discussion"
    other = "other"

class MeetingAgendaItemCreate(BaseModel):
    """Create a single agenda item"""
    item_type: AgendaItemType
    title: str
    description: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=1, le=240)
    priority: str = "normal"  # "low", "normal", "high"

class MeetingAgendaItemResponse(BaseModel):
    """Agenda item response"""
    agenda_item_id: str
    item_type: str
    title: str
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    priority: str
    completed: bool = False
    created_at: str

class MeetingAgendaCreate(BaseModel):
    """Create a meeting agenda"""
    trust_id: str
    meeting_type: MinutesType = MinutesType.quarterly
    scheduled_date: str
    estimated_duration_minutes: int = Field(60, ge=15, le=480)
    agenda_items: List[MeetingAgendaItemCreate] = []
    notes: Optional[str] = None
    location: Optional[str] = None
    virtual_meeting_link: Optional[str] = None

class MeetingAgendaUpdate(BaseModel):
    """Update meeting agenda"""
    scheduled_date: Optional[str] = None
    estimated_duration_minutes: Optional[int] = Field(None, ge=15, le=480)
    agenda_items: Optional[List[MeetingAgendaItemCreate]] = None
    notes: Optional[str] = None
    location: Optional[str] = None
    virtual_meeting_link: Optional[str] = None
    status: Optional[str] = None

class MeetingAgendaResponse(BaseModel):
    """Meeting agenda response"""
    agenda_id: str
    trust_id: str
    meeting_type: str
    scheduled_date: str
    estimated_duration_minutes: int
    agenda_items: List[MeetingAgendaItemResponse] = []
    notes: Optional[str] = None
    location: Optional[str] = None
    virtual_meeting_link: Optional[str] = None
    status: str = "scheduled"  # "scheduled", "completed", "cancelled"
    created_at: str
    updated_at: Optional[str] = None

class MeetingCreate(BaseModel):
    """Create a meeting record (links agenda to minutes)"""
    trust_id: str
    agenda_id: str
    meeting_type: MinutesType = MinutesType.quarterly
    actual_meeting_date: str
    attendees: List[str] = []
    other_attendees: List[str] = []
    location: Optional[str] = None
    virtual_meeting_link: Optional[str] = None
    notes: Optional[str] = None

class MeetingResponse(BaseModel):
    """Meeting record response"""
    meeting_id: str
    trust_id: str
    agenda_id: str
    meeting_type: str
    actual_meeting_date: str
    attendees: List[str] = []
    other_attendees: List[str] = []
    location: Optional[str] = None
    virtual_meeting_link: Optional[str] = None
    notes: Optional[str] = None
    status: str = "completed"  # "scheduled", "in_progress", "completed", "cancelled"
    linked_minutes_id: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


# ==================== MINUTES APPROVAL WORKFLOW MODELS ====================

class ApprovalStatus(str, Enum):
    """Approval workflow status"""
    draft = "draft"
    pending_review = "pending_review"
    under_review = "under_review"
    changes_requested = "changes_requested"
    approved = "approved"
    rejected = "rejected"
    finalized = "finalized"

class ApprovalRole(str, Enum):
    """Roles in the approval workflow"""
    drafter = "drafter"
    reviewer = "reviewer"
    approver = "approver"

class MinutesApprovalStatusCreate(BaseModel):
    """Create approval workflow status for minutes"""
    minutes_id: str
    trust_id: str
    current_status: ApprovalStatus = ApprovalStatus.draft
    drafter_user_id: str
    reviewer_user_id: Optional[str] = None
    approver_user_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = "normal"  # "low", "normal", "high"

class MinutesApprovalStatusUpdate(BaseModel):
    """Update approval workflow status"""
    current_status: Optional[ApprovalStatus] = None
    reviewer_user_id: Optional[str] = None
    approver_user_id: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    changes_requested_note: Optional[str] = None
    rejection_reason: Optional[str] = None

class ApprovalActionLog(BaseModel):
    """Single action in the approval workflow"""
    action: str  # "created", "submitted", "reviewed", "approved", "rejected", "changes_requested", "finalized"
    performed_by_user_id: str
    performed_by_name: str
    performed_by_role: ApprovalRole
    timestamp: str
    note: Optional[str] = None

class MinutesApprovalStatusResponse(BaseModel):
    """Approval workflow status response"""
    approval_id: str
    minutes_id: str
    trust_id: str
    current_status: str
    drafter_user_id: str
    drafter_name: str
    reviewer_user_id: Optional[str] = None
    reviewer_name: Optional[str] = None
    approver_user_id: Optional[str] = None
    approver_name: Optional[str] = None
    due_date: Optional[str] = None
    priority: str
    action_log: List[ApprovalActionLog] = []
    changes_requested_note: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

class ApprovalWorkflowSummary(BaseModel):
    """High-level workflow status for a trust"""
    trust_id: str
    pending_approvals_count: int = 0
    overdue_approvals_count: int = 0
    recently_completed_approvals: List[dict] = []
    calculated_at: str


# ==================== DEADLINE MODELS ====================

class DeadlineCategory(str, Enum):
    """Categories of compliance deadlines"""
    quarterly_review = "quarterly_review"
    annual_review = "annual_review"
    tax_filing_1041 = "tax_filing_1041"
    tax_filing_k1 = "tax_filing_k1"
    estimated_tax_payment = "estimated_tax_payment"
    state_compliance = "state_compliance"
    beneficiary_notification = "beneficiary_notification"
    trustee_compensation_review = "trustee_compensation_review"
    insurance_compliance = "insurance_compliance"
    document_retention = "document_retention"
    other = "other"

class DeadlinePriority(str, Enum):
    """Priority levels for deadlines"""
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"

class DeadlineStatus(str, Enum):
    """Status of a deadline"""
    upcoming = "upcoming"
    due_soon = "due_soon"
    overdue = "overdue"
    completed = "completed"
    waived = "waived"

class DeadlineCreate(BaseModel):
    """Create a compliance deadline"""
    trust_id: str
    category: DeadlineCategory
    title: str
    description: Optional[str] = None
    due_date: str
    priority: DeadlinePriority = DeadlinePriority.high
    recurrence: Optional[str] = None  # "once", "quarterly", "annual", "monthly"
    recurrence_end_date: Optional[str] = None
    reminder_days_before: List[int] = [30, 14, 7, 3, 1]
    is_statutory: bool = False  # True for legal/statutory deadlines
    state_specific: Optional[str] = None  # State code if state-specific deadline
    reference_document: Optional[str] = None  # Minutes ID or document reference
    notes: Optional[str] = None

class DeadlineUpdate(BaseModel):
    """Update a deadline"""
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[DeadlinePriority] = None
    status: Optional[DeadlineStatus] = None
    recurrence: Optional[str] = None
    recurrence_end_date: Optional[str] = None
    reminder_days_before: Optional[List[int]] = None
    completion_date: Optional[str] = None
    completion_notes: Optional[str] = None
    notes: Optional[str] = None

class DeadlineResponse(BaseModel):
    """Deadline response"""
    deadline_id: str
    trust_id: str
    trust_name: Optional[str] = None
    category: str
    title: str
    description: Optional[str] = None
    due_date: str
    priority: str
    status: str = "upcoming"
    recurrence: Optional[str] = None
    recurrence_end_date: Optional[str] = None
    reminder_days_before: List[int] = []
    is_statutory: bool = False
    state_specific: Optional[str] = None
    reference_document: Optional[str] = None
    completion_date: Optional[str] = None
    completion_notes: Optional[str] = None
    notes: Optional[str] = None
    days_remaining: Optional[int] = None
    is_overdue: bool = False
    created_at: str
    updated_at: Optional[str] = None

class DeadlineSummary(BaseModel):
    """Summary of deadlines for a trust"""
    trust_id: str
    total_deadlines: int
    upcoming_count: int = 0
    due_soon_count: int = 0
    overdue_count: int = 0
    completed_count: int = 0
    by_category: dict = {}
    by_priority: dict = {}
    next_deadline: Optional[DeadlineResponse] = None
    calculated_at: str

class ClientDeadlineSummary(BaseModel):
    """Client-level deadline summary (multi-trust view)"""
    client_id: str
    email: str
    trust_count: int
    total_deadlines: int
    upcoming_count: int = 0
    due_soon_count: int = 0
    overdue_count: int = 0
    critical_count: int = 0
    next_deadline: Optional[DeadlineResponse] = None
    calculated_at: str


# ==================== CUSTOMER MEMORY MODELS ====================

class ContactRole(str, Enum):
    """Role of a contact within the TrustOffice ecosystem"""
    trustee = "trustee"
    advisor = "advisor"
    beneficiary = "beneficiary"
    prospect = "prospect"

class ContactStatus(str, Enum):
    """Lifecycle status of a contact"""
    prospect = "prospect"
    active_client = "active_client"
    former = "former"

class ContactCreate(BaseModel):
    """Create a contact record (customer memory)"""
    name: str
    email: EmailStr
    phone: Optional[str] = None
    organization: Optional[str] = None
    role: ContactRole = ContactRole.prospect
    status: ContactStatus = ContactStatus.prospect
    plan: Optional[str] = None
    tags: Optional[List[str]] = None

class ContactResponse(BaseModel):
    """Contact record response"""
    contact_id: str
    name: str
    email: str
    phone: Optional[str] = None
    organization: Optional[str] = None
    role: str
    status: str
    plan: Optional[str] = None
    tags: List[str] = []
    created_at: str
    updated_at: Optional[str] = None

class SupportInteractionChannel(str, Enum):
    """Channel through which a support interaction occurred"""
    email = "email"
    chat = "chat"
    call_summary = "call_summary"
    in_app = "in_app"

class SupportInteractionSentiment(str, Enum):
    """Sentiment classification of a support interaction"""
    positive = "positive"
    neutral = "neutral"
    negative = "negative"

class SupportInteractionStatus(str, Enum):
    """Resolution status of a support interaction"""
    open = "open"
    pending = "pending"
    resolved = "resolved"

class SupportInteractionCreate(BaseModel):
    """Create a support interaction record linked to a contact"""
    contact_id: str
    channel: SupportInteractionChannel = SupportInteractionChannel.email
    raw_content: str
    generated_reply: Optional[str] = None
    summary: str
    topics: List[str] = []
    sentiment: SupportInteractionSentiment = SupportInteractionSentiment.neutral
    urgency: int = Field(3, ge=1, le=5)
    status: SupportInteractionStatus = SupportInteractionStatus.open

class SupportInteractionResponse(BaseModel):
    """Support interaction response"""
    interaction_id: str
    contact_id: str
    channel: str
    raw_content: str
    generated_reply: Optional[str] = None
    summary: str
    topics: List[str] = []
    sentiment: str
    urgency: int
    status: str
    created_at: str
    resolved_at: Optional[str] = None

class ContactPhase(str, Enum):
    """Lifecycle phase of a contact used in the profile summary"""
    onboarding = "onboarding"
    implementation = "implementation"
    renewal = "renewal"
    at_risk = "at_risk"
    active = "active"

class ContactProfileSummary(BaseModel):
    """Structured, updatable profile summary maintained for a contact"""
    contact_id: str
    current_phase: ContactPhase = ContactPhase.active
    key_preferences: List[str] = []
    constraints: List[str] = []
    last_major_issue: Optional[str] = None
    last_major_issue_outcome: Optional[str] = None
    recommended_next_actions: List[str] = []
    follow_up_notes: Optional[str] = None
    updated_at: Optional[str] = None

class ContactContextResponse(BaseModel):
    """Aggregated context bundle for a contact: contact + profile summary + recent interactions"""
    contact: ContactResponse
    profile_summary: Optional[ContactProfileSummary] = None
    recent_interactions: List[SupportInteractionResponse] = []
