"""
Cloud backup router — OAuth callbacks, connection management, manual trigger.

Endpoints:
  GET  /api/backup/oauth/connect    — initiate OAuth flow (returns auth_url)
  GET  /api/backup/oauth/callback    — OAuth callback from provider
  GET  /api/backup/status           — get backup connection + last backup status
  POST /api/backup/trigger          — trigger manual backup now
  DELETE /api/backup/disconnect     — revoke tokens, deactivate connection
"""
import os
import jwt
import secrets
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse
from urllib.parse import urlencode

from database import db
from dependencies import get_current_user
from services.backup_service import backup_user_vault
from services.backup_providers import get_provider

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cloud_backup"])

# OAuth provider configuration
OAUTH_CONFIG = {
    "google_drive": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
        "redirect_key": "GOOGLE_REDIRECT_URI",
    },
    "dropbox": {
        "auth_url": "https://www.dropbox.com/oauth2/authorize",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
        "scope": "files.content.write files.content.read",
        "client_id_env": "DROPBOX_CLIENT_ID",
        "client_secret_env": "DROPBOX_CLIENT_SECRET",
        "redirect_key": "DROPBOX_REDIRECT_URI",
    },
    "onedrive": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "Files.ReadWrite offline_access",
        "client_id_env": "MICROSOFT_CLIENT_ID",
        "client_secret_env": "MICROSOFT_CLIENT_SECRET",
        "redirect_key": "MICROSOFT_REDIRECT_URI",
    },
}


def _create_oauth_state(user_id: str, provider: str) -> str:
    """Create a JWT-signed OAuth state parameter to prevent CSRF."""
    return jwt.encode({
        "user_id": user_id,
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }, os.environ["JWT_SECRET"], algorithm="HS256")


def _verify_oauth_state(state: str) -> dict:
    """Verify and decode the OAuth state."""
    try:
        return jwt.decode(state, os.environ["JWT_SECRET"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="OAuth state expired. Please try again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid OAuth state. Please try again.")


@router.get("/backup/oauth/connect")
async def initiate_oauth(provider: str, user: dict = Depends(get_current_user)):
    """Initiate OAuth flow — returns the provider's authorization URL."""
    if provider not in OAUTH_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    config = OAUTH_CONFIG[provider]
    client_id = os.environ.get(config["client_id_env"])
    redirect_uri = os.environ.get(config["redirect_key"])

    if not client_id or not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail=f"Cloud backup is not configured for {provider}. Please contact support."
        )

    state = _create_oauth_state(user["user_id"], provider)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
        "access_type": "offline",
        "prompt": "consent",  # Force consent to get refresh_token
    }

    auth_url = f"{config['auth_url']}?{urlencode(params)}"
    return {"auth_url": auth_url}


@router.get("/backup/oauth/callback")
async def oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    provider: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle OAuth callback from cloud provider."""
    if error:
        logger.warning(f"OAuth callback error: {error}")
        return RedirectResponse(url="/settings?backup_error=" + error)

    if not code or not state:
        return RedirectResponse(url="/settings?backup_error=missing_params")

    # Verify state JWT
    state_data = _verify_oauth_state(state)
    user_id = state_data["user_id"]
    provider_name = state_data["provider"]

    # Determine provider from state (not query param, for security)
    if provider_name not in OAUTH_CONFIG:
        return RedirectResponse(url="/settings?backup_error=invalid_provider")

    config = OAUTH_CONFIG[provider_name]
    client_id = os.environ.get(config["client_id_env"])
    client_secret = os.environ.get(config["client_secret_env"])
    redirect_uri = os.environ.get(config["redirect_key"])

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(config["token_url"], data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        })

    if token_resp.status_code != 200:
        logger.error(f"Token exchange failed: {token_resp.text}")
        return RedirectResponse(url="/settings?backup_error=token_exchange_failed")

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)

    if not access_token:
        return RedirectResponse(url="/settings?backup_error=no_access_token")

    if not refresh_token:
        # Some providers don't return refresh_token on re-auth.
        # Update existing connection's access token only.
        existing = await db.cloud_backup_connections.find_one({"user_id": user_id, "provider": provider_name})
        if existing and existing.get("refresh_token"):
            await db.cloud_backup_connections.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "access_token": access_token,
                    "token_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
                    "is_active": True,
                }}
            )
            return RedirectResponse(url="/vault?backup_connected=true")
        return RedirectResponse(url="/settings?backup_error=no_refresh_token")

    # Store connection in DB
    now_iso = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    # Upsert — one connection per provider per user
    await db.cloud_backup_connections.update_one(
        {"user_id": user_id, "provider": provider_name},
        {
            "$set": {
                "user_id": user_id,
                "provider": provider_name,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires_at": expires_at,
                "connected_at": now_iso,
                "backup_frequency": "weekly",
                "last_backup_at": None,
                "last_backup_status": "connected",
                "last_backup_error": None,
                "last_backup_doc_count": 0,
                "backup_folder_id": None,
                "is_active": True,
            }
        },
        upsert=True,
    )

    logger.info(f"Cloud backup connected: user={user_id}, provider={provider_name}")
    return RedirectResponse(url="/vault?backup_connected=true")


@router.get("/backup/status")
async def get_backup_status(user: dict = Depends(get_current_user)):
    """Get backup connection status for the current user."""
    connections = []
    cursor = db.cloud_backup_connections.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "access_token": 0, "refresh_token": 0}  # Never expose tokens
    )
    async for conn in cursor:
        connections.append(conn)

    # Count documents that have been backed up
    backed_up_count = await db.vault_documents.count_documents({
        "user_id": user["user_id"],
        "last_backup_at": {"$ne": None}
    })
    total_docs = await db.vault_documents.count_documents({
        "user_id": user["user_id"],
        "file_content": {"$ne": None}
    })

    return {
        "connections": connections,
        "stats": {
            "total_documents": total_docs,
            "backed_up_documents": backed_up_count,
        }
    }


@router.post("/backup/trigger")
async def trigger_backup(user: dict = Depends(get_current_user)):
    """Trigger a manual backup for the current user."""
    conn = await db.cloud_backup_connections.find_one(
        {"user_id": user["user_id"], "is_active": True}
    )
    if not conn:
        raise HTTPException(status_code=400, detail="No active cloud backup connection. Please connect a provider first.")

    try:
        result = await backup_user_vault(user["user_id"], conn)
        return {
            "message": "Backup complete",
            "result": result,
        }
    except Exception as e:
        logger.error(f"Manual backup failed for user {user['user_id']}: {e}")
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.delete("/backup/disconnect")
async def disconnect_backup(provider: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Disconnect cloud backup — revoke tokens and remove connection."""
    query = {"user_id": user["user_id"]}
    if provider:
        query["provider"] = provider

    conn = await db.cloud_backup_connections.find_one(query)
    if not conn:
        raise HTTPException(status_code=404, detail="No backup connection found")

    # Revoke token at provider
    try:
        prov = get_provider(conn["provider"])
        await prov.revoke_token(conn.get("refresh_token", ""))
    except Exception as e:
        logger.warning(f"Token revocation failed (continuing with cleanup): {e}")

    # Remove connection record
    await db.cloud_backup_connections.delete_one({"_id": conn["_id"]})

    # Clear backup tracking from vault documents
    await db.vault_documents.update_many(
        {"user_id": user["user_id"]},
        {"$unset": {"last_backup_at": "", "backup_path": ""}}
    )

    logger.info(f"Cloud backup disconnected: user={user['user_id']}, provider={conn['provider']}")
    return {"message": "Cloud backup disconnected. Your files remain in your cloud storage."}