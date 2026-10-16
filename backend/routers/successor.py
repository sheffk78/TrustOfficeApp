# Successor Trustee router - successor communication endpoints
import hashlib
import secrets
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request
from pydantic import BaseModel
from pymongo import ReturnDocument

from fastapi.encoders import jsonable_encoder

from database import db
from dependencies import require_write_access, require_org_grant, get_current_user
from models import GrantLevel
from email_service import email_service
from utils.audit import log_audit_event
from utils.stepup_2fa import require_2fa_stepup
from utils.tax_calendar_math import filter_income_tax_entries
from routers.auth import rate_limit as _auth_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(tags=["successor"])

# One-time packet access link validity (30 days)
SUCCESSOR_LINK_TTL_DAYS = 30

# Access-code method (Jeff 2026-10-16: trustee-selected successor access method, code default)
SUCCESSOR_ACCESS_CODE_GROUPS = 4   # XXXX-XXXX-XXXX-XXXX
SUCCESSOR_CODE_CLAIM_RATE = 10     # claims per window per IP — brute-force guard
SUCCESSOR_CODE_CLAIM_WINDOW = 3600


def _normalize_code(value: str) -> str:
    """Uppercase and strip non-alphanumerics — 'abcd-efgh-ijkl-mnop' == 'ABCDEFGHIJKLMNOP'."""
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _generate_code() -> str:
    """Human-friendly grouped access code (no 0/O/1/I ambiguity)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    groups = []
    for _ in range(SUCCESSOR_ACCESS_CODE_GROUPS):
        groups.append("".join(secrets.choice(alphabet) for _ in range(4)))
    return "-".join(groups)


def _power_labels(powers) -> list:
    """Map stored trust protector power keys to human-readable labels for the appointment email.

    Single source of truth for label text: backend/data/trust_protector_powers.json.
    """
    labels = _trust_protector_label_map()
    return [labels.get(p, p) for p in powers] if isinstance(powers, list) else []


def _trust_protector_label_map() -> dict:
    """Load the {key: label} map from the canonical JSON (backend/data/trust_protector_powers.json)."""
    import json
    here = __file__
    data_path = __import__("pathlib").Path(here).resolve().parent.parent / "data" / "trust_protector_powers.json"
    try:
        data = json.loads(data_path.read_text())
        return {p["value"]: p["label"] for p in data.get("powers", [])}
    except Exception as exc:  # pragma: no cover - defensive; JSON is versioned
        logger.warning(f"Could not load trust_protector_powers.json ({exc}); falling back to inline map")
        return _TRUST_PROTECTOR_POWER_LABELS_FALLBACK


# Fallback inline map — only used if the JSON file is missing/unreadable at runtime.
_TRUST_PROTECTOR_POWER_LABELS_FALLBACK = {
    "remove_or_replace_trustee": "Remove or replace a trustee",
    "amend_for_tax": "Amend the trust for tax efficiency",
    "veto_distributions": "Veto a proposed distribution",
    "add_or_remove_beneficiaries": "Add or remove beneficiaries",
    "resolve_disputes": "Resolve disputes between trustees or beneficiaries",
    "change_situs": "Change the trust's jurisdiction or situs",
    "terminate_trust": "Terminate the trust",
}




def _public_doc(doc: dict, *, exclude_file_content: bool = False) -> dict:
    """Remove internal identity/secrets and non-JSON file payloads from packet data."""
    excluded = {"_id", "user_id", "password", "password_hash", "hashed_password"}
    if exclude_file_content:
        excluded.add("file_content")
    return {key: value for key, value in doc.items() if key not in excluded}


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


async def _build_successor_packet(trust_id: str, user_id: str) -> dict:
    """Assemble the successor packet payload for one trust. Shared by the token path and the access-code path."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    scope = {"trust_id": trust_id, "user_id": user_id}
    entities = await db.entities.find(scope, {"_id": 0}).to_list(1000)
    # Beneficiary dashboard is backed by active unit certificates and class designations.
    beneficiaries = await db.trust_unit_certificates.find(
        {**scope, "status": "active"}, {"_id": 0}
    ).to_list(1000)
    beneficiaries += await db.class_beneficiaries.find(scope, {"_id": 0}).to_list(1000)
    bank_accounts = await db.bank_accounts.find(
        {**scope, "is_archived": {"$ne": True}}, {"_id": 0}
    ).to_list(1000)
    vault_documents = await db.vault_documents.find(
        scope, {"_id": 0, "file_content": 0}
    ).to_list(1000)
    governance_tasks = await db.governance_tasks.find(scope, {"_id": 0}).to_list(1000)
    tax_calendar = await db.tax_calendar.find(scope, {"_id": 0}).sort("due_date", 1).to_list(1000)
    # Tax-exempt trusts (508/501c3): hide income-tax deadlines from successor packets.
    tax_calendar = filter_income_tax_entries(tax_calendar, trust)

    return {
        "trust": _public_doc(trust),
        "entities": [_public_doc(doc) for doc in entities],
        "beneficiaries": [_public_doc(doc) for doc in beneficiaries],
        "bank_accounts": [_public_doc(doc) for doc in bank_accounts],
        "vault_documents": [_public_doc(doc, exclude_file_content=True) for doc in vault_documents],
        "governance_tasks": [_public_doc(doc) for doc in governance_tasks],
        "tax_calendar": [_public_doc(doc) for doc in tax_calendar],
        "successor_instructions": trust.get("successor_instructions", ""),
        "successor_name": trust.get("successor_trustee_name", ""),
        "trust_name": trust.get("name", "Trust"),
        "trustee_name": trust.get("trustee_names", ""),
    }


