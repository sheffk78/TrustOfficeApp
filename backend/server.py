from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, BackgroundTasks, Body
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import secrets
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from enum import Enum
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import httpx
import stripe
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
import io
import base64

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import email service after dotenv is loaded
from email_service import email_service
from background_tasks import background_runner, run_task_status_update, run_daily_reminders, run_health_snapshots

# Import subscription state helper from dependencies
from dependencies import (
    get_subscription_state, 
    SubscriptionState,
    require_write_access,
    READ_ONLY_ERROR_MESSAGE,
    READ_ONLY_ERROR_CODE,
    Feature,
    check_feature_access,
    require_premium_feature,
    get_user_features
)

# Import routers
from routers.distributions import router as distributions_router
from routers.governance import router as governance_router
from routers.minutes import router as minutes_router
from routers.schedule_a import router as schedule_a_router

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'trustoffice_secret_key_change_in_production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

# Stripe Config
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
STRIPE_MONTHLY_PRICE_ID = os.environ.get('STRIPE_MONTHLY_PRICE_ID')
STRIPE_ANNUAL_PRICE_ID = os.environ.get('STRIPE_ANNUAL_PRICE_ID')
TRIAL_DAYS = 14

# Create the main app
app = FastAPI(title="TrustOffice API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBearer(auto_error=False)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths that don't require active subscription (full access - both read and write)
SUBSCRIPTION_EXEMPT_PATHS = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
    "/api/auth/me",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-reset-token",
    "/api/subscription",
    "/api/subscription/create-checkout",
    "/api/subscription/verify-payment",
    "/api/subscription/create-portal",
    "/api/subscription/cancel",
    "/api/subscription/reactivate",
    "/api/subscription/upgrade",
    "/api/stripe/webhook",
    "/api/categories",
}

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

# Schedule A Asset Categories
class AssetCategory(str, Enum):
    real_property = "real_property"
    personal_property = "personal_property"
    financial_accounts = "financial_accounts"
    business_interests = "business_interests"
    digital_assets = "digital_assets"
    intellectual_property = "intellectual_property"
    notes_receivable = "notes_receivable"
    other_property = "other_property"

# Minutes Template Types
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

# Asset Status for Schedule A
class AssetStatus(str, Enum):
    active = "active"
    disposed = "disposed"

# Benevolence Purpose Categories
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

# ==================== MODELS ====================

# User Models
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

# Trust Models
class TrustCreate(BaseModel):
    name: str
    trust_type: TrustType = TrustType.family
    jurisdiction: str = ""

class TrustUpdate(BaseModel):
    name: Optional[str] = None
    trust_type: Optional[TrustType] = None
    jurisdiction: Optional[str] = None
    benevolence_enabled: Optional[bool] = None
    tax_status: Optional[str] = None  # e.g., "501c3", "508", "private"

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

# Password Reset Models
class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

# Entity Models
class EntityCreate(BaseModel):
    trust_id: str
    name: str
    entity_type: EntityType
    legal_name: str = ""
    formation_date: Optional[str] = None
    governing_law: str = ""
    ein: Optional[str] = None
    # Trust-specific
    trustee_names: str = ""
    beneficiary_standard: str = ""
    article_ref_distribution: str = ""
    article_ref_compensation: str = ""
    article_ref_amendment: str = ""
    oversight_required: bool = False
    # LLC-specific
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

# Entity Relationship Models
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

class CertificateStatus(str, Enum):
    active = "active"
    cancelled = "cancelled"
    replaced = "replaced"

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
    percentage: float  # Computed: units / total_authorized_units * 100
    issue_date: str
    certificate_number: str
    status: str
    replaced_by_certificate_id: Optional[str] = None
    notes: str
    created_at: str
    updated_at: Optional[str] = None

class TrustUnitTransferCreate(BaseModel):
    trust_id: str
    from_holder: Optional[str] = None  # Nullable for initial issuance
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

# Governance Task Models
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
    status: str  # upcoming, completed, overdue
    description: str
    created_at: str

# Minutes Models
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

# Distribution Models
class DistributionCreate(BaseModel):
    trust_id: str
    beneficiary_name: str
    amount: float
    date: str
    purpose_classification: PurposeClassification
    authority_clause_ref: str = ""
    notes: str = ""
    # Benevolence mode fields
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
    # Benevolence mode fields
    is_benevolence: bool = False
    benevolence_recipient_name: Optional[str] = None
    benevolence_need_description: Optional[str] = None
    benevolence_notes: Optional[str] = None

class DistributionUpdate(BaseModel):
    """Model for updating distribution fields"""
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

# Benevolence Log Models
class BenevolenceMonthlyAggregate(BaseModel):
    month: str  # YYYY-MM format
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
    incomplete_documentation_count: int  # Benevolence distributions missing key fields

# Compensation Models
class CompensationPlanCreate(BaseModel):
    trust_id: str
    trustee_name: str = ""
    role: str = ""
    annual_amount: float = 0
    annual_approved_amount: float = 0  # Alias for annual_amount for backwards compatibility
    fee_type: str = "fixed"
    effective_date: str
    notes: str = ""

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
    notes: str = ""
    created_at: str

class CompensationPaymentCreate(BaseModel):
    trust_id: str
    amount: float
    date: str
    classification_text: str = ""

class CompensationPaymentResponse(BaseModel):
    payment_id: str
    trust_id: str
    amount: float
    date: str
    classification_text: str
    exceeds_plan_flag: bool
    minutes_record_id: Optional[str] = None
    created_at: str

# Onboarding Models
class OnboardingState(BaseModel):
    user_id: str
    entities_confirmed: bool = False
    calendar_set: bool = False
    minutes_generated: bool = False
    distribution_logged: bool = False
    checklist_dismissed: bool = False

# Schedule A Asset Models
class ScheduleAItemCreate(BaseModel):
    trust_id: str
    category: AssetCategory
    description: str
    identifier: str = ""  # VIN, account number, legal description, etc.
    location: str = ""  # Address, institution, platform
    approximate_value: Optional[float] = None
    date_conveyed: str
    notes: str = ""
    minutes_ref: Optional[str] = None  # Reference to the minutes that authorized this asset

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
    status: str = "active"  # active or disposed
    minutes_ref: Optional[str] = None  # Reference to minutes that added this asset
    disposition_minutes_ref: Optional[str] = None  # Reference to minutes that disposed this asset
    disposition_date: Optional[str] = None  # Date of disposition
    disposition_notes: Optional[str] = None  # Sale price, buyer, etc.

# Minutes Template Models
class MinutesResolution(BaseModel):
    title: str
    whereas_clauses: List[str]
    resolved_clauses: List[str]
    vote: str = "Unanimous approval"
    effective_date: str = "Immediately upon adoption"

class MinutesTemplateData(BaseModel):
    # General meeting info
    minute_number: str = ""
    meeting_date: str = ""
    meeting_time: str = ""
    meeting_location: str = ""
    meeting_type: str = "unanimous_written_consent"  # in_person, video_conference, unanimous_written_consent
    trustees_present: List[str] = []
    protector_present: Optional[str] = None
    quorum_met: bool = True
    
    # Trust indenture date
    trust_indenture_date: str = ""
    
    # Resolutions
    resolutions: List[dict] = []
    
    # Distribution specific
    distribution_total: Optional[float] = None
    distribution_items: List[dict] = []
    distribution_date: Optional[str] = None
    distribution_characterization: str = "income"  # income, principal, return_of_corpus
    
    # Property acceptance specific
    property_description: str = ""
    property_value: Optional[float] = None
    grantor_name: str = ""
    conveyance_date: str = ""
    add_to_schedule_a: bool = True
    schedule_a_category: Optional[str] = None
    property_identifier: str = ""  # VIN, account number, legal description
    property_location: str = ""  # Address, institution, platform
    
    # Asset disposition specific
    disposition_asset_id: Optional[str] = None  # ID of the Schedule A asset being disposed
    disposition_asset_description: str = ""  # Description of asset being disposed
    disposition_reason: str = ""  # sale, transfer, destruction, donation
    disposition_date: str = ""
    disposition_value: Optional[float] = None  # Sale price or fair market value at disposition
    disposition_recipient: str = ""  # Buyer, recipient, or new owner
    disposition_notes: str = ""  # Additional details about the disposition
    update_schedule_a: bool = True  # Whether to mark asset as disposed in Schedule A
    
    # Trustee appointment specific
    appointment_type: str = ""  # additional, successor
    departing_trustee_name: str = ""
    departing_reason: str = ""  # resigned, died, incapacitated, removed
    new_trustee_name: str = ""
    new_trustee_gender: str = "man"  # man, woman
    signature_requirement: str = "any_one"  # any_one, any_two, all_trustees
    signature_threshold: Optional[float] = None
    banking_powers_granted: bool = True
    executive_trustee: str = ""
    secretary_trustee: str = ""
    treasurer_trustee: str = ""

class MinutesTemplateCreate(BaseModel):
    trust_id: str
    template_type: MinutesTemplateType
    template_data: dict = {}  # Flexible JSON for template-specific data

class MinutesTemplateResponse(BaseModel):
    minutes_id: str
    trust_id: str
    template_type: str
    template_data: dict
    generated_document: str  # Full text of the minutes
    original_document: str  # Original generated version for audit
    meeting_date: str
    status: str  # draft, final
    created_at: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

# Benevolence Models
class BenevolenceRecordCreate(BaseModel):
    trust_id: str
    beneficiary_name: str
    beneficiary_type: str = "individual"  # individual, family, organization
    purpose: BenevolencePurpose
    purpose_description: str
    amount: float
    date: str
    approved_by: List[str]  # List of trustee names who approved
    approval_method: str = "unanimous"  # unanimous, majority, single_trustee
    minutes_id: Optional[str] = None  # Link to minutes if created via template
    notes: str = ""
    status: str = "approved"  # pending, approved, disbursed, declined

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

# Health Score Models
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

# Dashboard Models
class GovernanceInsight(BaseModel):
    type: str  # "warning", "error", "info"
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

class DashboardSubscriptionState(BaseModel):
    """Subscription state for dashboard - subset of full SubscriptionState"""
    plan_type: str
    status: str
    is_trial: bool
    is_active: bool
    is_read_only: bool
    trial_days_remaining: Optional[int] = None

class DashboardResponse(BaseModel):
    trust_id: str
    trust_name: str
    health_score: HealthScoreResponse
    onboarding_state: OnboardingState
    recent_activity: List[dict]
    stats: DashboardStats
    governance_insights: List[GovernanceInsight]
    subscription: Optional[DashboardSubscriptionState] = None

# Beneficiary Dashboard Models
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

# Subscription Models
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
    plan_type: str  # "monthly" or "annual"
    success_url: str
    cancel_url: str
    promotion_code: Optional[str] = None  # Stripe promotion code (e.g., "WINGPOINT10")

class PortalRequest(BaseModel):
    return_url: str

# ==================== HELPER FUNCTIONS ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    session_token = request.cookies.get("session_token")
    auth_header = request.headers.get("Authorization")
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif session_token:
        token = session_token
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Try JWT token first
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0})
        if user:
            return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        pass
    
    # Try session token
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if session:
        expires_at = session.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
        
        user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
        if user:
            return user
    
    raise HTTPException(status_code=401, detail="Invalid token")

async def should_show_watermark(user_id: str) -> bool:
    """
    Check if watermark should be shown on PDFs.
    Returns True if watermark should show (not subscribed or preference not set).
    Soft gating: unsubscribed users always see watermark.
    """
    # Check subscription status
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    if not sub:
        return True  # No subscription = show watermark
    
    # Check if subscription is active
    is_subscribed = False
    if sub["status"] == "active":
        is_subscribed = True
    elif sub["status"] == "trialing" and sub.get("trial_end_date"):
        try:
            trial_end = datetime.fromisoformat(sub["trial_end_date"].replace('Z', '+00:00'))
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            is_subscribed = trial_end >= datetime.now(timezone.utc)
        except (ValueError, TypeError, AttributeError):
            is_subscribed = False
    
    if not is_subscribed:
        return True  # Not subscribed = show watermark
    
    # User is subscribed - check their preference
    user_prefs = await db.user_preferences.find_one({"user_id": user_id}, {"_id": 0})
    hide_watermark = user_prefs.get("hide_watermark", False) if user_prefs else False
    
    return not hide_watermark  # Show watermark if preference is False

