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
from routers.compensation import router as compensation_router
from routers.subscriptions import router as subscriptions_router
from routers.benevolence import router as benevolence_router
from routers.exports import router as exports_router
from routers.trust_units import router as trust_units_router
from routers.trusts import router as trusts_router
from routers.entities import router as entities_router
from routers.tasks import router as tasks_router
from routers.auth import router as auth_router

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
# MIGRATED TO: /app/backend/routers/trusts.py
# Endpoints: POST/GET/PUT/DELETE /trusts

# ==================== ENTITY ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/entities.py
# Endpoints: POST/GET/PATCH/DELETE /entities, POST/GET/DELETE /entity-relationships

# ==================== GOVERNANCE TASK ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/tasks.py
# Endpoints: POST/GET /tasks, PATCH /tasks/{id}/complete, PATCH /tasks/{id}/uncomplete, DELETE /tasks/{id}

# ==================== TRUST UNITS ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/trust_units.py
# Endpoints: GET /trust-units/summary, PATCH /trust-units/settings,
#            POST/PATCH/GET /trust-units/certificates, GET /trust-units/certificates/{id}/pdf,
#            POST/GET /trust-units/transfers, POST /trust-units/create-from-minutes/{id},
#            POST /trust-units/bootstrap-from-minutes/{id}

# ==================== GOVERNANCE TASK ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/tasks.py
# Endpoints: POST/GET /tasks, PATCH /tasks/{id}/complete, PATCH /tasks/{id}/uncomplete, DELETE /tasks/{id}

# ==================== BENEFICIARY DASHBOARD ====================

@api_router.get("/beneficiaries/dashboard", response_model=BeneficiaryDashboardResponse)
async def get_beneficiary_dashboard(
    trust_id: Optional[str] = None,
    user: dict = Depends(require_premium_feature(Feature.BENEFICIARY_DASHBOARD))
):
    """
    Beneficiary Dashboard showing current unit allocations per certificate holder.
    
    Feature Gate: BENEFICIARY_DASHBOARD
    - Trial users cannot access the beneficiary dashboard
    - Paid users can view unit allocations and transfer history
    
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
# MIGRATED TO: /app/backend/routers/benevolence.py
# Endpoints: POST/GET/PUT/DELETE /benevolence, GET /benevolence/summary/{trust_id},
#            GET /benevolence/export/{trust_id}/pdf

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
# MIGRATED TO: /app/backend/routers/compensation.py
# Endpoints: POST/GET /compensation-plans, POST/GET/DELETE /compensation-payments, GET /compensation-ytd


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
# MIGRATED TO: /app/backend/routers/exports.py
# Endpoints: GET /export/minutes, GET /export/distributions,
#            GET /export/compensation, GET /export/tasks

# ==================== SUBSCRIPTION ENDPOINTS ====================
# MIGRATED TO: /app/backend/routers/subscriptions.py
# Endpoints: GET /subscription, GET /subscription/state, GET /subscription/features,
#            POST /subscription/create-checkout, GET /subscription/verify-payment,
#            POST /subscription/create-portal, POST /subscription/cancel,
#            POST /subscription/reactivate, POST /subscription/upgrade, POST /stripe/webhook

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
app.include_router(compensation_router, prefix="/api")
app.include_router(subscriptions_router, prefix="/api")
app.include_router(benevolence_router, prefix="/api")
app.include_router(exports_router, prefix="/api")
app.include_router(trust_units_router, prefix="/api")
app.include_router(trusts_router, prefix="/api")
app.include_router(entities_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(auth_router, prefix="/api")

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
