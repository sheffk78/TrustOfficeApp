"""
Poll TidyCal bookings and update leads in MongoDB.

Fetches bookings from TidyCal API, matches them to existing leads by email,
and updates lead documents with booked_call: true and meeting_date.

Run inside Railway container where MongoDB is accessible.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database import db
import httpx


async def load_tidycal_api_key() -> str:
    """Load TidyCal API key from env var or secrets file."""
    api_key = os.environ.get("TIDYCAL_API_KEY")
    if api_key:
        return api_key.strip()
    api_key_file = Path.home() / '.hermes' / 'secrets' / 'tidycal_api_key.txt'
    if not api_key_file.exists():
        raise FileNotFoundError(f"TidyCal API key not found at {api_key_file} nor TIDYCAL_API_KEY env var")
    with open(api_key_file, 'r') as f:
        return f.read().strip()


async def fetch_bookings_from_tidycal(api_key: str, limit: int = 100) -> list:
    """
    Fetch bookings from TidyCal API.

    Args:
        api_key: TidyCal API key
        limit: Maximum number of bookings to fetch

    Returns:
        List of booking objects
    """
    url = "https://tidycal.com/api/bookings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    params = {"limit": limit}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
    except Exception as e:
        print(f"Error fetching bookings from TidyCal: {e}")
        return []


async def update_leads_from_bookings(bookings: list) -> int:
    """
    Update leads in MongoDB based on fetched bookings.

    Args:
        bookings: List of booking objects from TidyCal

    Returns:
        Count of leads updated
    """
    updated_count = 0

    for booking in bookings:
        # Extract email from booking details
        contact = booking.get("contact", {})
        email = contact.get("email")

        if not email:
            continue

        # Build update payload
        meeting_time = booking.get("starts_at")  # ISO 8601 format
        if meeting_time:
            meeting_date = datetime.fromisoformat(meeting_time.replace('Z', '+00:00'))
        else:
            meeting_date = None

        update_data = {
            "booked_call": True,
            "booked_call_at": datetime.now(timezone.utc).isoformat(),
            "meeting_date": meeting_date.isoformat() if meeting_date else None,
        }

        # Update lead document
        result = await db.leads.update_one(
            {"email": email},
            {"$set": update_data}
        )

        if result.modified_count > 0:
            updated_count += 1
            print(f"  Updated lead: {email}")

    return updated_count


async def main():
    """Main polling logic."""
    print("🔍 Polling TidyCal for new bookings...\n")

    # Load API key
    try:
        api_key = await load_tidycal_api_key()
        print("  ✓ API key loaded")
    except FileNotFoundError as e:
        print(f"  ✗ {e}")
        return

    # Fetch bookings
    bookings = await fetch_bookings_from_tidycal(api_key)
    print(f"  ✓ Fetched {len(bookings)} bookings from TidyCal\n")

    if not bookings:
        print("  No new bookings to process.")
        return

    # Update leads
    print("  Updating leads in MongoDB...\n")
    updated = await update_leads_from_bookings(bookings)

    # Summary
    print(f"\n✅ Complete:")
    print(f"  Bookings processed: {len(bookings)}")
    print(f"  Leads updated: {updated}")
    print(f"  Leads without TidyCal booking: {len(bookings) - updated}")


if __name__ == "__main__":
    asyncio.run(main())