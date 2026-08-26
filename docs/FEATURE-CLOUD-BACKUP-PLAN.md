# Feature: Automatic Cloud Backup for Vault

**Status:** Design Plan · August 25, 2026
**Author:** Kit
**Sponsor:** Kenneth Kohler

---

## Summary

Users can connect their Dropbox, Google Drive, or OneDrive account and have their TrustOffice vault documents automatically backed up to their chosen cloud storage on a scheduled basis. This is a user-opt-in feature configured in Settings, following the same toggle pattern as the existing admin access lock.

---

## 1. Cloud Providers to Support

### Phase 1 (MVP — ship first)

| Provider | Why | API | OAuth Scopes |
|---|---|---|---|
| **Google Drive** | Most common cloud storage; largest user base | Google Drive API v3 | `drive.file` (only files our app creates — least privilege) |
| **Dropbox** | Popular with professionals; simplest API | Dropbox API v2 | `files.content.write`, `files.content.read` |
| **OneDrive** | Enterprise/Office 365 users | Microsoft Graph API | `Files.ReadWrite` |

### Phase 2 (later)

| Provider | Why |
|---|---|
| **iCloud Drive** | Apple ecosystem users — but no public API for third-party file writes (only via CloudKit, very limited) |
| **Box** | Enterprise users — similar to OneDrive flow |
| **AWS S3** | Technical users who want direct bucket backup |

**Recommendation:** Ship Google Drive + Dropbox + OneDrive in Phase 1. These three cover ~90%+ of personal cloud storage users. iCloud has no viable third-party write API — skip it.

---

## 2. OAuth Flow Design

### Architecture

```
User clicks "Connect Google Drive" in Settings
    │
    ▼
Frontend redirects to provider OAuth consent screen
    │
    ▼
Provider redirects back to /api/backup/oauth/callback?code=xxx&state=xxx
    │
    ▼
Backend exchanges code for access_token + refresh_token
    │
    ▼
Tokens stored in MongoDB (db.cloud_backup_connections)
    │
    ▼
User sees "Connected ✓" status, backup schedule active
```

### Per-Provider OAuth Details

#### Google Drive

```python
# OAuth 2.0 with PKCE (no client secret needed for web server apps, but we'll use standard flow)
# Redirect URI: https://trustoffice.app/api/backup/oauth/callback?provider=google

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.file"

# State parameter: JSON-encoded {user_id, provider, nonce} (JWT-signed for tamper resistance)
```

#### Dropbox

```python
AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
SCOPE = "files.content.write files.content.read"
# Dropbox uses token_type=bearer, returns refresh_token for long-term access
```

#### OneDrive

```python
AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPE = "Files.ReadWrite offline_access"
# offline_access scope is required to get refresh_token
```

### OAuth State Management

```python
# backend/routers/cloud_backup.py (NEW FILE)

from cryptography.fernet import Fernet
import jwt, os, json, secrets

JWT_SECRET = os.environ["JWT_SECRET"]  # already exists for auth

def create_oauth_state(user_id: str, provider: str) -> str:
    """Create a JWT-signed OAuth state parameter to prevent CSRF."""
    return jwt.encode({
        "user_id": user_id,
        "provider": provider,
        "nonce": secrets.token_urlsafe(16),
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }, JWT_SECRET, algorithm="HS256")

def verify_oauth_state(state: str) -> dict:
    """Verify and decode the OAuth state."""
    return jwt.decode(state, JWT_SECRET, algorithms=["HS256"])
```

### Environment Variables Needed

| Variable | Purpose |
|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | `https://trustoffice.app/api/backup/oauth/callback?provider=google` |
| `DROPBOX_CLIENT_ID` | Dropbox app key |
| `DROPBOX_CLIENT_SECRET` | Dropbox app secret |
| `DROPBOX_REDIRECT_URI` | `https://trustoffice.app/api/backup/oauth/callback?provider=dropbox` |
| `MICROSOFT_CLIENT_ID` | Microsoft app client ID |
| `MICROSOFT_CLIENT_SECRET` | Microsoft app client secret |
| `MICROSOFT_REDIRECT_URI` | `https://trustoffice.app/api/backup/oauth/callback?provider=onedrive` |

---

## 3. Backup Strategy

### What Gets Backed Up

Only vault documents that have uploaded file content (not external reference links):

