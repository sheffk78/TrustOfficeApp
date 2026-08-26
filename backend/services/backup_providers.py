"""
Cloud backup providers for TrustOffice vault documents.

Supports: Google Drive, Dropbox, OneDrive (Microsoft Graph).
Each provider implements the BaseBackupProvider interface.
"""
import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)


class BaseBackupProvider:
    """Abstract base class for cloud backup providers."""

    async def refresh_token_if_needed(self, conn: dict) -> str:
        """Return a valid access token, refreshing if necessary. Updates conn in DB."""
        raise NotImplementedError

    async def ensure_backup_folder(self, access_token: str, conn: dict) -> str:
        """Create or find the TrustOffice-Backup folder. Return folder ID/path."""
        raise NotImplementedError

    async def upload_file(self, access_token: str, folder_ref: str, path: str, content: bytes, content_type: str):
        """Upload a file to the specified path within the backup folder."""
        raise NotImplementedError

    async def update_manifest(self, access_token: str, folder_ref: str, manifest_data: dict):
        """Upload or update the manifest JSON file."""
        raise NotImplementedError

    async def revoke_token(self, refresh_token: str):
        """Revoke OAuth tokens at the provider."""
        raise NotImplementedError


class GoogleDriveProvider(BaseBackupProvider):
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    DRIVE_API = "https://www.googleapis.com/drive/v3"
    DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"

    async def refresh_token_if_needed(self, conn: dict) -> str:
        from datetime import datetime, timezone, timedelta
        from database import db

        expires_at = conn.get("token_expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp > datetime.now(timezone.utc):
                    return conn["access_token"]
            except Exception:
                pass

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "refresh_token": conn["refresh_token"],
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = resp.json()

        new_expires = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
        await db.cloud_backup_connections.update_one(
            {"_id": conn["_id"]},
            {"$set": {
                "access_token": tokens["access_token"],
                "token_expires_at": new_expires.isoformat(),
            }}
        )
        return tokens["access_token"]

    async def ensure_backup_folder(self, access_token: str, conn: dict) -> str:
        folder_id = conn.get("backup_folder_id")
        if folder_id:
            return folder_id

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": "name='TrustOffice-Backup' and mimeType='application/vnd.google-apps.folder' and trashed=false"}
            )
            resp.raise_for_status()
            files = resp.json().get("files", [])

            if files:
                return files[0]["id"]

            resp = await client.post(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"name": "TrustOffice-Backup", "mimeType": "application/vnd.google-apps.folder"}
            )
            resp.raise_for_status()
            return resp.json()["id"]

    async def upload_file(self, access_token: str, folder_ref: str, path: str, content: bytes, content_type: str):
        parts = path.split("/")
        filename = parts[-1]
        subfolders = parts[1:-1]  # Skip "TrustOffice-Backup"

        current_parent = folder_ref
        for folder_name in subfolders:
            current_parent = await self._find_or_create_folder(access_token, current_parent, folder_name)

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(
                f"{self.DRIVE_API}/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": f"name='{filename}' and '{current_parent}' in parents and trashed=false"}
            )
            existing = resp.json().get("files", [])

            if existing:
                file_id = existing[0]["id"]
                resp = await client.patch(
                    f"{self.DRIVE_UPLOAD}/files/{file_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"uploadType": "media"},
                    content=content,
                )
            else:
                boundary = "trustoffice_boundary_12345"
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
        async with httpx.AsyncClient(timeout=30) as client:
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

    async def update_manifest(self, access_token: str, folder_ref: str, manifest_data: dict):
        content = json.dumps(manifest_data, indent=2).encode()
        await self.upload_file(access_token, folder_ref, "TrustOffice-Backup/_TrustOffice-Manifest.json", content, "application/json")

    async def revoke_token(self, refresh_token: str):
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": refresh_token}
            )


