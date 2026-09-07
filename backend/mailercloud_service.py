# Mailercloud integration service for managing email lists
import os
import logging
import httpx

logger = logging.getLogger(__name__)

MAILERCLOUD_API_KEY = os.environ.get('MAILERCLOUD_API_KEY')
MAILERCLOUD_PAID_LIST_ID = os.environ.get('MAILERCLOUD_PAID_LIST_ID', 'fySyKK')
MAILERCLOUD_LEADS_LIST_ID = os.environ.get('MAILERCLOUD_LEADS_LIST_ID', 'fySyKH')
# Keep trial list ID as alias for backwards compatibility
MAILERCLOUD_TRIAL_LIST_ID = MAILERCLOUD_LEADS_LIST_ID

MAILERCLOUD_API_URL = "https://cloudapi.mailercloud.com/v1/contacts"


async def add_contact_to_list(email: str, name: str, list_id: str, list_name: str = "list"):
    """
    Add a contact to a Mailercloud list.
    
    Args:
        email: Contact's email address
        name: Contact's name
        list_id: Mailercloud list ID
        list_name: Human-readable list name for logging
    
    Returns:
        dict with success status and details
    """
    if not MAILERCLOUD_API_KEY:
        logger.warning("Mailercloud API key not configured, skipping list update")
        return {"success": False, "error": "API key not configured"}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                MAILERCLOUD_API_URL,
                headers={
                    "Authorization": MAILERCLOUD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "email": email,
                    "name": name or "",
                    "list_id": list_id
                },
                timeout=10.0
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Successfully added {email} to Mailercloud {list_name}")
                return {"success": True, "email": email, "list": list_name}
            elif response.status_code == 409:
                # Contact already exists in this list
                logger.info(f"Contact {email} already exists in Mailercloud {list_name}")
                return {"success": True, "email": email, "list": list_name, "note": "already_exists"}
            else:
                logger.error(f"Failed to add {email} to Mailercloud {list_name}: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
                
    except Exception as e:
        logger.error(f"Mailercloud API error for {email}: {str(e)}")
        return {"success": False, "error": str(e)}


async def add_to_lead_list(email: str, name: str = None):
    """Add a contact to the TrustOffice Leads list (main nurture list)."""
    return await add_contact_to_list(
        email=email,
        name=name or "",
        list_id=MAILERCLOUD_LEADS_LIST_ID,
        list_name="TrustOffice Leads"
    )


# Keep old alias for backwards compatibility
async def add_to_trial_list(email: str, name: str = None):
    """Add a contact to the TrustOffice Leads list (formerly trial list)."""
    return await add_to_lead_list(email, name)


async def add_to_paid_list(email: str, name: str = None):
    """Add a contact to the TrustOffice Active Members list."""
    return await add_contact_to_list(
        email=email,
        name=name or "",
        list_id=MAILERCLOUD_PAID_LIST_ID,
        list_name="Active Members"
    )


async def move_to_paid_list(email: str, name: str = None):
    """Move a contact from the Leads list to the Active Members list.

    Adds to paid list first, then removes from leads list.
    If add fails, the contact stays on the leads list (safe fallback).
    """
    # First add to paid list
    add_result = await add_to_paid_list(email, name)
    if not add_result.get("success"):
        logger.warning(f"Could not add {email} to paid list — keeping on leads list")
        return add_result

    # Then remove from leads list
    remove_result = await remove_contact_from_list(
        email=email,
        list_id=MAILERCLOUD_LEADS_LIST_ID,
        list_name="TrustOffice Leads"
    )
    if remove_result.get("success"):
        logger.info(f"Moved {email} from Leads to Active Members in Mailercloud")
    else:
        logger.warning(f"Added {email} to paid list but could not remove from leads: {remove_result.get('error')}")

    return {"success": True, "email": email, "moved": True}


async def remove_contact_from_list(email: str, list_id: str, list_name: str = "list"):
    """Remove a contact from a Mailercloud list by email."""
    if not MAILERCLOUD_API_KEY:
        logger.warning("Mailercloud API key not configured, skipping list removal")
        return {"success": False, "error": "API key not configured"}

    try:
        async with httpx.AsyncClient() as client:
            # MailerCloud DELETE endpoint for removing a contact from a list
            response = await client.request(
                "DELETE",
                f"https://cloudapi.mailercloud.com/v1/contacts",
                headers={
                    "Authorization": MAILERCLOUD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "email": email,
                    "list_id": list_id
                },
                timeout=10.0
            )

            if response.status_code in [200, 202, 204]:
                logger.info(f"Successfully removed {email} from Mailercloud {list_name}")
                return {"success": True, "email": email, "list": list_name}
            elif response.status_code == 404:
                # Contact not found — already not on this list
                logger.info(f"Contact {email} not found on Mailercloud {list_name} — nothing to remove")
                return {"success": True, "email": email, "list": list_name, "note": "not_on_list"}
            else:
                logger.error(f"Failed to remove {email} from Mailercloud {list_name}: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}

    except Exception as e:
        logger.error(f"Mailercloud API error removing {email}: {str(e)}")
        return {"success": False, "error": str(e)}


# ==================== MAILERCLOUD EMAIL API ====================

MAILERCLOUD_EMAIL_API_URL = "https://email-api.mailercloud.com/v1/email"
MAILERCLOUD_SENDER_EMAIL = os.environ.get("MAILERCLOUD_SENDER_EMAIL", "contact@trustoffice.app")
MAILERCLOUD_SENDER_NAME = os.environ.get("MAILERCLOUD_SENDER_NAME", "Kenneth Kohler")

# 7-email nurture sequence: (step, day_offset, subject, body_text)
# Reduced & spread out (2026-09-07) from the old 12-email sequence to be less
# overwhelming for an anxious accidental-trustee audience:
#   - max 2 emails in the first 7 days (day 0 + day 3)
#   - 6 emails total in the first 30 days (steps 1-6), 7th at day 35
# Kept emails are Kenneth-signed and carry the book-a-call CTA. Old steps
# 3, 7, 9, 10, 11 were dropped entirely.
NURTURE_SEQUENCE = [
    (1, 0, "Welcome â you're now equipped to manage your trust",
     "Hi there,\n\nYou filled out a form about trust management, and I want to start by saying â you're already ahead of most trustees.\n\nMost people get handed a trust document, nod politely, and have no idea what they're supposed to do next. That was me once. It's why I built TrustOffice.\n\nSo let's start simple: a trust is a legal arrangement where you (the trustee) hold and manage assets for the benefit of someone else (the beneficiaries). Your job is to protect those assets, follow the trust's rules, and act in the beneficiaries' best interest.\n\nThat's it. Everything else â the minutes, the distributions, the tax filings â flows from those three responsibilities.\n\nOver the next few weeks, I'll send you short, practical emails covering the things I wish someone had told me when I started. No legal jargon. No fear-mongering. Just straight talk from someone who's been there.\n\nIf you ever want to skip ahead and talk through your specific situation, you can book a free call with me here:\nhttps://trustoffice.app/book-a-call/\n\nNo pressure. I'm here when you need me.\n\nBest,\nKenneth Kohler\nFounder, TrustOffice"),
    (2, 3, "The #1 mistake new trustees make (it's not what you think)",
     "Hi there,\n\nIf there's one thing I'd drill into every new trustee, it's this: don't mix trust money with personal money.\n\nIt's called \"commingling,\" and it's the single most common way trustees get into trouble â even when they have the best intentions.\n\nHere's how it happens: you need to pay a trust expense, your personal checking account is right there, so you just use it. Or trust income comes in and it lands in your personal account. Seems harmless, right?\n\nIt's not.\n\nCommingling can give a court reason to pierce your trust â meaning the legal protection you set up could be set aside. The fix is simple: separate accounts. One for trust funds, one for personal funds. Never the twain shall meet.\n\nIf you're not sure whether your current setup is clean, that's exactly the kind of thing I walk through on a discovery call:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (3, 7, "The 7-minute trustee checkup",
     "Hi there,\n\nLet's do a quick checkup. Here are 7 questions to gauge how well your trust is being managed:\n\n1. Does your trust have its own bank account, separate from all personal accounts?\n2. Do you have written minutes from every trust meeting or decision in the past year?\n3. Have you reviewed the trust's investments in the last 12 months?\n4. Do you know when your trust's tax return is due â and is it filed separately from your personal return?\n5. Can you name all your beneficiaries and what each is entitled to?\n6. Have you made any distributions in the past year, and are they documented?\n7. If you were hit by a bus tomorrow, would someone know how to step in as trustee?\n\nScore yourself:\n- 7 yes: You're in great shape. Keep it up.\n- 4-6 yes: You've got gaps. Let's talk about closing them.\n- 0-3 yes: You're exposed. We should talk soon.\n\nIf you scored anything less than 7, a 15-minute call could help:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (4, 12, "Trust taxes â the simple version nobody tells you",
     "Hi there,\n\nTrust taxes sound complicated. Let me make them simple.\n\nA trust is its own taxpayer. It gets its own tax identification number (EIN) and files its own tax return â typically Form 1041.\n\nHere's what most people get wrong: they think the trust's income flows onto their personal return automatically. It doesn't. The trust files separately. If the trust distributes income to beneficiaries, those distributions are reported on K-1 forms.\n\nThree things to keep in mind:\n1. File on time â the trust's tax deadline is usually April 15\n2. Keep trust expenses documented â many are deductible\n3. Don't file the trust return under your personal SSN â always use the trust's EIN\n\nIf you're not sure whether your tax setup is right, I'm happy to walk through it:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (5, 18, "How good trust governance saved a family (real story)",
     "Hi there,\n\nI want to share a story that shows exactly why trust governance matters.\n\nA family I know â let's call them the Andersons â had a trust set up by their father. He passed away, and the oldest son became trustee. He meant well, but he had no system. No separate accounts. No minutes. No records of distributions. When one of the siblings asked for an accounting, he couldn't produce one.\n\nThat sibling sued. The court found that the trust had been so poorly managed that the trust's protections were compromised.\n\nNow contrast that with another family. Same situation â but this trustee did three things: kept separate accounts, documented every decision in writing, and held an annual review meeting with minutes. When a creditor tried to come after the trust assets, the court looked at the records and said: this trust is clean. The shield held.\n\nThe difference wasn't the trust document. It was the behavior. The governance.\n\nIf you want to make sure you're on the right side of that story, let's talk:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (6, 25, "Your first 90 days as a trustee â a roadmap",
     "Hi there,\n\nIf you're newly appointed as a trustee â or if you've been one for a while but haven't really gotten organized â here's a 90-day roadmap.\n\nDays 1-30: Get the basics in place\n- Read the entire trust document. Understand your powers and duties.\n- Open a dedicated trust bank account if you don't have one.\n- Get the trust's EIN and make sure tax filings are current.\n- List all trust assets and their current values.\n\nDays 31-60: Start documenting\n- Hold your first trustee meeting. Take minutes.\n- Review the trust's investment strategy. Document your analysis.\n- If any distributions are needed, make them and document the HEMS rationale.\n\nDays 61-90: Build the habit\n- Schedule a recurring quarterly trustee meeting.\n- Review the trust's performance against its goals.\n- Prepare the trust's tax documents (Form 1041).\n- Create a succession plan â who takes over if you can't?\n\nThis is exactly what TrustOffice automates. If you'd like me to walk you through this roadmap for your specific trust, book a call:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (7, 35, "Let's get your trust in order â together",
     "Hi there,\n\nIt's been a little while since you first reached out about trust management. I hope the emails have been helpful.\n\nNow I want to make a direct ask: book a call with me.\n\nNot a sales pitch. A 15-minute conversation where I:\n- Look at your current trust setup\n- Identify any gaps or risks\n- Give you a clear next-step plan â whether or not you use TrustOffice\n\nI do these calls because most trustees are operating with good intentions but without a system. They know they should be keeping minutes, tracking distributions, reviewing their trust annually â but they don't have the infrastructure to make it happen consistently.\n\nI can help you change that. Here's my calendar:\nhttps://trustoffice.app/book-a-call/\n\nPick any time that works for you. I'll be there.\n\nBest,\nKenneth Kohler\nFounder, TrustOffice\n\nP.S. If you've already booked â thank you. I'm looking forward to our conversation."),
]


async def send_nurture_email_via_mailercloud(to_email: str, name: str, step: int) -> dict:
    """Send a specific nurture email step via MailerCloud Email API.
    
    Args:
        to_email: Recipient email
        name: Recipient name
        step: Email step number (1-12)
    
    Returns:
        dict with success status
    """
    if not MAILERCLOUD_API_KEY:
        logger.warning("MailerCloud API key not configured, skipping nurture email")
        return {"success": False, "error": "API key not configured"}
    
    # Find the email content for this step
    email_data = None
    for s, day, subject, body in NURTURE_SEQUENCE:
        if s == step:
            email_data = (day, subject, body)
            break
    
    if not email_data:
        logger.error(f"Nurture step {step} not found in sequence")
        return {"success": False, "error": f"Step {step} not found"}
    
    day_offset, subject, body_text = email_data
    
    # Convert plain text body to simple HTML
    html_body = body_text.replace("\n\n", "</p><p>").replace("\n", "<br>\n")
    html_body = f"<p>{html_body}</p>"
    
    # Personalize: replace "Hi there" with name if available
    if name:
        greeting = f"Hi {name.split()[0]},"
        body_text = body_text.replace("Hi there,", greeting)
        html_body = html_body.replace("Hi there,", greeting)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                MAILERCLOUD_EMAIL_API_URL,
                headers={
                    "Authorization": MAILERCLOUD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "email": {
                        "from": MAILERCLOUD_SENDER_EMAIL,
                        "fromName": MAILERCLOUD_SENDER_NAME,
                        "subject": subject,
                        "text": body_text,
                        "html": html_body,
                        "recipients": {
                            "to": [{"name": name or "", "email": to_email}]
                        }
                    },
                    "version": "1.0"
                },
                timeout=15.0
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Sent nurture email {step}/12 to {to_email}")
                return {"success": True, "step": step, "email": to_email}
            else:
                logger.error(f"Failed to send nurture email {step} to {to_email}: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
                
    except Exception as e:
        logger.error(f"MailerCloud email API error for {to_email}: {str(e)}")
        return {"success": False, "error": str(e)}


async def send_welcome_email_via_mailercloud(to_email: str, name: str) -> dict:
    """Send the welcome email (step 1) immediately via MailerCloud Email API."""
    return await send_nurture_email_via_mailercloud(to_email, name, step=1)