```python
# Documents in db.vault_documents where file_content exists and is not None
# Each backup copies: file_content (binary), file_name, file_content_type, 
#                     doc_id, title, category, created_at
```

### Backup Frequency: Weekly (Recommended)

**Why weekly, not daily:**
- Trust documents change infrequently — they're legal documents, meeting minutes, tax returns. These are not daily-active working files.
- Most vault content is uploaded once and rarely updated.
- Weekly backup covers the "I uploaded something this week and want it safe" use case.
- Daily backups would hit provider API rate limits unnecessarily and create noise.

**Override option:** Users can trigger an on-demand "Back up now" button from Settings at any time.

### Backup Mode: Incremental (changed-documents-only)

```python
# Track last_backup_at per document. Only back up docs where:
#   updated_at > last_backup_at OR doc has never been backed up

cursor = db.vault_documents.find({
    "user_id": user_id,
    "file_content": {"$ne": None},
    "$or": [
        {"last_backup_at": None},  # never backed up
        {"updated_at": {"$gt": "$last_backup_at"}}  # modified since last backup
    ]
})
```

### Backup File Organization in User's Cloud

```
/TrustOffice-Backup/
  ├── Trust-Instrument/
  │   └── Smith_Family_Trust_2024.pdf
  ├── Minutes/
  │   └── Annual_Minutes_2024-01-15.pdf
  ├── Tax-Returns/
  │   └── Form_1041_2023.pdf
  ├── Bank-Statements/
  │   └── Statement_2024-Q1.pdf
  └── _TrustOffice-Manifest.json    ← metadata file with full document list + backup timestamp
```

The manifest file (`_TrustOffice-Manifest.json`) contains:
```json
{
  "backup_date": "2026-08-25T19:00:00Z",
  "total_documents": 47,
  "documents": [
    {"doc_id": "doc_abc123", "title": "Smith Family Trust", "category": "trust_instrument", "file_name": "trust.pdf", "backup_path": "Trust-Instrument/trust.pdf", "backup_date": "2026-08-25T19:00:00Z"}
  ]
}
```

This lets users see exactly what was backed up and restore individual files if needed.

---

## 4. Backend Architecture

### New Files

```
backend/
  routers/
    cloud_backup.py          ← OAuth callbacks, connection management, manual trigger
  services/
    backup_service.py        ← Core backup logic (orchestration)
    providers/
      __init__.py
      base_provider.py       ← Abstract base class
      google_drive.py        ← Google Drive API client
      dropbox_provider.py    ← Dropbox API client
      onedrive_provider.py   ← Microsoft Graph API client
  cloud_backup_scheduler.py  ← APScheduler job registration
  tests/
    test_cloud_backup.py
    test_backup_providers.py
```

### Database Collections

```python
# db.cloud_backup_connections — OAuth tokens + connection state
{
    "user_id": "usr_123",
    "provider": "google_drive",       # "google_drive" | "dropbox" | "onedrive"
    "access_token": "ya29.xxx",       # encrypted at rest
    "refresh_token": "1//xxx",        # encrypted at rest
    "token_expires_at": "2026-08-25T20:00:00Z",
    "connected_at": "2026-08-25T19:00:00Z",
    "backup_frequency": "weekly",     # "weekly" | "daily" | "manual"
    "last_backup_at": "2026-08-25T19:05:00Z",
    "last_backup_status": "success",  # "success" | "failed" | "partial" | "in_progress"
    "last_backup_error": None,
    "last_backup_doc_count": 47,
    "backup_folder_id": "folder_id_in_provider",  # ID of the TrustOffice-Backup folder
    "is_active": True
}

# db.vault_documents — add backup tracking fields
{
    ...existing fields...,
    "last_backup_at": "2026-08-25T19:05:00Z",  # NEW
    "backup_path": "Trust-Instrument/trust.pdf",  # NEW — path in user's cloud
}
```

### Scheduler: APScheduler (already in requirements.txt)

```python
# backend/cloud_backup_scheduler.py (NEW FILE)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from services.backup_service import run_scheduled_backups
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

def init_backup_scheduler(app):
    """Initialize the backup scheduler. Call from server.py startup."""
    
    # Run every Sunday at 2 AM UTC (low traffic time)
    scheduler.add_job(
        run_scheduled_backups,
        CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_backup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Cloud backup scheduler started — weekly backups at Sunday 2 AM UTC")
    
    # Shutdown on app exit
    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))
```

