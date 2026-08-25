# Email Archive router — BCC capture via Postmark inbound email
# Enables per-trust email addresses ({slug}@archive.trustoffice.app)
# Trustee BCCs the address on outbound emails → auto-logged in communications
#
# Tier gating: Estate ($149/mo) and Advisor ($399/mo) only.
# Trustee ($79/mo) gets 403 with upgrade message.

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from datetime import datetime, timezone
from typing import Optional
import re
import uuid
import logging
import json
import os

from database import db
from dependencies import get_current_user, require_write_access
from routers.subscriptions import get_subscription_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["email-archive"])

INBOUND_DOMAIN = os.environ.get("EMAIL_ARCHIVE_DOMAIN", "archive.trustoffice.app")

# Plans allowed to use email archive
ALLOWED_PLANS = {"estate", "advisor"}

# Postmark inbound webhook secret — set via env var, included in webhook URL path
WEBHOOK_SECRET = os.environ.get("POSTMARK_INBOUND_SECRET", "")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(trust_name: str) -> str:
    """Convert trust name to URL-safe slug for email local part.
    Kohler Family Trust → kohler-family-trust"""
    slug = re.sub(r'[^a-z0-9]+', '-', trust_name.lower()).strip('-')
    slug = re.sub(r'-+', '-', slug)[:40]  # max 40 chars
    return slug


async def _generate_unique_slug(trust_name: str, trust_id: str) -> str:
    """Generate a slug, append short ID on collision with another trust."""
    base = _slugify(trust_name)
    if not base:
        base = f"trust-{trust_id[:8]}"

    # Check if this slug is already in use by a DIFFERENT trust
    existing = await db.trusts.find_one({
        "email_archive_slug": base,
        "trust_id": {"$ne": trust_id}
    })
    if not existing:
        return base

    # Collision — append short ID
    suffix = uuid.uuid4().hex[:4]
    return f"{base}-{suffix}"


async def _require_email_archive_tier(user: dict) -> None:
    """Raise 403 if the user's plan is not Estate or Advisor."""
    state = await get_subscription_state(user["user_id"])
    if state.plan_type not in ALLOWED_PLANS:
        raise HTTPException(
            status_code=403,
            detail="Email Archive is available on Estate and Advisor plans. Upgrade to enable this feature."
        )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/trusts/{trust_id}/email-archive/enable")
async def enable_email_archive(trust_id: str, user: dict = Depends(require_write_access)):
    """Enable BCC email capture for a trust. Generates a per-trust archive address.
    Tier-gated: only Estate and Advisor plans can enable."""
    # Tier gate
    await _require_email_archive_tier(user)

    # Find the trust
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Already enabled? Return existing address
    if trust.get("email_archive_enabled"):
        return {
            "enabled": True,
            "address": trust.get("email_archive_slug"),
            "full_address": f"{trust.get('email_archive_slug')}@{INBOUND_DOMAIN}",
            "enabled_at": trust.get("email_archive_enabled_at"),
            "message": "Email Archive is already enabled for this trust."
        }

    # Generate slug
    slug = await _generate_unique_slug(trust.get("name", "trust"), trust_id)

    # Update trust record
    now = datetime.now(timezone.utc).isoformat()
    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": {
            "email_archive_enabled": True,
            "email_archive_slug": slug,
            "email_archive_enabled_at": now,
        }}
    )

    logger.info(f"Email archive enabled for trust {trust_id}: {slug}@{INBOUND_DOMAIN}")

    return {
        "enabled": True,
        "address": slug,
        "full_address": f"{slug}@{INBOUND_DOMAIN}",
        "enabled_at": now,
        "message": "Email Archive enabled. BCC this address on emails to beneficiaries to auto-log them."
    }