async def check_subscription_active(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency that checks if user has active subscription.
    Returns user if subscription is active, raises 402 if expired.
    """
    sub = await db.subscriptions.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    if not sub:
        # No subscription record - create trial and allow access
        now = datetime.now(timezone.utc)
        sub = {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user["user_id"],
            "plan_type": "trial",
            "status": "trialing",
            "trial_start_date": now.isoformat(),
            "trial_end_date": (now + timedelta(days=TRIAL_DAYS)).isoformat(),
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        await db.subscriptions.insert_one(sub)
        return user
    
    # Check if subscription is active
    if sub["status"] == "active":
        return user
    
    if sub["status"] == "trialing" and sub.get("trial_end_date"):
        trial_end = datetime.fromisoformat(sub["trial_end_date"].replace('Z', '+00:00'))
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        
        if trial_end >= datetime.now(timezone.utc):
            return user
        
        # Trial expired
        raise HTTPException(
            status_code=402,
            detail="Trial expired. Please subscribe to continue using TrustOffice."
        )
    
    if sub["status"] in ["canceled", "expired", "past_due"]:
        raise HTTPException(
            status_code=402,
            detail="Subscription inactive. Please subscribe to continue using TrustOffice."
        )
    
    return user

def get_task_status(due_date: str, completed_at: Optional[str]) -> str:
    """Calculate task status based on due_date and completed_at"""
    if completed_at:
        return "completed"
    
    try:
        due = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due < datetime.now(timezone.utc):
            return "overdue"
    except (ValueError, AttributeError):
        pass
    
    return "upcoming"

def get_quarter_start(dt: datetime) -> datetime:
    """Get the start of the current quarter"""
    quarter = (dt.month - 1) // 3
    month = quarter * 3 + 1
    return datetime(dt.year, month, 1, tzinfo=timezone.utc)

def get_year_start(dt: datetime) -> datetime:
    """Get the start of the current year"""
    return datetime(dt.year, 1, 1, tzinfo=timezone.utc)

async def calculate_health_score(trust_id: str, user_id: str) -> dict:
    """
    Calculate governance health score using 5 criteria (20 points each):
    1. Quarterly Minutes - minutes generated this quarter
    2. Task Compliance - no overdue tasks
    3. Compensation Alignment - YTD ≤ approved annual
    4. Distribution Documentation - at least 1 distribution logged
    5. Annual Review - annual_review task completed in last 12 months
    """
    now = datetime.now(timezone.utc)
    criteria = []
    total_score = 0
    
    # 1. Quarterly Minutes (+20)
    quarter_start = get_quarter_start(now)
    quarterly_minutes = await db.minutes_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$gte": quarter_start.isoformat()}
    })
    quarterly_achieved = quarterly_minutes > 0
    criteria.append(HealthScoreCriterion(
        name="Quarterly Minutes",
        description="Minutes generated this quarter",
        points=20 if quarterly_achieved else 0,
        achieved=quarterly_achieved
    ))
    if quarterly_achieved:
        total_score += 20
    
    # 2. Task Compliance (+20)
    overdue_tasks = await db.governance_tasks.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "completed_at": None,
        "due_date": {"$lt": now.isoformat()}
    })
    task_compliance = overdue_tasks == 0
    criteria.append(HealthScoreCriterion(
        name="Task Compliance",
        description="No overdue governance tasks",
        points=20 if task_compliance else 0,
        achieved=task_compliance
    ))
    if task_compliance:
        total_score += 20
    
    # 3. Compensation Alignment (+20)
    year_start = get_year_start(now)
    comp_plan = await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    
    if comp_plan:
        # Calculate YTD payments
        ytd_payments = await db.compensation_payments.find(
            {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start.isoformat()}},
            {"_id": 0}
        ).to_list(1000)
        ytd_total = sum(p.get("amount", 0) for p in ytd_payments)
        # Support both annual_approved_amount and annual_fee fields
        approved_amount = comp_plan.get("annual_approved_amount") or comp_plan.get("annual_fee") or comp_plan.get("annual_amount", 0)
        comp_aligned = ytd_total <= approved_amount
    else:
        comp_aligned = True  # No plan means no overage
    
    criteria.append(HealthScoreCriterion(
        name="Compensation Alignment",
        description="YTD compensation within approved plan",
        points=20 if comp_aligned else 0,
        achieved=comp_aligned
    ))
    if comp_aligned:
        total_score += 20
    
    # 4. Distribution Documentation (+20) - includes benevolence documentation quality
    dist_count = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    
    # Check benevolence documentation quality
    benevolence_dists = await db.distribution_records.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "is_benevolence": True
    }, {"_id": 0}).to_list(1000)
    
    benevolence_count = len(benevolence_dists)
    incomplete_benevolence = 0
    
    for bd in benevolence_dists:
        # Check for missing key fields
        if not bd.get("benevolence_recipient_name") or not bd.get("benevolence_need_description"):
            incomplete_benevolence += 1
        # Check for missing approval/minutes
        elif not bd.get("approved_at") and not bd.get("minutes_record_id"):
            incomplete_benevolence += 1
    
    # Determine points based on documentation completeness
    if dist_count == 0:
        dist_documented = False
        dist_points = 0
        dist_description = "No distributions logged"
    elif benevolence_count > 0 and incomplete_benevolence > 0:
        # Has benevolence distributions but some incomplete
        dist_documented = True  # Partially achieved
        completeness_ratio = (benevolence_count - incomplete_benevolence) / benevolence_count
        dist_points = int(20 * (0.5 + 0.5 * completeness_ratio))  # 10-20 points based on completeness
        dist_description = f"Distributions logged; {incomplete_benevolence}/{benevolence_count} benevolence distributions need documentation"
    else:
        dist_documented = True
        dist_points = 20
        if benevolence_count > 0:
            dist_description = f"All distributions documented ({benevolence_count} benevolence distributions fully documented)"
        else:
            dist_description = "Distributions logged"
    
    criteria.append(HealthScoreCriterion(
        name="Distribution Documentation",
        description=dist_description,
        points=dist_points,
        achieved=dist_documented
    ))
    total_score += dist_points
    
    # 5. Annual Review (+20)
    one_year_ago = (now - timedelta(days=365)).isoformat()
    annual_review = await db.governance_tasks.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "task_type": "annual_review",
        "completed_at": {"$gte": one_year_ago}
    }, {"_id": 0})
    annual_done = annual_review is not None
    criteria.append(HealthScoreCriterion(
        name="Annual Review",
        description="Annual review completed in last 12 months",
        points=20 if annual_done else 0,
        achieved=annual_done
    ))
    if annual_done:
        total_score += 20
    
    # Determine color
    if total_score >= 80:
        color = HealthColor.green
    elif total_score >= 60:
        color = HealthColor.yellow
    else:
        color = HealthColor.red
    
    # Save snapshot
    snapshot = {
        "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user_id,
        "score_value": total_score,
        "color": color.value,
        "calculated_at": now.isoformat()
    }
    await db.health_score_snapshots.insert_one(snapshot)
    
    return {
        "trust_id": trust_id,
        "total_score": total_score,
        "max_score": 100,
        "color": color.value,
        "criteria": [c.model_dump() for c in criteria],
        "calculated_at": now.isoformat()
    }

async def auto_update_onboarding(user_id: str, trust_id: str):
    """Auto-update onboarding state based on user actions"""
    updates = {}
    
    # Check entities
    entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
    if entity_count > 0:
        updates["entities_confirmed"] = True
    
    # Check calendar (non-custom tasks)
    task_count = await db.governance_tasks.count_documents({
        "trust_id": trust_id, 
        "user_id": user_id,
        "task_type": {"$ne": "custom"}
    })
    if task_count > 0:
        updates["calendar_set"] = True
    
    # Check minutes
    minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    if minutes_count > 0:
        updates["minutes_generated"] = True
    
    # Check distributions or compensation
    dist_count = await db.distribution_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    comp_count = await db.compensation_payments.count_documents({"trust_id": trust_id, "user_id": user_id})
    if dist_count > 0 or comp_count > 0:
        updates["distribution_logged"] = True
    
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.user_onboarding.update_one(
            {"user_id": user_id},
            {"$set": updates},
            upsert=True
        )

async def create_initial_governance_tasks(trust_id: str, user_id: str):
    """Seed a new trust with default governance tasks"""
    now = datetime.now(timezone.utc)
    
    default_tasks = [
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "annual_review",
            "due_date": (now + timedelta(days=365)).isoformat(),
            "completed_at": None,
            "description": "Annual trust review and documentation",
            "created_at": now.isoformat()
        },
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "quarterly_review",
            "due_date": (now + timedelta(days=90)).isoformat(),
            "completed_at": None,
            "description": "Quarterly trust performance review",
            "created_at": now.isoformat()
        },
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "compensation_review",
            "due_date": (now + timedelta(days=180)).isoformat(),
            "completed_at": None,
            "description": "Review trustee compensation arrangements",
            "created_at": now.isoformat()
        }
    ]
    
    await db.governance_tasks.insert_many(default_tasks)

# ==================== AUTH ENDPOINTS ====================

@api_router.post("/auth/register", response_model=UserResponse)
async def register(user: UserCreate, background_tasks: BackgroundTasks):
    existing = await db.users.find_one({"email": user.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": user.email,
        "name": user.name,
        "password_hash": hash_password(user.password),
        "picture": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(user_doc)
    
    # Initialize onboarding state
    await db.user_onboarding.insert_one({
        "user_id": user_id,
        "entities_confirmed": False,
        "calendar_set": False,
        "minutes_generated": False,
        "distribution_logged": False,
        "checklist_dismissed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Send welcome email in background
    background_tasks.add_task(
        email_service.send_welcome_email,
        to_email=user.email,
        user_name=user.name
    )
    
    return UserResponse(
        user_id=user_id,
        email=user.email,
        name=user.name,
        picture=None,
        created_at=user_doc["created_at"]
    )

@api_router.post("/auth/login")
async def login(user: UserLogin, response: Response):
    user_doc = await db.users.find_one({"email": user.email}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user_doc.get("password_hash"):
        raise HTTPException(status_code=401, detail="Please use Google login")
    
    if not verify_password(user.password, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_jwt_token(user_doc["user_id"], user_doc["email"])
    
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=JWT_EXPIRATION_HOURS * 3600,
        path="/"
    )
    
    return {
        "token": token,
        "user": {
            "user_id": user_doc["user_id"],
            "email": user_doc["email"],
            "name": user_doc["name"],
            "picture": user_doc.get("picture")
        }
    }

@api_router.post("/auth/forgot-password")
async def forgot_password(request: PasswordResetRequest, background_tasks: BackgroundTasks):
    """Request a password reset email"""
    user = await db.users.find_one({"email": request.email}, {"_id": 0})
    
    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If an account exists with this email, you will receive a password reset link."}
    
    # Check if user has a password (not OAuth-only)
    if not user.get("password_hash"):
        return {"message": "If an account exists with this email, you will receive a password reset link."}
    
    # Generate reset token (expires in 1 hour)
    reset_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    # Store reset token
    await db.password_resets.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "token": reset_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    # Send reset email
    frontend_url = os.environ['FRONTEND_URL']
    reset_url = f"{frontend_url}/reset-password?token={reset_token}"
    
    background_tasks.add_task(
        email_service.send_password_reset_email,
        to_email=user["email"],
        user_name=user.get("name", ""),
        reset_url=reset_url
    )
    
    return {"message": "If an account exists with this email, you will receive a password reset link."}

@api_router.post("/auth/reset-password")
async def reset_password(request: PasswordResetConfirm):
    """Reset password using token"""
    # Find valid reset token
    reset_record = await db.password_resets.find_one({"token": request.token}, {"_id": 0})
    
    if not reset_record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    # Check expiration
    expires_at = datetime.fromisoformat(reset_record["expires_at"].replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        await db.password_resets.delete_one({"token": request.token})
        raise HTTPException(status_code=400, detail="Reset token has expired. Please request a new one.")
    
    # Validate password
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    # Update password
    new_hash = hash_password(request.new_password)
    await db.users.update_one(
        {"user_id": reset_record["user_id"]},
        {"$set": {"password_hash": new_hash}}
    )
    
    # Delete used token
    await db.password_resets.delete_one({"token": request.token})
    
    # Invalidate all sessions for this user
    await db.user_sessions.delete_many({"user_id": reset_record["user_id"]})
    
    return {"message": "Password has been reset successfully. Please log in with your new password."}

@api_router.get("/auth/verify-reset-token")
async def verify_reset_token(token: str):
    """Verify if a reset token is valid"""
    reset_record = await db.password_resets.find_one({"token": token}, {"_id": 0})
    
    if not reset_record:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    
    expires_at = datetime.fromisoformat(reset_record["expires_at"].replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token has expired")
    
    return {"valid": True}

@api_router.post("/auth/session")
async def exchange_session(request: Request, response: Response):
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session")
            
            session_data = resp.json()
        except httpx.RequestError as e:
            logger.error(f"Error fetching session data: {e}")
            raise HTTPException(status_code=500, detail="Auth service unavailable")
    
    email = session_data.get("email")
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    
    if existing_user:
        user_id = existing_user["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": session_data.get("name", existing_user.get("name")),
                "picture": session_data.get("picture", existing_user.get("picture"))
            }}
        )
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": session_data.get("name", "User"),
            "picture": session_data.get("picture"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user_doc)
        
        # Initialize onboarding
        await db.user_onboarding.insert_one({
            "user_id": user_id,
            "entities_confirmed": False,
            "calendar_set": False,
            "minutes_generated": False,
            "distribution_logged": False,
            "checklist_dismissed": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    
    session_token = session_data.get("session_token")
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=7 * 24 * 3600,
        path="/"
    )
    
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    return {
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture")
        }
    }

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        user_id=user["user_id"],
        email=user["email"],
        name=user["name"],
        picture=user.get("picture"),
        created_at=user.get("created_at", "")
    )

@api_router.put("/auth/profile")
async def update_profile(profile: ProfileUpdate, user: dict = Depends(get_current_user)):
    """Update user profile (name)"""
    update_fields = {}
    
    if profile.name is not None:
        if len(profile.name.strip()) < 1:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        update_fields["name"] = profile.name.strip()
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": update_fields}
    )
    
    # Get updated user
    updated_user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    return {
        "message": "Profile updated successfully",
        "user": {
            "user_id": updated_user["user_id"],
            "email": updated_user["email"],
            "name": updated_user["name"],
            "picture": updated_user.get("picture")
        }
    }

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}

# ==================== NOTIFICATION PREFERENCES ====================

@api_router.get("/notifications/preferences")
async def get_notification_preferences(user: dict = Depends(get_current_user)):
    """Get user's notification preferences"""
    # Default preferences
    defaults = {
        "user_id": user["user_id"],
        "minutes_created": True,
        "distribution_created": True,
        "distribution_approved": True,
        "task_reminders": True,
        "task_overdue": True,
        "subscription_updates": True,
        "weekly_digest": False
    }
    
    prefs = await db.notification_preferences.find_one(
        {"user_id": user["user_id"]}, 
        {"_id": 0}
    )
    
    if not prefs:
        return defaults
    
    # Merge stored prefs with defaults (stored values take precedence)
    return {**defaults, **prefs}

@api_router.put("/notifications/preferences")
async def update_notification_preferences(
    prefs: NotificationPreferencesUpdate, 
    user: dict = Depends(get_current_user)
):
    """Update user's notification preferences"""
    update_fields = {k: v for k, v in prefs.dict().items() if v is not None}
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Upsert preferences
    await db.notification_preferences.update_one(
        {"user_id": user["user_id"]},
        {
            "$set": update_fields,
            "$setOnInsert": {"user_id": user["user_id"]}
        },
        upsert=True
    )
    
    # Get updated preferences
    updated_prefs = await db.notification_preferences.find_one(
        {"user_id": user["user_id"]}, 
        {"_id": 0}
    )
    
    return {
        "message": "Notification preferences updated",
        "preferences": updated_prefs
    }

@api_router.get("/user/preferences")
async def get_user_preferences(user: dict = Depends(get_current_user)):
    """Get user preferences (watermark settings, etc.)"""
    prefs = await db.user_preferences.find_one(
        {"user_id": user["user_id"]}, 
        {"_id": 0}
    )
    
    if not prefs:
        return {
            "user_id": user["user_id"],
            "hide_watermark": False
        }
    
    return prefs

@api_router.put("/user/preferences")
async def update_user_preferences(
    prefs: UserPreferencesUpdate, 
    user: dict = Depends(get_current_user)
):
    """Update user preferences - hide_watermark requires active subscription"""
    update_fields = {k: v for k, v in prefs.dict().items() if v is not None}
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Check subscription for watermark removal
    if "hide_watermark" in update_fields and update_fields["hide_watermark"]:
        subscription = await db.subscriptions.find_one(
            {"user_id": user["user_id"]},
            {"_id": 0}
        )
        if not subscription or subscription.get("status") not in ["active", "trialing"]:
            raise HTTPException(
                status_code=403, 
                detail="Watermark removal is only available for paid subscribers"
            )
    
    # Upsert preferences
    await db.user_preferences.update_one(
        {"user_id": user["user_id"]},
        {
            "$set": update_fields,
            "$setOnInsert": {"user_id": user["user_id"]}
        },
        upsert=True
    )
    
    updated_prefs = await db.user_preferences.find_one(
        {"user_id": user["user_id"]}, 
        {"_id": 0}
    )
    
    return {
        "message": "Preferences updated",
        "preferences": updated_prefs
    }

# ==================== TRUST ENDPOINTS ====================

@api_router.post("/trusts", response_model=TrustResponse)
async def create_trust(trust: TrustCreate, user: dict = Depends(get_current_user)):
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"
    trust_doc = {
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "name": trust.name,
        "trust_type": trust.trust_type.value,
        "jurisdiction": trust.jurisdiction,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.trusts.insert_one(trust_doc)
    
    # Create initial governance tasks
    await create_initial_governance_tasks(trust_id, user["user_id"])
    
    return TrustResponse(**trust_doc, governance_score=0)

@api_router.get("/trusts", response_model=List[TrustResponse])
async def get_trusts(user: dict = Depends(get_current_user)):
    trusts = await db.trusts.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
    
    result = []
    for trust in trusts:
        health = await calculate_health_score(trust["trust_id"], user["user_id"])
        result.append(TrustResponse(**trust, governance_score=health["total_score"]))
    
    return result

@api_router.get("/trusts/{trust_id}", response_model=TrustResponse)
async def get_trust(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    health = await calculate_health_score(trust_id, user["user_id"])
    return TrustResponse(**trust, governance_score=health["total_score"])

@api_router.put("/trusts/{trust_id}", response_model=TrustResponse)
async def update_trust(trust_id: str, update: TrustUpdate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    update_data = {k: v.value if isinstance(v, Enum) else v for k, v in update.model_dump().items() if v is not None}
    if update_data:
        await db.trusts.update_one({"trust_id": trust_id}, {"$set": update_data})
    
    updated = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0})
    health = await calculate_health_score(trust_id, user["user_id"])
    return TrustResponse(**updated, governance_score=health["total_score"])

@api_router.delete("/trusts/{trust_id}")
async def delete_trust(trust_id: str, user: dict = Depends(get_current_user)):
    result = await db.trusts.delete_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Delete related data
    await db.entities.delete_many({"trust_id": trust_id})
    await db.entity_relationships.delete_many({"trust_id": trust_id})
    await db.governance_tasks.delete_many({"trust_id": trust_id})
    await db.minutes_records.delete_many({"trust_id": trust_id})
    await db.distribution_records.delete_many({"trust_id": trust_id})
    await db.compensation_plans.delete_many({"trust_id": trust_id})
    await db.compensation_payments.delete_many({"trust_id": trust_id})
    await db.health_score_snapshots.delete_many({"trust_id": trust_id})
    
    return {"message": "Trust deleted"}

# ==================== ENTITY ENDPOINTS ====================

@api_router.post("/entities", response_model=EntityResponse)
async def create_entity(entity: EntityCreate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": entity.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    entity_doc = {
        "entity_id": entity_id,
        "user_id": user["user_id"],
        **entity.model_dump(),
        "entity_type": entity.entity_type.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.entities.insert_one(entity_doc)
    await auto_update_onboarding(user["user_id"], entity.trust_id)
    
    return EntityResponse(**entity_doc)

@api_router.get("/entities", response_model=List[EntityResponse])
async def get_entities(trust_id: str, user: dict = Depends(get_current_user)):
    entities = await db.entities.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(100)
    
    return [EntityResponse(**e) for e in entities]

@api_router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(entity_id: str, user: dict = Depends(get_current_user)):
    entity = await db.entities.find_one(
        {"entity_id": entity_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    return EntityResponse(**entity)

@api_router.patch("/entities/{entity_id}", response_model=EntityResponse)
async def update_entity(entity_id: str, updates: dict, user: dict = Depends(get_current_user)):
    entity = await db.entities.find_one(
        {"entity_id": entity_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Filter only allowed fields
    allowed_fields = [
        "name", "legal_name", "formation_date", "governing_law", "ein",
        "trustee_names", "beneficiary_standard", "article_ref_distribution",
        "article_ref_compensation", "article_ref_amendment", "oversight_required",
        "member_names", "manager_names", "article_ref_authority", "article_ref_profit_distribution"
    ]
    update_data = {k: v for k, v in updates.items() if k in allowed_fields}
    
    if update_data:
        await db.entities.update_one({"entity_id": entity_id}, {"$set": update_data})
    
    updated = await db.entities.find_one({"entity_id": entity_id}, {"_id": 0})
    return EntityResponse(**updated)

@api_router.delete("/entities/{entity_id}")
async def delete_entity(entity_id: str, user: dict = Depends(get_current_user)):
    result = await db.entities.delete_one({"entity_id": entity_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Delete related relationships
    await db.entity_relationships.delete_many({"$or": [
        {"parent_entity_id": entity_id},
        {"child_entity_id": entity_id}
    ]})
    
    return {"message": "Entity deleted"}

# ==================== ENTITY RELATIONSHIP ENDPOINTS ====================

@api_router.post("/entity-relationships", response_model=EntityRelationshipResponse)
async def create_relationship(rel: EntityRelationshipCreate, user: dict = Depends(get_current_user)):
    rel_id = f"rel_{uuid.uuid4().hex[:12]}"
    rel_doc = {
        "relationship_id": rel_id,
        "user_id": user["user_id"],
        **rel.model_dump(),
        "relationship_type": rel.relationship_type.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.entity_relationships.insert_one(rel_doc)
    
    return EntityRelationshipResponse(**rel_doc)

@api_router.get("/entity-relationships", response_model=List[EntityRelationshipResponse])
async def get_relationships(trust_id: str, user: dict = Depends(get_current_user)):
    rels = await db.entity_relationships.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(100)
    
    return [EntityRelationshipResponse(**r) for r in rels]

@api_router.delete("/entity-relationships/{relationship_id}")
async def delete_relationship(relationship_id: str, user: dict = Depends(get_current_user)):
    result = await db.entity_relationships.delete_one({
        "relationship_id": relationship_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Relationship not found")
    
    return {"message": "Relationship deleted"}

# ==================== TRUST UNITS ENDPOINTS ====================

async def get_or_create_units_settings(trust_id: str, user_id: str) -> dict:
    """Get or create default units settings for a trust"""
    settings = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not settings:
        # Create default settings
        settings = {
            "trust_id": trust_id,
            "user_id": user_id,
            "total_authorized_units": 100,
            "unit_label": "Certificate Unit",
            "allow_fractional": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_units_settings.insert_one(settings)
    return settings

async def get_total_active_units(trust_id: str, user_id: str, exclude_certificate_id: str = None) -> float:
    """Calculate total units across all active certificates for a trust"""
    query = {
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    }
    if exclude_certificate_id:
        query["certificate_id"] = {"$ne": exclude_certificate_id}
    
    certificates = await db.trust_unit_certificates.find(query, {"_id": 0, "units": 1}).to_list(1000)
    return sum(cert.get("units", 0) for cert in certificates)

async def get_next_certificate_number(trust_id: str, user_id: str) -> str:
    """Get the next sequential certificate number for a trust"""
    # Count existing certificates for this trust
    count = await db.trust_unit_certificates.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    return f"CU-{str(count + 1).zfill(3)}"

def validate_units(units: float, allow_fractional: bool) -> float:
    """Validate and normalize unit value"""
    if not allow_fractional:
        if units != int(units):
            raise HTTPException(
                status_code=400, 
                detail="Fractional units not allowed. Enable 'allow_fractional' in settings first."
            )
        return int(units)
    return round(units, 4)

@api_router.get("/trust-units/summary", response_model=TrustUnitsSummaryResponse)
async def get_trust_units_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """Get complete units summary for a trust including settings, certificates, and aggregates"""
    # Verify trust exists and belongs to user
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Get or create settings
    settings = await get_or_create_units_settings(trust_id, user["user_id"])
    
    # Get all certificates
    certificates_raw = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("certificate_number", 1).to_list(1000)
    
    total_authorized = settings["total_authorized_units"]
    
    # Compute percentage for each certificate
    certificates = []
    total_issued = 0
    active_count = 0
    
    for cert in certificates_raw:
        percentage = (cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
        cert_response = TrustUnitCertificateResponse(
            **cert,
            percentage=round(percentage, 4)
        )
        certificates.append(cert_response)
        
        if cert["status"] == "active":
            total_issued += cert["units"]
            active_count += 1
    
    return TrustUnitsSummaryResponse(
        settings=TrustUnitsSettingsResponse(**settings),
        certificates=certificates,
        total_issued_units=total_issued,
        remaining_units=total_authorized - total_issued,
        active_certificate_count=active_count
    )

@api_router.patch("/trust-units/settings", response_model=TrustUnitsSettingsResponse)
async def update_trust_units_settings(
    trust_id: str, 
    update: TrustUnitsSettingsUpdate, 
    user: dict = Depends(get_current_user)
):
    """Update units settings for a trust"""
    # Verify trust exists
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Ensure settings exist (creates default if not)
    await get_or_create_units_settings(trust_id, user["user_id"])
    
    # If reducing total_authorized_units, validate against active certificates
    if update.total_authorized_units is not None:
        current_active_units = await get_total_active_units(trust_id, user["user_id"])
        if update.total_authorized_units < current_active_units:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reduce total authorized units to {update.total_authorized_units}. "
                       f"There are currently {current_active_units} active units issued."
            )
    
    # Build update fields
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if update.total_authorized_units is not None:
        update_fields["total_authorized_units"] = update.total_authorized_units
    if update.unit_label is not None:
        update_fields["unit_label"] = update.unit_label
    if update.allow_fractional is not None:
        update_fields["allow_fractional"] = update.allow_fractional
    
    await db.trust_units_settings.update_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": update_fields}
    )
    
    updated = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    return TrustUnitsSettingsResponse(**updated)

@api_router.post("/trust-units/certificates", response_model=TrustUnitCertificateResponse)
async def create_unit_certificate(
    certificate: TrustUnitCertificateCreate, 
    user: dict = Depends(get_current_user)
):
    """Issue a new unit certificate"""
    # Verify trust exists
    trust = await db.trusts.find_one({"trust_id": certificate.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Get settings
    settings = await get_or_create_units_settings(certificate.trust_id, user["user_id"])
    
    # Validate units
    units = validate_units(certificate.units, settings["allow_fractional"])
    
    if units <= 0:
        raise HTTPException(status_code=400, detail="Units must be greater than 0")
    
    # Validate total units won't exceed authorized
    current_active = await get_total_active_units(certificate.trust_id, user["user_id"])
    total_authorized = settings["total_authorized_units"]
    
    if current_active + units > total_authorized:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot issue {units} units. Only {total_authorized - current_active} units remaining. "
                   f"(Active: {current_active}, Authorized: {total_authorized})"
        )
    
    # Generate certificate
    certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
    certificate_number = await get_next_certificate_number(certificate.trust_id, user["user_id"])
    
    cert_doc = {
        "certificate_id": certificate_id,
        "trust_id": certificate.trust_id,
        "user_id": user["user_id"],
        "holder_name": certificate.holder_name,
        "holder_identifier": certificate.holder_identifier,
        "units": units,
        "issue_date": certificate.issue_date,
        "certificate_number": certificate_number,
        "status": "active",
        "replaced_by_certificate_id": None,
        "notes": certificate.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None
    }
    
    await db.trust_unit_certificates.insert_one(cert_doc)
    
    # Record the transfer (issuance)
    transfer_doc = {
        "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
        "trust_id": certificate.trust_id,
        "user_id": user["user_id"],
        "from_holder": None,  # Initial issuance
        "to_holder": certificate.holder_name,
        "units": units,
        "reason": "Initial certificate issuance",
        "minutes_record_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.trust_unit_transfers.insert_one(transfer_doc)
    
    # Compute percentage
    percentage = (units / total_authorized * 100) if total_authorized > 0 else 0
    
    return TrustUnitCertificateResponse(**cert_doc, percentage=round(percentage, 4))

@api_router.patch("/trust-units/certificates/{certificate_id}", response_model=TrustUnitCertificateResponse)
async def update_unit_certificate(
    certificate_id: str,
    update: TrustUnitCertificateUpdate,
    user: dict = Depends(get_current_user)
):
    """Update a unit certificate"""
    # Find existing certificate
    cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    # Get settings
    settings = await get_or_create_units_settings(cert["trust_id"], user["user_id"])
    
    # Build update fields
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if update.holder_name is not None:
        update_fields["holder_name"] = update.holder_name
    if update.holder_identifier is not None:
        update_fields["holder_identifier"] = update.holder_identifier
    if update.notes is not None:
        update_fields["notes"] = update.notes
    if update.status is not None:
        update_fields["status"] = update.status.value
    
    # If updating units, validate
    if update.units is not None:
        units = validate_units(update.units, settings["allow_fractional"])
        
        if units <= 0:
            raise HTTPException(status_code=400, detail="Units must be greater than 0")
        
        # Calculate new total (excluding this certificate's current units)
        current_active_excluding_this = await get_total_active_units(
            cert["trust_id"], 
            user["user_id"], 
            exclude_certificate_id=certificate_id
        )
        
        # Only count new units if certificate will be active
        new_status = update.status.value if update.status else cert["status"]
        if new_status == "active":
            total_authorized = settings["total_authorized_units"]
            if current_active_excluding_this + units > total_authorized:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update to {units} units. Would exceed authorized total. "
                           f"(Other active: {current_active_excluding_this}, Authorized: {total_authorized})"
                )
        
        update_fields["units"] = units
    
    await db.trust_unit_certificates.update_one(
        {"certificate_id": certificate_id},
        {"$set": update_fields}
    )
    
    # Get updated certificate
    updated_cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id},
        {"_id": 0}
    )
    
    # Compute percentage
    total_authorized = settings["total_authorized_units"]
    percentage = (updated_cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
    
    return TrustUnitCertificateResponse(**updated_cert, percentage=round(percentage, 4))

@api_router.get("/trust-units/certificates", response_model=List[TrustUnitCertificateResponse])
async def list_unit_certificates(
    trust_id: str,
    status: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """List all certificates for a trust, optionally filtered by status"""
    # Verify trust exists
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Get settings for percentage calculation
    settings = await get_or_create_units_settings(trust_id, user["user_id"])
    total_authorized = settings["total_authorized_units"]
    
    # Build query
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    if status:
        query["status"] = status
    
    certificates = await db.trust_unit_certificates.find(query, {"_id": 0}).sort("certificate_number", 1).to_list(1000)
    
    # Add computed percentage
    result = []
    for cert in certificates:
        percentage = (cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
        result.append(TrustUnitCertificateResponse(**cert, percentage=round(percentage, 4)))
    
    return result

@api_router.post("/trust-units/transfers", response_model=TrustUnitTransferResponse)
async def create_unit_transfer(
    transfer: TrustUnitTransferCreate,
    user: dict = Depends(get_current_user)
):
    """Record a unit transfer between holders (cancels old certificate, issues new one)"""
    # Verify trust exists
    trust = await db.trusts.find_one({"trust_id": transfer.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Get settings
    settings = await get_or_create_units_settings(transfer.trust_id, user["user_id"])
    
    # Validate units
    units = validate_units(transfer.units, settings["allow_fractional"])
    
    if units <= 0:
        raise HTTPException(status_code=400, detail="Transfer units must be greater than 0")
    
    # If from_holder is specified, find and cancel/reduce their certificate
    if transfer.from_holder:
        from_cert = await db.trust_unit_certificates.find_one({
            "trust_id": transfer.trust_id,
            "user_id": user["user_id"],
            "holder_name": transfer.from_holder,
            "status": "active"
        }, {"_id": 0})
        
        if not from_cert:
            raise HTTPException(
                status_code=404, 
                detail=f"No active certificate found for holder '{transfer.from_holder}'"
            )
        
        if from_cert["units"] < units:
            raise HTTPException(
                status_code=400,
                detail=f"Holder '{transfer.from_holder}' only has {from_cert['units']} units. Cannot transfer {units}."
            )
        
        # Cancel the old certificate
        new_cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        await db.trust_unit_certificates.update_one(
            {"certificate_id": from_cert["certificate_id"]},
            {"$set": {
                "status": "replaced",
                "replaced_by_certificate_id": new_cert_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # If from_holder has remaining units, issue new certificate for remainder
        remaining_units = from_cert["units"] - units
        if remaining_units > 0:
            remainder_cert_number = await get_next_certificate_number(transfer.trust_id, user["user_id"])
            remainder_cert = {
                "certificate_id": new_cert_id,
                "trust_id": transfer.trust_id,
                "user_id": user["user_id"],
                "holder_name": transfer.from_holder,
                "holder_identifier": from_cert.get("holder_identifier"),
                "units": remaining_units,
                "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "certificate_number": remainder_cert_number,
                "status": "active",
                "replaced_by_certificate_id": None,
                "notes": f"Remainder after transfer of {units} units to {transfer.to_holder}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None
            }
            await db.trust_unit_certificates.insert_one(remainder_cert)
    
    # Issue new certificate to to_holder (or add to existing)
    existing_to_cert = await db.trust_unit_certificates.find_one({
        "trust_id": transfer.trust_id,
        "user_id": user["user_id"],
        "holder_name": transfer.to_holder,
        "status": "active"
    }, {"_id": 0})
    
    if existing_to_cert:
        # Add units to existing certificate (cancel old, issue new with combined)
        combined_units = existing_to_cert["units"] + units
        new_to_cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        
        await db.trust_unit_certificates.update_one(
            {"certificate_id": existing_to_cert["certificate_id"]},
            {"$set": {
                "status": "replaced",
                "replaced_by_certificate_id": new_to_cert_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        new_cert_number = await get_next_certificate_number(transfer.trust_id, user["user_id"])
        new_to_cert = {
            "certificate_id": new_to_cert_id,
            "trust_id": transfer.trust_id,
            "user_id": user["user_id"],
            "holder_name": transfer.to_holder,
            "holder_identifier": existing_to_cert.get("holder_identifier"),
            "units": combined_units,
            "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "certificate_number": new_cert_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": f"Combined certificate after receiving {units} units" + 
                     (f" from {transfer.from_holder}" if transfer.from_holder else ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_unit_certificates.insert_one(new_to_cert)
    else:
        # Create new certificate for to_holder
        new_cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        new_cert_number = await get_next_certificate_number(transfer.trust_id, user["user_id"])
        
        new_cert = {
            "certificate_id": new_cert_id,
            "trust_id": transfer.trust_id,
            "user_id": user["user_id"],
            "holder_name": transfer.to_holder,
            "holder_identifier": None,
            "units": units,
            "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "certificate_number": new_cert_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": "Transfer" + (f" from {transfer.from_holder}" if transfer.from_holder else " (new issuance)"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_unit_certificates.insert_one(new_cert)
    
    # Record the transfer
    transfer_id = f"transfer_{uuid.uuid4().hex[:12]}"
    transfer_doc = {
        "transfer_id": transfer_id,
        "trust_id": transfer.trust_id,
        "user_id": user["user_id"],
        "from_holder": transfer.from_holder,
        "to_holder": transfer.to_holder,
        "units": units,
        "reason": transfer.reason,
        "minutes_record_id": transfer.minutes_record_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.trust_unit_transfers.insert_one(transfer_doc)
    
    return TrustUnitTransferResponse(**transfer_doc)

@api_router.get("/trust-units/transfers", response_model=List[TrustUnitTransferResponse])
async def list_unit_transfers(
    trust_id: str,
    user: dict = Depends(get_current_user)
):
    """List all transfers for a trust"""
    transfers = await db.trust_unit_transfers.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(1000)
    
    return [TrustUnitTransferResponse(**t) for t in transfers]

def generate_certificate_pdf(cert: dict, trust: dict, settings: dict, hide_watermark: bool = False) -> bytes:
    """Generate a professional PDF certificate for trust units"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1*inch, bottomMargin=0.75*inch)
    
    # Custom styles matching TrustOffice design
    styles = getSampleStyleSheet()
    
    # Navy color for headers
    navy = colors.HexColor('#010079')
    
    title_style = ParagraphStyle(
        'CertTitle',
        parent=styles['Heading1'],
        fontName='Times-Bold',
        fontSize=24,
        spaceAfter=6,
        textColor=navy,
        alignment=1  # Center
    )
    
    subtitle_style = ParagraphStyle(
        'CertSubtitle',
        parent=styles['Heading2'],
        fontName='Times-Roman',
        fontSize=14,
        spaceBefore=4,
        spaceAfter=20,
        textColor=navy,
        alignment=1
    )
    
    heading_style = ParagraphStyle(
        'CertHeading',
        parent=styles['Heading2'],
        fontName='Times-Bold',
        fontSize=12,
        spaceBefore=16,
        spaceAfter=8,
        textColor=navy
    )
    
    body_style = ParagraphStyle(
        'CertBody',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        leading=16,
        spaceAfter=8
    )
    
    label_style = ParagraphStyle(
        'CertLabel',
        fontName='Courier',
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        spaceBefore=4
    )
    
    mono_style = ParagraphStyle(
        'CertMono',
        fontName='Courier',
        fontSize=10,
        textColor=colors.HexColor('#333333')
    )
    
    story = []
    
    # Certificate Header
    story.append(Paragraph("CERTIFICATE OF BENEFICIAL INTEREST", title_style))
    story.append(Paragraph(trust.get('name', 'Trust'), subtitle_style))
    
    # Certificate Number box
    cert_number_data = [
        [Paragraph("CERTIFICATE NUMBER", label_style)],
        [Paragraph(cert.get('certificate_number', 'N/A'), ParagraphStyle('Big', fontName='Courier-Bold', fontSize=18, alignment=1))]
    ]
    cert_number_table = Table(cert_number_data, colWidths=[2.5*inch])
    cert_number_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOX', (0, 0), (-1, -1), 1, navy),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(cert_number_table)
    story.append(Spacer(1, 24))
    
    # Main certificate text
    percentage = cert.get('percentage', 0)
    units = cert.get('units', 0)
    holder_name = cert.get('holder_name', 'Unknown')
    issue_date = cert.get('issue_date', '')
    if 'T' in issue_date:
        issue_date = issue_date.split('T')[0]
    
    cert_text = f"""This certifies that <b>{holder_name}</b> is the registered holder of 
    <b>{units} {settings.get('unit_label', 'Certificate Units')}</b>, representing 
    <b>{percentage:.4f}%</b> of the total authorized beneficial interest in the above-named trust."""
    
    story.append(Paragraph(cert_text, body_style))
    story.append(Spacer(1, 16))
    
    # Details table
    details_data = [
        [Paragraph("HOLDER NAME", label_style), Paragraph(holder_name, mono_style)],
        [Paragraph("HOLDER IDENTIFIER", label_style), Paragraph(cert.get('holder_identifier', 'N/A') or 'N/A', mono_style)],
        [Paragraph("UNITS HELD", label_style), Paragraph(str(units), mono_style)],
        [Paragraph("PERCENTAGE", label_style), Paragraph(f"{percentage:.4f}%", mono_style)],
        [Paragraph("ISSUE DATE", label_style), Paragraph(issue_date, mono_style)],
        [Paragraph("STATUS", label_style), Paragraph(cert.get('status', 'active').upper(), mono_style)],
    ]
    
    details_table = Table(details_data, colWidths=[2*inch, 4*inch])
    details_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#DDDDDD')),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 24))
    
    # Trust information
    story.append(Paragraph("TRUST INFORMATION", heading_style))
    trust_data = [
        [Paragraph("TRUST NAME", label_style), Paragraph(trust.get('name', 'N/A'), mono_style)],
        [Paragraph("JURISDICTION", label_style), Paragraph(trust.get('jurisdiction', 'N/A') or 'N/A', mono_style)],
        [Paragraph("TOTAL AUTHORIZED UNITS", label_style), Paragraph(str(settings.get('total_authorized_units', 100)), mono_style)],
    ]
    
    trust_table = Table(trust_data, colWidths=[2*inch, 4*inch])
    trust_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(trust_table)
    story.append(Spacer(1, 36))
    
    # Signature blocks
    story.append(Paragraph("TRUSTEE CERTIFICATION", heading_style))
    story.append(Paragraph(
        "The undersigned Trustee(s) hereby certify that this certificate has been duly issued in accordance with the terms of the trust instrument.",
        body_style
    ))
    story.append(Spacer(1, 24))
    
    # Signature lines
    sig_data = [
        [Paragraph('_' * 40, body_style), Paragraph('_' * 40, body_style)],
        [Paragraph('Trustee Signature', label_style), Paragraph('Date', label_style)],
    ]
    sig_table = Table(sig_data, colWidths=[3*inch, 3*inch])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 20))
    
    sig_data2 = [
        [Paragraph('_' * 40, body_style), Paragraph('_' * 40, body_style)],
        [Paragraph('Trustee Signature', label_style), Paragraph('Date', label_style)],
    ]
    sig_table2 = Table(sig_data2, colWidths=[3*inch, 3*inch])
    sig_table2.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(sig_table2)
    
    # Footer with watermark
    story.append(Spacer(1, 30))
    if not hide_watermark:
        story.append(Paragraph(
            f"Generated by TrustOffice on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}",
            ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#999999'), alignment=1)
        ))
    
    doc.build(story)
    return buffer.getvalue()

@api_router.get("/trust-units/certificates/{certificate_id}/pdf")
async def get_certificate_pdf(certificate_id: str, user: dict = Depends(get_current_user)):
    """Generate and return PDF for a unit certificate"""
    cert = await db.trust_unit_certificates.find_one(
        {"certificate_id": certificate_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    trust = await db.trusts.find_one(
        {"trust_id": cert["trust_id"], "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    settings = await get_or_create_units_settings(cert["trust_id"], user["user_id"])
    
    # Compute percentage
    total_authorized = settings["total_authorized_units"]
    cert["percentage"] = (cert["units"] / total_authorized * 100) if total_authorized > 0 else 0
    
    # Check if watermark should be shown
    show_watermark = await should_show_watermark(user["user_id"])
    
    pdf_bytes = generate_certificate_pdf(cert, trust or {}, settings, hide_watermark=not show_watermark)
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    return {
        "pdf_base64": pdf_base64,
        "filename": f"certificate_{cert.get('certificate_number', certificate_id)}.pdf"
    }

async def create_certificates_from_beneficiary_designation(minutes_id: str, user_id: str) -> List[dict]:
    """
    Helper function to create initial certificates from a 'Designation of Beneficiaries' minutes template.
    Can be called after a designation minutes is finalized.
    
    Returns list of created certificate IDs.
    """
    # Find the minutes template
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user_id},
        {"_id": 0}
    )
    
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    if minutes.get("template_type") != "designation_of_beneficiaries":
        raise HTTPException(status_code=400, detail="Minutes is not a beneficiary designation template")
    
    template_data = minutes.get("template_data", {})
    beneficiaries = template_data.get("beneficiaries", [])
    total_units = template_data.get("total_units", 100)
    trust_id = minutes["trust_id"]
    
    if not beneficiaries:
        raise HTTPException(status_code=400, detail="No beneficiaries found in minutes template")
    
    # Get or create settings with total_units from the minutes
    settings = await get_or_create_units_settings(trust_id, user_id)
    
    # Update total_authorized_units to match the designation
    if settings["total_authorized_units"] != total_units:
        await db.trust_units_settings.update_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"$set": {
                "total_authorized_units": total_units,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    created_certificates = []
    
    for ben in beneficiaries:
        name = ben.get("name", "").strip()
        units = ben.get("units", 0)
        
        if not name or not units:
            continue
        
        try:
            units = float(units) if settings["allow_fractional"] else int(units)
        except (ValueError, TypeError):
            continue
        
        if units <= 0:
            continue
        
        # Create certificate
        certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
        certificate_number = await get_next_certificate_number(trust_id, user_id)
        
        cert_doc = {
            "certificate_id": certificate_id,
            "trust_id": trust_id,
            "user_id": user_id,
            "holder_name": name,
            "holder_identifier": None,
            "units": units,
            "issue_date": minutes.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "certificate_number": certificate_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": f"Created from beneficiary designation minutes ({minutes_id})",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        
        await db.trust_unit_certificates.insert_one(cert_doc)
        
        # Record transfer
        transfer_doc = {
            "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "from_holder": None,
            "to_holder": name,
            "units": units,
            "reason": f"Initial designation per minutes {minutes_id}",
            "minutes_record_id": minutes_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.trust_unit_transfers.insert_one(transfer_doc)
        
        created_certificates.append(certificate_id)
    
    return created_certificates

@api_router.post("/trust-units/create-from-minutes/{minutes_id}")
async def create_certificates_from_minutes(
    minutes_id: str,
    user: dict = Depends(get_current_user)
):
    """Create certificates from a finalized beneficiary designation minutes template"""
    created_ids = await create_certificates_from_beneficiary_designation(minutes_id, user["user_id"])
    
    return {
        "message": f"Created {len(created_ids)} certificates from minutes designation",
        "certificate_ids": created_ids
    }

class BootstrapFromMinutesResponse(BaseModel):
    """Response model for bootstrap-from-minutes endpoint"""
    success: bool
    message: str
    minutes_id: str
    trust_id: str
    total_authorized_units: int
    certificates_created: int
    certificates: List[TrustUnitCertificateResponse]
    total_issued_units: float
    remaining_units: float

@api_router.post("/trust-units/bootstrap-from-minutes/{minutes_id}", response_model=BootstrapFromMinutesResponse)
async def bootstrap_certificates_from_minutes(
    minutes_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Populate Trust Unit Certificates from an existing 'Designation of Beneficiaries' minutes record.
    
    This is an explicit admin/advanced operation that:
    1. Reads template_data.total_units and beneficiaries array from the minutes
    2. Creates trust_units_settings if it doesn't exist (with total_authorized_units = template_data.total_units)
    3. Creates trust_unit_certificates for each beneficiary
    4. Validates that summed units do not exceed total_authorized_units
    5. Returns the resulting certificates summary
    
    Note: This does not duplicate certificates if called multiple times - it checks for existing certificates.
    """
    # Find the minutes template
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    if minutes.get("template_type") != "designation_of_beneficiaries":
        raise HTTPException(
            status_code=400, 
            detail=f"Minutes is not a beneficiary designation template. Found type: {minutes.get('template_type')}"
        )
    
    template_data = minutes.get("template_data", {})
    beneficiaries = template_data.get("beneficiaries", [])
    total_units_from_minutes = template_data.get("total_units", 100)
    trust_id = minutes["trust_id"]
    meeting_date = minutes.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    
    if not beneficiaries:
        raise HTTPException(status_code=400, detail="No beneficiaries found in minutes template_data")
    
    # Calculate total units requested from beneficiaries
    total_requested_units = 0
    valid_beneficiaries = []
    for ben in beneficiaries:
        name = ben.get("name", "").strip()
        units = ben.get("units", 0)
        
        if not name or not units:
            continue
        
        try:
            units = float(units)
        except (ValueError, TypeError):
            continue
        
        if units <= 0:
            continue
        
        total_requested_units += units
        valid_beneficiaries.append({"name": name, "units": units})
    
    if not valid_beneficiaries:
        raise HTTPException(status_code=400, detail="No valid beneficiaries with units found in minutes template_data")
    
    # Validate total requested doesn't exceed what's designated
    if total_requested_units > total_units_from_minutes:
        raise HTTPException(
            status_code=400,
            detail=f"Sum of beneficiary units ({total_requested_units}) exceeds total_units in designation ({total_units_from_minutes})"
        )
    
    # Get or create settings
    existing_settings = await db.trust_units_settings.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    if not existing_settings:
        # Create settings with total_units from the minutes
        settings = {
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "total_authorized_units": total_units_from_minutes,
            "unit_label": "Certificate Unit",
            "allow_fractional": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.trust_units_settings.insert_one(settings)
        total_authorized = total_units_from_minutes
        allow_fractional = False
    else:
        total_authorized = existing_settings["total_authorized_units"]
        allow_fractional = existing_settings.get("allow_fractional", False)
    
    # Check for existing certificates from this minutes record to avoid duplicates FIRST
    existing_from_minutes = await db.trust_unit_certificates.count_documents({
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "notes": {"$regex": f"minutes \\({minutes_id}\\)"}
    })
    
    if existing_from_minutes > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Certificates have already been created from this minutes record ({existing_from_minutes} found). "
                   "This operation can only be performed once per minutes record."
        )
    
    # Check current active units
    current_active_units = await get_total_active_units(trust_id, user["user_id"])
    
    # Validate total won't exceed authorized
    if current_active_units + total_requested_units > total_authorized:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create certificates. Current active: {current_active_units}, "
                   f"Requested: {total_requested_units}, Authorized: {total_authorized}. "
                   f"Would exceed by {current_active_units + total_requested_units - total_authorized} units."
        )
    
    # Create certificates for each beneficiary
    created_certificates = []
    
    for ben in valid_beneficiaries:
        name = ben["name"]
        units = ben["units"]
        
        # Normalize units based on fractional setting
        if not allow_fractional:
            units = int(units)
        else:
            units = round(units, 4)
        
        certificate_id = f"cert_{uuid.uuid4().hex[:12]}"
        certificate_number = await get_next_certificate_number(trust_id, user["user_id"])
        
        cert_doc = {
            "certificate_id": certificate_id,
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "holder_name": name,
            "holder_identifier": None,
            "units": units,
            "issue_date": meeting_date,
            "certificate_number": certificate_number,
            "status": "active",
            "replaced_by_certificate_id": None,
            "notes": f"Created from beneficiary designation minutes ({minutes_id})",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        
        await db.trust_unit_certificates.insert_one(cert_doc)
        
        # Record transfer (issuance)
        transfer_doc = {
            "transfer_id": f"transfer_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "from_holder": None,
            "to_holder": name,
            "units": units,
            "reason": f"Initial designation per minutes {minutes_id}",
            "minutes_record_id": minutes_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.trust_unit_transfers.insert_one(transfer_doc)
        
        # Add to created list with computed percentage
        percentage = (units / total_authorized * 100) if total_authorized > 0 else 0
        created_certificates.append(TrustUnitCertificateResponse(
            **cert_doc,
            percentage=round(percentage, 4)
        ))
    
    # Calculate summary
    total_issued = sum(cert.units for cert in created_certificates)
    
    return BootstrapFromMinutesResponse(
        success=True,
        message=f"Successfully created {len(created_certificates)} certificates from beneficiary designation",
        minutes_id=minutes_id,
        trust_id=trust_id,
        total_authorized_units=total_authorized,
        certificates_created=len(created_certificates),
        certificates=created_certificates,
        total_issued_units=total_issued,
        remaining_units=total_authorized - (current_active_units + total_issued)
    )

# ==================== GOVERNANCE TASK ENDPOINTS ====================

@api_router.post("/tasks", response_model=GovernanceTaskResponse)
async def create_task(task: GovernanceTaskCreate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": task.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task_doc = {
        "task_id": task_id,
        "trust_id": task.trust_id,
        "user_id": user["user_id"],
        "task_type": task.task_type.value,
        "due_date": task.due_date,
        "completed_at": None,
        "description": task.description,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.governance_tasks.insert_one(task_doc)
    await auto_update_onboarding(user["user_id"], task.trust_id)
    
    status = get_task_status(task.due_date, None)
    return GovernanceTaskResponse(**task_doc, status=status)

@api_router.get("/tasks", response_model=List[GovernanceTaskResponse])
async def get_tasks(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    tasks = await db.governance_tasks.find(query, {"_id": 0}).sort("due_date", 1).to_list(1000)
    
    result = []
    for t in tasks:
        status = get_task_status(t["due_date"], t.get("completed_at"))
        result.append(GovernanceTaskResponse(**t, status=status))
    
    return result

@api_router.patch("/tasks/{task_id}/complete")
async def complete_task(task_id: str, user: dict = Depends(get_current_user)):
    task = await db.governance_tasks.find_one(
        {"task_id": task_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    completed_at = datetime.now(timezone.utc).isoformat()
    await db.governance_tasks.update_one(
        {"task_id": task_id},
        {"$set": {"completed_at": completed_at}}
    )
    
    return {"message": "Task completed", "completed_at": completed_at}

@api_router.patch("/tasks/{task_id}/uncomplete")
async def uncomplete_task(task_id: str, user: dict = Depends(get_current_user)):
    result = await db.governance_tasks.update_one(
        {"task_id": task_id, "user_id": user["user_id"]},
        {"$set": {"completed_at": None}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"message": "Task marked incomplete"}

@api_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    result = await db.governance_tasks.delete_one({"task_id": task_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"message": "Task deleted"}

# ==================== BENEFICIARY DASHBOARD ====================

@api_router.get("/beneficiaries/dashboard", response_model=BeneficiaryDashboardResponse)
async def get_beneficiary_dashboard(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Beneficiary Dashboard showing current unit allocations per certificate holder.
    
    Returns:
    - Trust unit settings and totals
    - List of beneficiaries with their aggregated holdings
    - Recent transfers
    """
    user_id = user["user_id"]
    
    # Get trust (use provided or default to most recent)
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
        if not trust:
            raise HTTPException(status_code=404, detail="Trust not found")
    else:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        if not trust:
            raise HTTPException(status_code=404, detail="No trust found")
    
    trust_id = trust["trust_id"]
    trust_name = trust.get("name", "Unnamed Trust")
    
    # Get unit settings
    settings = await get_or_create_units_settings(trust_id, user_id)
    total_authorized = settings["total_authorized_units"]
    unit_label = settings.get("unit_label", "Certificate Unit")
    
    # Get all active certificates
    certificates = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "user_id": user_id, "status": "active"},
        {"_id": 0}
    ).to_list(1000)
    
    # Aggregate by holder
    holder_map = {}
    for cert in certificates:
        holder = cert["holder_name"]
        if holder not in holder_map:
            holder_map[holder] = {
                "holder_name": holder,
                "holder_identifier": cert.get("holder_identifier"),
                "total_units": 0,
                "certificates": []
            }
        holder_map[holder]["total_units"] += cert["units"]
        holder_map[holder]["certificates"].append({
            "certificate_id": cert["certificate_id"],
            "certificate_number": cert["certificate_number"],
            "units": cert["units"],
            "issue_date": cert["issue_date"],
            "notes": cert.get("notes", "")
        })
    
    # Build beneficiary allocations with percentages
    beneficiaries = []
    total_issued = 0
    for holder_data in holder_map.values():
        percentage = (holder_data["total_units"] / total_authorized * 100) if total_authorized > 0 else 0
        total_issued += holder_data["total_units"]
        beneficiaries.append(BeneficiaryAllocation(
            holder_name=holder_data["holder_name"],
            holder_identifier=holder_data["holder_identifier"],
            total_units=holder_data["total_units"],
            percentage=round(percentage, 4),
            certificate_count=len(holder_data["certificates"]),
            certificates=holder_data["certificates"]
        ))
    
    # Sort by total_units descending
    beneficiaries.sort(key=lambda x: x.total_units, reverse=True)
    
    # Get recent transfers
    transfers = await db.trust_unit_transfers.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)
    
    return BeneficiaryDashboardResponse(
        trust_id=trust_id,
        trust_name=trust_name,
        total_authorized_units=total_authorized,
        total_issued_units=total_issued,
        remaining_units=total_authorized - total_issued,
        unit_label=unit_label,
        active_certificate_count=len(certificates),
        beneficiaries=beneficiaries,
        recent_transfers=transfers
    )


# ==================== MINUTES ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/minutes.py
# Endpoints: POST/GET/DELETE /minutes, GET /minutes/{id}/pdf

# ==================== SCHEDULE A ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/schedule_a.py
# Endpoints: POST/GET/PUT/DELETE /schedule-a, GET /schedule-a/summary/{trust_id}, GET /schedule-a/export/{trust_id}/pdf


# ==================== MINUTES TEMPLATES ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/minutes.py
# Endpoints: POST/GET/PUT/DELETE /minutes-templates, GET /template-options
# Helper functions: generate_template_document(), generate_*_content()

# ==================== BENEVOLENCE ENDPOINTS ====================

@api_router.post("/benevolence", response_model=BenevolenceRecordResponse)
async def create_benevolence_record(record: BenevolenceRecordCreate, user: dict = Depends(get_current_user)):
    """Create a new benevolence record"""
    trust = await db.trusts.find_one({"trust_id": record.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    if not trust.get("benevolence_enabled"):
        raise HTTPException(status_code=400, detail="Benevolence mode is not enabled for this trust")
    
    record_id = f"ben_{uuid.uuid4().hex[:12]}"
    record_doc = {
        "record_id": record_id,
        "trust_id": record.trust_id,
        "user_id": user["user_id"],
        "beneficiary_name": record.beneficiary_name,
        "beneficiary_type": record.beneficiary_type,
        "purpose": record.purpose.value,
        "purpose_description": record.purpose_description,
        "amount": record.amount,
        "date": record.date,
        "approved_by": record.approved_by,
        "approval_method": record.approval_method,
        "minutes_id": record.minutes_id,
        "notes": record.notes,
        "status": record.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None
    }
    
    await db.benevolence_records.insert_one(record_doc)
    return BenevolenceRecordResponse(**record_doc)

@api_router.get("/benevolence", response_model=List[BenevolenceRecordResponse])
async def get_benevolence_records(
    trust_id: str,
    purpose: Optional[str] = None,
    status: Optional[str] = None,
    approver: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Get benevolence records with optional filters"""
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    
    if purpose:
        query["purpose"] = purpose
    if status:
        query["status"] = status
    if approver:
        query["approved_by"] = {"$in": [approver]}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        if "date" in query:
            query["date"]["$lte"] = end_date
        else:
            query["date"] = {"$lte": end_date}
    
    records = await db.benevolence_records.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return [BenevolenceRecordResponse(**r) for r in records]

@api_router.get("/benevolence/{record_id}", response_model=BenevolenceRecordResponse)
async def get_benevolence_record(record_id: str, user: dict = Depends(get_current_user)):
    """Get a single benevolence record"""
    record = await db.benevolence_records.find_one(
        {"record_id": record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Benevolence record not found")
    return BenevolenceRecordResponse(**record)

@api_router.put("/benevolence/{record_id}", response_model=BenevolenceRecordResponse)
async def update_benevolence_record(record_id: str, update: BenevolenceRecordUpdate, user: dict = Depends(get_current_user)):
    """Update a benevolence record"""
    record = await db.benevolence_records.find_one(
        {"record_id": record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Benevolence record not found")
    
    update_data = {k: v for k, v in update.dict().items() if v is not None}
    if "purpose" in update_data and hasattr(update_data["purpose"], "value"):
        update_data["purpose"] = update_data["purpose"].value
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.benevolence_records.update_one(
        {"record_id": record_id},
        {"$set": update_data}
    )
    
    updated = await db.benevolence_records.find_one({"record_id": record_id}, {"_id": 0})
    return BenevolenceRecordResponse(**updated)

@api_router.delete("/benevolence/{record_id}")
async def delete_benevolence_record(record_id: str, user: dict = Depends(get_current_user)):
    """Delete a benevolence record"""
    result = await db.benevolence_records.delete_one(
        {"record_id": record_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Benevolence record not found")
    return {"message": "Benevolence record deleted"}

@api_router.get("/benevolence/summary/{trust_id}")
async def get_benevolence_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """Get benevolence summary with totals by period and purpose"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    records = await db.benevolence_records.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    
    # Calculate totals
    total_amount = sum(r.get("amount", 0) for r in records)
    total_count = len(records)
    
    # Group by purpose
    by_purpose = {}
    for r in records:
        purpose = r.get("purpose", "other")
        if purpose not in by_purpose:
            by_purpose[purpose] = {"count": 0, "total": 0}
        by_purpose[purpose]["count"] += 1
        by_purpose[purpose]["total"] += r.get("amount", 0)
    
    # Group by month/quarter/year
    by_month = {}
    by_quarter = {}
    by_year = {}
    
    for r in records:
        date_str = r.get("date", "")
        amount = r.get("amount", 0)
        
        try:
            if "T" in date_str:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                date = datetime.strptime(date_str[:10], "%Y-%m-%d")
            
            # Month key (YYYY-MM)
            month_key = date.strftime("%Y-%m")
            if month_key not in by_month:
                by_month[month_key] = {"count": 0, "total": 0}
            by_month[month_key]["count"] += 1
            by_month[month_key]["total"] += amount
            
            # Quarter key (YYYY-Q#)
            quarter = (date.month - 1) // 3 + 1
            quarter_key = f"{date.year}-Q{quarter}"
            if quarter_key not in by_quarter:
                by_quarter[quarter_key] = {"count": 0, "total": 0}
            by_quarter[quarter_key]["count"] += 1
            by_quarter[quarter_key]["total"] += amount
            
            # Year key
            year_key = str(date.year)
            if year_key not in by_year:
                by_year[year_key] = {"count": 0, "total": 0}
            by_year[year_key]["count"] += 1
            by_year[year_key]["total"] += amount
        except (ValueError, AttributeError):
            pass
    
    # Get list of unique approvers
    all_approvers = set()
    for r in records:
        for approver in r.get("approved_by", []):
            all_approvers.add(approver)
    
    return {
        "trust_id": trust_id,
        "trust_name": trust.get("name", ""),
        "total_amount": total_amount,
        "total_count": total_count,
        "by_purpose": by_purpose,
        "by_month": dict(sorted(by_month.items(), reverse=True)),
        "by_quarter": dict(sorted(by_quarter.items(), reverse=True)),
        "by_year": dict(sorted(by_year.items(), reverse=True)),
        "approvers": list(all_approvers)
    }

@api_router.get("/benevolence/export/{trust_id}/pdf")
async def export_benevolence_pdf(
    trust_id: str, 
    year: Optional[int] = None,
    user: dict = Depends(get_current_user)
):
    """Generate a styled PDF export of Benevolence Report"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    if not trust.get("benevolence_enabled"):
        raise HTTPException(status_code=400, detail="Benevolence mode is not enabled for this trust")
    
    # Check if watermark should be shown (soft gating based on subscription)
    show_watermark = await should_show_watermark(user["user_id"])
    hide_watermark = not show_watermark
    
    # Get records, optionally filtered by year
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    records = await db.benevolence_records.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    
    # Filter by year if specified
    if year:
        filtered_records = []
        for r in records:
            try:
                date_str = r.get("date", "")
                if "T" in date_str:
                    record_year = int(date_str[:4])
                elif "-" in date_str:
                    record_year = int(date_str[:4])
                else:
                    continue
                if record_year == year:
                    filtered_records.append(r)
            except (ValueError, TypeError):
                pass
        records = filtered_records
    
    # Purpose category display names
    PURPOSE_LABELS = {
        "medical": "Medical Expenses",
        "housing": "Housing Assistance",
        "education": "Education",
        "food_necessities": "Food & Necessities",
        "utilities": "Utilities",
        "transportation": "Transportation",
        "emergency": "Emergency Relief",
        "spiritual": "Spiritual/Ministry",
        "assistance": "General Assistance",
        "other": "Other"
    }
    
    # Group by purpose
    grouped_by_purpose = {}
    for r in records:
        purpose = r.get("purpose", "other")
        if purpose not in grouped_by_purpose:
            grouped_by_purpose[purpose] = []
        grouped_by_purpose[purpose].append(r)
    
    # Calculate totals
    total_amount = sum(r.get("amount", 0) for r in records)
    total_grants = len(records)
    unique_beneficiaries = len(set(r.get("beneficiary_name", "") for r in records))
    
    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        topMargin=0.75*inch, 
        bottomMargin=0.75*inch,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'BenevolenceTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=6,
        textColor=colors.HexColor('#010079'),
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'BenevolenceSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=12,
        textColor=colors.HexColor('#666666'),
        alignment=1,
        fontName='Helvetica'
    )
    
    category_style = ParagraphStyle(
        'CategoryTitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=18,
        spaceAfter=6,
        textColor=colors.HexColor('#010079'),
        fontName='Helvetica-Bold'
    )
    
    story = []
    
    # Header
    story.append(Paragraph("BENEVOLENCE REPORT", title_style))
    year_text = f"Year {year}" if year else "All Time"
    story.append(Paragraph(f"Charitable Assistance Record • {year_text}", subtitle_style))
    story.append(Spacer(1, 6))
    
    # Trust & Report info
    trust_name = trust.get("name", "Private Trust")
    tax_status = trust.get("tax_status", "private")
    tax_label = {"501c3": "501(c)(3) Organization", "508": "508 Church/Religious Org", "private": "Private Foundation"}.get(tax_status, tax_status)
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    info_data = [
        ["Trust Name:", trust_name],
        ["Tax Status:", tax_label],
        ["Report Generated:", current_date],
        ["Period:", f"January 1 - December 31, {year}" if year else "All Records"],
    ]
    
    info_table = Table(info_data, colWidths=[1.5*inch, 4.5*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#010079')),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))
    
    # Separator line
    story.append(Table([[""]], colWidths=[6.5*inch], rowHeights=[1]))
    story[-1].setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#010079')),
    ]))
    story.append(Spacer(1, 16))
    
    # Summary Statistics
    story.append(Paragraph("SUMMARY", category_style))
    
    summary_data = [
        ["Total Grants:", str(total_grants)],
        ["Total Disbursed:", f"${total_amount:,.2f}"],
        ["Unique Beneficiaries:", str(unique_beneficiaries)],
        ["Categories Used:", str(len(grouped_by_purpose))],
    ]
    
    summary_table = Table(summary_data, colWidths=[1.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#010079')),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 16))
    
    # Breakdown by Purpose
    story.append(Paragraph("GRANTS BY PURPOSE CATEGORY", category_style))
    
    purpose_order = ["medical", "housing", "education", "food_necessities", "utilities", 
                     "transportation", "emergency", "spiritual", "assistance", "other"]
    
    for purpose_key in purpose_order:
        purpose_records = grouped_by_purpose.get(purpose_key, [])
        if not purpose_records:
            continue
        
        purpose_label = PURPOSE_LABELS.get(purpose_key, purpose_key.title())
        purpose_total = sum(r.get("amount", 0) for r in purpose_records)
        
        # Category sub-header
        cat_header = ParagraphStyle(
            'PurposeHeader',
            parent=styles['Normal'],
            fontSize=11,
            spaceBefore=12,
            spaceAfter=4,
            textColor=colors.HexColor('#333333'),
            fontName='Helvetica-Bold'
        )
        story.append(Paragraph(f"{purpose_label} ({len(purpose_records)} grants • ${purpose_total:,.2f})", cat_header))
        
        # Table of grants in this category
        table_data = [["Date", "Beneficiary", "Description", "Amount"]]
        
        for r in purpose_records:
            date_str = r.get("date", "N/A")
            try:
                if "T" in date_str:
                    date_str = datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%m/%d/%Y")
                elif "-" in date_str and len(date_str) >= 10:
                    date_str = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%m/%d/%Y")
            except (ValueError, AttributeError):
                pass
            
            beneficiary = r.get("beneficiary_name", "N/A")[:25]
            if len(r.get("beneficiary_name", "")) > 25:
                beneficiary += "..."
            
            desc = r.get("purpose_description", "")[:35]
            if len(r.get("purpose_description", "")) > 35:
                desc += "..."
            
            amount = f"${r.get('amount', 0):,.2f}"
            
            table_data.append([date_str, beneficiary, desc, amount])
        
        col_widths = [0.9*inch, 1.5*inch, 2.8*inch, 1*inch]
        grant_table = Table(table_data, colWidths=col_widths)
        grant_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#010079')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F8F8')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(grant_table)
    
    # Footer
    story.append(Spacer(1, 24))
    story.append(Table([[""]], colWidths=[6.5*inch], rowHeights=[1]))
    story[-1].setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#010079')),
    ]))
    story.append(Spacer(1, 8))
    
    footer_style = ParagraphStyle(
        'ReportFooter',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#888888'),
        alignment=1,
        fontName='Helvetica'
    )
    if not hide_watermark:
        story.append(Paragraph(
            f"This report was generated by {trust_name} on {current_date}. "
            "Maintain this record for tax reporting and audit purposes.",
            footer_style
        ))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Return PDF
    year_suffix = f"_{year}" if year else ""
    filename = f"benevolence_report{year_suffix}_{trust_id}.pdf"
    
    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

# ==================== DISTRIBUTION ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/distributions.py
# The following distribution endpoints have been moved to the distributions router:
# - POST /distributions
# - GET /distributions
# - PATCH /distributions/{id}
# - PATCH /distributions/{id}/approve
# - PATCH /distributions/{id}/status
# - PUT /distributions/{id}
# - DELETE /distributions/{id}
# - GET /benevolence-log

# ==================== COMPENSATION PLAN ENDPOINTS ====================

@api_router.post("/compensation-plans", response_model=CompensationPlanResponse)
async def create_comp_plan(plan: CompensationPlanCreate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": plan.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    plan_doc = {
        "plan_id": plan_id,
        "trust_id": plan.trust_id,
        "user_id": user["user_id"],
        "trustee_name": plan.trustee_name,
        "role": plan.role,
        "annual_fee": plan.annual_amount or plan.annual_approved_amount,
        "annual_amount": plan.annual_amount or plan.annual_approved_amount,
        "annual_approved_amount": plan.annual_approved_amount or plan.annual_amount,
        "fee_type": plan.fee_type,
        "effective_date": plan.effective_date,
        "notes": plan.notes,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.compensation_plans.insert_one(plan_doc)
    
    return CompensationPlanResponse(**plan_doc)

@api_router.get("/compensation-plans", response_model=List[CompensationPlanResponse])
async def get_comp_plans(trust_id: str, user: dict = Depends(get_current_user)):
    plans = await db.compensation_plans.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("effective_date", -1).to_list(100)
    
    return [CompensationPlanResponse(**p) for p in plans]

# ==================== COMPENSATION PAYMENT ENDPOINTS ====================

@api_router.post("/compensation-payments", response_model=CompensationPaymentResponse)
async def create_comp_payment(payment: CompensationPaymentCreate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": payment.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    payment_id = f"payment_{uuid.uuid4().hex[:12]}"
    
    # Check if exceeds plan
    exceeds_plan = False
    plan = await db.compensation_plans.find_one(
        {"trust_id": payment.trust_id, "user_id": user["user_id"]},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    
    if plan:
        year_start = get_year_start(datetime.now(timezone.utc))
        existing = await db.compensation_payments.find(
            {"trust_id": payment.trust_id, "user_id": user["user_id"], "date": {"$gte": year_start.isoformat()}},
            {"_id": 0}
        ).to_list(1000)
        ytd_total = sum(p.get("amount", 0) for p in existing) + payment.amount
        # Support both annual_approved_amount and annual_fee fields
        approved_amount = plan.get("annual_approved_amount") or plan.get("annual_fee") or plan.get("annual_amount", 0)
        exceeds_plan = ytd_total > approved_amount
    
    payment_doc = {
        "payment_id": payment_id,
        "trust_id": payment.trust_id,
        "user_id": user["user_id"],
        "amount": payment.amount,
        "date": payment.date,
        "classification_text": payment.classification_text,
        "exceeds_plan_flag": exceeds_plan,
        "minutes_record_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.compensation_payments.insert_one(payment_doc)
    await auto_update_onboarding(user["user_id"], payment.trust_id)
    
    return CompensationPaymentResponse(**payment_doc)

@api_router.get("/compensation-payments", response_model=List[CompensationPaymentResponse])
async def get_comp_payments(trust_id: str, user: dict = Depends(get_current_user)):
    payments = await db.compensation_payments.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("date", -1).to_list(1000)
    
    return [CompensationPaymentResponse(**p) for p in payments]

@api_router.get("/compensation-ytd")
async def get_comp_ytd(trust_id: str, user: dict = Depends(get_current_user)):
    """Get YTD compensation total and plan info"""
    year_start = get_year_start(datetime.now(timezone.utc))
    
    payments = await db.compensation_payments.find(
        {"trust_id": trust_id, "user_id": user["user_id"], "date": {"$gte": year_start.isoformat()}},
        {"_id": 0}
    ).to_list(1000)
    ytd_total = sum(p.get("amount", 0) for p in payments)
    
    plan = await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    # Support both annual_approved_amount and annual_fee fields
    annual_approved = 0
    if plan:
        annual_approved = plan.get("annual_approved_amount") or plan.get("annual_fee") or plan.get("annual_amount", 0)
    
    return {
        "ytd_total": ytd_total,
        "annual_approved": annual_approved,
        "exceeds_plan": ytd_total > annual_approved if plan else False,
        "remaining": max(0, annual_approved - ytd_total)
    }

@api_router.delete("/compensation-payments/{payment_id}")
async def delete_comp_payment(payment_id: str, user: dict = Depends(get_current_user)):
    result = await db.compensation_payments.delete_one({
        "payment_id": payment_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"message": "Payment deleted"}


# ==================== GOVERNANCE, ONBOARDING, ACTIVITY, DASHBOARD ====================
# MIGRATED TO: /app/backend/routers/governance.py
# Endpoints: /governance/{trust_id}, /governance/{trust_id}/history,
#            /onboarding, /activity, /dashboard

# ==================== CATEGORIES ====================

@api_router.get("/categories")
async def get_categories():
    return {
        "purpose_classifications": [c.value for c in PurposeClassification],
        "task_types": [t.value for t in TaskType],
        "minutes_types": [m.value for m in MinutesType],
        "entity_types": [e.value for e in EntityType],
        "relationship_types": [r.value for r in RelationshipType]
    }

# ==================== EXPORT ENDPOINTS ====================

@api_router.get("/export/minutes")
async def export_minutes_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export minutes records as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    minutes = await db.minutes_records.find(query, {"_id": 0}).sort("meeting_date", -1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(m["trust_id"] for m in minutes))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Minutes Type,Meeting Date,Participants,Decisions,Created At"]
    for m in minutes:
        trust_name = trust_map.get(m["trust_id"], "Unknown").replace(",", ";")
        minutes_type = m.get("minutes_type", "").replace("_", " ").title()
        meeting_date = m.get("meeting_date", "")[:10]
        participants = m.get("participants_text", "").replace(",", ";").replace("\n", " ")[:200]
        decisions = m.get("decisions_text", "").replace(",", ";").replace("\n", " ")[:500]
        created_at = m.get("created_at", "")[:10]
        
        csv_lines.append(f'"{trust_name}","{minutes_type}","{meeting_date}","{participants}","{decisions}","{created_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=minutes_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@api_router.get("/export/distributions")
async def export_distributions_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export distribution records as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    dists = await db.distribution_records.find(query, {"_id": 0}).sort("date", -1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(d["trust_id"] for d in dists))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Beneficiary,Amount,Date,Category,Authority Reference,Notes,Status,Approved By,Approved At"]
    for d in dists:
        trust_name = trust_map.get(d["trust_id"], "Unknown").replace(",", ";")
        beneficiary = d.get("beneficiary_name", "").replace(",", ";")
        amount = d.get("amount", 0)
        date = d.get("date", "")[:10]
        category = d.get("purpose_classification", "").replace("_", " ").title()
        authority = d.get("authority_clause_ref", "").replace(",", ";")[:100]
        notes = d.get("notes", "").replace(",", ";").replace("\n", " ")[:200]
        status = "Approved" if d.get("approved_at") else "Pending"
        approved_by = d.get("approved_by", "") or ""
        approved_at = (d.get("approved_at", "") or "")[:10]
        
        csv_lines.append(f'"{trust_name}","{beneficiary}",{amount},"{date}","{category}","{authority}","{notes}","{status}","{approved_by}","{approved_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=distributions_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@api_router.get("/export/compensation")
async def export_compensation_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export compensation payments as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    payments = await db.compensation_payments.find(query, {"_id": 0}).sort("date", -1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(p["trust_id"] for p in payments))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Amount,Date,Classification,Exceeds Plan,Created At"]
    for p in payments:
        trust_name = trust_map.get(p["trust_id"], "Unknown").replace(",", ";")
        amount = p.get("amount", 0)
        date = p.get("date", "")[:10]
        classification = p.get("classification_text", "").replace(",", ";")[:200]
        exceeds = "Yes" if p.get("exceeds_plan_flag") else "No"
        created_at = p.get("created_at", "")[:10]
        
        csv_lines.append(f'"{trust_name}",{amount},"{date}","{classification}","{exceeds}","{created_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=compensation_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@api_router.get("/export/tasks")
async def export_tasks_csv(
    trust_id: Optional[str] = None, 
    user: dict = Depends(require_premium_feature(Feature.CSV_EXPORT))
):
    """Export governance tasks as CSV (Premium feature)"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    tasks = await db.governance_tasks.find(query, {"_id": 0}).sort("due_date", 1).to_list(10000)
    
    # Get trust names for lookup
    trust_ids = list(set(t["trust_id"] for t in tasks))
    trusts = await db.trusts.find({"trust_id": {"$in": trust_ids}}, {"_id": 0}).to_list(100)
    trust_map = {t["trust_id"]: t["name"] for t in trusts}
    
    # Build CSV
    csv_lines = ["Trust Name,Task Type,Due Date,Description,Status,Completed At"]
    for t in tasks:
        trust_name = trust_map.get(t["trust_id"], "Unknown").replace(",", ";")
        task_type = t.get("task_type", "").replace("_", " ").title()
        due_date = t.get("due_date", "")[:10]
        description = t.get("description", "").replace(",", ";").replace("\n", " ")[:200]
        status = get_task_status(t.get("due_date", ""), t.get("completed_at"))
        completed_at = (t.get("completed_at", "") or "")[:10]
        
        csv_lines.append(f'"{trust_name}","{task_type}","{due_date}","{description}","{status}","{completed_at}"')
    
    csv_content = "\n".join(csv_lines)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tasks_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

# ==================== SUBSCRIPTION ENDPOINTS ====================

async def get_or_create_subscription(user_id: str) -> dict:
    """Get or create subscription for a user"""
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    if not sub:
        now = datetime.now(timezone.utc)
        sub = {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "plan_type": "trial",
            "status": "trialing",
            "trial_start_date": now.isoformat(),
            "trial_end_date": (now + timedelta(days=TRIAL_DAYS)).isoformat(),
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        await db.subscriptions.insert_one(sub)
    
    return sub

def calculate_subscription_status(sub: dict) -> dict:
    """Calculate current status and days remaining, fetch Stripe data if available"""
    now = datetime.now(timezone.utc)
    
    result = {
        **sub,
        "current_period_end": None,
        "cancel_at_period_end": None
    }
    
    # If there's an active Stripe subscription, fetch details
    if sub.get("stripe_subscription_id") and sub["status"] == "active":
        try:
            stripe_sub = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
            result["current_period_end"] = datetime.fromtimestamp(
                stripe_sub.current_period_end, tz=timezone.utc
            ).isoformat()
            result["cancel_at_period_end"] = stripe_sub.cancel_at_period_end
            result["is_active"] = True
            result["days_remaining"] = None
            
            # Update plan type from Stripe if needed
            if stripe_sub.items.data:
                price_id = stripe_sub.items.data[0].price.id
                if price_id == STRIPE_ANNUAL_PRICE_ID:
                    result["plan_type"] = "annual"
                elif price_id == STRIPE_MONTHLY_PRICE_ID:
                    result["plan_type"] = "monthly"
            
            return result
        except stripe.StripeError as e:
            logger.warning(f"Could not fetch Stripe subscription: {e}")
    
    if sub["status"] == "active":
        return {
            **result,
            "is_active": True,
            "days_remaining": None
        }
    
    if sub["status"] == "trialing" and sub.get("trial_end_date"):
        trial_end = datetime.fromisoformat(sub["trial_end_date"].replace('Z', '+00:00'))
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        
        days_remaining = (trial_end - now).days
        is_expired = days_remaining < 0
        
        return {
            **result,
            "is_active": not is_expired,
            "days_remaining": max(0, days_remaining),
            "status": "expired" if is_expired else "trialing"
        }
    
    return {
        **result,
        "is_active": sub["status"] == "active",
        "days_remaining": None
    }

@api_router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(user: dict = Depends(get_current_user)):
    sub = await get_or_create_subscription(user["user_id"])
    enriched = calculate_subscription_status(sub)
    return SubscriptionResponse(**enriched)

@api_router.get("/subscription/state")
async def get_subscription_state_endpoint(user: dict = Depends(get_current_user)):
    """
    Get normalized subscription state with all computed fields.
    This endpoint provides the single source of truth for subscription status.
    
    Returns:
        - plan_type: "trial", "monthly", "annual"
        - status: "trialing", "active", "past_due", "canceled", "expired"
        - is_trial: boolean
        - is_active: boolean
        - is_read_only: boolean (determines if write operations are blocked)
        - trial_days_remaining: int or null
    """
    state = await get_subscription_state(user["user_id"])
    return state.model_dump()

@api_router.get("/subscription/features")
async def get_subscription_features(user: dict = Depends(get_current_user)):
    """
    Get available features for the user's subscription plan.
    Used by frontend to show/hide premium features.
    
    Returns:
        - plan_type: Current plan
        - is_active: Whether subscription is active
        - is_trial: Whether on trial
        - features: Dict of feature flags (feature_name -> boolean)
    
    Feature flags:
        - minutes_basic, distributions_basic, governance_basic, single_trust (core)
        - pdf_no_watermark, csv_export, multiple_trusts, benevolence_mode,
          beneficiary_dashboard, trust_units, governance_history, advanced_templates (premium)
    """
    return await get_user_features(user["user_id"])

@api_router.post("/subscription/create-checkout")
async def create_checkout_session(checkout: CheckoutRequest, user: dict = Depends(get_current_user)):
    """Create a Stripe checkout session for subscription"""
    if checkout.plan_type not in ["monthly", "annual"]:
        raise HTTPException(status_code=400, detail="Invalid plan type")
    
    price_id = STRIPE_MONTHLY_PRICE_ID if checkout.plan_type == "monthly" else STRIPE_ANNUAL_PRICE_ID
    
    # Get or create subscription to get/create stripe customer
    sub = await get_or_create_subscription(user["user_id"])
    
    try:
        customer_id = None
        
        # Try to use existing customer if we have one
        if sub.get("stripe_customer_id"):
            try:
                # Verify the customer exists in Stripe (handles test->live mode switch)
                stripe.Customer.retrieve(sub["stripe_customer_id"])
                customer_id = sub["stripe_customer_id"]
            except stripe.InvalidRequestError:
                # Customer doesn't exist (likely switched from test to live mode)
                logger.info(f"Customer {sub['stripe_customer_id']} not found in Stripe, creating new one")
                customer_id = None
        
        # Create new customer if needed
        if not customer_id:
            customer = stripe.Customer.create(
                email=user["email"],
                name=user.get("name", ""),
                metadata={"user_id": user["user_id"]}
            )
            customer_id = customer.id
            await db.subscriptions.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"stripe_customer_id": customer_id, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
        
        # Create checkout session params
        checkout_params = {
            "customer": customer_id,
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": checkout.success_url,
            "cancel_url": checkout.cancel_url,
            "metadata": {"user_id": user["user_id"], "plan_type": checkout.plan_type},
            "allow_promotion_codes": True  # Always allow entering promo codes
        }
        
        # If a specific promotion code is provided, try to apply it
        if checkout.promotion_code:
            try:
                # Look up the promotion code in Stripe
                promo_codes = stripe.PromotionCode.list(code=checkout.promotion_code, active=True, limit=1)
                if promo_codes.data:
                    checkout_params["discounts"] = [{"promotion_code": promo_codes.data[0].id}]
                    logger.info(f"Applied promotion code: {checkout.promotion_code}")
            except stripe.StripeError as promo_error:
                logger.warning(f"Could not apply promotion code {checkout.promotion_code}: {promo_error}")
                # Continue without the promo code - user can still enter it manually
        
        # Create checkout session
        session = stripe.checkout.Session.create(**checkout_params)
        
        # Record transaction
        await db.payment_transactions.insert_one({
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "user_id": user["user_id"],
            "session_id": session.id,
            "amount": 79.00 if checkout.plan_type == "monthly" else 790.00,
            "currency": "usd",
            "plan_type": checkout.plan_type,
            "payment_status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        
        return {"checkout_url": session.url, "session_id": session.id}
        
    except stripe.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=500, detail="Payment service unavailable")

@api_router.get("/subscription/verify-payment")
async def verify_payment(session_id: str, user: dict = Depends(get_current_user)):
    """Verify a checkout session and update subscription"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == "paid":
            plan_type = session.metadata.get("plan_type", "monthly")
            
            # Update subscription
            await db.subscriptions.update_one(
                {"user_id": user["user_id"]},
                {"$set": {
                    "plan_type": plan_type,
                    "status": "active",
                    "stripe_subscription_id": session.subscription,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Update transaction
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            
            return {"status": "success", "plan_type": plan_type}
        
        return {"status": "pending"}
        
    except stripe.StripeError as e:
        logger.error(f"Stripe verification error: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed")

@api_router.post("/subscription/create-portal")
async def create_customer_portal(portal: PortalRequest, user: dict = Depends(get_current_user)):
    """Create a Stripe customer portal session for managing subscription"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="No billing account found. Please subscribe first.")
    
    try:
        session = stripe.billing_portal.Session.create(
            customer=sub["stripe_customer_id"],
            return_url=portal.return_url
        )
        return {"portal_url": session.url}
    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=500, detail="Could not create billing portal")

@api_router.post("/subscription/cancel")
async def cancel_subscription(user: dict = Depends(get_current_user)):
    """Cancel subscription at end of current billing period"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription found")
    
    try:
        # Cancel at period end (user keeps access until subscription ends)
        stripe_sub = stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            cancel_at_period_end=True
        )
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        cancel_date = datetime.fromtimestamp(
            stripe_sub.current_period_end, tz=timezone.utc
        ).strftime('%B %d, %Y')
        
        # Send cancellation email
        if email_service.is_configured:
            try:
                await email_service.send_subscription_canceled(
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    access_until=cancel_date
                )
            except Exception as e:
                logger.error(f"Failed to send cancellation email: {e}")
        
        return {
            "status": "canceled",
            "message": f"Your subscription will be canceled on {cancel_date}. You'll have access until then.",
            "cancel_at": stripe_sub.current_period_end
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe cancel error: {e}")
        raise HTTPException(status_code=500, detail="Could not cancel subscription")

@api_router.post("/subscription/reactivate")
async def reactivate_subscription(user: dict = Depends(get_current_user)):
    """Reactivate a subscription that was set to cancel at period end"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No subscription found")
    
    try:
        stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            cancel_at_period_end=False
        )
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        return {
            "status": "active",
            "message": "Your subscription has been reactivated."
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe reactivate error: {e}")
        raise HTTPException(status_code=500, detail="Could not reactivate subscription")

@api_router.post("/subscription/upgrade")
async def upgrade_subscription(user: dict = Depends(get_current_user)):
    """Upgrade from monthly to annual plan"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription found")
    
    if sub.get("plan_type") == "annual":
        raise HTTPException(status_code=400, detail="Already on annual plan")
    
    try:
        # Get current subscription
        stripe_sub = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
        
        # Update to annual price
        stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            items=[{
                "id": stripe_sub["items"]["data"][0]["id"],
                "price": STRIPE_ANNUAL_PRICE_ID
            }],
            proration_behavior="create_prorations"
        )
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "plan_type": "annual",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Send upgrade email
        if email_service.is_configured:
            try:
                await email_service.send_subscription_upgraded(
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    old_plan="monthly",
                    new_plan="annual"
                )
            except Exception as e:
                logger.error(f"Failed to send upgrade email: {e}")
        
        return {
            "status": "upgraded",
            "message": "Successfully upgraded to annual plan. You'll be charged the prorated difference.",
            "new_plan": "annual"
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe upgrade error: {e}")
        raise HTTPException(status_code=500, detail="Could not upgrade subscription")

@api_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for subscription lifecycle"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event_type = event["type"]
    logger.info(f"Stripe webhook received: {event_type}")
    
    # Helper to get user info from stripe customer ID
    async def get_user_by_customer_id(customer_id: str):
        sub = await db.subscriptions.find_one({"stripe_customer_id": customer_id}, {"_id": 0})
        if sub:
            user = await db.users.find_one({"user_id": sub["user_id"]}, {"_id": 0})
            return user, sub
        return None, None
    
    # Helper to format date from timestamp
    def format_date(timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime('%B %d, %Y')
    
    # Helper to format amount
    def format_amount(amount_cents: int) -> str:
        return f"{amount_cents / 100:.2f}"
    
    # ========== CHECKOUT COMPLETED (New subscription) ==========
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        plan_type = session.get("metadata", {}).get("plan_type", "monthly")
        
        if user_id:
            # Update subscription status
            await db.subscriptions.update_one(
                {"user_id": user_id},
                {"$set": {
                    "plan_type": plan_type,
                    "status": "active",
                    "stripe_subscription_id": session.get("subscription"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Update payment transaction
            await db.payment_transactions.update_one(
                {"session_id": session["id"]},
                {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            
            # Send activation email
            user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if user and email_service.is_configured:
                try:
                    # Get subscription details from Stripe
                    stripe_sub = stripe.Subscription.retrieve(session.get("subscription"))
                    next_billing = format_date(stripe_sub.current_period_end)
                    amount = "790" if plan_type == "annual" else "79"
                    
                    await email_service.send_subscription_activated(
                        to_email=user["email"],
                        user_name=user.get("name", ""),
                        plan_type=plan_type,
                        amount=amount,
                        next_billing_date=next_billing
                    )
                except Exception as e:
                    logger.error(f"Failed to send activation email: {e}")
    
    # ========== SUBSCRIPTION UPDATED ==========
    elif event_type == "customer.subscription.updated":
        subscription = event["data"]["object"]
        previous_attributes = event["data"].get("previous_attributes", {})
        customer_id = subscription.get("customer")
        
        user, sub = await get_user_by_customer_id(customer_id)
        if not user:
            return {"status": "ok", "message": "User not found"}
        
        # Check if plan changed (upgrade)
        if "items" in previous_attributes:
            old_price = previous_attributes.get("items", {}).get("data", [{}])[0].get("price", {}).get("id")
            new_price = subscription.get("items", {}).get("data", [{}])[0].get("price", {}).get("id")
            
            if old_price and new_price and old_price != new_price:
                # Determine plan types
                old_plan = "annual" if old_price == STRIPE_ANNUAL_PRICE_ID else "monthly"
                new_plan = "annual" if new_price == STRIPE_ANNUAL_PRICE_ID else "monthly"
                
                # Update database
                await db.subscriptions.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": {
                        "plan_type": new_plan,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # Send upgrade email
                if email_service.is_configured:
                    try:
                        await email_service.send_subscription_upgraded(
                            to_email=user["email"],
                            user_name=user.get("name", ""),
                            old_plan=old_plan,
                            new_plan=new_plan
                        )
                    except Exception as e:
                        logger.error(f"Failed to send upgrade email: {e}")
        
        # Check if cancel_at_period_end changed (cancellation scheduled)
        if "cancel_at_period_end" in previous_attributes:
            if subscription.get("cancel_at_period_end") and not previous_attributes.get("cancel_at_period_end"):
                # Subscription scheduled for cancellation
                access_until = format_date(subscription.get("current_period_end"))
                
                if email_service.is_configured:
                    try:
                        await email_service.send_subscription_canceled(
                            to_email=user["email"],
                            user_name=user.get("name", ""),
                            access_until=access_until
                        )
                    except Exception as e:
                        logger.error(f"Failed to send cancellation email: {e}")
    
    # ========== SUBSCRIPTION DELETED (fully canceled) ==========
    elif event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await db.subscriptions.update_one(
            {"stripe_subscription_id": subscription["id"]},
            {"$set": {
                "status": "canceled",
                "stripe_subscription_id": None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    # ========== INVOICE PAID (renewal) ==========
    elif event_type == "invoice.paid":
        invoice = event["data"]["object"]
        customer_id = invoice.get("customer")
        
        # Skip if this is the first invoice (handled by checkout.session.completed)
        if invoice.get("billing_reason") == "subscription_create":
            return {"status": "ok", "message": "Initial invoice, skipping"}
        
        user, sub = await get_user_by_customer_id(customer_id)
        if not user:
            return {"status": "ok", "message": "User not found"}
        
        # Ensure subscription is active
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "status": "active",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Send renewal email
        if email_service.is_configured and invoice.get("billing_reason") == "subscription_cycle":
            try:
                # Get next billing date from subscription
                stripe_sub = stripe.Subscription.retrieve(invoice.get("subscription"))
                next_billing = format_date(stripe_sub.current_period_end)
                amount = format_amount(invoice.get("amount_paid", 0))
                plan_type = sub.get("plan_type", "monthly")
                
                await email_service.send_subscription_renewed(
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    plan_type=plan_type,
                    amount=amount,
                    next_billing_date=next_billing
                )
            except Exception as e:
                logger.error(f"Failed to send renewal email: {e}")
    
    # ========== INVOICE PAYMENT FAILED ==========
    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        customer_id = invoice.get("customer")
        
        user, sub = await get_user_by_customer_id(customer_id)
        if user:
            # Update subscription status
            await db.subscriptions.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": {
                    "status": "past_due",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Send payment failed email
            if email_service.is_configured:
                try:
                    amount = format_amount(invoice.get("amount_due", 0))
                    next_attempt = invoice.get("next_payment_attempt")
                    retry_date = format_date(next_attempt) if next_attempt else None
                    
                    await email_service.send_payment_failed(
                        to_email=user["email"],
                        user_name=user.get("name", ""),
                        amount=amount,
                        retry_date=retry_date
                    )
                except Exception as e:
                    logger.error(f"Failed to send payment failed email: {e}")
    
    return {"status": "ok", "event_type": event_type}

# ==================== EMAIL ENDPOINTS ====================

@api_router.get("/email/status")
async def get_email_status(user: dict = Depends(get_current_user)):
    """Get email service status and configuration"""
    return {
        "configured": email_service.is_configured,
        "from_email": email_service.from_email,
        "from_name": email_service.from_name,
        "available_templates": email_service.get_available_templates()
    }

@api_router.post("/email/test")
async def send_test_email(user: dict = Depends(get_current_user)):
    """Send a test welcome email to the current user"""
    if not email_service.is_configured:
        raise HTTPException(status_code=503, detail="Email service not configured")
    
    result = await email_service.send_welcome_email(
        to_email=user["email"],
        user_name=user.get("name", "")
    )
    
    return {
        "message": "Test email sent",
        "recipient": user["email"],
        "result": result
    }

@api_router.post("/email/send-task-reminders")
async def send_task_reminders(background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    """
    Manually trigger task reminder emails for upcoming/overdue tasks.
    In production, this would be called by a cron job.
    """
    if not email_service.is_configured:
        raise HTTPException(status_code=503, detail="Email service not configured")
    
    # Get all user's trusts
    trusts = await db.trusts.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
    
    emails_queued = 0
    now = datetime.now(timezone.utc).date()
    
    for trust in trusts:
        # Get incomplete tasks (status is calculated dynamically, not stored)
        upcoming_date = (now + timedelta(days=7)).isoformat()
        tasks = await db.governance_tasks.find({
            "trust_id": trust["trust_id"],
            "user_id": user["user_id"],
            "completed_at": None  # Only incomplete tasks
        }, {"_id": 0}).to_list(100)
        
        for task in tasks:
            task_due = task.get("due_date", "")[:10]
            # Calculate status dynamically
            task_status = get_task_status(task.get("due_date", ""), task.get("completed_at"))
            
            if task_status == "overdue":
                # Calculate days overdue
                try:
                    due_date = datetime.fromisoformat(task_due).date()
                    days_overdue = (now - due_date).days
                except ValueError:
                    days_overdue = 1
                
                background_tasks.add_task(
                    email_service.send_task_overdue,
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    trust_name=trust.get("name", ""),
                    task_type=task.get("task_type", ""),
                    due_date=task_due,
                    days_overdue=days_overdue
                )
                emails_queued += 1
            
            elif task_status == "upcoming" and task_due <= upcoming_date:
                background_tasks.add_task(
                    email_service.send_task_reminder,
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    trust_name=trust.get("name", ""),
                    task_type=task.get("task_type", ""),
                    due_date=task_due,
                    description=task.get("description", "")
                )
                emails_queued += 1
    
    return {
        "message": f"Queued {emails_queued} reminder emails",
        "emails_queued": emails_queued
    }

# ==================== BACKGROUND JOBS ENDPOINTS ====================

@api_router.get("/background-jobs/status")
async def get_background_jobs_status(user: dict = Depends(get_current_user)):
    """Get status of scheduled background jobs"""
    return {
        "running": background_runner.running,
        "jobs": background_runner.get_jobs_info(),
        "scheduler_active": background_runner.scheduler is not None and background_runner.scheduler.running if background_runner.scheduler else False
    }

@api_router.post("/background-jobs/run/task-status-update")
async def trigger_task_status_update(user: dict = Depends(get_current_user)):
    """Manually trigger task status update job"""
    try:
        updates = await run_task_status_update()
        return {
            "success": True,
            "message": "Task status update complete",
            "tasks_updated": updates
        }
    except Exception as e:
        logger.error(f"Error running task status update: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/background-jobs/run/daily-reminders")
async def trigger_daily_reminders(user: dict = Depends(get_current_user)):
    """Manually trigger daily reminder emails job"""
    try:
        emails_sent = await run_daily_reminders()
        return {
            "success": True,
            "message": "Daily reminders sent",
            "emails_sent": emails_sent
        }
    except Exception as e:
        logger.error(f"Error running daily reminders: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/background-jobs/run/health-snapshots")
async def trigger_health_snapshots(user: dict = Depends(get_current_user)):
    """Manually trigger health score snapshots job"""
    try:
        snapshots = await run_health_snapshots()
        return {
            "success": True,
            "message": "Health snapshots created",
            "snapshots_created": snapshots
        }
    except Exception as e:
        logger.error(f"Error running health snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DEMO DATA ====================

@api_router.post("/demo/seed")
async def seed_demo_data(user: dict = Depends(get_current_user)):
    existing = await db.trusts.count_documents({"user_id": user["user_id"]})
    if existing > 0:
        return {"message": "User already has trusts", "seeded": False}
    
    now = datetime.now(timezone.utc)
    
    # ==================== TRUST 1: Smith Family Trust (Full featured with Benevolence) ====================
    trust1_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    await db.trusts.insert_one({
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Family Trust",
        "trust_type": "family",
        "jurisdiction": "Delaware",
        "benevolence_enabled": True,
        "tax_status": "501c3",
        "description": "Irrevocable family trust for asset protection and generational wealth transfer.",
        "review_cadence": "quarterly",
        "role": "Trustee",
        "created_at": now.isoformat()
    })
    
    # ==================== TRUST 2: Johnson Education Trust ====================
    trust2_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    await db.trusts.insert_one({
        "trust_id": trust2_id,
        "user_id": user["user_id"],
        "name": "Johnson Education Trust",
        "trust_type": "family",
        "jurisdiction": "California",
        "benevolence_enabled": False,
        "description": "Education trust for grandchildren's college expenses.",
        "review_cadence": "annual",
        "role": "Trustee",
        "created_at": now.isoformat()
    })
    
    # ==================== ENTITIES for Trust 1 ====================
    trust1_entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": trust1_entity_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Family Trust",
        "entity_type": "Trust",
        "legal_name": "The Smith Family Irrevocable Trust",
        "formation_date": "2020-01-15",
        "governing_law": "Delaware",
        "ein": "12-3456789",
        "trustee_names": "John Smith, Jane Smith",
        "beneficiary_standard": "Health, Education, Maintenance, and Support",
        "article_ref_distribution": "Article IV, Section 4.1",
        "article_ref_compensation": "Article V, Section 5.2",
        "article_ref_amendment": "Article VIII",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": "",
        "article_ref_profit_distribution": "",
        "created_at": now.isoformat()
    })
    
    holding_llc_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": holding_llc_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Holdings LLC",
        "entity_type": "Holding LLC",
        "legal_name": "Smith Holdings, LLC",
        "formation_date": "2020-03-01",
        "governing_law": "Delaware",
        "ein": "98-7654321",
        "trustee_names": "",
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "Smith Family Trust (100%)",
        "manager_names": "John Smith",
        "article_ref_authority": "Section 3.2",
        "article_ref_profit_distribution": "Section 5.1",
        "created_at": now.isoformat()
    })
    
    real_estate_llc_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": real_estate_llc_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Real Estate LLC",
        "entity_type": "Operating LLC",
        "legal_name": "Smith Real Estate Holdings, LLC",
        "formation_date": "2021-06-15",
        "governing_law": "Delaware",
        "ein": "55-1234567",
        "trustee_names": "",
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "Smith Holdings LLC (100%)",
        "manager_names": "John Smith",
        "article_ref_authority": "Section 3.1",
        "article_ref_profit_distribution": "Section 4.2",
        "created_at": now.isoformat()
    })
    
    investment_corp_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": investment_corp_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Investments Inc",
        "entity_type": "Corporation",
        "legal_name": "Smith Investments, Inc.",
        "formation_date": "2022-01-10",
        "governing_law": "Nevada",
        "ein": "88-9876543",
        "trustee_names": "",
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "John Smith (President), Jane Smith (Secretary)",
        "article_ref_authority": "Bylaws Article III",
        "article_ref_profit_distribution": "Bylaws Article V",
        "created_at": now.isoformat()
    })
    
    # ==================== ENTITY RELATIONSHIPS (Hierarchy) for Trust 1 ====================
    await db.entity_relationships.insert_one({
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "parent_entity_id": trust1_entity_id,
        "child_entity_id": holding_llc_id,
        "relationship_type": "owns",
        "ownership_percentage": 100,
        "notes": "Trust is sole member of holding LLC",
        "created_at": now.isoformat()
    })
    
    await db.entity_relationships.insert_one({
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "parent_entity_id": holding_llc_id,
        "child_entity_id": real_estate_llc_id,
        "relationship_type": "owns",
        "ownership_percentage": 100,
        "notes": "Holding LLC is sole member of real estate entity",
        "created_at": now.isoformat()
    })
    
    await db.entity_relationships.insert_one({
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "parent_entity_id": holding_llc_id,
        "child_entity_id": investment_corp_id,
        "relationship_type": "owns",
        "ownership_percentage": 100,
        "notes": "Holding LLC is sole shareholder of investment corp",
        "created_at": now.isoformat()
    })
    
    # ==================== ENTITIES for Trust 2 ====================
    trust2_entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": trust2_entity_id,
        "trust_id": trust2_id,
        "user_id": user["user_id"],
        "name": "Johnson Education Trust",
        "entity_type": "Trust",
        "legal_name": "The Johnson Education Trust",
        "formation_date": "2023-01-01",
        "governing_law": "California",
        "ein": "77-1234567",
        "trustee_names": "John Smith",
        "beneficiary_standard": "Education expenses for grandchildren",
        "article_ref_distribution": "Article III",
        "article_ref_compensation": "Article IV",
        "article_ref_amendment": "Article VI",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": "",
        "article_ref_profit_distribution": "",
        "created_at": now.isoformat()
    })
    
    # ==================== GOVERNANCE TASKS ====================
    await db.governance_tasks.insert_many([
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "annual_review", "due_date": (now + timedelta(days=60)).isoformat(),
         "completed_at": None, "description": "Annual trust administration review", "created_at": now.isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "quarterly_review", "due_date": (now + timedelta(days=30)).isoformat(),
         "completed_at": None, "description": "Q1 2026 quarterly review", "created_at": now.isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "compensation_review", "due_date": (now - timedelta(days=5)).isoformat(),
         "completed_at": None, "description": "Review trustee compensation for 2026 (OVERDUE)", "created_at": (now - timedelta(days=30)).isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "distribution_review", "due_date": (now + timedelta(days=15)).isoformat(),
         "completed_at": (now - timedelta(days=2)).isoformat(), "description": "Review Q4 distributions - COMPLETED", "created_at": (now - timedelta(days=20)).isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "task_type": "annual_review", "due_date": (now + timedelta(days=90)).isoformat(),
         "completed_at": None, "description": "Annual education trust review", "created_at": now.isoformat()}
    ])
    
    # ==================== MINUTES ====================
    await db.minutes_records.insert_many([
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "quarterly", "meeting_date": (now - timedelta(days=15)).isoformat(),
         "participants_text": "John Smith (Trustee), Jane Smith (Trustee), Robert Attorney (Advisor)",
         "decisions_text": "Reviewed Q4 2025 performance. Approved education distribution for Emily. Confirmed investment strategy remains aligned with trust objectives.",
         "created_at": (now - timedelta(days=15)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=60)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Accept Beach Condo Unit 4B into trust corpus. Value: $425,000. Schedule A amended.",
         "generated_from_template": "acceptance_of_property",
         "template_data": {"property_description": "Beach Condo Unit 4B", "estimated_value": 425000},
         "created_at": (now - timedelta(days=60)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=45)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Approve $25,000 benevolent grant to Grace Community Church for youth ministry programs.",
         "generated_from_template": "benevolence_approval",
         "template_data": {"beneficiary_name": "Grace Community Church", "amount": 25000},
         "created_at": (now - timedelta(days=45)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "distribution", "meeting_date": (now - timedelta(days=30)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "Approved $15,000 distribution to Emily Smith for spring semester tuition. Solvency confirmed.",
         "created_at": (now - timedelta(days=30)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "minutes_type": "annual", "meeting_date": (now - timedelta(days=90)).isoformat(),
         "participants_text": "John Smith",
         "decisions_text": "Annual review of education trust. 529 account performing well. Reviewed beneficiary designations.",
         "created_at": (now - timedelta(days=90)).isoformat()}
    ])
    
    # ==================== DISTRIBUTIONS ====================
    await db.distribution_records.insert_many([
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Emily Smith", "amount": 15000, "date": (now - timedelta(days=10)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(a)",
         "notes": "Spring 2026 semester tuition - State University", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=10)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=10)).isoformat()},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Emily Smith", "amount": 2500, "date": (now - timedelta(days=3)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(b)",
         "notes": "Monthly living allowance - PENDING APPROVAL", "solvency_confirmed": False,
         "recusal_acknowledged": False, "approved_by": None, "approved_at": None,
         "minutes_record_id": None, "created_at": (now - timedelta(days=3)).isoformat()},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Michael Smith", "amount": 8000, "date": (now - timedelta(days=45)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.2",
         "notes": "Medical expenses - dental surgery", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=44)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=45)).isoformat()},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "beneficiary_name": "Sarah Johnson", "amount": 12000, "date": (now - timedelta(days=20)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article III",
         "notes": "College tuition - freshman year", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=20)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=20)).isoformat()}
    ])
    
    # ==================== SCHEDULE A (Trust Corpus) ====================
    await db.schedule_a_items.insert_many([
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "real_property", "description": "Primary Family Residence - 123 Oak Street",
         "identifier": "Deed #2020-12345", "location": "Wilmington, Delaware",
         "approximate_value": 650000, "date_conveyed": "2020-01-15",
         "notes": "Original trust corpus - 4BR/3BA Colonial", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "real_property", "description": "Vacation Property - Beach Condo Unit 4B",
         "identifier": "Deed #2021-67890", "location": "Rehoboth Beach, Delaware",
         "approximate_value": 425000, "date_conveyed": "2021-06-01",
         "notes": "Added via property acceptance minutes - 2BR oceanfront", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "Schwab Brokerage Account - Growth Portfolio",
         "identifier": "Acct #****7890", "location": "Charles Schwab",
         "approximate_value": 1250000, "date_conveyed": "2020-01-15",
         "notes": "Primary investment account - diversified equity/bond mix", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "First National Bank - Operating Account",
         "identifier": "Acct #****1234", "location": "First National Bank, DE",
         "approximate_value": 85000, "date_conveyed": "2020-02-01",
         "notes": "Trust checking account for distributions", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "business_interests", "description": "Smith Holdings LLC - 100% Membership Interest",
         "identifier": "Member Certificate #001", "location": "Delaware",
         "approximate_value": 500000, "date_conveyed": "2020-03-01",
         "notes": "Wholly-owned holding company", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "personal_property", "description": "2022 Mercedes-Benz S-Class",
         "identifier": "VIN: WDDUG8FB2NA******", "location": "Wilmington, Delaware",
         "approximate_value": 95000, "date_conveyed": "2022-04-15",
         "notes": "Trust vehicle", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "other_property", "description": "Fine Art Collection - Various Works",
         "identifier": "Appraised Inventory #2023-001", "location": "Family Residence",
         "approximate_value": 175000, "date_conveyed": "2020-01-15",
         "notes": "12 paintings and 3 sculptures", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "529 Education Savings Account",
         "identifier": "Acct #****5678", "location": "Fidelity Investments",
         "approximate_value": 250000, "date_conveyed": "2023-01-15",
         "notes": "College savings - aggressive growth allocation", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "Trust Operating Account",
         "identifier": "Acct #****9999", "location": "Wells Fargo",
         "approximate_value": 15000, "date_conveyed": "2023-01-15",
         "notes": "Operating account for expenses", "created_at": now.isoformat()}
    ])
    
    # ==================== BENEVOLENCE RECORDS (Trust 1 only - has benevolence enabled) ====================
    await db.benevolence_records.insert_many([
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Grace Community Church", "beneficiary_type": "organization", "purpose": "spiritual",
         "purpose_description": "Annual ministry support for youth programs and community outreach",
         "amount": 25000, "date": (now - timedelta(days=45)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "5th consecutive year of support", "created_at": (now - timedelta(days=45)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Johnson Family", "beneficiary_type": "family", "purpose": "medical",
         "purpose_description": "Cancer treatment expenses - chemotherapy and hospital bills",
         "amount": 15000, "date": (now - timedelta(days=30)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "Referred by Pastor Williams", "created_at": (now - timedelta(days=30)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Maria Rodriguez", "beneficiary_type": "individual", "purpose": "education",
         "purpose_description": "Community college tuition for nursing program",
         "amount": 4500, "date": (now - timedelta(days=20)).isoformat(),
         "approved_by": ["John Smith"], "approval_method": "majority", "status": "approved",
         "minutes_id": None, "notes": "Single mother pursuing RN degree", "created_at": (now - timedelta(days=20)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Local Food Bank", "beneficiary_type": "organization", "purpose": "food_necessities",
         "purpose_description": "Thanksgiving meal packages for 200 families",
         "amount": 5000, "date": (now - timedelta(days=90)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "Annual holiday contribution", "created_at": (now - timedelta(days=90)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Thomas Williams", "beneficiary_type": "individual", "purpose": "housing",
         "purpose_description": "Emergency rent assistance - 2 months rent after job loss",
         "amount": 3200, "date": (now - timedelta(days=7)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "New job starting next month", "created_at": (now - timedelta(days=7)).isoformat()}
    ])
    
    # ==================== COMPENSATION PLANS ====================
    await db.compensation_plans.insert_many([
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat()},
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat()}
    ])
    
    # ==================== COMPENSATION PAYMENTS ====================
    await db.compensation_payments.insert_many([
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "amount": 6000, "payment_date": (now - timedelta(days=90)).isoformat(),
         "notes": "Q4 2025 compensation", "created_at": (now - timedelta(days=90)).isoformat()},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "amount": 6000, "payment_date": (now - timedelta(days=90)).isoformat(),
         "notes": "Q4 2025 compensation", "created_at": (now - timedelta(days=90)).isoformat()},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "amount": 6000, "payment_date": (now - timedelta(days=5)).isoformat(),
         "notes": "Q1 2026 compensation", "created_at": (now - timedelta(days=5)).isoformat()},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "amount": 6000, "payment_date": (now - timedelta(days=5)).isoformat(),
         "notes": "Q1 2026 compensation", "created_at": (now - timedelta(days=5)).isoformat()}
    ])
    
    # ==================== NOTIFICATION PREFERENCES ====================
    await db.notification_preferences.insert_one({
        "user_id": user["user_id"],
        "minutes_created": True,
        "distribution_created": True,
        "distribution_approved": True,
        "task_reminders": True,
        "task_overdue": True,
        "subscription_updates": True,
        "weekly_digest": True
    })
    
    return {"message": "Demo data created with 2 trusts", "seeded": True, "trust_ids": [trust1_id, trust2_id]}

# Include router and middleware
app.include_router(api_router)
app.include_router(distributions_router, prefix="/api")
app.include_router(governance_router, prefix="/api")
app.include_router(minutes_router, prefix="/api")
app.include_router(schedule_a_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# HTTP methods that modify data (write operations)
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that should allow write access even in read-only mode (subscription management)
WRITE_EXEMPT_PATHS = {
    "/api/subscription/create-checkout",
    "/api/subscription/verify-payment",
    "/api/subscription/create-portal",
    "/api/subscription/cancel",
    "/api/subscription/reactivate",
    "/api/subscription/upgrade",
    "/api/stripe/webhook",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/profile",  # Allow profile updates
}

class SubscriptionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check subscription status for protected routes.
    
    Read-only mode behavior:
    - GET requests: Always allowed (users can view all their data)
    - POST/PUT/PATCH/DELETE requests: Blocked with 403 if subscription is inactive
    
    This ensures users can always access their data but cannot modify it without
    an active subscription.
    """
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        
        # Skip subscription check for fully exempt paths
        if path in SUBSCRIPTION_EXEMPT_PATHS or not path.startswith("/api/"):
            return await call_next(request)
        
        # Skip for OPTIONS requests (CORS preflight)
        if method == "OPTIONS":
            return await call_next(request)
        
        # Get auth token
        session_token = request.cookies.get("session_token")
        auth_header = request.headers.get("Authorization")
        
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        elif session_token:
            token = session_token
        
        if not token:
            # No token - let the endpoint handle 401
            return await call_next(request)
        
        # Try to get user_id from token
        user_id = None
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("user_id")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass
        
        if not user_id:
            # Try session token
            session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
            if session:
                user_id = session.get("user_id")
        
        if not user_id:
            # Can't determine user - let endpoint handle it
            return await call_next(request)
        
        # Get subscription state using the unified helper
        state = await get_subscription_state(user_id)
        
        # If subscription is active, allow all operations
        if state.is_active:
            return await call_next(request)
        
        # Subscription is not active - check if this is a read or write operation
        is_write_operation = method in WRITE_METHODS
        is_write_exempt = path in WRITE_EXEMPT_PATHS
        
        # Allow read operations (GET) even with expired subscription
        if not is_write_operation:
            return await call_next(request)
        
        # Allow certain write paths even in read-only mode
        if is_write_exempt:
            return await call_next(request)
        
        # Block write operations for inactive subscriptions
        return JSONResponse(
            status_code=READ_ONLY_ERROR_CODE,
            content={
                "detail": READ_ONLY_ERROR_MESSAGE,
                "subscription_status": state.status,
                "is_read_only": True,
                "trial_days_remaining": state.trial_days_remaining
            },
            headers={"X-Subscription-Status": state.status}
        )

app.add_middleware(SubscriptionMiddleware)

@app.on_event("startup")
async def startup_event():
    """Start background task runner and create indexes on app startup"""
    try:
        await background_runner.start()
        logger.info("Background task runner started successfully")
    except Exception as e:
        logger.error(f"Failed to start background runner: {e}")
    
    # Create database indexes for performance
    try:
        # User-related indexes
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id", unique=True)
        
        # Subscription indexes
        await db.subscriptions.create_index("user_id", unique=True)
        await db.subscriptions.create_index("stripe_customer_id", sparse=True)
        
        # Trust indexes
        await db.trusts.create_index("user_id")
        await db.trusts.create_index("trust_id", unique=True)
        
        # Entity indexes
        await db.entities.create_index([("trust_id", 1), ("user_id", 1)])
        await db.entities.create_index("entity_id", unique=True)
        
        # Governance tasks indexes
        await db.governance_tasks.create_index([("trust_id", 1), ("user_id", 1)])
        await db.governance_tasks.create_index([("user_id", 1), ("due_date", 1)])
        await db.governance_tasks.create_index("task_id", unique=True)
        
        # Minutes indexes
        await db.minutes_records.create_index([("trust_id", 1), ("user_id", 1)])
        await db.minutes_records.create_index([("user_id", 1), ("meeting_date", -1)])
        await db.minutes_records.create_index("minutes_id", unique=True)
        
        # Distribution indexes
        await db.distribution_records.create_index([("trust_id", 1), ("user_id", 1)])
        await db.distribution_records.create_index([("user_id", 1), ("date", -1)])
        await db.distribution_records.create_index("distribution_id", unique=True)
        
        # Health score snapshots indexes
        await db.health_score_snapshots.create_index([("trust_id", 1), ("calculated_at", -1)])
        await db.health_score_snapshots.create_index("snapshot_id", unique=True)
        
        # Session indexes with TTL
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("user_id")
        
        # Password reset with TTL (auto-expire after 2 hours)
        await db.password_resets.create_index("token", unique=True)
        await db.password_resets.create_index("user_id", unique=True)
        
        # Audit logs
        await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_logs.create_index("audit_id", unique=True)
        
        logger.info("Database indexes created/verified successfully")
    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    await background_runner.stop()
    client.close()