### Core Backup Service

```python
# backend/services/backup_service.py (NEW FILE)

from database import db
from services.providers import get_provider
from datetime import datetime, timezone
import logging
import asyncio

logger = logging.getLogger(__name__)

async def run_scheduled_backups():
    """Run weekly backup for all users with active connections."""
    cursor = db.cloud_backup_connections.find({"is_active": True})
    async for conn in cursor:
        try:
            await backup_user_vault(conn["user_id"], conn)
        except Exception as e:
            logger.error(f"Backup failed for user {conn['user_id']}: {e}")
            await db.cloud_backup_connections.update_one(
                {"_id": conn["_id"]},
                {"$set": {"last_backup_status": "failed", "last_backup_error": str(e)}}
            )

async def backup_user_vault(user_id: str, conn: dict):
    """Back up all changed vault documents for a user."""
    provider = get_provider(conn["provider"])
    
    # Refresh token if needed
    access_token = await provider.refresh_token_if_needed(conn)
    
    # Ensure backup folder exists
    folder_id = await provider.ensure_backup_folder(access_token)
    
    # Find documents that need backup
    cursor = db.vault_documents.find({
        "user_id": user_id,
        "file_content": {"$ne": None},
        "$or": [
            {"last_backup_at": None},
            {"$expr": {"$gt": ["$updated_at", "$last_backup_at"]}}
        ]
    })
    
    backed_up = 0
    failed = 0
    async for doc in cursor:
        try:
            # Build folder path based on category
            category_folder = doc.get("category", "Other").replace("_", "-").title()
            file_name = doc.get("file_name", f"{doc['doc_id']}.bin")
            
            # Upload to provider
            backup_path = f"TrustOffice-Backup/{category_folder}/{file_name}"
            await provider.upload_file(
                access_token,
                folder_id,
                f"{category_folder}/{file_name}",
                doc["file_content"],
                doc.get("file_content_type", "application/octet-stream")
            )
            
            # Update document backup tracking
            await db.vault_documents.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "last_backup_at": datetime.now(timezone.utc).isoformat(),
                    "backup_path": backup_path,
                }}
            )
            backed_up += 1
        except Exception as e:
            logger.error(f"Failed to back up doc {doc.get('doc_id')}: {e}")
            failed += 1
    
    # Update manifest file
    await provider.update_manifest(access_token, folder_id, user_id)
    
    # Update connection status
    status = "success" if failed == 0 else ("partial" if backed_up > 0 else "failed")
    await db.cloud_backup_connections.update_one(
        {"_id": conn["_id"]},
        {"$set": {
            "last_backup_at": datetime.now(timezone.utc).isoformat(),
            "last_backup_status": status,
            "last_backup_error": None if status == "success" else f"{failed} files failed",
            "last_backup_doc_count": backed_up,
            "backup_folder_id": folder_id,
        }}
    )
    
    # Send notification to user
    await send_backup_notification(user_id, status, backed_up, failed)
    
    logger.info(f"Backup complete for user {user_id}: {backed_up} backed up, {failed} failed")
```

### Provider Abstraction

```python
# backend/services/providers/base_provider.py

from abc import ABC, abstractmethod

class BaseBackupProvider(ABC):
    @abstractmethod
    async def refresh_token_if_needed(self, conn: dict) -> str:
        """Return a valid access token, refreshing if necessary."""
        pass
    
    @abstractmethod
    async def ensure_backup_folder(self, access_token: str) -> str:
        """Create or find the TrustOffice-Backup folder. Return folder ID."""
        pass
    
    @abstractmethod
    async def upload_file(self, access_token: str, folder_id: str, path: str, content: bytes, content_type: str):
        """Upload a file to the specified path within the backup folder."""
        pass
    
    @abstractmethod
    async def update_manifest(self, access_token: str, folder_id: str, user_id: str):
        """Upload or update the manifest JSON file."""
        pass
    
    @abstractmethod
    async def disconnect(self, conn: dict):
        """Revoke OAuth tokens and clean up."""
        pass
```

### Google Drive Provider (Example Implementation)