class DropboxProvider(BaseBackupProvider):
    TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
    UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
    REVOKE_URL = "https://api.dropboxapi.com/2/auth/token/revoke"

    async def refresh_token_if_needed(self, conn: dict) -> str:
        from datetime import datetime, timezone, timedelta
        from database import db

        expires_at = conn.get("token_expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp > datetime.now(timezone.utc):
                    return conn["access_token"]
            except Exception:
                pass

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_id": os.environ["DROPBOX_CLIENT_ID"],
                "client_secret": os.environ["DROPBOX_CLIENT_SECRET"],
                "refresh_token": conn["refresh_token"],
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            tokens = resp.json()

        new_expires = datetime.now(timezone.utc) + timedelta(seconds=tokens.get("expires_in", 14400))
        await db.cloud_backup_connections.update_one(
            {"_id": conn["_id"]},
            {"$set": {
                "access_token": tokens["access_token"],
                "token_expires_at": new_expires.isoformat(),
            }}
        )
        return tokens["access_token"]

    async def ensure_backup_folder(self, access_token: str, conn: dict) -> str:
        # Dropbox uses paths, not folder IDs. Return empty string as folder_ref.
        return ""

    async def upload_file(self, access_token: str, folder_ref: str, path: str, content: bytes, content_type: str):
        dropbox_path = f"/{path}"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Dropbox-API-Arg": json.dumps({
                        "path": dropbox_path,
                        "mode": "overwrite",
                        "autorename": False,
                        "mute": True,
                    }),
                    "Content-Type": "application/octet-stream",
                },
                content=content,
            )
            resp.raise_for_status()

    async def update_manifest(self, access_token: str, folder_ref: str, manifest_data: dict):
        content = json.dumps(manifest_data, indent=2).encode()
        await self.upload_file(access_token, folder_ref, "TrustOffice-Backup/_TrustOffice-Manifest.json", content, "application/json")

    async def revoke_token(self, refresh_token: str):
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                self.REVOKE_URL,
                headers={"Authorization": f"Bearer {refresh_token}"},
            )


class OneDriveProvider(BaseBackupProvider):
    TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    async def refresh_token_if_needed(self, conn: dict) -> str:
        from datetime import datetime, timezone, timedelta
        from database import db

        expires_at = conn.get("token_expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp > datetime.now(timezone.utc):
                    return conn["access_token"]
            except Exception:
                pass

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.TOKEN_URL, data={
                "client_id": os.environ["MICROSOFT_CLIENT_ID"],
                "client_secret": os.environ["MICROSOFT_CLIENT_SECRET"],
                "refresh_token": conn["refresh_token"],
                "grant_type": "refresh_token",
                "scope": "Files.ReadWrite offline_access",
            })
            resp.raise_for_status()
            tokens = resp.json()

        new_expires = datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
        await db.cloud_backup_connections.update_one(
            {"_id": conn["_id"]},
            {"$set": {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", conn["refresh_token"]),
                "token_expires_at": new_expires.isoformat(),
            }}
        )
        return tokens["access_token"]

    async def ensure_backup_folder(self, access_token: str, conn: dict) -> str:
        folder_id = conn.get("backup_folder_id")
        if folder_id:
            return folder_id

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.GRAPH_BASE}/me/drive/root:/TrustOffice-Backup",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                return resp.json().get("id", "TrustOffice-Backup")

            resp = await client.patch(
                f"{self.GRAPH_BASE}/me/drive/root:/TrustOffice-Backup",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "@microsoft.graph.conflictBehavior": "fail",
                    "name": "TrustOffice-Backup",
                    "folder": {},
                },
            )
            if resp.status_code in (200, 201):
                return resp.json().get("id", "TrustOffice-Backup")
            return "TrustOffice-Backup"

    async def upload_file(self, access_token: str, folder_ref: str, path: str, content: bytes, content_type: str):
        onedrive_path = f"/TrustOffice-Backup/{'/'.join(path.split('/')[1:])}"
        url = f"{self.GRAPH_BASE}/me/drive/root:{onedrive_path}:/content"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.put(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": content_type,
                },
                content=content,
            )
            resp.raise_for_status()

    async def update_manifest(self, access_token: str, folder_ref: str, manifest_data: dict):
        content = json.dumps(manifest_data, indent=2).encode()
        await self.upload_file(access_token, folder_ref, "TrustOffice-Backup/_TrustOffice-Manifest.json", content, "application/json")

    async def revoke_token(self, refresh_token: str):
        # Microsoft doesn't have a simple token revoke endpoint.
        # For cleanup, we just delete our stored tokens.
        pass


# Factory
PROVIDERS = {
    "google_drive": GoogleDriveProvider,
    "dropbox": DropboxProvider,
    "onedrive": OneDriveProvider,
}


def get_provider(provider_name: str) -> BaseBackupProvider:
    cls = PROVIDERS.get(provider_name)
    if not cls:
        raise ValueError(f"Unknown backup provider: {provider_name}")
    return cls()