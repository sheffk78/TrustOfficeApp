"""
Proton Drive backup provider — talks to the TrustOffice Proton Bridge.

Why a bridge: Proton Drive has no public API. The official
`@protontech/drive-sdk` (TypeScript) is the only supported path, and it
needs a Node runtime + esbuild bundling (browser-condition crypto).

Auth model (session fork — the user's Proton password and 2FA NEVER touch
TrustOffice or the bridge):
  1. POST /connect/start  -> { connect_id, sign_in_url }
  2. Member signs in on Proton's own page (account.proton.me)
  3. Bridge polls Proton's fork endpoint -> scoped session tokens
  4. Python polls /connect/status -> stores ENCRYPTED credentials in MongoDB

Connection doc shape (cloud_backup_connections, provider="proton_drive"):
  provider: "proton_drive"
  bridge_url: str (optional override)
  proton_credentials_encrypted: str (Fernet-encrypted JSON of the SDK snapshot)
  ...standard fields (user_id, is_active, last_backup_*, backup_folder_id)
"""
import os
import base64
import logging
import httpx

logger = logging.getLogger(__name__)

BRIDGE_TIMEOUT_S = 120


class BridgeClientError(RuntimeError):
    """Bridge returned a structured JSON error (status >= 400).

    Carries the parsed body so callers can surface the real reason
    (e.g. not_signed_in) instead of a generic message.
    """

    def __init__(self, status: int, body: dict):
        self.status = status
        self.body = body
        super().__init__(f"Proton bridge error {status}: {body}")


def _bridge_key() -> str:
    return os.environ.get("PROTON_BRIDGE_KEY", "")


class ProtonDriveProvider:
    """Thin provider over the Proton bridge HTTP API.

    Duck-types BaseBackupProvider where it maps. The fork flow means there
    is no refresh_token/access_token pair — the router branches on
    provider == "proton_drive" before touching OAuth paths, and the bridge
    holds the session for the duration of each call.
    """

    PROVIDER_NAME = "proton_drive"

    def _bridge_url(self, conn: dict) -> str:
        return conn.get("bridge_url") or os.environ.get(
            "PROTON_BRIDGE_URL", "http://localhost:8181"
        )

    def _headers(self) -> dict:
        return {"X-Bridge-Key": _bridge_key(), "Content-Type": "application/json"}

    def _credentials_payload(self, conn: dict) -> dict:
        """Build the {connection: {credentials}} body the bridge expects."""
        import json as _json
        from services.crypto_utils import fernet_decrypt  # Fernet helper

        raw = conn.get("proton_credentials_encrypted")
        creds = _json.loads(fernet_decrypt(raw)) if raw else {}
        return {"connection": {"credentials": creds}}

    async def _post_bridge(self, path: str, payload: dict, conn: dict) -> dict:
        url = f"{self._bridge_url(conn)}{path}"
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except Exception:
                    body = {"error": "bridge_error", "message": resp.text[:300]}
                raise BridgeClientError(resp.status_code, body)
            return resp.json()

    # ---- connection lifecycle ----

    async def start_connect(self) -> dict:
        """Start a fork-flow connect. Returns {connect_id, sign_in_url}."""
        return await self._post_bridge("/connect/start", {}, {})

    async def connect_status(self, connect_id: str, conn: dict | None = None) -> dict:
        return await self._post_bridge(
            "/connect/status", {"connect_id": connect_id}, conn or {}
        )

    async def verify(self, conn: dict) -> dict:
        return await self._post_bridge("/verify", self._credentials_payload(conn), conn)

    # ---- BaseBackupProvider-shaped surface ----

    async def refresh_token_if_needed(self, conn: dict) -> str:
        """Fork sessions don't use bearer tokens on our side. The bridge
        handles Proton token refresh internally. Returns a placeholder
        string so backup_service's contract stays unchanged."""
        return "proton-bridge-session"

    async def upload_file(self, access_token: str, folder_ref: str, path: str, content: bytes, content_type: str):
        """Base-class signature — Proton requires the connection (credentials),
        so the real path is upload_file_with_conn (called by backup_service)."""
        raise NotImplementedError("proton_drive uses upload_file_with_conn(conn, ...)")

    async def update_manifest(self, access_token: str, folder_ref: str, manifest_data: dict):
        """Base-class signature — real path is update_manifest_with_conn."""
        raise NotImplementedError("proton_drive uses update_manifest_with_conn(conn, ...)")

    async def ensure_backup_folder(self, access_token: str, conn: dict) -> str:
        # Bridge creates/verifies TrustOffice-Backup on first upload/list.
        return "TrustOffice-Backup"

    async def upload_file_with_conn(self, conn: dict, path: str, content: bytes,
                                    content_type: str) -> dict:
        """Full upload using the connection (bridge needs credentials)."""
        parts = path.split("/")
        _root = parts[0]
        category_folder = parts[1] if len(parts) > 2 else "Other"
        file_name = parts[-1]
        payload = self._credentials_payload(conn)
        payload.update({
            "trust_name": category_folder,
            "file_name": file_name,
            "media_type": content_type,
            "content_base64": base64.b64encode(content).decode("ascii"),
        })
        return await self._post_bridge("/backup/upload", payload, conn)

    async def update_manifest_with_conn(self, conn: dict, manifest_data: dict):
        import json as _json
        content = _json.dumps(manifest_data, indent=2).encode()
        await self.upload_file_with_conn(
            conn, "TrustOffice-Backup/Other/_TrustOffice-Manifest.json",
            content, "application/json",
        )

    async def revoke_token(self, refresh_token: str):
        pass  # bridge /disconnect handled in router with credentials