```python
# backend/services/providers/google_drive.py

import httpx
from services.providers.base_provider import BaseBackupProvider
from database import db
from datetime import datetime, timezone
import os, json, logging

logger = logging.getLogger(__name__)

class GoogleDriveProvider(BaseBackupProvider):
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    DRIVE_API = "https://www.googleapis.com/drive/v3"
    DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
    
    async def refresh_token_if_needed(self, conn: dict) -> str:
        expires_at = conn.get("token_expires_at")
        if expires_at and datetime.fromisoformat(expires_at) > datetime.now(timezone.utc):
            return conn["access_token"]  # Still valid
        
        # Refresh the token
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "refresh_token": conn["refresh_token"],
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = resp.json()
        
        # Update stored tokens
        new_expires = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
        await db.cloud_backup_connections.update_one(
            {"_id": conn["_id"]},
            {"$set": {
                "access_token": tokens["access_token"],
                "token_expires_at": new_expires.isoformat(),
            }}
        )
        return tokens["access_token"]
    
    async def ensure_backup_folder(self, access_token: str) -> str:
        """Find or create 'TrustOffice-Backup' folder in user's Drive root."""
        async with httpx.AsyncClient() as client:
            # Search for existing folder
            resp = await client.get(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": "name='TrustOffice-Backup' and mimeType='application/vnd.google-apps.folder' and trashed=false"}
            )
            resp.raise_for_status()
            files = resp.json().get("files", [])
            
            if files:
                return files[0]["id"]
            
            # Create folder
            resp = await client.post(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"name": "TrustOffice-Backup", "mimeType": "application/vnd.google-apps.folder"}
            )
            resp.raise_for_status()
            return resp.json()["id"]
    
    async def upload_file(self, access_token: str, folder_id: str, path: str, content: bytes, content_type: str):
        """Upload file using Google Drive multipart upload."""
        # Split path into subfolders + filename
        parts = path.split("/")
        filename = parts[-1]
        subfolders = parts[1:-1]  # Skip "TrustOffice-Backup"
        
        # Navigate/create subfolders
        current_parent = folder_id
        for folder_name in subfolders:
            current_parent = await self._find_or_create_folder(access_token, current_parent, folder_name)
        
        # Check if file already exists (update vs create)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": f"name='{filename}' and '{current_parent}' in parents and trashed=false"}
            )
            existing = resp.json().get("files", [])
            
            if existing:
                # Update existing file
                file_id = existing[0]["id"]
                resp = await client.patch(
                    f"{self.DRIVE_UPLOAD}/files/{file_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"uploadType": "media"},
                    content=content,
                )
            else:
                # Create new file with metadata
                import aiohttp
                boundary = "trustoffice_boundary"
                metadata = {"name": filename, "parents": [current_parent]}
                body = (
                    f"--{boundary}\r\n"
                    f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                    f"{json.dumps(metadata)}\r\n"
                    f"--{boundary}\r\n"
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode() + content + f"\r\n--{boundary}--".encode()
                
                resp = await client.post(
                    f"{self.DRIVE_UPLOAD}/files",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": f"multipart/related; boundary={boundary}",
                    },
                    params={"uploadType": "multipart"},
                    content=body,
                )
            resp.raise_for_status()
    
    async def _find_or_create_folder(self, access_token, parent_id, folder_name):
        """Find or create a subfolder within a parent folder."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"}
            )
            files = resp.json().get("files", [])
            if files:
                return files[0]["id"]
            
            resp = await client.post(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"name": folder_name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
            )
            return resp.json()["id"]
```

---

## 5. Failure Handling

### Retry Logic

```python
MAX_RETRIES = 3
RETRY_DELAYS = [60, 300, 900]  # 1 min, 5 min, 15 min

async def backup_with_retry(provider, access_token, folder_id, doc):
    for attempt in range(MAX_RETRIES):
        try:
            await provider.upload_file(access_token, folder_id, doc["backup_path"], 
                                       doc["file_content"], doc.get("file_content_type", "application/octet-stream"))
            return True
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Upload attempt {attempt+1} failed for {doc['doc_id']}: {e}. Retrying in {RETRY_DELAYS[attempt]}s")
                await asyncio.sleep(RETRY_DELAYS[attempt])
            else:
                raise
```

### User Notification

