"""
TOTP two-factor authentication service for TrustOffice.

Owns everything 2FA that is not route wiring:
  - per-user TOTP secret generation + provisioning URI (pyotp)
  - recovery-code generation + bcrypt hashing at rest (same scheme as
    passwords — NOT a fast hash)
  - code verification (TOTP with ±1 window drift tolerance; recovery codes
    single-use, atomically consumed)
  - login-challenge JWTs: short-lived (5 min), payload type='2fa_challenge',
    never valid as an access token (get_current_user enforces type=='access')
  - step-up verification (header X-2FA-Code, ±1 window)
  - in-memory failed-TOTP backoff: >=5 failed codes per user per 5-minute
    window blocks verification (auto-clears when the window rolls off).
    Forgiving by design — the user base skews 55+ and will fumble codes;
    no permanent lockout, no admin intervention needed.

User persistence: Mongo `users` collection — fields added to the existing
user doc (no new auth system):
    totp = {
        enabled: bool,
        secret: str,                      # base32 secret (needed to verify codes)
        enrollment_secret: str,           # pending secret pre-verify
        recovery_codes: [{code_hash, used_at, used_ip}],
        created_at, verified_at, disabled_at,
    }
"""
from __future__ import annotations

import base64
import io
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import bcrypt
import jwt
import pyotp

from database import db

logger = logging.getLogger(__name__)

# JWT config — same secret/algorithm as session tokens (imported from
# dependencies so a secret rotation applies to both); scoping happens via
# the `type` claim and a 5-minute expiry.
JWT_ALGORITHM = "HS256"
try:
    from dependencies import JWT_SECRET as _JWT_SECRET
    JWT_SECRET = _JWT_SECRET
except Exception:  # pragma: no cover — module used standalone before app import
    JWT_SECRET = os.environ.get("JWT_SECRET", "")

CHALLENGE_TOKEN_MINUTES = 5
TOTP_ISSUER_NAME = "TrustOffice"
TOTP_DIGITS = 6

# Recovery codes: 10 single-use codes, bcrypt-hashed at rest, plaintext shown
# exactly once at activation.
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_BYTES = 5  # -> 8 base32 chars, ~40 bits of entropy

# Forgiving backoff: >=5 failed TOTP verifications per user within a 5-min
# window -> block until the window rolls off. Auto-clears; no permanent lock.
TOTP_FAIL_WINDOW_SECONDS = 5 * 60
TOTP_FAIL_LIMIT = 5

# In-memory failure tracker: user_id -> list[unix ts]
_totp_failures: Dict[str, List[float]] = {}


def prune_totp_failures() -> None:
    """Drop expired failure entries (called on every check)."""
    now = time.time()
    cutoff = now - TOTP_FAIL_WINDOW_SECONDS
    for user_id in list(_totp_failures.keys()):
        window = [t for t in _totp_failures[user_id] if t > cutoff]
        if window:
            _totp_failures[user_id] = window
        else:
            del _totp_failures[user_id]


def is_totp_rate_limited(user_id: str) -> bool:
    """True when the user has >= TOTP_FAIL_LIMIT failed codes inside the window."""
    prune_totp_failures()
    return len(_totp_failures.get(user_id, [])) >= TOTP_FAIL_LIMIT


def record_totp_failure(user_id: str) -> int:
    """Record a failed TOTP verification; returns the current window count."""
    prune_totp_failures()
    _totp_failures.setdefault(user_id, []).append(time.time())
    return len(_totp_failures[user_id])


def clear_totp_failures(user_id: str) -> None:
    """Called after a successful verification â fumbling then getting it right
    must not leave the user near the limit."""
    _totp_failures.pop(user_id, None)


def seconds_until_window_clears(user_id: str) -> int:
    """Integer seconds until the oldest recorded failure rolls out of the
    window (0 when there are no recorded failures for the user)."""
    prune_totp_failures()
    stamps = _totp_failures.get(user_id, [])
    if not stamps:
        return 0
    oldest = min(stamps)
    remaining = (oldest + TOTP_FAIL_WINDOW_SECONDS) - time.time()
    return max(0, int(math.ceil(remaining)))


