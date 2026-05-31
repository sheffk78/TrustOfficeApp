# Auth router - handles authentication, registration, password reset, and OAuth
from fastapi import APIRouter, HTTPException, Depends, Response, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets
import logging
import os
import httpx
import re
import urllib.parse

from database import db
from dependencies import get_current_user, hash_password, verify_password, create_jwt_token, JWT_EXPIRATION_HOURS
from models import UserCreate, UserLogin, UserResponse, PasswordResetRequest, PasswordResetConfirm, ProfileUpdate
from email_service import email_service
from security import InputSanitizer
from mailercloud_service import add_to_trial_list

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# ==================== INPUT VALIDATION HELPERS ====================

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements.
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    if not re.search(r'[A-Za-z]', password):
        return False, "Password must contain at least one letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, ""


def validate_email_format(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email)) and len(email) <= 254


def sanitize_name(name: str) -> str:
    """Sanitize user name input"""
    # Remove HTML, limit length, strip whitespace
    name = InputSanitizer.sanitize_html(name)
    name = name.strip()[:100]
    return name


# ==================== REGISTRATION & LOGIN ====================

@router.post("/auth/register", response_model=UserResponse)
async def register(user: UserCreate, background_tasks: BackgroundTasks):
    """Register a new user with email/password"""
    
    # Validate email format
    if not validate_email_format(user.email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    # Sanitize and validate inputs
    email = user.email.lower().strip()
    name = sanitize_name(user.name)
    
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    
    # Validate password strength
    is_valid, error_msg = validate_password_strength(user.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user_doc = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "password_hash": hash_password(user.password),
        "picture": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "wp_ref": user.wp_ref or None,
        "wp_trust_name": user.wp_trust_name or None,
    }
    
    await db.users.insert_one(user_doc)
    
    # Initialize onboarding state
    await db.user_onboarding.insert_one({
        "user_id": user_id,
        "formation_date_added": False,
        "ein_entered": False,
        "trust_doc_uploaded": False,
        "ein_doc_uploaded": False,
        "beneficiaries_added": False,
        "assets_added": False,
        "minutes_generated": False,
        "calendar_set": False,
        "checklist_dismissed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Track referral if code provided
    if user.referral_code:
        try:
            from routers.referrals import track_referral
            await track_referral(
                referee_user_id=user_id,
                referral_code=user.referral_code
            )
            logger.info(f"Tracked referral for new user {user_id} with code {user.referral_code}")
        except Exception as e:
            logger.error(f"Failed to track referral: {e}")
            # Don't fail registration if referral tracking fails
    
    # Send welcome email in background
    background_tasks.add_task(
        email_service.send_welcome_email,
        to_email=user.email,
        user_name=user.name
    )
    
    # Note: No longer adding to Mailercloud trial list — trial model removed
    
    return UserResponse(
        user_id=user_id,
        email=user.email,
        name=user.name,
        picture=None,
        created_at=user_doc["created_at"]
    )


@router.post("/auth/login")
async def login(user: UserLogin, response: Response, background_tasks: BackgroundTasks):
    """Login with email/password"""
    # Validate email format
    if not validate_email_format(user.email):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    email = user.email.lower().strip()
    
    user_doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not user_doc:
        # Use generic message to prevent email enumeration
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user_doc.get("password_hash"):
        raise HTTPException(status_code=401, detail="Please use Google login")
    
    if not verify_password(user.password, user_doc["password_hash"]):
        # Log failed login attempt (for security monitoring)
        logger.warning(f"Failed login attempt for email: {email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Auto-grant admin status for primary admin email
    PRIMARY_ADMIN_EMAIL = "contact@trustoffice.app"
    if email == PRIMARY_ADMIN_EMAIL:
        # Always ensure admin status and forever_free subscription
        if not user_doc.get("is_admin"):
            await db.users.update_one(
                {"user_id": user_doc["user_id"]},
                {"$set": {"is_admin": True}}
            )
        # Always ensure forever_free active subscription
        await db.subscriptions.update_one(
            {"user_id": user_doc["user_id"]},
            {"$set": {
                "plan_type": "forever_free", 
                "status": "active",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        logger.info(f"Ensured admin status and subscription for {email}")
    
    token = create_jwt_token(user_doc["user_id"], user_doc["email"])
    
    # Track last login and check if this is the first login (for WingPoint webhook)
    now_iso = datetime.now(timezone.utc).isoformat()
    previous_login = user_doc.get("last_login")
    
    # Update last_login timestamp
    await db.users.update_one(
        {"user_id": user_doc["user_id"]},
        {"$set": {"last_login": now_iso}}
    )
    
    # Fire first_login webhook for WingPoint-provisioned users (only on first login)
    # A first login = no previous last_login timestamp
    if not previous_login:
        try:
            from routers.external import fire_activation_webhook
            background_tasks.add_task(fire_activation_webhook, user_doc["user_id"], "first_login")
        except Exception as e:
            logger.warning(f"Failed to queue first_login webhook for {user_doc['user_id']}: {e}")
    
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=JWT_EXPIRATION_HOURS * 3600,
        path="/"
    )
    
    return {
        "token": token,
        "user": {
            "user_id": user_doc["user_id"],
            "email": user_doc["email"],
            "name": user_doc["name"],
            "picture": user_doc.get("picture"),
            "is_admin": user_doc.get("is_admin", False) or email == PRIMARY_ADMIN_EMAIL
        }
    }


# ==================== PASSWORD RESET ====================

@router.post("/auth/forgot-password")
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
    frontend_url = os.environ.get('FRONTEND_URL', '')
    reset_url = f"{frontend_url}/reset-password?token={reset_token}"
    
    background_tasks.add_task(
        email_service.send_password_reset_email,
        to_email=user["email"],
        user_name=user.get("name", ""),
        reset_url=reset_url
    )
    
    return {"message": "If an account exists with this email, you will receive a password reset link."}


@router.post("/auth/reset-password")
async def reset_password(request: PasswordResetConfirm, background_tasks: BackgroundTasks):
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
    
    # Validate password strength (same requirements as registration)
    is_valid, error_msg = validate_password_strength(request.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
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
    
    # Revoke all existing JWT tokens for this user
    await db.jwt_revocations.insert_one({
        "user_id": reset_record["user_id"],
        "jti": "all",  # Special marker: revoke ALL tokens for this user
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()  # Auto-cleanup after max token lifetime
    })
    
    # Fire activation webhook for WingPoint-provisioned users (fire-and-forget)
    try:
        from routers.external import fire_activation_webhook
        background_tasks.add_task(fire_activation_webhook, reset_record["user_id"], "password_set")
    except Exception as e:
        logger.warning(f"Failed to queue password_set webhook for {reset_record['user_id']}: {e}")
    
    return {"message": "Password has been reset successfully. Please log in with your new password."}


@router.get("/auth/verify-reset-token")
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


# ==================== OAUTH / SESSION ====================

@router.post("/auth/session")
async def exchange_session(request: Request, response: Response):
    """Exchange a one-time authorization code for a JWT token.
    
    This replaces the old JWT-in-URL pattern. The OAuth callback now generates
    a short-lived auth code that the frontend exchanges for the actual JWT.
    """
    body = await request.json()
    code = body.get("code")
    
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    
    # Look up the auth code
    auth_record = await db.oauth_auth_codes.find_one({"code": code})
    if not auth_record:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")
    
    # Check expiration
    expires_at = datetime.fromisoformat(auth_record["expires_at"].replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        await db.oauth_auth_codes.delete_one({"code": code})
        raise HTTPException(status_code=400, detail="Authorization code has expired")
    
    # Delete the code (one-time use)
    await db.oauth_auth_codes.delete_one({"code": code})
    
    # Return the JWT and user info
    user_doc = await db.users.find_one({"user_id": auth_record["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found")
    
    jwt_token = auth_record["jwt_token"]
    
    # Also set the session cookie
    response.set_cookie(
        key="session_token",
        value=auth_record["session_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/"
    )
    
    PRIMARY_ADMIN_EMAIL = "contact@trustoffice.app"
    is_admin = user_doc.get("is_admin", False) or user_doc.get("email", "").lower() == PRIMARY_ADMIN_EMAIL
    
    return {
        "token": jwt_token,
        "user": {
            "user_id": user_doc["user_id"],
            "email": user_doc["email"],
            "name": user_doc["name"],
            "picture": user_doc.get("picture"),
            "is_admin": is_admin
        }
    }


# ==================== USER PROFILE ====================

@router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user profile"""
    PRIMARY_ADMIN_EMAIL = "contact@trustoffice.app"
    is_admin = user.get("is_admin", False) or user.get("email", "").lower() == PRIMARY_ADMIN_EMAIL
    
    return UserResponse(
        user_id=user["user_id"],
        email=user["email"],
        name=user["name"],
        picture=user.get("picture"),
        created_at=user.get("created_at", ""),
        is_admin=is_admin
    )


@router.put("/auth/profile")
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


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout and clear session"""
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}



# ==================== CUSTOM GOOGLE OAUTH ====================

@router.get("/auth/google/login")
async def google_login(request: Request):
    """
    Initiate Google OAuth flow.
    Redirects user to Google's consent screen with TrustOffice branding.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    
    # Get the redirect URL from query params (where to go after successful auth)
    redirect_after = request.query_params.get("redirect", "/onboarding")
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state with redirect info (expires in 10 minutes)
    await db.oauth_states.update_one(
        {"state": state},
        {"$set": {
            "state": state,
            "redirect_after": redirect_after,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        }},
        upsert=True
    )
    
    # Build Google OAuth URL
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account"
    }
    
    auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    return RedirectResponse(url=auth_url)


@router.get("/auth/google/callback")
async def google_callback(request: Request, response: Response, code: str = None, state: str = None, error: str = None):
    """
    Handle Google OAuth callback.
    Exchanges authorization code for tokens, fetches user info, and creates/updates user.
    """
    frontend_url = os.environ.get('FRONTEND_URL', '')
    
    # Handle OAuth errors
    if error:
        logger.error(f"Google OAuth error: {error}")
        return RedirectResponse(url=f"{frontend_url}/login?error=oauth_failed")
    
    if not code or not state:
        return RedirectResponse(url=f"{frontend_url}/login?error=missing_params")
    
    # Verify state token
    state_record = await db.oauth_states.find_one({"state": state}, {"_id": 0})
    if not state_record:
        logger.warning(f"Invalid OAuth state: {state}")
        return RedirectResponse(url=f"{frontend_url}/login?error=invalid_state")
    
    # Check if state expired
    expires_at = datetime.fromisoformat(state_record["expires_at"].replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        await db.oauth_states.delete_one({"state": state})
        return RedirectResponse(url=f"{frontend_url}/login?error=state_expired")
    
    redirect_after = state_record.get("redirect_after", "/onboarding")
    
    # Delete used state
    await db.oauth_states.delete_one({"state": state})
    
    try:
        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": GOOGLE_REDIRECT_URI
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if token_response.status_code != 200:
                logger.error(f"Token exchange failed: status={token_response.status_code}")
                return RedirectResponse(url=f"{frontend_url}/login?error=token_exchange_failed")
            
            tokens = token_response.json()
            access_token = tokens.get("access_token")
            
            if not access_token:
                return RedirectResponse(url=f"{frontend_url}/login?error=no_access_token")
            
            # Fetch user info from Google
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if userinfo_response.status_code != 200:
                logger.error(f"Failed to fetch user info: status={userinfo_response.status_code}")
                return RedirectResponse(url=f"{frontend_url}/login?error=userinfo_failed")
            
            google_user = userinfo_response.json()
        
        email = google_user.get("email")
        if not email:
            return RedirectResponse(url=f"{frontend_url}/login?error=no_email")
        
        # Check if user exists
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user["user_id"]
            # Update user with latest Google info
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "name": google_user.get("name", existing_user.get("name")),
                    "picture": google_user.get("picture", existing_user.get("picture")),
                    "google_id": google_user.get("id"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        else:
            # Create new user
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            user_doc = {
                "user_id": user_id,
                "email": email,
                "name": google_user.get("name", "User"),
                "picture": google_user.get("picture"),
                "google_id": google_user.get("id"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.users.insert_one(user_doc)
            
            # Initialize onboarding state for new users
            await db.user_onboarding.insert_one({
                "user_id": user_id,
                "formation_date_added": False,
                "ein_entered": False,
                "trust_doc_uploaded": False,
                "ein_doc_uploaded": False,
                "beneficiaries_added": False,
                "assets_added": False,
                "minutes_generated": False,
                "calendar_set": False,
                "checklist_dismissed": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })
            
            # Send welcome email
            try:
                await email_service.send_welcome_email(
                    to_email=email,
                    user_name=google_user.get("name", "User")
                )
            except Exception as e:
                logger.error(f"Failed to send welcome email: {e}")
            
            # Note: No longer adding Google OAuth user to Mailercloud trial list — trial model removed
            # add_to_trial_list call removed
        
        # Generate JWT token
        jwt_token = create_jwt_token(user_id, email)
        
        # Create session
        session_token = secrets.token_urlsafe(32)
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
        
        # Security: Use a one-time authorization code instead of passing JWT in the URL.
        # The frontend exchanges this code for the JWT via POST /auth/session/exchange.
        auth_code = secrets.token_urlsafe(48)
        auth_code_expires = datetime.now(timezone.utc) + timedelta(minutes=2)
        
        await db.oauth_auth_codes.insert_one({
            "code": auth_code,
            "jwt_token": jwt_token,
            "user_id": user_id,
            "session_token": session_token,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": auth_code_expires.isoformat(),
        })
        
        # Set session cookie
        response = RedirectResponse(url=f"{frontend_url}/auth/callback?code={auth_code}&redirect={urllib.parse.quote(redirect_after)}")
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 3600,
            path="/"
        )
        
        logger.info(f"Google OAuth successful for user {user_id} ({email})")
        
        return response
        
    except httpx.RequestError as e:
        logger.error(f"HTTP error during Google OAuth: {e}")
        return RedirectResponse(url=f"{frontend_url}/login?error=network_error")
    except Exception as e:
        logger.error(f"Unexpected error during Google OAuth: {e}")
        return RedirectResponse(url=f"{frontend_url}/login?error=unexpected_error")