@router.get("/successor-access/{token}")
async def get_successor_packet(token: str):
    """Public, one-time successor packet access authenticated by the URL token."""
    token_hash = _hash_token(token)
    access = await db.successor_access.find_one({"token_hash": token_hash}, {"_id": 0})
    if not access:
        raise HTTPException(status_code=404, detail="Successor access link not found")

    now = datetime.now(timezone.utc)
    expires_at = _parse_datetime(access.get("expires_at"))
    if access.get("used_at") is not None or (expires_at is not None and expires_at <= now):
        raise HTTPException(status_code=410, detail="This successor access link has expired or already been used")

    # The used_at predicate makes the one-time credential atomic under concurrent opens.
    used_at = now.isoformat()
    claimed = await db.successor_access.find_one_and_update(
        # Re-check expiry in the atomic claim so a request racing the TTL/check
        # boundary can never consume an already-expired credential.
        {"token_hash": token_hash, "used_at": None, "expires_at": {"$gt": now}},
        {"$set": {"used_at": used_at}},
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise HTTPException(status_code=410, detail="This successor access link has expired or already been used")

    packet = await _build_successor_packet(claimed["trust_id"], claimed["user_id"])
    await log_audit_event(
        claimed["user_id"], "successor_packet_viewed", "trust", claimed["trust_id"],
        {"viewed_at": used_at, "expires_at": claimed.get("expires_at")},
    )
    return jsonable_encoder(packet)


# Existing send flow follows.

@router.post("/trusts/{trust_id}/successor/send")
async def send_successor_packet(trust_id: str, user: dict = Depends(require_write_access),
                                _stepup: None = Depends(require_2fa_stepup)):
    """Generate a one-time, expiring access token and email the successor a secure packet link.

    Requires a designated successor with an email on the trust record. The email
    link is valid for 30 days and can be used once (M1: send only; the access
    view is delivered in M2).
    """
    user = await require_org_grant(trust_id, min_level=GrantLevel.preparer, user=user)
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    successor_email = (trust.get("successor_trustee_email") or "").strip()
    if not successor_email:
        raise HTTPException(
            status_code=400,
            detail="No successor trustee email set. Add one in Settings > Trust Profile before sending.",
        )

    successor_name = (trust.get("successor_trustee_name") or "").strip() or successor_email

    # Generate a high-entropy one-time token (store only the hash)
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SUCCESSOR_LINK_TTL_DAYS)

    await db.successor_access.insert_one({
        "token_hash": token_hash,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "kind": "invite_token",
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "used_at": None,
    })

    method = trust.get("successor_access_method") or "access_code"
    packet_url = f"{email_service.app_url}/successor-access/{raw_token}"

    # Send the email
    if not email_service.is_configured:
        # Still record the token but surface that email did not send
        logger.warning(f"Email service not configured - successor packet link created but not sent for trust {trust_id}")
        await log_audit_event(
            user["user_id"], "successor_packet_link_created", "trust", trust_id,
            {"to_email": successor_email, "sent": False, "reason": "email_not_configured", "expires_at": expires_at.isoformat()},
        )
        return {
            "status": "not_sent",
            "message": "Email service is not configured. The secure link was created but not sent.",
            "expires_at": expires_at.isoformat(),
        }

    result = await email_service.send_successor_packet_email(
        to_email=successor_email,
        successor_name=successor_name,
        trust_name=trust.get("name") or "Trust",
        trustee_name=(trust.get("trustee_names") or user.get("name") or "The trustee"),
        packet_url=packet_url,
        access_method=method,
    )

    sent = result.get("status") == "sent"
    await log_audit_event(
        user["user_id"], "successor_packet_sent", "trust", trust_id,
        {"to_email": successor_email, "sent": sent, "expires_at": expires_at.isoformat(), "method": method},
    )

    # Item 2/5: org activity feed entry — additive, best-effort
    # (no natural free-text stamp field on the packet; activity log only)
    from services.org_activity import build_org_attribution, log_org_activity
    attribution, org_id = await build_org_attribution(trust_id, user)
    if attribution:
        await log_org_activity(
            trust_id=trust_id, actor=user, action="successor_packet_sent",
            attribution=attribution, org_id=org_id,
        )

    if not sent:
        logger.error(f"Failed to send successor packet email for trust {trust_id}: {result}")
        raise HTTPException(
            status_code=502,
            detail="The email could not be sent. Please try again, and contact support if the problem persists.",
        )

    return {
        "status": "sent",
        "message": f"Packet sent to {successor_email}",
        "to_email": successor_email,
        "expires_at": expires_at.isoformat(),
    }