@router.post("/trusts/{trust_id}/email-archive/disable")
async def disable_email_archive(trust_id: str, user: dict = Depends(require_write_access)):
    """Disable BCC email capture for a trust. Historical entries are preserved."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    if not trust.get("email_archive_enabled"):
        return {"enabled": False, "message": "Email Archive is not enabled for this trust."}

    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"$set": {
            "email_archive_enabled": False,
        }}
    )

    logger.info(f"Email archive disabled for trust {trust_id}")

    return {
        "enabled": False,
        "message": "Email Archive disabled. Existing captured emails are preserved. The address will no longer accept new emails."
    }


@router.get("/trusts/{trust_id}/email-archive/status")
async def email_archive_status(trust_id: str, user: dict = Depends(get_current_user)):
    """Get the email archive status for a trust."""
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"email_archive_enabled": 1, "email_archive_slug": 1, "email_archive_enabled_at": 1, "name": 1}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    # Check tier eligibility
    state = await get_subscription_state(user["user_id"])
    eligible = state.plan_type in ALLOWED_PLANS

    enabled = trust.get("email_archive_enabled", False)
    slug = trust.get("email_archive_slug")

    return {
        "enabled": enabled,
        "eligible": eligible,
        "plan_type": state.plan_type,
        "address": slug,
        "full_address": f"{slug}@{INBOUND_DOMAIN}" if slug else None,
        "enabled_at": trust.get("email_archive_enabled_at"),
        "trust_name": trust.get("name"),
    }


@router.get("/email-archive/addresses")
async def list_archive_addresses(user: dict = Depends(get_current_user)):
    """List all email archive addresses for the current user's trusts."""
    trusts = await db.trusts.find(
        {
            "user_id": user["user_id"],
            "email_archive_enabled": True,
        },
        {"trust_id": 1, "name": 1, "email_archive_slug": 1, "email_archive_enabled_at": 1, "_id": 0}
    ).to_list(100)

    return {
        "addresses": [
            {
                "trust_id": t["trust_id"],
                "trust_name": t.get("name", ""),
                "address": t["email_archive_slug"],
                "full_address": f"{t['email_archive_slug']}@{INBOUND_DOMAIN}",
                "enabled_at": t.get("email_archive_enabled_at"),
            }
            for t in trusts
        ],
        "count": len(trusts),
    }


# ── Postmark Inbound Webhook ─────────────────────────────────────────────────