```python
async def send_backup_notification(user_id: str, status: str, backed_up: int, failed: int):
    """Send in-app notification about backup result."""
    if status == "success":
        message = f"Cloud backup complete: {backed_up} document(s) backed up successfully."
    elif status == "partial":
        message = f"Cloud backup partially complete: {backed_up} backed up, {failed} failed. We'll retry failed files next time."
    else:
        message = f"Cloud backup failed. We'll retry automatically. Please check your cloud connection in Settings."
    
    await db.notifications.insert_one({
        "user_id": user_id,
        "type": "backup_status",
        "message": message,
        "status": status,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
```

### Token Expiry / Disconnection

- If token refresh fails (user revoked access), mark connection as `is_active: false` and notify user
- User must re-connect in Settings to resume backups
- Never silently fail — always surface the problem in the UI

---

## 6. Frontend UX

### Settings Page Integration

Add a new "Cloud Backup" section to `frontend/src/pages/SettingsPage.js`:

```javascript
// New section below the existing preferences toggles (~line 2500)

{/* Cloud Backup Section */}
<div className="border-t pt-6 mt-6">
  <h3 className="text-lg font-semibold text-navy">Cloud Backup</h3>
  <p className="text-sm text-gray-500 mt-1">
    Automatically back up your vault documents to your cloud storage account.
    Documents are backed up weekly. You can also trigger a backup manually.
  </p>
  
  {/* Provider Connection Buttons */}
  <div className="flex gap-3 mt-4">
    <ConnectProviderButton 
      provider="google_drive" 
      label="Connect Google Drive"
      icon={GoogleDriveIcon}
      connected={backupConn?.provider === 'google_drive'}
    />
    <ConnectProviderButton 
      provider="dropbox" 
      label="Connect Dropbox"
      icon={DropboxIcon}
      connected={backupConn?.provider === 'dropbox'}
    />
    <ConnectProviderButton 
      provider="onedrive" 
      label="Connect OneDrive"
      icon={OneDriveIcon}
      connected={backupConn?.provider === 'onedrive'}
    />
  </div>
  
  {/* Status Display (when connected) */}
  {backupConn && (
    <div className="mt-4 space-y-2">
      <div className="flex items-center gap-2">
        <CheckCircleIcon className="w-5 h-5 text-success" />
        <span className="text-sm">
          Connected to {formatProvider(backupConn.provider)}
        </span>
      </div>
      <div className="text-sm text-gray-500">
        Last backup: {formatDate(backupConn.last_backup_at)} — 
        {backupConn.last_backup_status === 'success' ? (
          <span className="text-success"> {backupConn.last_backup_doc_count} files backed up ✓</span>
        ) : (
          <span className="text-warning"> {backupConn.last_backup_status}</span>
        )}
      </div>
      <div className="flex gap-3 mt-2">
        <Button variant="outline" onClick={triggerBackupNow}>
          Back Up Now
        </Button>
        <Button variant="ghost" onClick={disconnectProvider}>
          Disconnect
        </Button>
      </div>
    </div>
  )}
</div>
```

### OAuth Connection Flow

```javascript
// frontend/src/components/settings/ConnectProviderButton.js (NEW FILE)

const connectProvider = async (provider) => {
  // Backend generates the OAuth URL and returns it
  const resp = await fetch(`/api/backup/oauth/connect?provider=${provider}`, {
    headers: authHeaders,
  });
  const { auth_url } = await resp.json();
  
  // Open OAuth consent screen in new tab
  window.location.href = auth_url;
  // Provider redirects back to /api/backup/oauth/callback
  // Callback handler redirects to /settings?backup_connected=true
  // Frontend shows success toast
};
```

### New API Endpoints

```
GET  /api/backup/oauth/connect?provider=google_drive    → returns {auth_url}
GET  /api/backup/oauth/callback?provider=...&code=...    → OAuth callback, stores tokens, redirects to /settings
GET  /api/backup/status                                 → returns connection + last backup status
POST /api/backup/trigger                                → trigger manual backup now
DELETE /api/backup/disconnect                           → revoke tokens, deactivate connection
```

---

## 7. Security Considerations

### OAuth Token Storage

- Access tokens and refresh tokens are stored in `db.cloud_backup_connections`
- If the encryption feature (Feature 1) is enabled, tokens should be encrypted using the same per-user Fernet key
- Tokens are NEVER returned in API responses to the frontend (only connection status + provider name)
- Token refresh happens server-side only