@router.post("/trusts/{trust_id}/protector/appoint")
async def send_trust_protector_appointment(trust_id: str, user: dict = Depends(require_write_access)):
    """Send a trust protector appointment notification."""
    user = await require_org_grant(trust_id, min_level=GrantLevel.preparer, user=user)
    """Notify the designated trust protector of their appointment, outlining their role and requested powers.

    Mirrors the successor trustee send flow but sends a plain appointment notice (no packet access link).
    """
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    protector_email = (trust.get("trust_protector_email") or "").strip()
    if not protector_email:
        raise HTTPException(
            status_code=400,
            detail="No trust protector email set. Add one in Settings > People > Trust Protector before sending.",
        )

    protector_name = (trust.get("trust_protector_name") or "").strip() or protector_email
    powers = _power_labels(trust.get("trust_protector_powers") or [])

    if not email_service.is_configured:
        await log_audit_event(
            user["user_id"], "trust_protector_notice_created", "trust", trust_id,
            {"to_email": protector_email, "sent": False, "reason": "email_not_configured"},
        )
        return {
            "status": "not_sent",
            "message": "Email service is not configured. The notice was not sent.",
        }

    result = await email_service.send_trust_protector_appointment_email(
        to_email=protector_email,
        protector_name=protector_name,
        trust_name=trust.get("name") or "Trust",
        trustee_name=(trust.get("trustee_names") or user.get("name") or "The trustee"),
        powers_list=powers,
    )

    sent = result.get("status") == "sent"
    await log_audit_event(
        user["user_id"], "trust_protector_notice_sent", "trust", trust_id,
        {"to_email": protector_email, "sent": sent, "powers": powers},
    )

    # Item 2/5: org activity feed entry — additive, best-effort
    from services.org_activity import build_org_attribution, log_org_activity
    attribution, org_id = await build_org_attribution(trust_id, user)
    if attribution:
        await log_org_activity(
            trust_id=trust_id, actor=user, action="trust_protector_appointment_sent",
            attribution=attribution, org_id=org_id,
        )

    if not sent:
        logger.error(f"Failed to send trust protector appointment email for trust {trust_id}: {result}")
        raise HTTPException(
            status_code=502,
            detail="The email could not be sent. Please try again, and contact support if the problem persists.",
        )

    return {
        "status": "sent",
        "message": f"Appointment notice sent to {protector_email}",
        "to_email": protector_email,
    }