def attempts_remaining(user_id: str) -> int:
    """How many more failed codes are accepted before the cooldown kicks in.

    Forgiving backoff: TOTP_FAIL_LIMIT failures within the window -> block.
    So before the limit is reached, (limit - current_count) attempts remain.
    """
    prune_totp_failures()
    count = len(_totp_failures.get(user_id, []))
    return max(0, TOTP_FAIL_LIMIT - count)


def build_rate_limited_body(user_id: str) -> dict:
    """Structured 429 body so clients can render an exact countdown.

    Keys (required by the frontend contract):
      detail      -> "2fa_rate_limited"
      retry_after -> integer seconds until the window clears (positive)
      message     -> plain human string mentioning the wait in whole minutes
    """
    seconds = seconds_until_window_clears(user_id)
    seconds = max(1, seconds)  # guaranteed positive while actually rate-limited
    minutes = max(1, math.ceil(seconds / 60))
    return {
        "detail": "2fa_rate_limited",
        "retry_after": int(seconds),
        "message": (
            f"Too many incorrect codes. You can try again in {minutes} minutes. "
            "Your account is not locked - you can also sign in with a recovery code."
        ),
    }


def build_invalid_code_body(user_id: str) -> dict:
    """Structured invalid-code body with remaining-attempt info.

    detail stays exactly "2fa_invalid_code" (the frontend keys off it);
    attempts_remaining tells the client how many more fails are tolerated.
    """
    return {
        "detail": "2fa_invalid_code",
        "attempts_remaining": int(attempts_remaining(user_id)),
        "message": "That code didn't match. Try again or use a recovery code.",
    }


# ---------------------------------------------------------------------------
# Secret / provisioning
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Generate a random base32 TOTP secret."""
    return pyotp.random_base32()


def build_provisioning_uri(secret: str, email: str) -> str:
    """otpauth:// URI for authenticator apps (QR rendered client-side from this)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email, issuer_name=TOTP_ISSUER_NAME
    )


def make_qr_data_uri(provisioning_uri: str) -> str:
    """Render the provisioning URI as a PNG data URI (qrcode, no extra deps)."""
    import qrcode

    img = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# User-doc 2FA state helpers (Mongo users collection)
# ---------------------------------------------------------------------------

def get_totp_state(user_doc: dict) -> dict:
    """Return the user's embedded totp state ({} when never enrolled)."""
    state = user_doc.get("totp")
    return state if isinstance(state, dict) else {}


def is_2fa_enabled(user_doc: dict) -> bool:
    return bool(get_totp_state(user_doc).get("enabled"))


def is_admin_user(user_doc: dict) -> bool:
    return bool(user_doc.get("is_admin"))


# ---------------------------------------------------------------------------
# Recovery codes — bcrypt-hashed (same scheme as passwords), single-use
# ---------------------------------------------------------------------------

