"""
Migration: Convert legacy trial subscriptions to gifted subscriptions.

Run this AFTER deploying the new Gifted code.
Connects to the same MongoDB database as the main app.

Usage:
    cd backend && python -m scripts.migrate_trial_to_gifted

Or trigger via Railway:
    railway run python scripts/migrate_trial_to_gifted.py
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

# Add parent directory to path so we can import database config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

# MongoDB connection — use same env var as main app
MONGODB_URL = os.environ.get("MONGODB_URL")
if not MONGODB_URL:
    print("ERROR: MONGODB_URL environment variable not set")
    sys.exit(1)

DB_NAME = os.environ.get("MONGODB_DB_NAME", "trustoffice")


async def migrate():
    """Convert legacy trial subscriptions to gifted subscriptions."""
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    now = datetime.now(timezone.utc)
    
    print(f"Migration started at {now.isoformat()}")
    print(f"Database: {DB_NAME}")
    print()
    
    # Step 1: Find all trials with gifted=True (admin_api.py gift flow) — add gift_type if missing
    step1 = await db.subscriptions.update_many(
        {"gifted": True, "plan_type": {"$in": ["monthly", "annual"]}, "gift_type": {"$exists": False}},
        [
            {"$set": {
                "gift_type": "$plan_type",
                "gift_start_date": {"$ifNull": ["$gifted_at", "$created_at"]},
                "gift_end_date": {"$ifNull": ["$current_period_end", None]},
                "updated_at": now.isoformat()
            }}
        ]
    )
    
    if step1.matched_count > 0:
        print(f"Step 1: Updated {step1.modified_count} existing gifted subscriptions with gift_type")
    else:
        print("Step 1: No gifted subscriptions missing gift_type found")
    
    # Step 2: Find all legacy trial subscriptions (plan_type=trial, status=trialing)
    # Convert them to gifted: true, gift_type: "14day"
    cursor = db.subscriptions.find({
        "plan_type": "trial"
    })
    
    trial_count = 0
    gifted_count = 0
    expired_count = 0
    
    async for sub in cursor:
        trial_count += 1
        sub_id = sub.get("subscription_id", "unknown")
        
        # Determine gift end date
        trial_end = sub.get("trial_end_date") or sub.get("trial_end")
        gift_end = sub.get("gift_end_date")
        
        if not gift_end and trial_end:
            gift_end = trial_end
        
        update_data = {
            "gifted": True,
            "gift_type": "14day",
            "gift_start_date": sub.get("trial_start_date") or sub.get("created_at") or now.isoformat(),
            "gift_end_date": gift_end,
            "gifted_at": sub.get("created_at") or now.isoformat(),
            "plan_type": "free",  # gifted users get the 'free' plan type (same features)
            "updated_at": now.isoformat()
        }
        
        # Check if already expired
        if gift_end:
            try:
                end = datetime.fromisoformat(gift_end.replace('Z', '+00:00'))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                if end < now:
                    update_data["status"] = "expired"
                    expired_count += 1
                else:
                    update_data["status"] = "active"
                    gifted_count += 1
            except (ValueError, TypeError, AttributeError):
                update_data["status"] = "active"
                gifted_count += 1
        else:
            # No end date — give them 14 days from migration
            update_data["gift_end_date"] = (now + timedelta(days=14)).isoformat()
            update_data["status"] = "active"
            gifted_count += 1
        
        await db.subscriptions.update_one(
            {"subscription_id": sub_id},
            {"$set": update_data}
        )
    
    print(f"Step 2: Found {trial_count} legacy trial subscriptions")
    print(f"  → {gifted_count} converted to active gifted (14-day)")
    print(f"  → {expired_count} already expired")
    print()
    
    # Step 3: Find any subscriptions with status "trialing" that aren't gifted yet
    cursor2 = db.subscriptions.find({"status": "trialing", "gifted": {"$ne": True}})
    trialing_count = 0
    async for sub in cursor2:
        trialing_count += 1
        sub_id = sub.get("subscription_id", "unknown")
        trial_end = sub.get("trial_end_date") or sub.get("trial_end")
        gift_end = sub.get("gift_end_date") or trial_end
        
        update_data = {
            "gifted": True,
            "gift_type": "14day",
            "gift_start_date": sub.get("trial_start_date") or sub.get("created_at") or now.isoformat(),
            "gift_end_date": gift_end,
            "gifted_at": sub.get("created_at") or now.isoformat(),
            "updated_at": now.isoformat()
        }
        
        # Check expiry
        if gift_end:
            try:
                end = datetime.fromisoformat(gift_end.replace('Z', '+00:00'))
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                update_data["status"] = "expired" if end < now else "active"
            except:
                update_data["status"] = "active"
        else:
            update_data["gift_end_date"] = (now + timedelta(days=14)).isoformat()
            update_data["status"] = "active"
        
        await db.subscriptions.update_one(
            {"subscription_id": sub_id},
            {"$set": update_data}
        )
    
    print(f"Step 3: Converted {trialing_count} additional trialing records")
    print()
    print(f"Migration complete! Total processed: {trial_count + trialing_count}")
    
    # Verify
    remaining_trial = await db.subscriptions.count_documents({"plan_type": "trial"})
    remaining_trialing = await db.subscriptions.count_documents({"status": "trialing"})
    total_gifted = await db.subscriptions.count_documents({"gifted": True})
    
    print(f"Remaining plan_type='trial': {remaining_trial}")
    print(f"Remaining status='trialing': {remaining_trialing}")
    print(f"Total gifted subscriptions: {total_gifted}")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(migrate())