def _hash_token(raw_token: str) -> str:
    """Hash a raw access token for storage. Only the hash is persisted."""
    import hashlib
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ==================== ACCESS-CODE METHOD (Jeff 2026-10-16) ====================
# Trustee chooses how a successor gets in: an access code (default, instant)
# or death-certificate verification (human-reviewed). Packet/email copy tells
# the successor which process is active.


class SuccessorMethodUpdate(BaseModel):
    method: Literal["access_code", "death_cert"]


def _hash_code(code: str) -> str:
    """Access codes are stored hashed (normalized), never in plaintext."""
    return hashlib.sha256(_normalize_code(code).encode("utf-8")).hexdigest()


@router.get("/trusts/{trust_id}/successor/access-status")
async def get_successor_access_status(trust_id: str, user: dict = Depends(get_current_user)):
    """Trustee view of the successor access setup: active method, code state, claims."""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0, "successor_access_method": 1, "successor_trustee_name": 1,
         "successor_trustee_email": 1, "name": 1},
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    method = trust.get("successor_access_method") or "access_code"
    code_doc = await db.successor_access.find_one(
        {"trust_id": trust_id, "kind": "access_code", "revoked_at": None},
        {"_id": 0, "code_hint": 1, "created_at": 1, "first_used_at": 1, "use_count": 1},
    )
    pending_claims = await db.successor_claims.count_documents(
        {"trust_id": trust_id, "status": "pending"}
    )
    return jsonable_encoder({
        "method": method,
        "code_set": code_doc is not None,
        "code_hint": (code_doc or {}).get("code_hint"),
        "code_created_at": (code_doc or {}).get("created_at"),
        "code_first_used_at": (code_doc or {}).get("first_used_at"),
        "code_use_count": (code_doc or {}).get("use_count", 0),
        "pending_claims": pending_claims,
        "successor_name": trust.get("successor_trustee_name", ""),
        "successor_email": trust.get("successor_trustee_email", ""),
    })


@router.post("/trusts/{trust_id}/successor/code")
async def generate_successor_code(trust_id: str, user: dict = Depends(require_write_access),
                                  _stepup: None = Depends(require_2fa_stepup)):
    """Generate (or rotate) the successor access code. Raw code returned once; only the hash is stored."""
    user = await require_org_grant(trust_id, min_level=GrantLevel.preparer, user=user)
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    raw_code = _generate_code()
    now = datetime.now(timezone.utc).isoformat()

    # Retire any active code for this trust (rotation), then store the new one.
    await db.successor_access.update_many(
        {"trust_id": trust_id, "kind": "access_code", "revoked_at": None},
        {"$set": {"revoked_at": now, "revoked_reason": "rotated"}},
    )
    code_hint = raw_code[:4] + "-••••-••••-" + raw_code[-4:]
    await db.successor_access.insert_one({
        "kind": "access_code",
        "code_hash": _hash_code(raw_code),
        "code_hint": code_hint,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "created_at": now,
        "first_used_at": None,
        "last_used_at": None,
        "use_count": 0,
        "revoked_at": None,
    })
    # Selecting/access provisioning is the trustee's explicit choice — record it.
    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": {"successor_access_method": "access_code"}},
    )
    await log_audit_event(
        user["user_id"], "successor_code_generated", "trust", trust_id,
        {"code_hint": code_hint, "rotated": True},
    )
    successor_notified = await _notify_successor_update(trust, "access_code", "code_generated")
    return jsonable_encoder({
        "code": raw_code,           # shown once — never retrievable again
        "code_hint": code_hint,
        "method": "access_code",
        "successor_notified": successor_notified,
    })