@router.post("/webhooks/postmark-inbound/{secret}")
async def postmark_inbound_webhook(secret: str, request: Request):
    """Receive inbound email from Postmark and log it as a communication.

    Postmark sends a JSON POST with the full email content whenever an email
    is received at any address @archive.trustoffice.app.

    The {secret} in the URL path must match POSTMARK_INBOUND_SECRET env var.
    """
    # Verify webhook secret
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        logger.warning("Postmark inbound webhook: invalid secret")
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    # Parse the Postmark inbound payload
    try:
        body = await request.body()
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"Postmark inbound: failed to parse body: {e}")
        return {"status": "ignored", "reason": "invalid_payload"}

    # Extract email fields
    from_email = payload.get("FromFull", {}).get("Email", payload.get("From", ""))
    from_name = payload.get("FromFull", {}).get("Name", payload.get("FromName", ""))
    subject = payload.get("Subject", "(no subject)")
    text_body = payload.get("TextBody", "")
    html_body = payload.get("HtmlBody", "")
    date_str = payload.get("Date", "")
    message_id = payload.get("MessageId", "")

    # Prefer text body; strip HTML if only HTML available
    content = text_body
    if not content and html_body:
        content = re.sub(r'<[^>]+>', '', html_body).strip()
    # Cap at 10,000 chars
    content = content[:10000] if content else ""

    # Find the archive address in CcFull or BccFull
    # The trustee BCCs the archive address — it appears in BccFull (or CcFull if CC'd)
    recipients = []
    for field in ["BccFull", "CcFull", "ToFull"]:
        field_recipients = payload.get(field, [])
        if isinstance(field_recipients, list):
            for r in field_recipients:
                if isinstance(r, dict):
                    recipients.append(r.get("Email", ""))
                elif isinstance(r, str):
                    recipients.append(r)

    # Find the matching archive address (ends with @archive.trustoffice.app)
    archive_address = None
    archive_slug = None
    for email in recipients:
        if email and INBOUND_DOMAIN in email.lower():
            archive_address = email
            archive_slug = email.split("@")[0].lower()
            break

    if not archive_slug:
        logger.info(f"Postmark inbound: no archive address found in recipients")
        return {"status": "ignored", "reason": "no_archive_address"}

    # Look up the trust by slug — must be enabled
    trust = await db.trusts.find_one({
        "email_archive_slug": archive_slug,
        "email_archive_enabled": True,
    })

    if not trust:
        logger.info(f"Postmark inbound: no enabled trust found for slug '{archive_slug}'")
        return {"status": "ignored", "reason": "no_matching_trust"}

    # Defense-in-depth: re-check tier eligibility
    state = await get_subscription_state(trust["user_id"])
    if state.plan_type not in ALLOWED_PLANS:
        logger.warning(f"Postmark inbound: trust {trust['trust_id']} user plan {state.plan_type} not eligible")
        return {"status": "ignored", "reason": "plan_not_eligible"}

    # Deduplicate by MessageId (Postmark may retry)
    if message_id:
        existing = await db.communications.find_one({"message_id": message_id})
        if existing:
            logger.info(f"Postmark inbound: duplicate message {message_id}, skipping")
            return {"status": "ignored", "reason": "duplicate"}

    # Extract To recipients for parties
    to_recipients = payload.get("ToFull", [])
    to_names = []
    if isinstance(to_recipients, list):
        for r in to_recipients:
            if isinstance(r, dict):
                to_names.append({"role": "recipient", "name": r.get("Name", r.get("Email", ""))})
            elif isinstance(r, str):
                to_names.append({"role": "recipient", "name": r})

    parties = [{"role": "trustee", "name": from_name or from_email}] + to_names

    # Parse the date
    comm_date = date_str or datetime.now(timezone.utc).isoformat()

    # Create the communication entry
    comm_id = f"comm_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "comm_id": comm_id,
        "trust_id": trust["trust_id"],
        "user_id": trust["user_id"],
        "comm_type": "email",
        "comm_type_label": "Email / Digital correspondence",
        "subject": subject,
        "content": content,
        "parties": parties,
        "direction": "outbound",  # trustee sent it (BCC'd)
        "document_ids": [],
        "action_required": False,
        "action_completed": False,
        "action_due": None,
        "tags": ["bcc-capture"],
        "source": "bcc_capture",
        "source_email_from": from_email,
        "source_email_to": [r if isinstance(r, str) else r.get("Email", "") for r in (to_recipients if isinstance(to_recipients, list) else [])],
        "message_id": message_id,
        "created_at": comm_date,
        "updated_at": now,
    }

    await db.communications.insert_one(doc)

    logger.info(f"Postmark inbound: logged communication {comm_id} for trust {trust['trust_id']} (slug: {archive_slug})")

    return {"status": "logged", "comm_id": comm_id}


# ── Indexes ──────────────────────────────────────────────────────────────────

async def ensure_email_archive_indexes():
    """Create indexes for email archive feature. Called at startup."""
    # Unique index on email_archive_slug (partial — only when exists)
    await db.trusts.create_index(
        "email_archive_slug",
        name="email_archive_slug_unique",
        unique=True,
        partialFilterExpression={"email_archive_slug": {"$type": "string"}}
    )

    # Index for webhook lookups: slug + enabled
    await db.trusts.create_index(
        [("email_archive_slug", 1), ("email_archive_enabled", 1)],
        name="email_archive_lookup"
    )

    # Dedup index on communications.message_id
    await db.communications.create_index(
        "message_id",
        name="message_id_dedup",
        sparse=True,
        unique=True
    )

    logger.info("Email archive indexes created")