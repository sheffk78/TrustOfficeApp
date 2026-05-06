"""
TrustOffice API - Main Server Entry Point
Reduced from ~7600 lines to ~350 lines through modular refactoring (95% reduction)

All business logic has been migrated to routers/:
- auth.py, trusts.py, entities.py, tasks.py, trust_units.py
- minutes.py, schedule_a.py, distributions.py, benevolence.py
- compensation.py, governance.py, subscriptions.py, exports.py
- preferences.py, email.py, background_jobs.py, categories.py
- beneficiaries.py, demo.py

This file contains only:
- FastAPI app configuration
- CORS middleware
- Subscription middleware (read-only enforcement)
- Router registration
- Database index creation
- Background task lifecycle
"""
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
import jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Import background tasks
from background_tasks import background_runner

# Import subscription state helper from dependencies
from dependencies import (
    get_subscription_state,
    READ_ONLY_ERROR_MESSAGE,
    READ_ONLY_ERROR_CODE,
)

# Import all routers
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
from routers.preferences import router as preferences_router
from routers.email import router as email_router
from routers.background_jobs import router as background_jobs_router
from routers.categories import router as categories_router
from routers.beneficiaries import router as beneficiaries_router
from routers.demo import router as demo_router
from routers.ai import router as ai_router
from routers.guided_minutes import router as guided_minutes_router
from routers.referrals import router as referrals_router
from routers.admin import router as admin_router
from routers.contact import router as contact_router
from routers.admin_api import router as admin_api_router
from routers.transactions import router as transactions_router
from routers.alerts import router as alerts_router
from routers.audit_defense import router as audit_defense_router
from routers.tax_calendar import router as tax_calendar_router

# Import security middleware
from security import (
    RateLimitMiddleware,
    RateLimitConfig,
    SecurityHeadersMiddleware,
    InputSanitizer
)

# MongoDB connection with pool configuration
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=20,
    minPoolSize=5,
    maxIdleTimeMS=30000,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required. Set it in Railway env vars.")
JWT_ALGORITHM = "HS256"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the main app
app = FastAPI(title="TrustOffice API")

# ==================== SUBSCRIPTION MIDDLEWARE ====================

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
        
        # If no token, let the endpoint handle authentication
        if not token:
            return await call_next(request)
        
        # Decode token to get user_id
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("user_id")
            if not user_id:
                return await call_next(request)
        except jwt.InvalidTokenError:
            return await call_next(request)
        
        # Get subscription state
        state = await get_subscription_state(user_id)
        
        # Allow all GET requests (read-only access)
        if method == "GET":
            return await call_next(request)
        
        # For write operations, check if subscription is active
        if method in WRITE_METHODS:
            # Skip check for write-exempt paths (subscription management, auth)
            if path in WRITE_EXEMPT_PATHS:
                return await call_next(request)
            
            # If subscription is inactive and user is in read-only mode, block write
            if state.is_read_only:
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
        
        return await call_next(request)


# ==================== MIDDLEWARE & ROUTER REGISTRATION ====================
# NOTE: In FastAPI/Starlette, middleware is LIFO — the LAST added executes FIRST.
# CORS must be outermost (added last) so it handles preflight before other middleware.

# Security headers middleware (OWASP recommendations)
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware, config=RateLimitConfig())

# Subscription enforcement middleware
app.add_middleware(SubscriptionMiddleware)

