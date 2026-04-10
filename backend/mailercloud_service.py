# Mailercloud integration service for managing email lists
import os
import logging
import httpx

logger = logging.getLogger(__name__)

MAILERCLOUD_API_KEY = os.environ.get('MAILERCLOUD_API_KEY')
MAILERCLOUD_PAID_LIST_ID = os.environ.get('MAILERCLOUD_PAID_LIST_ID', 'fySyKK')
MAILERCLOUD_TRIAL_LIST_ID = os.environ.get('MAILERCLOUD_TRIAL_LIST_ID', 'fySyKH')

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


async def add_to_trial_list(email: str, name: str = None):
    """Add a contact to the TrustOffice 14-Day Trial list."""
    return await add_contact_to_list(
        email=email,
        name=name or "",
        list_id=MAILERCLOUD_TRIAL_LIST_ID,
        list_name="14-Day Trial"
    )


async def add_to_paid_list(email: str, name: str = None):
    """Add a contact to the TrustOffice Active Members list."""
    return await add_contact_to_list(
        email=email,
        name=name or "",
        list_id=MAILERCLOUD_PAID_LIST_ID,
        list_name="Active Members"
    )
