from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'trustoffice_secret_key_change_in_production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

# Create the main app
app = FastAPI(title="TrustOffice API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

security = HTTPBearer(auto_error=False)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

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

class TrustCreate(BaseModel):
    name: str
    role: str = "Trustee"
    review_cadence: str = "quarterly"  # monthly, quarterly, annual
    description: Optional[str] = None

class TrustUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    review_cadence: Optional[str] = None
    description: Optional[str] = None

class TrustResponse(BaseModel):
    trust_id: str
    user_id: str
    name: str
    role: str
    review_cadence: str
    description: Optional[str] = None
    created_at: str
    governance_score: int = 0

class MinutesCreate(BaseModel):
    trust_id: str
    entry_type: str  # meeting, decision, distribution_approval
    date: str
    participants: List[str]
    summary: str
    details: str
    best_interest_rationale: Optional[str] = None

class MinutesResponse(BaseModel):
    minutes_id: str
    trust_id: str
    user_id: str
    entry_type: str
    date: str
    participants: List[str]
    summary: str
    details: str
    best_interest_rationale: Optional[str] = None
    created_at: str

class DistributionCreate(BaseModel):
    trust_id: str
    date: str
    amount: float
    distribution_type: str  # trust_distribution, loan, gift
    beneficiary: str
    category: str
    notes: Optional[str] = None
    status: str = "review"  # approved, review, declined

class DistributionResponse(BaseModel):
    distribution_id: str
    trust_id: str
    user_id: str
    date: str
    amount: float
    distribution_type: str
    beneficiary: str
    category: str
    notes: Optional[str] = None
    status: str
    created_at: str

class ExpenseCreate(BaseModel):
    trust_id: str
    date: str
    amount: float
    payee: str
    category: str
    notes: Optional[str] = None
    status: str = "review"

class ExpenseResponse(BaseModel):
    expense_id: str
    trust_id: str
    user_id: str
    date: str
    amount: float
    payee: str
    category: str
    notes: Optional[str] = None
    status: str
    created_at: str

class GovernanceHealthResponse(BaseModel):
    trust_id: str
    overall_score: int
    meeting_recency_score: int
    decisions_count_score: int
    pending_reviews_score: int
    last_meeting_date: Optional[str] = None
    total_decisions: int
    pending_reviews: int
    status: str  # good, warning, critical

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
    # Check cookie first
    session_token = request.cookies.get("session_token")
    
    # Then check Authorization header
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
    
    # Try session token (Google OAuth)
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

async def calculate_governance_score(trust_id: str, user_id: str) -> dict:
    """Calculate governance health score based on activity"""
    now = datetime.now(timezone.utc)
    
    # Get latest minutes/meeting
    latest_minutes = await db.minutes.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("date", -1)]
    )
    
    # Count decisions in last 90 days
    ninety_days_ago = (now - timedelta(days=90)).isoformat()
    decisions_count = await db.minutes.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "date": {"$gte": ninety_days_ago}
    })
    
    # Count pending reviews
    pending_distributions = await db.distributions.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "review"
    })
    pending_expenses = await db.expenses.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "review"
    })
    pending_reviews = pending_distributions + pending_expenses
    
    # Calculate scores (0-100 each)
    # Meeting recency score
    meeting_recency_score = 0
    last_meeting_date = None
    if latest_minutes:
        last_meeting_date = latest_minutes.get("date")
        try:
            last_date = datetime.fromisoformat(last_meeting_date.replace('Z', '+00:00'))
            days_since = (now - last_date).days
            if days_since <= 30:
                meeting_recency_score = 100
            elif days_since <= 60:
                meeting_recency_score = 75
            elif days_since <= 90:
                meeting_recency_score = 50
            elif days_since <= 180:
                meeting_recency_score = 25
            else:
                meeting_recency_score = 0
        except:
            meeting_recency_score = 0
    
    # Decisions count score (more = better, up to 10)
    decisions_count_score = min(decisions_count * 10, 100)
    
    # Pending reviews score (fewer = better)
    if pending_reviews == 0:
        pending_reviews_score = 100
    elif pending_reviews <= 2:
        pending_reviews_score = 75
    elif pending_reviews <= 5:
        pending_reviews_score = 50
    else:
        pending_reviews_score = 25
    
    # Overall score (weighted average)
    overall_score = int(
        meeting_recency_score * 0.4 +
        decisions_count_score * 0.35 +
        pending_reviews_score * 0.25
    )
    
    # Determine status
    if overall_score >= 70:
        status = "good"
    elif overall_score >= 40:
        status = "warning"
    else:
        status = "critical"
    
    return {
        "trust_id": trust_id,
        "overall_score": overall_score,
        "meeting_recency_score": meeting_recency_score,
        "decisions_count_score": decisions_count_score,
        "pending_reviews_score": pending_reviews_score,
        "last_meeting_date": last_meeting_date,
        "total_decisions": decisions_count,
        "pending_reviews": pending_reviews,
        "status": status
    }

