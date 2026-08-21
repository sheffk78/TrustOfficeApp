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