### What We Do NOT Store

- User's cloud storage password (never — we use OAuth tokens, not credentials)
- User's cloud file listings beyond our own backup folder
- Any data from the user's cloud that isn't created by TrustOffice

### Scope Minimization

- Google Drive: `drive.file` scope — only files created by our app are accessible. We cannot read or modify the user's other Drive files.
- Dropbox: `files.content.write` — limited to our app's folder
- OneDrive: `Files.ReadWrite` + `offline_access` — limited to app-created files

### Provider Disconnection

```python
@router.delete("/api/backup/disconnect")
async def disconnect_backup(user: dict = Depends(get_current_user)):
    conn = await db.cloud_backup_connections.find_one({"user_id": user["user_id"]})
    if not conn:
        raise HTTPException(404, "No backup connection found")
    
    # Revoke OAuth token at provider
    provider = get_provider(conn["provider"])
    await provider.revoke_token(conn["refresh_token"])
    
    # Remove connection record
    await db.cloud_backup_connections.delete_one({"user_id": user["user_id"]})
    
    # Clear backup tracking from vault documents
    await db.vault_documents.update_many(
        {"user_id": user["user_id"]},
        {"$unset": {"last_backup_at": "", "backup_path": ""}}
    )
    
    return {"message": "Cloud backup disconnected. Your files remain in your cloud storage."}
```

---

## 8. Railway Deployment Constraints

### Scheduler on Railway

Railway runs a single web process (uvicorn). APScheduler runs in-process (AsyncIOScheduler), which works because:
- Only one Railway instance is running (no horizontal scaling for our tier)
- If Railway restarts the container, APScheduler resumes on startup via the `init_backup_scheduler()` call in server.py startup

**Risk:** If Railway scales to multiple instances, each instance would run the scheduler. Mitigation: use an advisory lock (MongoDB-based) so only one instance runs backups.

```python
async def acquire_backup_lock():
    """Use MongoDB to ensure only one scheduler instance runs."""
    lock = await db.backup_locks.find_one_and_update(
        {"_id": "global_backup_lock", "locked_at": {"$lt": datetime.now(timezone.utc) - timedelta(minutes=30)}},
        {"$set": {"locked_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
        return_document=True,
    )
    return lock is not None
```

### Dependencies

Already in requirements.txt:
- `requests-oauthlib>=2.0.0` — OAuth library
- `APScheduler==3.11.2` — Scheduler
- `cryptography>=42.0.8` — Token encryption (if encryption feature is on)

New dependency needed:
- `httpx>=0.27.0` — async HTTP client for provider API calls (or use `requests` with `asyncio.to_thread`)

### Environment Variables to Add in Railway

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://trustoffice.app/api/backup/oauth/callback?provider=google
DROPBOX_CLIENT_ID=...
DROPBOX_CLIENT_SECRET=...
DROPBOX_REDIRECT_URI=https://trustoffice.app/api/backup/oauth/callback?provider=dropbox
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MICROSOFT_REDIRECT_URI=https://trustoffice.app/api/backup/oauth/callback?provider=onedrive
```

### OAuth App Registration

Before deployment, register OAuth apps at:
1. **Google Cloud Console** → APIs & Services → Credentials → Create OAuth 2.0 Client ID (Web application)
2. **Dropbox Developer** → App Console → Create App → Generate PKCE → Set redirect URI
3. **Microsoft Azure Portal** → App Registrations → New Registration → Add redirect URI

---

## 9. Implementation File List

### New Files

| File | Purpose |
|---|---|
| `backend/routers/cloud_backup.py` | OAuth endpoints, connection management, manual trigger |
| `backend/services/backup_service.py` | Core backup orchestration |
| `backend/services/providers/__init__.py` | Provider factory |
| `backend/services/providers/base_provider.py` | Abstract base class |
| `backend/services/providers/google_drive.py` | Google Drive implementation |
| `backend/services/providers/dropbox_provider.py` | Dropbox implementation |
| `backend/services/providers/onedrive_provider.py` | OneDrive implementation |
| `backend/cloud_backup_scheduler.py` | APScheduler job registration |
| `backend/tests/test_cloud_backup.py` | Integration tests |
| `backend/tests/test_backup_providers.py` | Provider unit tests (mock HTTP) |
| `frontend/src/components/settings/ConnectProviderButton.js` | OAuth connection button |
| `frontend/src/components/settings/BackupStatusCard.js` | Backup status display |
| `frontend/src/components/settings/CloudBackupSection.js` | Full cloud backup settings section |

### Modified Files

| File | Change |
|---|---|
| `backend/server.py` | Register cloud_backup router, init scheduler on startup |
| `backend/models.py` | Add CloudBackupConnection model, BackupSettings model |
| `frontend/src/pages/SettingsPage.js` | Add CloudBackup section (~line 2500) |
| `frontend/src/utils/api.js` | Add backup API helper functions |

### New Database Collections

| Collection | Purpose |
|---|---|
| `cloud_backup_connections` | OAuth tokens + backup status per user |
| `backup_locks` | Scheduler advisory lock (multi-instance safety) |

### New Environment Variables

7 variables (listed in Section 8 above).

---

## 10. Testing Strategy

### Provider Unit Tests (mock HTTP)

```python
# backend/tests/test_backup_providers.py