# ==================== AUTH ENDPOINTS ====================

@api_router.post("/auth/register", response_model=UserResponse)
async def register(user: UserCreate):
    # Check if user exists
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
        raise HTTPException(status_code=401, detail="Please use Google login for this account")
    
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
    """Exchange Google OAuth session_id for session data"""
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    # Call Emergent Auth to get session data
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
    
    # Check if user exists, create if not
    email = session_data.get("email")
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user info if needed
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
    
    # Store session
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
        "role": trust.role,
        "review_cadence": trust.review_cadence,
        "description": trust.description,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.trusts.insert_one(trust_doc)
    
    return TrustResponse(**trust_doc, governance_score=0)

@api_router.get("/trusts", response_model=List[TrustResponse])
async def get_trusts(user: dict = Depends(get_current_user)):
    trusts = await db.trusts.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
    
    result = []
    for trust in trusts:
        health = await calculate_governance_score(trust["trust_id"], user["user_id"])
        result.append(TrustResponse(**trust, governance_score=health["overall_score"]))
    
    return result

@api_router.get("/trusts/{trust_id}", response_model=TrustResponse)
async def get_trust(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    health = await calculate_governance_score(trust_id, user["user_id"])
    return TrustResponse(**trust, governance_score=health["overall_score"])

@api_router.put("/trusts/{trust_id}", response_model=TrustResponse)
async def update_trust(trust_id: str, update: TrustUpdate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if update_data:
        await db.trusts.update_one(
            {"trust_id": trust_id},
            {"$set": update_data}
        )
    
    updated = await db.trusts.find_one({"trust_id": trust_id}, {"_id": 0})
    health = await calculate_governance_score(trust_id, user["user_id"])
    return TrustResponse(**updated, governance_score=health["overall_score"])

@api_router.delete("/trusts/{trust_id}")
async def delete_trust(trust_id: str, user: dict = Depends(get_current_user)):
    result = await db.trusts.delete_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Delete related data
    await db.minutes.delete_many({"trust_id": trust_id})
    await db.distributions.delete_many({"trust_id": trust_id})
    await db.expenses.delete_many({"trust_id": trust_id})
    
    return {"message": "Trust deleted"}

# ==================== MINUTES ENDPOINTS ====================

@api_router.post("/minutes", response_model=MinutesResponse)
async def create_minutes(minutes: MinutesCreate, user: dict = Depends(get_current_user)):
    # Verify trust belongs to user
    trust = await db.trusts.find_one(
        {"trust_id": minutes.trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    minutes_id = f"min_{uuid.uuid4().hex[:12]}"
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": minutes.trust_id,
        "user_id": user["user_id"],
        "entry_type": minutes.entry_type,
        "date": minutes.date,
        "participants": minutes.participants,
        "summary": minutes.summary,
        "details": minutes.details,
        "best_interest_rationale": minutes.best_interest_rationale,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.minutes.insert_one(minutes_doc)
    
    return MinutesResponse(**minutes_doc)

@api_router.get("/minutes", response_model=List[MinutesResponse])
async def get_minutes(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    minutes = await db.minutes.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return [MinutesResponse(**m) for m in minutes]

@api_router.get("/minutes/{minutes_id}", response_model=MinutesResponse)
async def get_minutes_by_id(minutes_id: str, user: dict = Depends(get_current_user)):
    minutes = await db.minutes.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return MinutesResponse(**minutes)

@api_router.delete("/minutes/{minutes_id}")
async def delete_minutes(minutes_id: str, user: dict = Depends(get_current_user)):
    result = await db.minutes.delete_one({"minutes_id": minutes_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return {"message": "Minutes deleted"}

# ==================== DISTRIBUTION ENDPOINTS ====================

@api_router.post("/distributions", response_model=DistributionResponse)
async def create_distribution(dist: DistributionCreate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": dist.trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    dist_id = f"dist_{uuid.uuid4().hex[:12]}"
    dist_doc = {
        "distribution_id": dist_id,
        "trust_id": dist.trust_id,
        "user_id": user["user_id"],
        "date": dist.date,
        "amount": dist.amount,
        "distribution_type": dist.distribution_type,
        "beneficiary": dist.beneficiary,
        "category": dist.category,
        "notes": dist.notes,
        "status": dist.status,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.distributions.insert_one(dist_doc)
    
    return DistributionResponse(**dist_doc)

@api_router.get("/distributions", response_model=List[DistributionResponse])
async def get_distributions(trust_id: Optional[str] = None, status: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    if status:
        query["status"] = status
    
    dists = await db.distributions.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return [DistributionResponse(**d) for d in dists]

@api_router.put("/distributions/{distribution_id}", response_model=DistributionResponse)
async def update_distribution(distribution_id: str, status: str, user: dict = Depends(get_current_user)):
    result = await db.distributions.update_one(
        {"distribution_id": distribution_id, "user_id": user["user_id"]},
        {"$set": {"status": status}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Distribution not found")
    
    dist = await db.distributions.find_one({"distribution_id": distribution_id}, {"_id": 0})
    return DistributionResponse(**dist)

@api_router.delete("/distributions/{distribution_id}")
async def delete_distribution(distribution_id: str, user: dict = Depends(get_current_user)):
    result = await db.distributions.delete_one({"distribution_id": distribution_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Distribution not found")
    return {"message": "Distribution deleted"}

# ==================== EXPENSE ENDPOINTS ====================

@api_router.post("/expenses", response_model=ExpenseResponse)
async def create_expense(expense: ExpenseCreate, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": expense.trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    expense_id = f"exp_{uuid.uuid4().hex[:12]}"
    expense_doc = {
        "expense_id": expense_id,
        "trust_id": expense.trust_id,
        "user_id": user["user_id"],
        "date": expense.date,
        "amount": expense.amount,
        "payee": expense.payee,
        "category": expense.category,
        "notes": expense.notes,
        "status": expense.status,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.expenses.insert_one(expense_doc)
    
    return ExpenseResponse(**expense_doc)

@api_router.get("/expenses", response_model=List[ExpenseResponse])
async def get_expenses(trust_id: Optional[str] = None, status: Optional[str] = None, user: dict = Depends(get_current_user)):
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    if status:
        query["status"] = status
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return [ExpenseResponse(**e) for e in expenses]

@api_router.put("/expenses/{expense_id}", response_model=ExpenseResponse)
async def update_expense(expense_id: str, status: str, user: dict = Depends(get_current_user)):
    result = await db.expenses.update_one(
        {"expense_id": expense_id, "user_id": user["user_id"]},
        {"$set": {"status": status}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    expense = await db.expenses.find_one({"expense_id": expense_id}, {"_id": 0})
    return ExpenseResponse(**expense)

@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user: dict = Depends(get_current_user)):
    result = await db.expenses.delete_one({"expense_id": expense_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"message": "Expense deleted"}

# ==================== GOVERNANCE HEALTH ENDPOINT ====================

@api_router.get("/governance/{trust_id}", response_model=GovernanceHealthResponse)
async def get_governance_health(trust_id: str, user: dict = Depends(get_current_user)):
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    health = await calculate_governance_score(trust_id, user["user_id"])
    return GovernanceHealthResponse(**health)

# ==================== ACTIVITY TIMELINE ====================

@api_router.get("/activity")
async def get_activity(trust_id: Optional[str] = None, limit: int = 20, user: dict = Depends(get_current_user)):
    """Get recent activity across all trusts or a specific trust"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    activities = []
    
    # Get recent minutes
    minutes = await db.minutes.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    for m in minutes:
        activities.append({
            "type": "minutes",
            "id": m["minutes_id"],
            "trust_id": m["trust_id"],
            "title": m["summary"],
            "entry_type": m["entry_type"],
            "date": m["date"],
            "created_at": m["created_at"]
        })
    
    # Get recent distributions
    dists = await db.distributions.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    for d in dists:
        activities.append({
            "type": "distribution",
            "id": d["distribution_id"],
            "trust_id": d["trust_id"],
            "title": f"${d['amount']:,.2f} to {d['beneficiary']}",
            "status": d["status"],
            "date": d["date"],
            "created_at": d["created_at"]
        })
    
    # Get recent expenses
    expenses = await db.expenses.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    for e in expenses:
        activities.append({
            "type": "expense",
            "id": e["expense_id"],
            "trust_id": e["trust_id"],
            "title": f"${e['amount']:,.2f} to {e['payee']}",
            "status": e["status"],
            "date": e["date"],
            "created_at": e["created_at"]
        })
    
    # Sort by created_at and limit
    activities.sort(key=lambda x: x["created_at"], reverse=True)
    return activities[:limit]

# ==================== CATEGORIES ====================

@api_router.get("/categories")
async def get_categories():
    """Get default categories for distributions and expenses"""
    return {
        "distribution_categories": [
            "Trust Distribution",
            "Living Expenses",
            "Education",
            "Medical",
            "Housing",
            "Emergency",
            "Gift",
            "Loan",
            "Other"
        ],
        "expense_categories": [
            "Administrative",
            "Legal",
            "Accounting",
            "Investment Management",
            "Property Maintenance",
            "Insurance",
            "Taxes",
            "Professional Fees",
            "Other"
        ],
        "distribution_types": [
            "trust_distribution",
            "loan",
            "gift"
        ]
    }

# ==================== DEMO DATA ====================

@api_router.post("/demo/seed")
async def seed_demo_data(user: dict = Depends(get_current_user)):
    """Create demo trust with sample data"""
    # Check if user already has trusts
    existing = await db.trusts.count_documents({"user_id": user["user_id"]})
    if existing > 0:
        return {"message": "User already has trusts", "seeded": False}
    
    # Create demo trust
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    
    trust_doc = {
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "name": "Smith Family Trust",
        "role": "Trustee",
        "review_cadence": "quarterly",
        "description": "Family trust established for education and living expenses",
        "created_at": now.isoformat()
    }
    await db.trusts.insert_one(trust_doc)
    
    # Create sample minutes
    minutes_data = [
        {
            "minutes_id": f"min_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "entry_type": "meeting",
            "date": (now - timedelta(days=15)).isoformat(),
            "participants": ["John Smith", "Jane Smith", "Robert Attorney"],
            "summary": "Q4 2025 Quarterly Review Meeting",
            "details": "Reviewed trust performance, discussed upcoming distributions for education expenses, and approved budget for next quarter.",
            "best_interest_rationale": "Regular quarterly review ensures proper oversight and alignment with beneficiary needs.",
            "created_at": (now - timedelta(days=15)).isoformat()
        },
        {
            "minutes_id": f"min_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "entry_type": "decision",
            "date": (now - timedelta(days=30)).isoformat(),
            "participants": ["John Smith", "Jane Smith"],
            "summary": "Approved Education Distribution",
            "details": "Approved distribution of $15,000 for spring semester tuition at State University.",
            "best_interest_rationale": "Education expenses are a primary purpose of the trust and support beneficiary's long-term success.",
            "created_at": (now - timedelta(days=30)).isoformat()
        }
    ]
    await db.minutes.insert_many(minutes_data)
    
    # Create sample distributions
    distributions_data = [
        {
            "distribution_id": f"dist_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "date": (now - timedelta(days=10)).isoformat(),
            "amount": 15000.00,
            "distribution_type": "trust_distribution",
            "beneficiary": "Emily Smith",
            "category": "Education",
            "notes": "Spring 2026 semester tuition",
            "status": "approved",
            "created_at": (now - timedelta(days=10)).isoformat()
        },
        {
            "distribution_id": f"dist_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "date": (now - timedelta(days=5)).isoformat(),
            "amount": 2500.00,
            "distribution_type": "trust_distribution",
            "beneficiary": "Emily Smith",
            "category": "Living Expenses",
            "notes": "Monthly living allowance",
            "status": "review",
            "created_at": (now - timedelta(days=5)).isoformat()
        }
    ]
    await db.distributions.insert_many(distributions_data)
    
    # Create sample expenses
    expenses_data = [
        {
            "expense_id": f"exp_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "date": (now - timedelta(days=20)).isoformat(),
            "amount": 750.00,
            "payee": "Anderson & Associates",
            "category": "Legal",
            "notes": "Annual trust review and documentation",
            "status": "approved",
            "created_at": (now - timedelta(days=20)).isoformat()
        },
        {
            "expense_id": f"exp_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user["user_id"],
            "date": (now - timedelta(days=3)).isoformat(),
            "amount": 350.00,
            "payee": "Smith CPA",
            "category": "Accounting",
            "notes": "Quarterly tax preparation",
            "status": "review",
            "created_at": (now - timedelta(days=3)).isoformat()
        }
    ]
    await db.expenses.insert_many(expenses_data)
    
    return {"message": "Demo data created", "seeded": True, "trust_id": trust_id}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
