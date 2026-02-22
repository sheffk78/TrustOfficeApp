from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, BackgroundTasks
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
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

# Trust Models
class TrustCreate(BaseModel):
    name: str
    trust_type: TrustType = TrustType.family
    jurisdiction: str = ""

class TrustUpdate(BaseModel):
    name: Optional[str] = None
    trust_type: Optional[TrustType] = None
    jurisdiction: Optional[str] = None

class TrustResponse(BaseModel):
    trust_id: str
    user_id: str
    name: str
    trust_type: str
    jurisdiction: str
    created_at: str
    governance_score: int = 0

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

# Compensation Models
class CompensationPlanCreate(BaseModel):
    trust_id: str
    annual_approved_amount: float
    effective_date: str
    notes: str = ""

class CompensationPlanResponse(BaseModel):
    plan_id: str
    trust_id: str
    annual_approved_amount: float
    effective_date: str
    notes: str
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
        comp_aligned = ytd_total <= comp_plan.get("annual_approved_amount", 0)
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
    
    # 4. Distribution Documentation (+20)
    dist_count = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    dist_documented = dist_count > 0
    criteria.append(HealthScoreCriterion(
        name="Distribution Documentation",
        description="At least one distribution logged",
        points=20 if dist_documented else 0,
        achieved=dist_documented
    ))
    if dist_documented:
        total_score += 20
    
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

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}

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

# ==================== MINUTES ENDPOINTS ====================

