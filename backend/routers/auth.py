# Auth router - handles authentication, profile, notifications, preferences
from fastapi import APIRouter, HTTPException, Depends, Request, Response, BackgroundTasks
from datetime import datetime, timezone, timedelta
import uuid
import secrets
import httpx
import os
import logging

from database import db
from dependencies import (
    get_current_user, hash_password, verify_password, 
    create_jwt_token, JWT_EXPIRATION_HOURS
)
from models import (
    UserCreate, UserLogin, UserResponse, ProfileUpdate,
    PasswordResetRequest, PasswordResetConfirm,
    NotificationPreferences, NotificationPreferencesUpdate,
    UserPreferencesUpdate
)
from email_service import email_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserResponse)
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


@router.post("/login")
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


@router.post("/forgot-password")
async def forgot_password(request: PasswordResetRequest, background_tasks: BackgroundTasks):
    user = await db.users.find_one({"email": request.email}, {"_id": 0})
    
    if not user:
        return {"message": "If an account exists with this email, you will receive a password reset link."}
    
    if not user.get("password_hash"):
        return {"message": "If an account exists with this email, you will receive a password reset link."}
    
    reset_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    await db.password_resets.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "token": reset_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    frontend_url = os.environ['FRONTEND_URL']
    reset_url = f"{frontend_url}/reset-password?token={reset_token}"
    
    background_tasks.add_task(
        email_service.send_password_reset_email,
        to_email=user["email"],
        user_name=user.get("name", ""),
        reset_url=reset_url
    )
    
    return {"message": "If an account exists with this email, you will receive a password reset link."}


@router.post("/reset-password")
async def reset_password(request: PasswordResetConfirm):
    reset_record = await db.password_resets.find_one({"token": request.token}, {"_id": 0})
    
    if not reset_record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    
    expires_at = datetime.fromisoformat(reset_record["expires_at"].replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        await db.password_resets.delete_one({"token": request.token})
        raise HTTPException(status_code=400, detail="Reset token has expired. Please request a new one.")
    
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    new_hash = hash_password(request.new_password)
    await db.users.update_one(
        {"user_id": reset_record["user_id"]},
        {"$set": {"password_hash": new_hash}}
    )
    
    await db.password_resets.delete_one({"token": request.token})
    await db.user_sessions.delete_many({"user_id": reset_record["user_id"]})
    
    return {"message": "Password has been reset successfully. Please log in with your new password."}


@router.get("/verify-reset-token")
async def verify_reset_token(token: str):
    reset_record = await db.password_resets.find_one({"token": token}, {"_id": 0})
    
    if not reset_record:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    
    expires_at = datetime.fromisoformat(reset_record["expires_at"].replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token has expired")
    
    return {"valid": True}


@router.post("/session")
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


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        user_id=user["user_id"],
        email=user["email"],
        name=user["name"],
        picture=user.get("picture"),
        created_at=user.get("created_at", "")
    )


@router.put("/profile")
async def update_profile(profile: ProfileUpdate, user: dict = Depends(get_current_user)):
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


@router.post("/logout")
async def logout(request: Request, response: Response):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}


# Notifications router (will be mounted separately)
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])


@notifications_router.get("/preferences")
async def get_notification_preferences(user: dict = Depends(get_current_user)):
    prefs = await db.notification_preferences.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    if not prefs:
        prefs = {
            "user_id": user["user_id"],
            "minutes_created": True,
            "distribution_created": True,
            "distribution_approved": True,
            "task_reminders": True,
            "task_overdue": True,
            "subscription_updates": True,
            "weekly_digest": False
        }
    
    return prefs


@notifications_router.put("/preferences")
async def update_notification_preferences(
    update: NotificationPreferencesUpdate,
    user: dict = Depends(get_current_user)
):
    update_fields = {}
    for field, value in update.model_dump(exclude_unset=True).items():
        if value is not None:
            update_fields[field] = value
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.notification_preferences.update_one(
        {"user_id": user["user_id"]},
        {"$set": update_fields},
        upsert=True
    )
    
    return {"message": "Notification preferences updated"}


# User preferences router (will be mounted separately)
user_prefs_router = APIRouter(prefix="/user", tags=["user"])


@user_prefs_router.get("/preferences")
async def get_user_preferences(user: dict = Depends(get_current_user)):
    prefs = await db.user_preferences.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    if not prefs:
        prefs = {
            "user_id": user["user_id"],
            "hide_watermark": False
        }
    
    return prefs


@user_prefs_router.put("/preferences")
async def update_user_preferences(
    update: UserPreferencesUpdate,
    user: dict = Depends(get_current_user)
):
    update_fields = {}
    for field, value in update.model_dump(exclude_unset=True).items():
        if value is not None:
            update_fields[field] = value
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.user_preferences.update_one(
        {"user_id": user["user_id"]},
        {"$set": update_fields},
        upsert=True
    )
    
    prefs = await db.user_preferences.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    return {
        "message": "Preferences updated",
        "preferences": prefs
    }
