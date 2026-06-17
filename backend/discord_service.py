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
        async with httpx.AsyncClient() as client:
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
    lead_stage: str = "new"
) -> Dict[str, Any]:
    """Send a new lead notification to the leads Discord channel."""
    if not DISCORD_LEADS_WEBHOOK_URL:
        logger.info("Discord leads webhook not configured — skipping lead notification")
        return {"success": False, "error": "Not configured"}

    embed = {
        "title": f"{_stage_emoji(lead_stage)} New Lead: {name}",
        "color": NAVY,
        "fields": [
            {"name": "Name", "value": name or "Not provided", "inline": True},
            {"name": "Email", "value": email, "inline": True},
            {"name": "Source", "value": source or "direct", "inline": True},
            {"name": "Stage", "value": lead_stage.replace("_", " ").title(), "inline": True},
        ],
        "footer": {"text": "TrustOffice Lead Management"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    return await send_discord_message(
        webhook_url=DISCORD_LEADS_WEBHOOK_URL,
        content=f"**New lead** — {name} ({email}) via {source}",
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
    color: int = RUST
) -> Dict[str, Any]:
    """Send an alert to the alerts Discord channel (or leads channel as fallback)."""
    webhook_url = DISCORD_ALERTS_WEBHOOK_URL or DISCORD_LEADS_WEBHOOK_URL
    if not webhook_url:
        return {"success": False, "error": "Not configured"}

    embed = {
        "title": title,
        "description": message,
        "color": color,
        "footer": {"text": "TrustOffice Alerts"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    return await send_discord_message(
        webhook_url=webhook_url,
        content=f"**{title}**",
        embeds=[embed]
    )