# CORS middleware — added LAST so it executes FIRST (outermost)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(auth_router, prefix="/api")
app.include_router(trusts_router, prefix="/api")
app.include_router(entities_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(trust_units_router, prefix="/api")
app.include_router(minutes_router, prefix="/api")
app.include_router(schedule_a_router, prefix="/api")
app.include_router(distributions_router, prefix="/api")
app.include_router(benevolence_router, prefix="/api")
app.include_router(compensation_router, prefix="/api")
app.include_router(governance_router, prefix="/api")
app.include_router(subscriptions_router, prefix="/api")
app.include_router(exports_router, prefix="/api")
app.include_router(preferences_router, prefix="/api")
app.include_router(email_router, prefix="/api")
app.include_router(background_jobs_router, prefix="/api")
app.include_router(categories_router, prefix="/api")
app.include_router(beneficiaries_router, prefix="/api")
app.include_router(demo_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(guided_minutes_router, prefix="/api")
app.include_router(referrals_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(contact_router, prefix="/api")
app.include_router(admin_api_router, prefix="/api")
app.include_router(transactions_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(audit_defense_router, prefix="/api")
app.include_router(tax_calendar_router, prefix="/api")


# ==================== HEALTH CHECK ====================

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and load balancers"""
    try:
        await db.command("ping")
        return {"status": "ok", "service": "trustoffice-api", "db": "connected"}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "service": "trustoffice-api", "db": f"error: {str(e)[:100]}"}
        )


# ==================== LIFECYCLE EVENTS ====================

@app.on_event("startup")
async def startup_event():
    """Start background task runner and create indexes on app startup"""
    startup_errors = []
    
    try:
        await background_runner.start()
        logger.info("Background task runner started successfully")
    except Exception as e:
        logger.error(f"Failed to start background runner: {e}")
        startup_errors.append(f"background_runner: {e}")
    
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
        
        # Dismissed insights indexes
        await db.dismissed_insights.create_index([("trust_id", 1), ("user_id", 1)])
        await db.dismissed_insights.create_index([("trust_id", 1), ("criterion_name", 1)], unique=True)
        
        # Session indexes with TTL
        await db.user_sessions.create_index("session_token", unique=True)
        await db.user_sessions.create_index("user_id")
        
        # Password reset with TTL (auto-expire after 2 hours)
        await db.password_resets.create_index("token", unique=True)
        await db.password_resets.create_index("user_id", unique=True)
        
        # Audit logs
        await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_logs.create_index("audit_id", unique=True)
        
        # Referral indexes
        await db.referral_codes.create_index("user_id", unique=True)
        await db.referral_codes.create_index("code", unique=True)
        await db.referral_tracking.create_index("referrer_user_id")
        await db.referral_tracking.create_index("referee_user_id", unique=True)
        
        # JWT revocation indexes (auto-cleanup via TTL)
        await db.jwt_revocations.create_index("jti")
        await db.jwt_revocations.create_index("user_id")
        await db.jwt_revocations.create_index("expires_at", expireAfterSeconds=0)  # Auto-delete expired revocations
        
        # Admin audit log with TTL (90 days)
        await db.admin_audit_log.create_index([("user_id", 1), ("timestamp", -1)])
        await db.admin_audit_log.create_index("timestamp", expireAfterSeconds=7776000)  # 90 days
        
        # AI usage tracking indexes (for cost protection)
        await db.ai_usage_tracking.create_index([("user_id", 1), ("endpoint", 1), ("date", 1)], unique=True)
        await db.ai_usage_tracking.create_index("date")  # For monthly aggregation queries
        
        # AI suggestion cache indexes (1hr TTL)
        await db.ai_suggestion_cache.create_index([("user_id", 1), ("trust_id", 1)], unique=True)
        await db.ai_suggestion_cache.create_index("cached_at")  # For cache expiry queries
        
        # Admin user index
        await db.users.create_index("is_admin", sparse=True)
        
        # Transaction ledger indexes
        await db.transactions.create_index([("trust_id", 1), ("user_id", 1), ("date", -1)])
        await db.transactions.create_index([("entity_id", 1), ("user_id", 1)])
        await db.transactions.create_index("transaction_id", unique=True)
        await db.transaction_audit_log.create_index("transaction_id")
        await db.transaction_audit_log.create_index("audit_id", unique=True)
        
        # Separation alerts indexes
        await db.separation_alerts.create_index([("trust_id", 1), ("user_id", 1), ("status", 1)])
        await db.separation_alerts.create_index([("transaction_id", 1), ("alert_type", 1)])
        await db.separation_alerts.create_index("alert_id", unique=True)
        await db.alert_audit_log.create_index("alert_id")
        await db.alert_audit_log.create_index("audit_id", unique=True)
        await db.personal_vendors.create_index("user_id")
        
        logger.info("Database indexes created/verified successfully")
        
        # Ensure primary admin account exists
        await ensure_primary_admin()
        
    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")
        startup_errors.append(f"indexes: {e}")
    
    if startup_errors:
        logger.warning(f"App started with {len(startup_errors)} errors: {startup_errors}")


async def ensure_primary_admin():
    """Ensure the primary admin account (contact@trustoffice.app) exists."""
    import uuid
    import bcrypt
    from datetime import datetime, timezone
    
    primary_admin_email = "contact@trustoffice.app"
    default_password = os.environ.get('ADMIN_DEFAULT_PASSWORD')
    if not default_password:
        logger.error("ADMIN_DEFAULT_PASSWORD not set — cannot ensure admin account")
        return
    
    existing = await db.users.find_one({"email": primary_admin_email}, {"_id": 0})
    
    if existing:
        # Ensure admin flag is set and password exists
        updates = {}
        if not existing.get("is_admin"):
            updates["is_admin"] = True
        if not existing.get("password_hash"):
            updates["password_hash"] = bcrypt.hashpw(default_password.encode(), bcrypt.gensalt()).decode()
        
        if updates:
            await db.users.update_one(
                {"email": primary_admin_email},
                {"$set": updates}
            )
            logger.info(f"Updated {primary_admin_email} with admin status and/or password")
    else:
        # Create admin account with password
        now = datetime.now(timezone.utc)
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        await db.users.insert_one({
            "user_id": user_id,
            "email": primary_admin_email,
            "name": "TrustOffice Admin",
            "password_hash": bcrypt.hashpw(default_password.encode(), bcrypt.gensalt()).decode(),
            "is_admin": True,
            "created_at": now.isoformat()
        })
        
        # Create forever_free subscription
        await db.subscriptions.insert_one({
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "plan_type": "forever_free",
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        })
        
        # Initialize onboarding (mark as complete for admin)
        await db.user_onboarding.insert_one({
            "user_id": user_id,
            "entities_confirmed": True,
            "calendar_set": True,
            "minutes_generated": True,
            "distribution_logged": True,
            "checklist_dismissed": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        })
        
        logger.info(f"Created primary admin account: {primary_admin_email}")


@app.on_event("shutdown")
async def shutdown_db_client():
    """Stop background tasks and close database connection"""
    await background_runner.stop()
    client.close()
