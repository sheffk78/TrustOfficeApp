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
# Reduced & spread (2026-09-07) from the old 12-email / 30-day blast into a
# calmer cadence for an anxious accidental-trustee audience:
#   - max 2 emails in the first 7 days (day 0 + day 3) â the front stays light
#   - 6 emails total in the first 30 days (steps 1-6), 7th at day 35
# Kept emails are Kenneth-signed and carry the book-a-call CTA. Old steps
# 12-email nurture sequence: (step, day_offset, subject, body_text)
# Calm cadence for an anxious accidental-trustee audience. Every email is
# Kenneth-signed and carries exactly one book-a-call CTA as its final link.
# Copy refreshed 2026-09-07 per messaging-council recommendations:
# fear->protection reframe, emotional day-0 open, call-sync, soft endgame,
# 12-email nurture sequence: (step, day_offset, subject, body_text)
# Calm cadence for an anxious accidental-trustee audience. Every email is
# Kenneth-signed and carries exactly one book-a-call CTA as its final link.
# Copy refreshed 2026-09-07 per messaging-council recommendations:
# fear->protection reframe, emotional day-0 open, call-sync, soft endgame,
# resources framed as prep for a conversation.
NURTURE_SEQUENCE = [
    (1, 0, "Welcome — you're now equipped to manage your trust", "Hi there,\n\nYou didn't ask for this job. And if you're like most trustees, you're holding it alongside grief for the person who left it to you.\n\nFirst — I'm sorry for your loss. There's no training for this. Nobody handed you a manual when you became a trustee. You're doing the best you can with a job nobody prepared you for, and that's okay.\n\nYou may have already heard from me — I call every new trustee personally to introduce myself. If we've talked, great; if not, my cell is yours when you need it.\n\nHere's the one thing to know: a trust is a legal arrangement where you (the trustee) hold and manage assets for the benefit of someone else (the beneficiaries). Your job is to protect those assets, follow the trust's rules, and act in their best interest.\n\nThat's it. The minutes, the distributions, the tax filings — they all flow from those three responsibilities.\n\nOver the next few weeks I'll send short, practical emails. No jargon. No fear. Just straight talk from someone who's been there.\n\nIf you want to skip ahead and talk through your situation, book a free call with me here:\nhttps://trustoffice.app/book-a-call/\n\nNo pressure. I'm here when you need me.\n\nBest,\nKenneth Kohler\nFounder, TrustOffice"),
    (2, 3, "The #1 mistake new trustees make (it's not what you think)", "Hi there,\n\nBefore we dive in — I know this is a lot to absorb while you're also dealing with everything else life is throwing at you. Take it one email at a time.\n\nIf we've spoken on the phone, you know I'm a real person — if not, I'd love to connect.\n\nIf there's one thing I'd drill into every new trustee, it's this: don't mix trust money with personal money.\n\nIt's called 'commingling,' and it's the single most common way trustees get into trouble — even with the best intentions.\n\nHere's how it happens: a trust expense comes up, your personal checking is right there, so you use it. Or trust income lands in your personal account. Seems harmless, right? It's not.\n\nCommingling can give a court reason to pierce your trust — meaning the protection you set up could be set aside. The fix is simple: separate accounts. One for trust funds, one for personal. Never the twain shall meet.\n\nI put together a free commingling checklist — run through it in five minutes, and if you want a second set of eyes on your answers, bring it to a call and we'll review it together:\nhttps://trustoffice.app/the-commingling-checklist/\n\nIf you're not sure your setup is clean, that's exactly what I walk through on a call:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (3, 8, "The 7-minute trustee checkup", "Hi there,\n\nQuick check-in — I know the learning curve feels overwhelming on top of everything else. You're not behind. You're right where you should be.\n\nIf we've spoken on the phone, you know I'm a real person — if not, I'd love to connect.\n\nLet's do a quick checkup. Seven questions to gauge how well your trust is being managed:\n\n1. Does your trust have its own bank account, separate from all personal accounts?\n2. Do you have written minutes from every trust meeting or decision in the past year?\n3. Have you reviewed the trust's investments in the last 12 months?\n4. Do you know when your trust's tax return is due — and is it filed separately from your personal return?\n5. Can you name all your beneficiaries and what each is entitled to?\n6. Have you made any distributions in the past year, and are they documented?\n7. If something happened to you tomorrow, would someone know how to step in as trustee?\n\nScore yourself:\n- 7 yes: You're in great shape. Keep it up.\n- 4-6 yes: You've got gaps. Let's talk about closing them.\n- 0-3 yes: You're exposed. We should talk soon.\n\nIf you scored under 7, the free 90-Day Trustee Checklist walks you through this self-audit week by week — bring your score to a call and we'll prioritize what to fix first:\nhttps://trustoffice.app/trustee-90-day-checklist/\n\nOr just close the gaps with a short call:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (4, 12, "Trust taxes — the simple version nobody tells you", "Hi there,\n\nTrust taxes sound complicated. Let me make them simple.\n\nA trust is its own taxpayer. It gets its own tax identification number (EIN) and files its own tax return — typically Form 1041.\n\nHere's what most people get wrong: they think the trust's income flows onto their personal return automatically. It doesn't. The trust files separately. If the trust distributes income to beneficiaries, those distributions are reported on K-1 forms.\n\nThree things to keep in mind:\n1. File on time — the trust's tax deadline is usually April 15\n2. Keep trust expenses documented — many are deductible\n3. Don't file the trust return under your personal SSN — always use the trust's EIN\n\nIf you want a guided walkthrough of the tax piece plus everything else, the free Trustee 101 course covers it in short lessons — work through the tax module and bring your questions to a call, and we'll make sure your setup is right:\nhttps://trustoffice.app/trustee-101/\n\nIf you're not sure whether your tax setup is right, I'm happy to walk through it with you:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (5, 18, "How good trust governance saved a family (real story)", "Hi there,\n\nI want to share a story that shows exactly why trust governance matters.\n\nA family I know — let's call them the Andersons — had a trust set up by their father. He passed away, and the oldest son became trustee. He meant well, but he had no system. No separate accounts. No minutes. No records of distributions. When one of the siblings asked for an accounting, he couldn't produce one.\n\nThat sibling sued. The court found that the trust had been so poorly managed that the trust's protections were compromised.\n\nNow contrast that with another family. Same situation — but this trustee did three things: kept separate accounts, documented every decision in writing, and held an annual review meeting with minutes. When a creditor tried to come after the trust assets, the court looked at the records and said: this trust is clean. The shield held.\n\nThe difference wasn't the trust document. It was the behavior. The governance.\n\nIf this story hit home and you want to check your own governance, the free 90-Day Trustee Checklist is where to start — fill it in, then bring it to a call and we'll go through your answers together:\nhttps://trustoffice.app/trustee-90-day-checklist/\n\nIf you want to make sure you're on the right side of that story, let's talk:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (6, 25, "Your first 90 days as a trustee — a roadmap", "Hi there,\n\nIf you're newly appointed as a trustee — or if you've been one for a while but haven't really gotten organized — here's a 90-day roadmap.\n\nDays 1-30: Get the basics in place\n- Read the entire trust document. Understand your powers and duties.\n- Open a dedicated trust bank account if you don't have one.\n- Get the trust's EIN and make sure tax filings are current.\n- List all trust assets and their current values.\n\nDays 31-60: Start documenting\n- Hold your first trustee meeting. Take minutes.\n- Review the trust's investment strategy. Document your analysis.\n- If any distributions are needed, make them and document the HEMS rationale.\n\nDays 61-90: Build the habit\n- Schedule a recurring quarterly trustee meeting.\n- Review the trust's performance against its goals.\n- Prepare the trust's tax documents (Form 1041).\n- Create a succession plan — who takes over if you can't?\n\nIf you want to go deeper on any of this, the free Trustee 101 course covers each area in short lessons — work through the ones for your trust and bring any questions to a call, and we'll apply them to your situation:\nhttps://trustoffice.app/trustee-101/\n\nAnd if you'd like me to walk you through this roadmap for your specific trust, book a call:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (7, 42, "How to protect yourself from personal liability", "Hi there,\n\nA while back I mentioned commingling. Today let's talk about how to make yourself safe — because protecting your personal assets is simpler than people think.\n\nHere's the good news: a trust is a shield. When it's set up and run correctly, the wall between you and the trust holds. Creditors, lawsuits, and tax authorities can't reach the trust assets. The key is keeping that wall intact.\n\nWhat keeps you safe:\n- Separate bank accounts for trust and personal funds\n- Documented decisions (minutes of meetings)\n- Regular trust activity (distributions, investments, reviews)\n- No personal use of trust assets without proper documentation\n\nThat's it. It isn't scary — it's just discipline, and it's a lot easier than most people fear.\n\nA great first step is seeing what properly documented decisions look like. The free minutes template shows you exactly how — fill it out for one past decision, and on a call we'll check whether your trust is held up the right way:\nhttps://trustoffice.app/trust-meeting-minutes-template/\n\nWant me to look at how your trust is set up and flag any risks? Book a call:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (8, 50, "HEMS — the four letters that control every distribution", "Hi there,\n\nIf your trust document mentions distributions, you've probably seen the word 'HEMS.' It stands for Health, Education, Maintenance, and Support.\n\nHEMS gives you guidance on when it's appropriate to distribute trust funds:\n- Health: Medical care, insurance, treatments\n- Education: Tuition, books, fees, living expenses while in school\n- Maintenance: Keeping the beneficiary at their established standard of living\n- Support: Food, shelter, clothing, transportation\n\nThe key word is 'ascertainable.' A court can look at a distribution and determine whether it fits within HEMS. Every distribution you make should have a simple written record of what, why, and how much.\n\nImagine if all of that were tracked for you automatically — every distribution logged with its HEMS reason, no spreadsheet required.\n\nIf you want to go deeper on distributions and every other governance task, the free 90-Day Trustee Checklist lays it all out week by week — work through it, then bring your notes to a call and we'll tighten anything that's loose:\nhttps://trustoffice.app/trustee-90-day-checklist/\n\nWant to talk through your distribution process? I'm here:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (9, 60, "The #1 reason trusts fall apart (and how to avoid it)", "Hi there,\n\nHere's the #1 reason trusts fall apart: trustee inaction. Not a bad document — a passive trustee.\n\nThe stats back it up. When a trust gets no attention, problems compound fast:\n- No minutes = no evidence you were acting as a trustee\n- No separate accounts = commingling risk\n- No distributions = beneficiaries get frustrated and suspicious\n- No annual review = investments drift, deadlines get missed\n\nBut here's the fix, and it's good news: governance. A trust that's actively, consistently governed stays healthy. You don't need hours a week — a few hours a year, maybe 4-6 total, is enough.\n\nThat's exactly why I built TrustOffice: to make that consistent governance take minutes instead of hours, so the shield stays up without the grind.\n\nImagine if that consistency happened automatically, on a schedule you didn't have to remember.\n\nIf you'd rather build it yourself first, the free Trustee 101 course covers each area in short lessons — go through it and bring your questions to a call, and we'll make sure you're on the right track:\nhttps://trustoffice.app/trustee-101/\n\nIf you're ready to stop worrying, let's talk:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (10, 70, "The annual trustee checklist (print this out)", "Hi there,\n\nHere's your annual trustee checklist. Bookmark it, print it, tape it to your desk.\n\nBanking & Accounts\n[ ] Trust has its own bank account, separate from all personal accounts\n[ ] No personal funds have been mixed with trust funds\n\nDocumentation\n[ ] Minutes exist for every trust meeting or significant decision in the past year\n[ ] All distributions are documented with amount, date, beneficiary, and HEMS rationale\n\nTaxes\n[ ] Trust tax return (Form 1041) has been filed or is on track\n[ ] K-1 forms have been issued to beneficiaries who received distributions\n\nInvestments & Assets\n[ ] Trust assets have been reviewed and valued in the past 12 months\n[ ] Investment strategy aligns with the trust's purposes\n\nBeneficiaries\n[ ] All beneficiaries are accounted for and contact info is current\n[ ] Distribution plans for the coming year are outlined\n\nSuccession\n[ ] A successor trustee is identified and knows their role\n\nImagine if each of these got checked off automatically as the year went — no scramble at tax time.\n\nFor a guided version, the free 90-Day Trustee Checklist turns this into a week-by-week plan — run through it, then bring it to a call and we'll knock out any gaps together:\nhttps://trustoffice.app/trustee-90-day-checklist/\n\nIf you went through this list and found gaps, don't panic — just start fixing them. I'm a call away:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth"),
    (11, 80, "What if trust governance just... handled itself?", "Hi there,\n\nOver the past few months I've shared a lot about what good trust governance looks like — the minutes, the checklists, the distribution records, the annual reviews.\n\nIf you've ever thought 'this is a lot to keep up with,' you're not alone. I built TrustOffice for people exactly like you. After watching hundreds of trustees struggle to stay consistent, I built the system I wish every trustee had: an extension of the help I give on calls, available whenever you need it.\n\nIt takes the work you're already supposed to do and makes it take minutes instead of hours:\n- Generates your trust minutes with guided templates\n- Tracks distributions with HEMS tagging\n- Sends reminders before deadlines\n- Calculates a governance health score\n- Stores all trust documents securely\n\nIf you want to see what TrustOffice-generated minutes look like before you ever touch the product, there's a free template here — fill it in for one decision and bring it to a call, and I'll show you how the system would handle the rest:\nhttps://trustoffice.app/trust-meeting-minutes-template/\n\nIt's not a replacement for professional advice — it's the system that makes sure the advice you've gotten actually gets implemented.\n\nI'd love to show you how it works for your specific trust. Book a 15-minute discovery call:\nhttps://trustoffice.app/book-a-call/\n\nBest,\nKenneth Kohler\nFounder, TrustOffice"),
    (12, 90, "Let's get your trust in order — together", "Hi there,\n\nWe've been talking for about three months now. Wherever you are with your trust today — organized and rolling, or still with a stack of papers you haven't opened — that's okay. There's no grade here. You showed up, and that already puts you ahead of most trustees.\n\nOver the past three months I've shared a lot of free resources — the 90-Day Checklist, the Trustee 101 course, the minutes template. They're all still there for you:\nhttps://trustoffice.app/trustee-90-day-checklist/\n\nHere's my ask, and it's a choice, not a pitch. Pick whichever fits you right now:\n\nOption 1 — Book a 15-minute call. I'll look at your current setup, flag any gaps or risks, and give you a clear next-step plan — whether or not you ever use TrustOffice:\nhttps://trustoffice.app/book-a-call/\n\nOption 2 — Just hit reply and tell me what's still unclear about your trustee role. Seriously. What's the one thing that still doesn't make sense? I read every reply, and your answer helps me know what to explain next.\n\nEither way, thank you for letting me walk alongside you these past few months. You've got this.\n\nBest,\nKenneth Kohler\nFounder, TrustOffice\n\nP.S. If you've already booked — thank you. I'm looking forward to our conversation.")
]

async def send_nurture_email_via_mailercloud(to_email: str, name: str, step: int) -> dict:
    """Send a specific nurture email step via MailerCloud Email API.
    
    Args:
        to_email: Recipient email
        name: Recipient name
        step: Email step number (1-7)
    
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
                logger.info(f"Sent nurture email {step}/7 to {to_email}")
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