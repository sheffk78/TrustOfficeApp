"""Symmetric encryption helpers for credentials at rest (MongoDB).

Uses Fernet (AES-128-CBC + HMAC). Key source, in order:
  1. CREDENTIAL_ENCRYPTION_KEY env var (urlsafe-b64 32 bytes)
  2. Derived from JWT_SECRET (sha256) — stable across restarts, zero config
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
    if not key:
        secret = os.environ.get("JWT_SECRET")
        if not secret:
            raise RuntimeError(
                "No CREDENTIAL_ENCRYPTION_KEY or JWT_SECRET configured — "
                "cannot encrypt credentials at rest."
            )
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def fernet_encrypt(plaintext: str) -> str:
    """Encrypt a string; returns a urlsafe token string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def fernet_decrypt(token: str) -> str:
    """Decrypt a Fernet token; raises ValueError on tamper/bad key."""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Credential decryption failed (bad key or tampered data)") from e