@router.delete("/trusts/{trust_id}/successor/code")
async def revoke_successor_code(trust_id: str, user: dict = Depends(get_current_user),
                                _stepup: None = Depends(require_2fa_stepup)):
    """Revoke the active successor access code. The successor can no longer enter it."""
    user = await require_org_grant(trust_id, min_level=GrantLevel.preparer, user=user)
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    now = datetime.now(timezone.utc).isoformat()
    result = await db.successor_access.update_many(
        {"trust_id": trust_id, "kind": "access_code", "revoked_at": None},
        {"$set": {"revoked_at": now, "revoked_reason": "revoked_by_trustee", "revoked_by": user["user_id"]}},
    )
    await log_audit_event(
        user["user_id"], "successor_code_revoked", "trust", trust_id,
        {"count": result.modified_count},
    )
    return {"status": "revoked", "count": result.modified_count}


@router.post("/trusts/{trust_id}/successor/method")
async def set_successor_method(trust_id: str, payload: SuccessorMethodUpdate,
                               user: dict = Depends(require_write_access),
                               _stepup: None = Depends(require_2fa_stepup)):
    """Set the successor access method: 'access_code' (default) or 'death_cert'. Jeff's trustee-choice model."""
    user = await require_org_grant(trust_id, min_level=GrantLevel.preparer, user=user)
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    method = payload.method
    previous = trust.get("successor_access_method") or "access_code"
    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": {"successor_access_method": method}},
    )
    await log_audit_event(
        user["user_id"], "successor_method_changed", "trust", trust_id,
        {"from": previous, "to": method},
    )
    # Jeff fix 2026-10-16: the successor is told about the new process right away —
    # the "Send Packet" email is no longer the only thing that explains the method.
    trust_after = dict(trust)
    trust_after["successor_access_method"] = method
    successor_notified = await _notify_successor_update(
        trust_after, method, "method_access_code" if method == "access_code" else "method_death_cert",
    )
    return {"method": method, "previous": previous, "successor_notified": successor_notified}


# ==================== PUBLIC CLAIM ENDPOINTS ====================

class SuccessorCodeClaim(BaseModel):
    code: str


# Successor update notifications are rate-limited so a trustee flicking the method switch
# back and forth can't spam their successor (Jeff fix 2026-10-16 — successor stays informed).
SUCCESSOR_NOTIFY_MIN_INTERVAL_SECONDS = 15 * 60
_successor_notified_at: dict = {}  # trust_id -> last datetime a method-update email went out


async def _notify_successor_update(trust: dict, method: str, context: str) -> bool:
    """Email the successor trustee a short note describing the process their trustee chose.

    Called when the method changes or a new access code is generated, so the successor's
    mental model always matches reality without waiting for the trustee to press
    "Send Packet". Rate-limited to one email per trust per 15 minutes. Returns True
    when an email actually went out.
    """
    try:
        successor_email = (trust.get("successor_trustee_email") or "").strip()
        if not successor_email or not email_service.is_configured:
            return False
        now = datetime.now(timezone.utc)
        last = _successor_notified_at.get(trust["trust_id"])
        if last and (now - last).total_seconds() < SUCCESSOR_NOTIFY_MIN_INTERVAL_SECONDS:
            return False
        _successor_notified_at[trust["trust_id"]] = now
        context_method = "access_code" if method == "access_code" else "death_cert"
        block_html = _method_update_block(context).replace(
            "PLACEHOLDER_URL", f"{email_service.app_url}/successor-access")
        await email_service.send_templated_email(
            to_email=successor_email,
            template_name="successor_update",
            template_data={
                "successor_name": trust.get("successor_trustee_name") or "there",
                "trust_name": trust.get("name") or "Trust",
                "trustee_name": trust.get("trustee_names") or "The TrustOffice Team",
                "packet_url": f"{email_service.app_url}/successor-access",
                "method_block_html": block_html,
                "method_block_text": _method_update_block_text(context),
            },
            to_name=trust.get("successor_trustee_name"),
            tag="successor_update",
            metadata={"email_type": "successor_update", "context": context,
                      "method": context_method},
        )
        return True
    except Exception:
        # Never let a notification failure break the trustee's action.
        logger.exception("successor update email failed for trust %s", trust.get("trust_id"))
        return False


