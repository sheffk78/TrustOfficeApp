# Email→Minutes router (W3, Jeff priority 4, 2026-09-25)
# Postmark inbound webhook for {slug}@minutes.trustoffice.app.
#
# Flow: Postmark POST → trust lookup by minutes_slug → sender allowlist
# (trust owner email + trust_parties) → extract meeting signal → AI draft →
# minutes_records row with status="draft", source="email_capture".
# Never auto-finalizes; the trustee reviews in the existing minutes UI.
#
# Tier gating: Estate ($149/mo) and Advisor ($399/mo) — same as email archive.
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from database import db
from routers.email_archive import ALLOWED_PLANS
from routers.subscriptions import get_subscription_state
from services.email_minutes_service import (
    extract_meeting_signal,
    is_sender_allowed,
    thread_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["email-minutes"])

MINUTES_INBOUND_DOMAIN = os.environ.get("EMAIL_MINUTES_DOMAIN", "minutes.trustoffice.app")
MINUTES_WEBHOOK_SECRET = os.environ.get("POSTMARK_MINUTES_SECRET", "")


@router.post("/webhooks/postmark-inbound-minutes/{secret}")
async def postmark_minutes_webhook(secret: str, request: Request):
    """Receive an inbound meeting-notes email and create a minutes DRAFT.

    Same Postmark payload contract as the archive webhook. The slug is the
    local part of the address in BccFull/CcFull/ToFull pointing at the
    minutes domain.
    """
    if MINUTES_WEBHOOK_SECRET and secret != MINUTES_WEBHOOK_SECRET:
        logger.warning("Postmark minutes webhook: invalid secret")
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Postmark minutes: failed to parse body: {e}")
        return {"status": "ignored", "reason": "invalid_payload"}

    from_email = payload.get("FromFull", {}).get("Email", payload.get("From", ""))
    from_name = payload.get("FromFull", {}).get("Name", payload.get("FromName", ""))
    subject = payload.get("Subject", "(no subject)")
    text_body = payload.get("TextBody", "") or payload.get("HtmlBody", "") or ""
    message_id = payload.get("MessageId", "")

    # Find the minutes-domain address among recipients
    slug = None
    for field in ("BccFull", "CcFull", "ToFull"):
        for r in payload.get(field, []) or []:
            email = r.get("Email", "") if isinstance(r, dict) else (r if isinstance(r, str) else "")
            if email and MINUTES_INBOUND_DOMAIN in email.lower():
                slug = email.split("@")[0].lower()
                break
        if slug:
            break
    if not slug:
        return {"status": "ignored", "reason": "no_minutes_address"}

    trust = await db.trusts.find_one({
        "minutes_slug": slug,
        "minutes_email_enabled": True,
    })
    if not trust:
        logger.info(f"Postmark minutes: no enabled trust for slug '{slug}'")
        return {"status": "ignored", "reason": "no_matching_trust"}

    # Tier gate (defense-in-depth)
    state = await get_subscription_state(trust["user_id"])
    if state.plan_type not in ALLOWED_PLANS:
        logger.warning(f"Postmark minutes: trust {trust['trust_id']} plan {state.plan_type} not eligible")
        return {"status": "ignored", "reason": "plan_not_eligible"}

    # Sender allowlist: owner + trust parties with an email
    allowed = [trust.get("user_email") or ""]
    parties = await db.trust_parties.find(
        {"trust_id": trust["trust_id"]}
    ).to_list(500)
    allowed.extend(p.get("email", "") for p in parties)
    if not is_sender_allowed(from_email, allowed):
        logger.warning(f"Postmark minutes: sender {from_email} not on allowlist for {trust['trust_id']}")
        return {"status": "ignored", "reason": "sender_not_allowed"}

    # Dedup by MessageId
    if message_id:
        dup = await db.minutes_records.find_one({"source_message_id": message_id})
        if dup:
            return {"status": "ignored", "reason": "duplicate"}

    signal = extract_meeting_signal(text_body)
    tkey = thread_key(subject, message_id, payload.get("References", ""))

    minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": trust["trust_id"],
        "user_id": trust["user_id"],
        "minutes_type": signal["minutes_type"],
        "template_type": None,
        "meeting_date": signal["meeting_date"] or now[:10],
        "participants_text": ", ".join(signal["participants"]) or from_name or from_email,
        "decisions_text": "\n".join(f"- {d}" for d in signal["decisions"]) or "(extracted from email — review and complete)",
        "sections": [],
        "template_data": None,
        "status": "draft",
        "is_retroactive": False,
        "retroactive_reason": None,
        "retroactive_trustees_aware": None,
        "retroactive_type": None,
        "manually_edited": False,
        "created_at": now,
        "updated_at": now,
        "source": "email_capture",
        "source_email_from": from_email,
        "source_subject": subject,
        "source_thread_key": tkey,
        "source_message_id": message_id,
    }
    await db.minutes_records.insert_one(minutes_doc)
    logger.info(f"Postmark minutes: created draft {minutes_id} for trust {trust['trust_id']} (thread: {tkey})")
    return {"status": "logged", "minutes_id": minutes_id}


async def ensure_email_minutes_indexes():
    await db.trusts.create_index(
        "minutes_slug",
        name="minutes_slug_unique",
        unique=True,
        partialFilterExpression={"minutes_slug": {"$type": "string"}},
    )
    await db.minutes_records.create_index(
        "source_message_id",
        name="minutes_message_dedup",
        sparse=True,
        unique=True,
    )