def _hash_recovery_code(code: str) -> str:
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_recovery_code(code: str, code_hash: str) -> bool:
    try:
        return bcrypt.checkpw(code.encode("utf-8"), code_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> Tuple[List[str], List[dict]]:
    """Generate `count` plaintext recovery codes + their bcrypt-hashed at-rest form."""
    plaintext: List[str] = []
    hashed: List[dict] = []
    for _ in range(count):
        raw = base64.b32encode(os.urandom(RECOVERY_CODE_BYTES)).decode("utf-8").rstrip("=")
        plaintext.append(raw)
        hashed.append({
            "code_hash": _hash_recovery_code(raw),
            "used_at": None,
            "used_ip": None,
        })
    return plaintext, hashed


def count_unused_recovery_codes(user_doc: dict) -> int:
    codes = get_totp_state(user_doc).get("recovery_codes") or []
    return sum(1 for c in codes if isinstance(c, dict) and not c.get("used_at"))


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_totp_code(secret: str, code: str, valid_windows: int = 1) -> bool:
    """Verify a 6-digit TOTP code with ±`valid_windows` window drift tolerance.

    Accepts codes with spaces/dashes stripped (users fumble typing).
    """
    if not secret or not code:
        return False
    normalized = code.strip().replace(" ", "").replace("-", "")
    if not normalized.isdigit():
        return False
    try:
        totp = pyotp.TOTP(secret, digits=TOTP_DIGITS)
        return bool(totp.verify(normalized, valid_window=valid_windows))
    except Exception:
        return False


def verify_stepup_code(user_doc: dict, code: str) -> bool:
    """Step-up check for a 2FA-enabled user (vault download, successor grant)."""
    if not is_2fa_enabled(user_doc):
        return False
    secret = get_totp_state(user_doc).get("secret")
    return bool(secret) and verify_totp_code(secret, code)


# ---------------------------------------------------------------------------
# Login-challenge JWT (5 min, type='2fa_challenge', session-inert)
# ---------------------------------------------------------------------------

def create_challenge_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "2fa_challenge",
        "jti": f"2fa_{int(time.time() * 1000)}",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=CHALLENGE_TOKEN_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_challenge_token(token: str) -> Optional[dict]:
    """Return the payload when the token is a valid, unexpired 2FA challenge.

    Anything else (expired, wrong type, garbage) -> None.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    if payload.get("type") != "2fa_challenge":
        return None
    if not payload.get("user_id"):
        return None
    return payload


# ---------------------------------------------------------------------------
# Login-time code check: TOTP or single-use recovery code
# ---------------------------------------------------------------------------

def _normalize_code(code: str) -> str:
    return (code or "").strip().replace(" ", "").replace("-", "").upper()


async def consume_login_code(user_doc: dict, code: str) -> Tuple[bool, str]:
    """Validate a login code against the user's 2FA state.

    Returns (ok, method) where method is 'totp' | 'recovery_code' | 'invalid'
    | 'rate_limited'. A matched recovery code is consumed atomically (only the
    matching unused slot is updated — concurrent guesses cannot burn two slots
    or reuse one).
    """
    if is_totp_rate_limited(user_doc.get("user_id", "")):
        return False, "rate_limited"

    state = get_totp_state(user_doc)
    secret = state.get("secret")

    if verify_totp_code(secret, code):
        clear_totp_failures(user_doc.get("user_id", ""))
        return True, "totp"

    normalized = _normalize_code(code)

    # Recovery-code path — find the first unused slot whose bcrypt hash matches.
    codes = state.get("recovery_codes") or []
    for idx, slot in enumerate(codes):
        if not isinstance(slot, dict) or slot.get("used_at"):
            continue
        if _verify_recovery_code(normalized, slot.get("code_hash", "")):
            consumed = await _consume_recovery_slot(user_doc.get("user_id", ""), idx)
            if consumed:
                clear_totp_failures(user_doc.get("user_id", ""))
                return True, "recovery_code"
            # Another concurrent request consumed it first — this attempt did
            # not verify, but the code itself was valid at some point.
            return False, "recovery_code"

    # No TOTP or recovery-code match. Do NOT record the failure here — the
    # caller (router) records exactly one failure per attempt so the window
    # count stays correct.
    return False, "invalid"


async def _consume_recovery_slot(user_id: str, idx: int) -> bool:
    """Atomically mark recovery slot `idx` used. False when lost to a race."""
    field = f"totp.recovery_codes.{idx}.used_at"
    existing = await db.users.find_one(
        {"user_id": user_id, field: None, "totp.enabled": True},
        {"_id": 1},
    )
    if not existing:
        return False
    await db.users.update_one(
        {"user_id": user_id, field: None},
        {"$set": {field: datetime.now(timezone.utc).isoformat()}},
    )
    return True
