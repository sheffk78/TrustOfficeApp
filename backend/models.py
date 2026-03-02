# Shared Pydantic models and enums for TrustOffice API
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from enum import Enum


# ==================== ENUMS ====================

class TrustType(str, Enum):
    family = "family"
    institutional = "institutional"

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
    custom = "custom"

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


# ==================== USER MODELS ====================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: str

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

class UserPreferencesUpdate(BaseModel):
    hide_watermark: Optional[bool] = None


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

class TrustUpdate(BaseModel):
    name: Optional[str] = None
    trust_type: Optional[TrustType] = None
    jurisdiction: Optional[str] = None
    benevolence_enabled: Optional[bool] = None
    tax_status: Optional[str] = None

class TrustResponse(BaseModel):
    trust_id: str
    user_id: str
    name: str
    trust_type: Optional[str] = "irrevocable"
    jurisdiction: Optional[str] = ""
    benevolence_enabled: Optional[bool] = False
    tax_status: Optional[str] = "private"
    created_at: str
    governance_score: int = 0
    trustees: Optional[List[str]] = []


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
    ownership_percentage: Optional[float] = None
    notes: str = ""

class EntityRelationshipResponse(BaseModel):
    relationship_id: str
    trust_id: str
    parent_entity_id: str
    child_entity_id: str
    relationship_type: str
    ownership_percentage: Optional[float] = None
    notes: str
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

class TrustUnitsSettingsResponse(BaseModel):
    trust_id: str
    total_authorized_units: int
    unit_label: str
    allow_fractional: bool
    created_at: str
    updated_at: Optional[str] = None

class TrustUnitCertificateCreate(BaseModel):
    trust_id: str
    holder_name: str
    holder_identifier: Optional[str] = None
    units: float
    issue_date: str
    notes: str = ""

class TrustUnitCertificateUpdate(BaseModel):
    holder_name: Optional[str] = None
    holder_identifier: Optional[str] = None
    units: Optional[float] = None
    status: Optional[CertificateStatus] = None
    notes: Optional[str] = None

class TrustUnitCertificateResponse(BaseModel):
    certificate_id: str
    trust_id: str
    holder_name: str
    holder_identifier: Optional[str]
    units: float
    percentage: float
    issue_date: str
    certificate_number: str
    status: str
    replaced_by_certificate_id: Optional[str] = None
    notes: str
    created_at: str
    updated_at: Optional[str] = None

class TrustUnitTransferCreate(BaseModel):
    trust_id: str
    from_holder: Optional[str] = None
    to_holder: str
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

class GovernanceTaskCreate(BaseModel):
    trust_id: str
    task_type: TaskType
    due_date: str
    description: str = ""

class GovernanceTaskResponse(BaseModel):
    task_id: str
    trust_id: str
    task_type: str
    due_date: str
    completed_at: Optional[str] = None
    status: str
    description: str
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

class MinutesResponse(BaseModel):
    minutes_id: str
    trust_id: str
    minutes_type: str
    meeting_date: str
    participants_text: str
    decisions_text: str
    created_at: str

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
    trust_indenture_date: str = ""
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


# ==================== SCHEDULE A MODELS ====================

class ScheduleAItemCreate(BaseModel):
    trust_id: str
    category: AssetCategory
    description: str
    identifier: str = ""
    location: str = ""
    approximate_value: Optional[float] = None
    date_conveyed: str
    notes: str = ""
    minutes_ref: Optional[str] = None

class ScheduleAItemUpdate(BaseModel):
    description: Optional[str] = None
    identifier: Optional[str] = None
    location: Optional[str] = None
    approximate_value: Optional[float] = None
    date_conveyed: Optional[str] = None
    notes: Optional[str] = None

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
    amount: float
    date: str
    purpose_classification: PurposeClassification
    authority_clause_ref: str = ""
    notes: str = ""
    is_benevolence: bool = False
    benevolence_recipient_name: Optional[str] = None
    benevolence_need_description: Optional[str] = None
    benevolence_notes: Optional[str] = None

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
    minutes_record_id: Optional[str] = None
    created_at: str
    is_benevolence: bool = False
    benevolence_recipient_name: Optional[str] = None
    benevolence_need_description: Optional[str] = None
    benevolence_notes: Optional[str] = None

class DistributionUpdate(BaseModel):
    beneficiary_name: Optional[str] = None
    amount: Optional[float] = None
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


# ==================== BENEVOLENCE MODELS ====================

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


# ==================== COMPENSATION MODELS ====================

class CompensationPlanCreate(BaseModel):
    trust_id: str
    trustee_name: str = ""
    role: str = ""
    annual_amount: float = 0
    annual_approved_amount: float = 0
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
    amount: float
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
    max_points: int = 20
    achieved: bool

class HealthScoreResponse(BaseModel):
    trust_id: str
    total_score: int
    max_score: int = 100
    color: str
    criteria: List[HealthScoreCriterion]
    calculated_at: str


# ==================== DASHBOARD MODELS ====================

class GovernanceInsight(BaseModel):
    type: str
    criterion_name: str
    title: str
    description: str
    action_path: str
    action_label: str
    points: int = 20

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

class OnboardingState(BaseModel):
    user_id: str
    entities_confirmed: bool = False
    calendar_set: bool = False
    minutes_generated: bool = False
    distribution_logged: bool = False
    checklist_dismissed: bool = False


# ==================== BENEFICIARY DASHBOARD MODELS ====================

class BeneficiaryAllocation(BaseModel):
    holder_name: str
    holder_identifier: Optional[str] = None
    total_units: float
    percentage: float
    certificate_count: int
    certificates: List[dict]

class BeneficiaryDashboardResponse(BaseModel):
    trust_id: str
    trust_name: str
    total_authorized_units: int
    total_issued_units: float
    remaining_units: float
    unit_label: str
    active_certificate_count: int
    beneficiaries: List[BeneficiaryAllocation]
    recent_transfers: List[dict]


# ==================== SUBSCRIPTION MODELS ====================

class SubscriptionState(BaseModel):
    """Normalized subscription state object for consistent access across modules"""
    user_id: str
    subscription_id: Optional[str] = None
    plan_type: str  # "trial", "monthly", "annual"
    status: str  # "trialing", "active", "past_due", "canceled", "expired"
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
    trial_start_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    days_remaining: Optional[int] = None
    is_active: bool
    current_period_end: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None

class CheckoutRequest(BaseModel):
    plan_type: str
    success_url: str
    cancel_url: str
    promotion_code: Optional[str] = None

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


# Fix forward reference
DashboardResponse.model_rebuild()