@patch('httpx.AsyncClient')
async def test_google_drive_refresh_token():
    """Token refresh requests correct endpoint with correct payload."""
    
async def test_google_drive_ensure_folder_creates_if_missing():
    """Folder creation API called when folder doesn't exist."""
    
async def test_google_drive_upload_new_file():
    """Multipart upload called with correct metadata + content."""
    
async def test_google_drive_upload_updates_existing():
    """PATCH called when file already exists in target folder."""
    
async def test_dropbox_upload_uses_correct_path():
    """Dropbox upload uses /TrustOffice-Backup/ prefix."""
    
async def test_onedrive_token_refresh():
    """Microsoft token refresh uses correct tenant endpoint."""
```

### Integration Tests

```python
# backend/tests/test_cloud_backup.py

async def test_oauth_callback_stores_tokens():
    """OAuth callback stores access + refresh tokens in DB."""
    
async def test_oauth_state_csrf_protection():
    """Invalid/expired state JWT is rejected."""
    
async def test_scheduled_backup_only_processes_changed_docs():
    """Only docs with updated_at > last_backup_at are backed up."""
    
async def test_manual_backup_works():
    """POST /api/backup/trigger runs backup immediately."""
    
async def test_backup_failure_retries():
    """Failed upload retries with backoff."""
    
async def test_disconnect_revokes_tokens():
    """DELETE /api/backup/disconnect calls provider revoke + clears DB."""
    
async def test_backup_with_encryption_feature_on():
    """Backup works correctly when data encryption feature is enabled — 
    files are decrypted before upload so user gets readable files in their cloud."""
```

### Manual E2E Test Plan

1. Connect Google Drive → verify redirect flow → verify tokens stored
2. Upload a vault document → trigger manual backup → verify file appears in Google Drive
3. Upload a second document → trigger backup → verify only new doc backed up
4. Wait for weekly schedule → verify backup runs automatically
5. Disconnect → verify tokens revoked + files remain in user's cloud
6. Repeat for Dropbox and OneDrive

---

## 11. Implementation Sequence

1. **Phase 1 (OAuth):** Register OAuth apps, build `cloud_backup.py` router with connect/callback/disconnect endpoints
2. **Phase 2 (Providers):** Implement all three providers (Google Drive first, then Dropbox, then OneDrive)
3. **Phase 3 (Backup Service):** Core backup logic + scheduler registration
4. **Phase 4 (Frontend):** Settings section with connect buttons, status display, manual trigger
5. **Phase 5 (Testing):** Unit tests with mocked HTTP → integration tests → manual E2E with real accounts
6. **Phase 6 (Deploy):** Add env vars to Railway → deploy → test OAuth flow on staging

**Estimated effort:** 3-4 days. The OAuth app registrations and provider API implementations are the bulk of the work; the backup orchestration itself is straightforward.

---

## Interaction with Feature 1 (Encryption)

If both features are enabled:
- Vault documents are encrypted at rest in MongoDB (Feature 1)
- Backup service decrypts them using the user's Fernet key before uploading to the cloud
- User gets readable files in their Google Drive/Dropbox/OneDrive
- The cloud backup does NOT upload ciphertext — it uploads the original file content
- This is intentional: the cloud backup is the user's own copy in their own account; they should be able to read it