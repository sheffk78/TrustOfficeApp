# Successor Trustee router - successor communication endpoints
import secrets
import uuid
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends
from pymongo import ReturnDocument

from fastapi.encoders import jsonable_encoder

from database import db
from dependencies import require_write_access
from email_service import email_service
from utils.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["successor"])

# One-time packet access link validity (30 days)
SUCCESSOR_LINK_TTL_DAYS = 30



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

    trust_id = claimed["trust_id"]
    user_id = claimed["user_id"]
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

    packet = {
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
    await log_audit_event(
        user_id, "successor_packet_viewed", "trust", trust_id,
        {"viewed_at": used_at, "expires_at": claimed.get("expires_at")},
    )
    return jsonable_encoder(packet)


# Existing send flow follows.

@router.post("/trusts/{trust_id}/successor/send")
async def send_successor_packet(trust_id: str, user: dict = Depends(require_write_access)):
    """Generate a one-time, expiring access token and email the successor a secure packet link.

    Requires a designated successor with an email on the trust record. The email
    link is valid for 30 days and can be used once (M1: send only; the access
    view is delivered in M2).
    """
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
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "used_at": None,
    })

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
    )

    sent = result.get("status") == "sent"
    await log_audit_event(
        user["user_id"], "successor_packet_sent", "trust", trust_id,
        {"to_email": successor_email, "sent": sent, "expires_at": expires_at.isoformat()},
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


def _hash_token(raw_token: str) -> str:
    """Hash a raw access token for storage. Only the hash is persisted."""
    import hashlib
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
