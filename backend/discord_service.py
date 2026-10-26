"""
Discord Webhook Service for TrustOffice
Sends notifications to Discord channels for lead events, alerts, and admin notifications.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

DISCORD_LEADS_WEBHOOK_URL = os.environ.get('DISCORD_LEADS_WEBHOOK_URL')
DISCORD_ALERTS_WEBHOOK_URL = os.environ.get('DISCORD_ALERTS_WEBHOOK_URL')
# #trustoffice-main channel (1479343804527153262) — pipeline health RED alerts.
DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL = os.environ.get('DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL') or DISCORD_ALERTS_WEBHOOK_URL
TRUSTOFFICE_MAIN_CHANNEL_ID = "1479343804527153262"

# Last-resort fallback webhook for ALERTS (the "Kit Leads Monitor" webhook).
# Hard-coded on purpose: it must keep working even when every alert env var
# is unconfigured, which is exactly the failure this fallback exists to
# prevent. The same webhook id is provisioned on the production service as
# DISCORD_ALERTS_WEBHOOK_URL / DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL.
DISCORD_ALERT_FALLBACK_WEBHOOK_URL = os.environ.get(
    'DISCORD_ALERT_FALLBACK_WEBHOOK_URL'
) or (
    "https://discord.com/api/webhooks/1545668684788539442/"
    "siGQryY9y2qc22SY5B6c3G_Lr1SSYxy7JX2GnrlxDdqKSJdYtCL9eaLmovpxIds-hLRM"
)


def _resolve_alert_webhook(primary: Optional[str]):
    """Resolve the webhook an ALERT should go to, with a hard fallback.

    Returns (webhook_url, used_fallback: bool).

    A monitor that silently drops its RED alert is the exact failure mode
    this module exists to prevent (2026-10-23 audit: the pipeline monitor
    went dark for weeks because both alert env vars were unset on the
    production service and the notifier returned success=False into a caller
    that never checked it). So when the primary alert webhook is
    unconfigured we fall back to the known-good alert webhook instead of
    dropping the alert.
    """
    if primary:
        return primary, False
    if DISCORD_ALERT_FALLBACK_WEBHOOK_URL:
        return DISCORD_ALERT_FALLBACK_WEBHOOK_URL, True
    return None, False


def missing_alert_webhook_env() -> list:
    """Names of the alert webhook env vars that are NOT configured.

    Used by the app-factory startup assertion so the monitoring layer can
    never go dark silently again.
    """
    missing = []
    if not DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL:
        missing.append("DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL")
    if not DISCORD_ALERTS_WEBHOOK_URL:
        missing.append("DISCORD_ALERTS_WEBHOOK_URL")
    return missing

# TrustOffice brand colors
NAVY = 0x010079
GOLD = 0xD5AD36
RUST = 0xB44040


async def send_discord_message(
    webhook_url: str,
    content: str,
    username: Optional[str] = "TrustOffice Bot",
    avatar_url: Optional[str] = None,
    embeds: Optional[list] = None
) -> Dict[str, Any]:
    """Send a message to a Discord webhook."""
    if not webhook_url:
        logger.warning("Discord webhook URL not configured — skipping notification")
        return {"success": False, "error": "Webhook URL not configured"}

    payload = {
        "content": content,
        "username": username,
    }
    if avatar_url:
        payload["avatar_url"] = avatar_url
    if embeds:
        payload["embeds"] = embeds

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "TrustOfficeBackend (https://trustoffice.app, 1.0)"},
            timeout=10.0,
        ) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=10.0
            )
            if response.status_code in [200, 204]:
                logger.info("Discord notification sent successfully")
                return {"success": True}
            else:
                logger.error(f"Discord webhook error: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
    except Exception as e:
        logger.error(f"Discord webhook exception: {str(e)}")
        return {"success": False, "error": str(e)}


def _stage_emoji(stage: str) -> str:
    """Return the emoji for a lead stage."""
    emojis = {
        "new": "🆕",
        "engaged": "📺",
        "warm": "📧",
        "converted": "✅",
        "lost": "❌",
    }
    return emojis.get(stage, "📋")


async def notify_new_lead(
    name: str,
    email: str,
    source: str,
    lead_stage: str = "new",
    phone: Optional[str] = None,
    ping_on_phone: bool = False,
) -> Dict[str, Any]:
    """Send a new lead notification to the leads Discord channel.

    ping_on_phone=True prepends a direct @mention of Kenneth when the lead has
    a phone number — he calls phone leads immediately, so the notification
    must actually interrupt him (web-form + FB-lead-ad capture both use this).
    TidyCal booking notifications omit the flag: that's an appointment, not a
    cold lead to call.
    """
    if not DISCORD_LEADS_WEBHOOK_URL:
        logger.info("Discord leads webhook not configured — skipping lead notification")
        return {"success": False, "error": "Not configured"}

    KENNETH_DISCORD_ID = "1479298864539373702"
    if ping_on_phone and phone:
        from phone_sanity import is_calling_quality
        if is_calling_quality(phone):
            content = (
                f"<@{KENNETH_DISCORD_ID}> **📞 Call now** — {name} · "
                f"{phone} · {email}"
            )
        else:
            # Junk-looking number (sequential sweep, repeated digits, placeholder):
            # surface it without interrupting Kenneth — 2026-10-26 Rhonda lesson
            # (typed 12345678910; line turned out to dial, so keep the number
            # visible and verifiable, just not ping-worthy).
            content = (
                f"**New phone lead** — {name} · {phone} · {email} via {source}\n"
                f"⚠️ Submitted phone failed sanity check (possible typo/fake) — verify before calling. Booking link: https://trustoffice.app/book-a-call/"
            )
    else:
        content = f"**New lead** — {name} ({email}) via {source}"

    embed = {
        "title": f"{_stage_emoji(lead_stage)} New Lead: {name}",
        "color": NAVY,
        "fields": [
            {"name": "Name", "value": name or "Not provided", "inline": True},
            {"name": "Email", "value": email, "inline": True},
            {"name": "Phone", "value": phone or "Not provided", "inline": True},
            {"name": "Source", "value": source or "direct", "inline": True},
            {"name": "Stage", "value": lead_stage.replace("_", " ").title(), "inline": True},
        ],
        "footer": {"text": "TrustOffice Lead Management"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    return await send_discord_message(
        webhook_url=DISCORD_LEADS_WEBHOOK_URL,
        content=content,
        embeds=[embed]
    )


async def notify_lead_stage_change(
    name: str,
    email: str,
    old_stage: str,
    new_stage: str,
    details: Optional[str] = None
) -> Dict[str, Any]:
    """Send a notification when a lead changes stage."""
    if not DISCORD_LEADS_WEBHOOK_URL:
        return {"success": False, "error": "Not configured"}

    embed = {
        "title": f"🔄 Lead Stage Change: {name}",
        "color": GOLD,
        "fields": [
            {"name": "Name", "value": name or "Not provided", "inline": True},
            {"name": "Email", "value": email, "inline": True},
            {"name": "From", "value": old_stage.replace("_", " ").title(), "inline": True},
            {"name": "To", "value": new_stage.replace("_", " ").title(), "inline": True},
        ],
        "footer": {"text": "TrustOffice Lead Management"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    if details:
        embed["fields"].append({"name": "Details", "value": details, "inline": False})

    return await send_discord_message(
        webhook_url=DISCORD_LEADS_WEBHOOK_URL,
        content=f"**Stage change** — {name} moved to {new_stage.replace('_', ' ').title()}",
        embeds=[embed]
    )


async def notify_alert(
    title: str,
    message: str,
    color: int = RUST,
    ping_kit: bool = False,
) -> Dict[str, Any]:
    """Send an alert to the alerts Discord channel (or leads channel as fallback).

    If ping_kit is True, prepends a mention of the Kit bot so Hermes triggers
    the agent to investigate and fix the error automatically — no cron or
    polling needed, the webhook mention IS the trigger.
    """
    webhook_url, used_fallback = _resolve_alert_webhook(
        DISCORD_ALERTS_WEBHOOK_URL or DISCORD_LEADS_WEBHOOK_URL
    )
    if not webhook_url:
        logger.error(
            "ALERT NOT SENT - no Discord webhook configured for alerts "
            "(DISCORD_ALERTS_WEBHOOK_URL, DISCORD_LEADS_WEBHOOK_URL and the "
            "hard-coded fallback are all unset). The alert was DROPPED."
        )
        return {"success": False, "error": "Not configured", "dropped": True}
    if used_fallback:
        logger.error(
            "ALERT WEBHOOK NOT CONFIGURED - falling back to the hard-coded "
            "alert webhook. Set DISCORD_ALERTS_WEBHOOK_URL to silence this."
        )

    # Kit bot user ID — mentioning triggers Hermes to investigate automatically
    KIT_BOT_ID = "1488210610893230160"
    content = f"**{title}**"
    if ping_kit:
        content = f"<@{KIT_BOT_ID}> {content}"

    embed = {
        "title": title,
        "description": message,
        "color": color,
        "footer": {"text": "TrustOffice Alerts"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    result = await send_discord_message(
        webhook_url=webhook_url,
        content=content,
        embeds=[embed]
    )
    if not result.get("success"):
        logger.error(
            f"ALERT FAILED to deliver: {result.get('error')} - "
            f"title={title!r} message={message!r}"
        )
    return result


async def notify_pipeline_alert(
    title: str,
    message: str,
    details: Optional[dict] = None,
    alert_level: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a RED pipeline-health alert to #trustoffice-main (1479343804527153262).

    Used by the leads pipeline monitor (leads_monitor.check_leads_pipeline_health)
    when nurture throughput or booking-reminder asserts fail. Distinct from
    notify_alert (which targets the generic alerts channel) so pipeline failures
    surface in the TrustOffice brand channel.
    """
    webhook_url, used_fallback = _resolve_alert_webhook(
        DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL
    )
    if not webhook_url:
        logger.error(
            "PIPELINE RED ALERT NOT SENT - no Discord webhook configured "
            "(DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL, DISCORD_ALERTS_WEBHOOK_URL "
            "and the hard-coded fallback are all unset). The alert was DROPPED."
        )
        return {"success": False, "error": "Not configured", "dropped": True}
    if used_fallback:
        logger.error(
            "PIPELINE WEBHOOK NOT CONFIGURED - falling back to the hard-coded "
            "alert webhook. Set DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL to silence this."
        )

    fields = [
        {"name": "Channel", "value": f"#trustoffice-main ({TRUSTOFFICE_MAIN_CHANNEL_ID})", "inline": True},
        {"name": "Severity", "value": "RED", "inline": True},
    ]
    if details:
        for k, v in details.items():
            fields.append({"name": k, "value": str(v), "inline": False})

    embed = {
        "title": f"🔴 {title}",
        "description": message,
        "color": RUST,
        "fields": fields,
        "footer": {"text": "TrustOffice Lead Pipeline Monitor"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    result = await send_discord_message(
        webhook_url=webhook_url,
        content=f"<@{TRUSTOFFICE_MAIN_CHANNEL_ID}> **RED ALERT** — {title}",
        embeds=[embed],
    )
    if not result.get("success"):
        logger.error(
            f"PIPELINE RED ALERT FAILED to deliver: {result.get('error')} - "
            f"title={title!r} message={message!r}"
        )
    return result
