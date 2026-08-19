# Preferences router - handles notification and user preferences
from fastapi import APIRouter, HTTPException, Depends

from database import db
from dependencies import get_current_user, get_subscription_state
from models import NotificationPreferencesUpdate, UserPreferencesUpdate

# Plan types that qualify for watermark removal when status is active/trialing
_WATERMARK_ELIGIBLE_PLAN_TYPES = {"trustee", "estate", "advisor", "forever_free"}


async def _can_hide_watermark(user_id: str) -> bool:
    """Return True if the user's subscription qualifies for watermark removal.

    Qualifies when:
      - plan_type is trustee/estate/advisor/forever_free AND status is active/trialing, OR
      - the account is gifted (is_gifted == True)
    """
    try:
        state = await get_subscription_state(user_id)
    except Exception:
        return False
    if getattr(state, "is_gifted", False):
        return True
    if state.plan_type in _WATERMARK_ELIGIBLE_PLAN_TYPES and state.status in ("active", "trialing"):
        return True
    return False

router = APIRouter(tags=["preferences"])


# ==================== NOTIFICATION PREFERENCES ====================

@router.get("/notifications/preferences")
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


@router.put("/notifications/preferences")
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


# ==================== USER PREFERENCES ====================

@router.get("/user/preferences")
async def get_user_preferences(user: dict = Depends(get_current_user)):
    """Get user preferences (watermark settings, etc.)"""
    prefs = await db.user_preferences.find_one(
        {"user_id": user["user_id"]}, 
        {"_id": 0}
    )
    
    if not prefs:
        # No saved preference yet — auto-enable watermark removal for eligible
        # subscribers (paid plans active/trialing, forever_free, or gifted).
        hide_watermark = await _can_hide_watermark(user["user_id"])
        return {
            "user_id": user["user_id"],
            "hide_watermark": hide_watermark,
            "admin_access_locked": False
        }
    
    return prefs


@router.put("/user/preferences")
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
        if not await _can_hide_watermark(user["user_id"]):
            raise HTTPException(
                status_code=403, 
                detail="Watermark removal is only available for paid, gift, and free-forever accounts"
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