def _method_update_block(context: str) -> str:
    """One-paragraph explanation of the newly active process (HTML), for update emails."""
    if context == "code_generated":
        return (
            "<p><strong>Update:</strong> your access code was just generated or replaced. "
            "Ask the trustee for the current code, then enter it on the Successor Access page — "
            "the full packet opens instantly, any time.</p>"
            "<p style=\"text-align: center; margin: 20px 0;\">"
            "<a href=\"PLACEHOLDER_URL\" class=\"button\">Successor Access — Enter Your Code</a></p>"
        )
    if context == "method_access_code":
        return (
            "<p><strong>Update:</strong> the trustee has selected the <strong>access-code process</strong> "
            "for your packet. They'll share a private access code with you. Enter it on the Successor "
            "Access page and the full packet opens instantly — no paperwork, no waiting, any time.</p>"
            "<p style=\"text-align: center; margin: 20px 0;\">"
            "<a href=\"PLACEHOLDER_URL\" class=\"button\">Successor Access — Enter Your Code</a></p>"
        )
    return (
        "<p><strong>Update:</strong> the trustee has selected the <strong>death-certificate "
        "verification process</strong> for your packet. When the time comes, submit the death "
        "certificate and your ID through the Successor Access page — our team reviews each request "
        "personally, and you'll get your secure packet link by email once it's approved. Nothing is "
        "visible to anyone until then.</p>"
        "<p style=\"text-align: center; margin: 20px 0;\">"
        "<a href=\"PLACEHOLDER_URL\" class=\"button\">Successor Access — Submit When Needed</a></p>"
    )


def _method_update_block_text(context: str) -> str:
    if context == "code_generated":
        return (
            "Update: your access code was just generated or replaced. Ask the trustee for the "
            "current code, then enter it on the Successor Access page - the full packet opens "
            "instantly, any time."
        )
    if context == "method_access_code":
        return (
            "Update: the trustee has selected the access-code process for your packet. They'll "
            "share a private access code with you. Enter it on the Successor Access page and the "
            "full packet opens instantly - no paperwork, no waiting, any time."
        )
    return (
        "Update: the trustee has selected the death-certificate verification process for your "
        "packet. When the time comes, submit the death certificate and your ID through the "
        "Successor Access page - our team reviews each request personally, and you'll get your "
        "secure packet link by email once it's approved. Nothing is visible to anyone until then."
    )


async def _notify_trustee_code_used(access_doc: dict, trust: dict) -> None:
    """Email the trustee when their successor uses the access code.

    First use: immediate. Later uses: max one email per day (digest behavior).
    """
    try:
        user_doc = await db.users.find_one(
            {"user_id": access_doc.get("user_id")}, {"_id": 0, "email": 1, "name": 1}
        )
        trustee_email = (user_doc or {}).get("email")
        if not trustee_email or not email_service.is_configured:
            return
        now = datetime.now(timezone.utc)
        last_used = _parse_datetime(access_doc.get("last_used_at") or access_doc.get("first_used_at"))
        # First use always emails; repeat uses email at most daily.
        if last_used and (now - last_used).total_seconds() < 86400:
            return
        await email_service.send_templated_email(
            to_email=trustee_email,
            template_name="successor_code_used",
            template_data={
                "trustee_name": (user_doc or {}).get("name") or trust.get("trustee_names") or "there",
                "trust_name": trust.get("name") or "your trust",
                "successor_name": trust.get("successor_trustee_name") or "Your successor trustee",
                "use_count": (access_doc.get("use_count") or 0) + 1,
                "used_at": now.strftime("%B %d, %Y at %I:%M %p"),
            },
            tag="successor_code_used",
            metadata={"email_type": "successor_code_used"},
        )
    except Exception:
        # Notification is best-effort; never block the successor's packet access on it.
        logger.exception("successor_code_used notification failed (non-fatal)")