@api_router.post("/minutes", response_model=MinutesResponse)
async def create_minutes(minutes: MinutesCreate, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": minutes.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": minutes.trust_id,
        "user_id": user["user_id"],
        "minutes_type": minutes.minutes_type.value,
        "meeting_date": minutes.meeting_date,
        "participants_text": minutes.participants_text,
        "decisions_text": minutes.decisions_text,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.minutes_records.insert_one(minutes_doc)
    
    # Link to distribution if provided
    if minutes.distribution_id:
        await db.distribution_records.update_one(
            {"distribution_id": minutes.distribution_id},
            {"$set": {"minutes_record_id": minutes_id}}
        )
    
    # Link to compensation payment if provided
    if minutes.compensation_payment_id:
        await db.compensation_payments.update_one(
            {"payment_id": minutes.compensation_payment_id},
            {"$set": {"minutes_record_id": minutes_id}}
        )
    
    await auto_update_onboarding(user["user_id"], minutes.trust_id)
    
    # Send notification email
    background_tasks.add_task(
        email_service.send_minutes_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", ""),
        minutes_type=minutes.minutes_type.value,
        meeting_date=minutes.meeting_date,
        participants=minutes.participants_text,
        decisions=minutes.decisions_text
    )
    
    return MinutesResponse(**minutes_doc)

@api_router.get("/minutes", response_model=List[MinutesResponse])
async def get_minutes(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    minutes = await db.minutes_records.find(query, {"_id": 0}).sort("meeting_date", -1).to_list(1000)
    return [MinutesResponse(**m) for m in minutes]

@api_router.get("/minutes/{minutes_id}", response_model=MinutesResponse)
async def get_minutes_by_id(minutes_id: str, user: dict = Depends(get_current_user)):
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return MinutesResponse(**minutes)

@api_router.delete("/minutes/{minutes_id}")
async def delete_minutes(minutes_id: str, user: dict = Depends(get_current_user)):
    result = await db.minutes_records.delete_one({"minutes_id": minutes_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return {"message": "Minutes deleted"}

def generate_minutes_pdf(minutes: dict, trust: dict) -> bytes:
    """Generate a professional PDF for minutes record"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    # Custom styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TrustTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=6,
        textColor=colors.HexColor('#010079')
    )
    heading_style = ParagraphStyle(
        'TrustHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor('#010079')
    )
    body_style = ParagraphStyle(
        'TrustBody',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        spaceAfter=8
    )
    label_style = ParagraphStyle(
        'TrustLabel',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666')
    )
    
    story = []
    
    # Header
    story.append(Paragraph(trust.get('name', 'Trust'), title_style))
    story.append(Paragraph(f"Meeting Minutes - {minutes.get('minutes_type', 'General').replace('_', ' ').title()}", heading_style))
    story.append(Spacer(1, 12))
    
    # Meeting details table
    meeting_date = minutes.get('meeting_date', 'N/A')
    if 'T' in meeting_date:
        meeting_date = meeting_date.split('T')[0]
    
    details_data = [
        ['Meeting Date:', meeting_date],
        ['Minutes Type:', minutes.get('minutes_type', 'General').replace('_', ' ').title()],
        ['Trust:', trust.get('name', 'N/A')],
        ['Jurisdiction:', trust.get('jurisdiction', 'N/A')]
    ]
    
    details_table = Table(details_data, colWidths=[1.5*inch, 4.5*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 20))
    
    # Participants
    if minutes.get('participants_text'):
        story.append(Paragraph('Participants Present', heading_style))
        participants = minutes.get('participants_text', '').split(',')
        for p in participants:
            if p.strip():
                story.append(Paragraph(f"• {p.strip()}", body_style))
        story.append(Spacer(1, 12))
    
    # Decisions/Discussion
    if minutes.get('decisions_text'):
        story.append(Paragraph('Decisions & Discussion', heading_style))
        story.append(Paragraph(minutes.get('decisions_text', ''), body_style))
        story.append(Spacer(1, 12))
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph('_' * 50, body_style))
    story.append(Paragraph('Trustee Signature', label_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph('_' * 50, body_style))
    story.append(Paragraph('Date', label_style))
    
    # Generated timestamp
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f"Generated by TrustOffice on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#999999'))
    ))
    
    doc.build(story)
    return buffer.getvalue()

@api_router.get("/minutes/{minutes_id}/pdf")
async def get_minutes_pdf(minutes_id: str, user: dict = Depends(get_current_user)):
    """Generate and return PDF for minutes record"""
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    trust = await db.trusts.find_one(
        {"trust_id": minutes["trust_id"], "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    pdf_bytes = generate_minutes_pdf(minutes, trust or {})
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    return {
        "pdf_base64": pdf_base64,
        "filename": f"minutes_{minutes_id}.pdf"
    }

# ==================== DISTRIBUTION ENDPOINTS ====================

@api_router.post("/distributions", response_model=DistributionResponse)
async def create_distribution(dist: DistributionCreate, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one({"trust_id": dist.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    dist_id = f"dist_{uuid.uuid4().hex[:12]}"
    dist_doc = {
        "distribution_id": dist_id,
        "trust_id": dist.trust_id,
        "user_id": user["user_id"],
        "beneficiary_name": dist.beneficiary_name,
        "amount": dist.amount,
        "date": dist.date,
        "purpose_classification": dist.purpose_classification.value,
        "authority_clause_ref": dist.authority_clause_ref,
        "notes": dist.notes,
        "solvency_confirmed": False,
        "recusal_acknowledged": False,
        "approved_by": None,
        "approved_at": None,
        "minutes_record_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.distribution_records.insert_one(dist_doc)
    await auto_update_onboarding(user["user_id"], dist.trust_id)
    
    # Send notification email
    background_tasks.add_task(
        email_service.send_distribution_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", ""),
        amount=dist.amount,
        beneficiary=dist.beneficiary_name,
        category=dist.purpose_classification.value,
        date=dist.date,
        status="review"
    )
    
    return DistributionResponse(**dist_doc)

@api_router.get("/distributions", response_model=List[DistributionResponse])
async def get_distributions(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    dists = await db.distribution_records.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return [DistributionResponse(**d) for d in dists]

@api_router.patch("/distributions/{distribution_id}/approve", response_model=DistributionResponse)
async def approve_distribution(distribution_id: str, approval: DistributionApprove, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    dist = await db.distribution_records.find_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution not found")
    
    if not approval.solvency_confirmed:
        raise HTTPException(status_code=400, detail="Solvency must be confirmed to approve distribution")
    
    if not approval.recusal_acknowledged:
        raise HTTPException(status_code=400, detail="Recusal must be acknowledged")
    
    approval_time = datetime.now(timezone.utc).isoformat()
    
    await db.distribution_records.update_one(
        {"distribution_id": distribution_id},
        {"$set": {
            "solvency_confirmed": True,
            "recusal_acknowledged": True,
            "approved_by": user["user_id"],
            "approved_at": approval_time
        }}
    )
    
    updated = await db.distribution_records.find_one({"distribution_id": distribution_id}, {"_id": 0})
    
    # Get trust name for email
    trust = await db.trusts.find_one({"trust_id": dist["trust_id"]}, {"_id": 0})
    
    # Send approval notification
    background_tasks.add_task(
        email_service.send_distribution_approved_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", "") if trust else "",
        amount=dist["amount"],
        beneficiary=dist["beneficiary_name"],
        approved_by=user.get("name", user["email"]),
        approval_date=approval_time.split("T")[0]
    )
    
    return DistributionResponse(**updated)

@api_router.delete("/distributions/{distribution_id}")
async def delete_distribution(distribution_id: str, user: dict = Depends(get_current_user)):
    result = await db.distribution_records.delete_one({
        "distribution_id": distribution_id,
        "user_id": user["user_id"]
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Distribution not found")
    return {"message": "Distribution deleted"}

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
        "annual_approved_amount": plan.annual_approved_amount,
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
        exceeds_plan = ytd_total > plan.get("annual_approved_amount", 0)
    
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
    annual_approved = plan.get("annual_approved_amount", 0) if plan else 0
    
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

# ==================== GOVERNANCE HEALTH ENDPOINTS ====================

@api_router.get("/governance/{trust_id}", response_model=HealthScoreResponse)
async def get_governance_health(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    health = await calculate_health_score(trust_id, user["user_id"])
    
    # Store snapshot for history tracking
    snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
    await db.health_score_snapshots.insert_one({
        "snapshot_id": snapshot_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "score_value": health["total_score"],
        "color": health["color"],
        "criteria_summary": {c["name"]: c["achieved"] for c in health["criteria"]},
        "calculated_at": datetime.now(timezone.utc).isoformat()
    })
    
    return HealthScoreResponse(**health)

@api_router.get("/governance/{trust_id}/history")
async def get_governance_history(trust_id: str, days: int = 30, user: dict = Depends(get_current_user)):
    """Get historical health score snapshots for charting"""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # Get snapshots grouped by day (take latest per day)
    snapshots = await db.health_score_snapshots.find(
        {"trust_id": trust_id, "user_id": user["user_id"], "calculated_at": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("calculated_at", -1).to_list(1000)
    
    # Deduplicate by day, keeping latest
    daily_scores = {}
    for snap in snapshots:
        date_key = snap["calculated_at"][:10]  # YYYY-MM-DD
        if date_key not in daily_scores:
            daily_scores[date_key] = {
                "date": date_key,
                "score": snap["score_value"],
                "color": snap["color"]
            }
    
    # Sort by date ascending for chart
    history = sorted(daily_scores.values(), key=lambda x: x["date"])
    
    return {
        "trust_id": trust_id,
        "days": days,
        "history": history,
        "current_score": history[-1]["score"] if history else 0
    }

# ==================== ONBOARDING ENDPOINTS ====================

@api_router.get("/onboarding", response_model=OnboardingState)
async def get_onboarding(user: dict = Depends(get_current_user)):
    # Get user's trust to auto-update
    trust = await db.trusts.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if trust:
        await auto_update_onboarding(user["user_id"], trust["trust_id"])
    
    state = await db.user_onboarding.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not state:
        state = {
            "user_id": user["user_id"],
            "entities_confirmed": False,
            "calendar_set": False,
            "minutes_generated": False,
            "distribution_logged": False,
            "checklist_dismissed": False
        }
    
    return OnboardingState(**state)

@api_router.patch("/onboarding")
async def update_onboarding(updates: dict, user: dict = Depends(get_current_user)):
    allowed_fields = ["entities_confirmed", "calendar_set", "minutes_generated", "distribution_logged", "checklist_dismissed"]
    update_data = {k: v for k, v in updates.items() if k in allowed_fields}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.user_onboarding.update_one(
        {"user_id": user["user_id"]},
        {"$set": update_data},
        upsert=True
    )
    
    return {"message": "Onboarding updated"}

@api_router.post("/onboarding/dismiss")
async def dismiss_onboarding(user: dict = Depends(get_current_user)):
    await db.user_onboarding.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "checklist_dismissed": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    return {"message": "Onboarding dismissed"}

# ==================== ACTIVITY TIMELINE ====================

@api_router.get("/activity")
async def get_activity(trust_id: Optional[str] = None, limit: int = 20, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    activities = []
    
    # Minutes
    minutes = await db.minutes_records.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    for m in minutes:
        activities.append({
            "type": "minutes",
            "id": m["minutes_id"],
            "trust_id": m["trust_id"],
            "title": f"{m['minutes_type'].title()} Minutes",
            "subtitle": m.get("decisions_text", "")[:100],
            "date": m["meeting_date"],
            "created_at": m["created_at"]
        })
    
    # Distributions
    dists = await db.distribution_records.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    for d in dists:
        activities.append({
            "type": "distribution",
            "id": d["distribution_id"],
            "trust_id": d["trust_id"],
            "title": f"${d['amount']:,.2f} to {d['beneficiary_name']}",
            "subtitle": d.get("purpose_classification", ""),
            "status": "approved" if d.get("approved_at") else "pending",
            "date": d["date"],
            "created_at": d["created_at"]
        })
    
    # Compensation Payments
    payments = await db.compensation_payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    for p in payments:
        activities.append({
            "type": "compensation",
            "id": p["payment_id"],
            "trust_id": p["trust_id"],
            "title": f"${p['amount']:,.2f} Compensation",
            "subtitle": p.get("classification_text", ""),
            "status": "exceeds" if p.get("exceeds_plan_flag") else "within_plan",
            "date": p["date"],
            "created_at": p["created_at"]
        })
    
    # Tasks completed
    tasks = await db.governance_tasks.find({**query, "completed_at": {"$ne": None}}, {"_id": 0}).sort("completed_at", -1).to_list(limit)
    for t in tasks:
        activities.append({
            "type": "task",
            "id": t["task_id"],
            "trust_id": t["trust_id"],
            "title": f"{t['task_type'].replace('_', ' ').title()} Completed",
            "subtitle": t.get("description", ""),
            "status": "completed",
            "date": t["completed_at"],
            "created_at": t["completed_at"]
        })
    
    activities.sort(key=lambda x: x["created_at"], reverse=True)
    return activities[:limit]

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

@api_router.post("/subscription/create-checkout")
async def create_checkout_session(checkout: CheckoutRequest, user: dict = Depends(get_current_user)):
    """Create a Stripe checkout session for subscription"""
    if checkout.plan_type not in ["monthly", "annual"]:
        raise HTTPException(status_code=400, detail="Invalid plan type")
    
    price_id = STRIPE_MONTHLY_PRICE_ID if checkout.plan_type == "monthly" else STRIPE_ANNUAL_PRICE_ID
    
    # Get or create subscription to get/create stripe customer
    sub = await get_or_create_subscription(user["user_id"])
    
    try:
        # Get or create Stripe customer
        if sub.get("stripe_customer_id"):
            customer_id = sub["stripe_customer_id"]
        else:
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
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=checkout.success_url,
            cancel_url=checkout.cancel_url,
            metadata={"user_id": user["user_id"], "plan_type": checkout.plan_type}
        )
        
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

@api_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        plan_type = session.get("metadata", {}).get("plan_type", "monthly")
        
        if user_id:
            await db.subscriptions.update_one(
                {"user_id": user_id},
                {"$set": {
                    "plan_type": plan_type,
                    "status": "active",
                    "stripe_subscription_id": session.get("subscription"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            await db.payment_transactions.update_one(
                {"session_id": session["id"]},
                {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
    
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await db.subscriptions.update_one(
            {"stripe_subscription_id": subscription["id"]},
            {"$set": {"status": "canceled", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        customer_id = invoice.get("customer")
        if customer_id:
            await db.subscriptions.update_one(
                {"stripe_customer_id": customer_id},
                {"$set": {"status": "past_due", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
    
    return {"status": "ok"}

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
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    # Create trust
    await db.trusts.insert_one({
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "name": "Smith Family Trust",
        "trust_type": "family",
        "jurisdiction": "Delaware",
        "created_at": now.isoformat()
    })
    
    # Create trust entity
    trust_entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": trust_entity_id,
        "trust_id": trust_id,
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
    
    # Create holding LLC
    holding_llc_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": holding_llc_id,
        "trust_id": trust_id,
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
    
    # Create relationship
    await db.entity_relationships.insert_one({
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "parent_entity_id": trust_entity_id,
        "child_entity_id": holding_llc_id,
        "relationship_type": "owns",
        "ownership_percentage": 100,
        "notes": "Trust is sole member of holding LLC",
        "created_at": now.isoformat()
    })
    
    # Create governance tasks
    await db.governance_tasks.insert_many([
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "task_type": "annual_review",
            "due_date": (now + timedelta(days=60)).isoformat(),
            "completed_at": None,
            "description": "Annual trust administration review",
            "created_at": now.isoformat()
        },
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "task_type": "quarterly_review",
            "due_date": (now + timedelta(days=30)).isoformat(),
            "completed_at": None,
            "description": "Q1 2026 quarterly review",
            "created_at": now.isoformat()
        },
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "task_type": "compensation_review",
            "due_date": (now - timedelta(days=5)).isoformat(),  # Overdue
            "completed_at": None,
            "description": "Review trustee compensation for 2026",
            "created_at": (now - timedelta(days=30)).isoformat()
        }
    ])
    
    # Create minutes
    await db.minutes_records.insert_many([
        {
            "minutes_id": f"minutes_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "minutes_type": "quarterly",
            "meeting_date": (now - timedelta(days=15)).isoformat(),
            "participants_text": "John Smith, Jane Smith, Robert Attorney",
            "decisions_text": "Reviewed Q4 2025 performance. Approved education distribution for Emily. Confirmed investment strategy.",
            "created_at": (now - timedelta(days=15)).isoformat()
        },
        {
            "minutes_id": f"minutes_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "minutes_type": "distribution",
            "meeting_date": (now - timedelta(days=30)).isoformat(),
            "participants_text": "John Smith, Jane Smith",
            "decisions_text": "Approved $15,000 distribution for spring semester tuition at State University. Solvency confirmed.",
            "created_at": (now - timedelta(days=30)).isoformat()
        }
    ])
    
    # Create compensation plan
    await db.compensation_plans.insert_one({
        "plan_id": f"plan_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "annual_approved_amount": 25000,
        "effective_date": f"{now.year}-01-01",
        "notes": "Annual trustee compensation approved by trust protector",
        "created_at": now.isoformat()
    })
    
    # Create compensation payments
    await db.compensation_payments.insert_many([
        {
            "payment_id": f"payment_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "amount": 6250,
            "date": (now - timedelta(days=60)).isoformat(),
            "classification_text": "Q4 2025 trustee services",
            "exceeds_plan_flag": False,
            "minutes_record_id": None,
            "created_at": (now - timedelta(days=60)).isoformat()
        },
        {
            "payment_id": f"payment_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "amount": 6250,
            "date": (now - timedelta(days=5)).isoformat(),
            "classification_text": "Q1 2026 trustee services",
            "exceeds_plan_flag": False,
            "minutes_record_id": None,
            "created_at": (now - timedelta(days=5)).isoformat()
        }
    ])
    
    # Create distributions
    await db.distribution_records.insert_many([
        {
            "distribution_id": f"dist_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "beneficiary_name": "Emily Smith",
            "amount": 15000,
            "date": (now - timedelta(days=10)).isoformat(),
            "purpose_classification": "distribution",
            "authority_clause_ref": "Article IV, Section 4.1(a)",
            "notes": "Spring 2026 semester tuition",
            "solvency_confirmed": True,
            "recusal_acknowledged": True,
            "approved_by": user["user_id"],
            "approved_at": (now - timedelta(days=10)).isoformat(),
            "minutes_record_id": None,
            "created_at": (now - timedelta(days=10)).isoformat()
        },
        {
            "distribution_id": f"dist_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "beneficiary_name": "Emily Smith",
            "amount": 2500,
            "date": (now - timedelta(days=3)).isoformat(),
            "purpose_classification": "distribution",
            "authority_clause_ref": "Article IV, Section 4.1(b)",
            "notes": "Monthly living allowance",
            "solvency_confirmed": False,
            "recusal_acknowledged": False,
            "approved_by": None,
            "approved_at": None,
            "minutes_record_id": None,
            "created_at": (now - timedelta(days=3)).isoformat()
        }
    ])
    
    # Update onboarding
    await db.user_onboarding.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "entities_confirmed": True,
            "calendar_set": True,
            "minutes_generated": True,
            "distribution_logged": True,
            "updated_at": now.isoformat()
        }},
        upsert=True
    )
    
    return {"message": "Demo data created", "seeded": True, "trust_id": trust_id}

# Include router and middleware
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Start background task runner on app startup"""
    try:
        await background_runner.start()
        logger.info("Background task runner started successfully")
    except Exception as e:
        logger.error(f"Failed to start background runner: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    await background_runner.stop()
    client.close()