@router.post("/successor-access/claim-code")
async def claim_successor_code(
    payload: SuccessorCodeClaim,
    request: Request,
    _rl: None = Depends(_auth_rate_limit(SUCCESSOR_CODE_CLAIM_RATE, SUCCESSOR_CODE_CLAIM_WINDOW)),
):
    """Public: successor enters the access code the trustee shared. Reusable until revoked; every use logged."""
    code_hash = _hash_code(_normalize_code(payload.code))
    if len(code_hash) != 64:
        raise HTTPException(status_code=400, detail="That code doesn't look right. Check it and try again.")

    now = datetime.now(timezone.utc)
    access = await db.successor_access.find_one_and_update(
        {"code_hash": code_hash, "kind": "access_code", "revoked_at": None},
        {
            "$set": {"last_used_at": now.isoformat()},
            "$inc": {"use_count": 1},
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not access:
        raise HTTPException(status_code=404, detail="That access code isn't valid. Ask the trustee to confirm it.")
    if not access.get("first_used_at"):
        # First successful use claims the "first" timestamp atomically enough for
        # notification behavior (digest gating reads this field).
        await db.successor_access.update_one(
            {"code_hash": code_hash, "first_used_at": None},
            {"$set": {"first_used_at": now.isoformat()}},
        )

    trust = await db.trusts.find_one(
        {"trust_id": access["trust_id"], "user_id": access["user_id"]}, {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    packet = await _build_successor_packet(access["trust_id"], access["user_id"])
    await log_audit_event(
        access["user_id"], "successor_code_used", "trust", access["trust_id"],
        {"use_count": access.get("use_count"), "first_used_at": access.get("first_used_at")},
    )
    await _notify_trustee_code_used(access, trust)
    return jsonable_encoder(packet)


class SuccessorVerificationClaim(BaseModel):
    trust_token: str            # the standing packet token emailed to the successor earlier
    claimant_name: str
    claimant_email: str
    claimant_phone: str = ""
    notes: str = ""


@router.post("/successor-access/claim-verification")
async def claim_successor_verification(
    payload: SuccessorVerificationClaim,
    file: UploadFile = File(...),
    _rl: None = Depends(_auth_rate_limit(SUCCESSOR_CODE_CLAIM_RATE, SUCCESSOR_CODE_CLAIM_WINDOW)),
):
    """Public: death-certificate method. Successor uploads the certificate; a human reviews before any access.

    Nothing about the trust is disclosed here — the claim only records intent + documents.
    """
    # Validate the standing invite token so the claim is attached to a real trust.
    token_hash = _hash_token(payload.trust_token)
    access = await db.successor_access.find_one({"token_hash": token_hash}, {"_id": 0})
    if not access:
        raise HTTPException(status_code=404, detail="We couldn't find that successor invitation.")

    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith(("image/", "application/pdf")):
        raise HTTPException(status_code=400, detail="Upload the certificate as a PDF or a photo (JPG/PNG).")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="That file is larger than 10 MB — upload a photo or compressed copy.")

    now = datetime.now(timezone.utc).isoformat()
    claim_id = f"claim_{uuid.uuid4().hex[:12]}"
    await db.successor_claims.insert_one({
        "claim_id": claim_id,
        "trust_id": access["trust_id"],
        "user_id": access["user_id"],
        "method": "death_cert",
        "status": "pending",
        "claimant_name": payload.claimant_name.strip(),
        "claimant_email": payload.claimant_email.strip().lower(),
        "claimant_phone": payload.claimant_phone.strip(),
        "notes": payload.notes.strip(),
        "certificate_name": file.filename,
        "certificate_content_type": content_type,
        "certificate_content": contents,
        "submitted_at": now,
        "reviewed_at": None,
        "reviewed_by": None,
        "review_reason": None,
    })
    await log_audit_event(
        access["user_id"], "successor_claim_submitted", "trust", access["trust_id"],
        {"claim_id": claim_id, "claimant_email": payload.claimant_email.strip().lower()},
    )
    return {
        "status": "submitted",
        "claim_id": claim_id,
        "message": "Thank you. Our team reviews every request personally — you'll hear from us by email once it's approved.",
    }


@router.post("/admin/successor-claims/{claim_id}/approve")
async def approve_successor_claim(claim_id: str, user: dict = Depends(get_current_user),
                                  _stepup: None = Depends(require_2fa_stepup)):
    """Review-lane: approve a death-certificate claim and email the successor a one-time packet link."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin review required")

    claim = await db.successor_claims.find_one({"claim_id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.get("status") != "pending":
        raise HTTPException(status_code=409, detail="This claim was already reviewed")

    now = datetime.now(timezone.utc)
    trust = await db.trusts.find_one({"trust_id": claim["trust_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    raw_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=SUCCESSOR_LINK_TTL_DAYS)
    await db.successor_access.insert_one({
        "token_hash": _hash_token(raw_token),
        "trust_id": claim["trust_id"],
        "user_id": claim["user_id"],
        "kind": "claim_release",
        "claim_id": claim_id,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "used_at": None,
    })
    packet_url = f"{email_service.app_url}/successor-access/{raw_token}"

    sent = False
    if email_service.is_configured:
        result = await email_service.send_successor_packet_email(
            to_email=claim["claimant_email"],
            successor_name=claim["claimant_name"],
            trust_name=trust.get("name") or "Trust",
            trustee_name=trust.get("trustee_names") or "The trustee",
            packet_url=packet_url,
        )
        sent = result.get("status") == "sent"

    await db.successor_claims.update_one(
        {"claim_id": claim_id},
        {"$set": {"status": "approved", "reviewed_at": now.isoformat(),
                  "reviewed_by": user.get("user_id"), "packet_sent": sent}},
    )
    await log_audit_event(
        user["user_id"], "successor_claim_approved", "trust", claim["trust_id"],
        {"claim_id": claim_id, "packet_sent": sent},
    )
    return {"claim_id": claim_id, "status": "approved", "packet_sent": sent}


@router.post("/admin/successor-claims/{claim_id}/reject")
async def reject_successor_claim(claim_id: str, reason: str = Form(""),
                                 user: dict = Depends(get_current_user),
                                 _stepup: None = Depends(require_2fa_stepup)):
    """Review-lane: reject a claim; the claimant can re-submit with better documents."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin review required")

    claim = await db.successor_claims.find_one({"claim_id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if claim.get("status") != "pending":
        raise HTTPException(status_code=409, detail="This claim was already reviewed")

    now = datetime.now(timezone.utc)
    await db.successor_claims.update_one(
        {"claim_id": claim_id},
        {"$set": {"status": "rejected", "reviewed_at": now.isoformat(),
                  "reviewed_by": user.get("user_id"), "review_reason": reason.strip()}},
    )
    await log_audit_event(
        user["user_id"], "successor_claim_rejected", "trust", claim["trust_id"],
        {"claim_id": claim_id, "reason": reason.strip()},
    )
    return {"claim_id": claim_id, "status": "rejected"}


@router.get("/admin/successor-claims")
async def list_successor_claims(user: dict = Depends(get_current_user)):
    """Review-lane: pending death-certificate claims (documents NOT returned here — view in secure admin UI)."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin review required")
    claims = await db.successor_claims.find(
        {"status": "pending"},
        {"_id": 0, "certificate_content": 0},
    ).sort("submitted_at", 1).to_list(200)
    return jsonable_encoder(claims)
