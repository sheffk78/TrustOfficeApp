"""
One-time migration script: Fix chat-created compensation plans with wrong field names.

Before Phase 1 fix, the chat execution wrote these fields to compensation_plans:
  amount, frequency, status

The correct schema (matching compensation.py router) expects:
  annual_fee, annual_amount, annual_approved_amount, fee_type, year, is_primary

This script finds plans that have "amount" but not "annual_amount" and migrates them.

Usage:
  cd backend && python migrate_comp_plans.py          # dry run (prints count)
  cd backend && python migrate_comp_plans.py --apply   # actually migrate
"""
import asyncio
import sys
from database import db


async def migrate(dry_run: bool = True):
    # Find plans with old fields (has "amount" but not "annual_amount")
    query = {"amount": {"$exists": True}, "annual_amount": {"$exists": False}}
    cursor = db.compensation_plans.find(query)
    count = 0
    
    async for plan in cursor:
        count += 1
        if dry_run:
            print(f"  Would migrate plan {plan.get('plan_id', '?')}: "
                  f"amount={plan.get('amount')}, frequency={plan.get('frequency')}")
            continue
        
        # Build the update
        amount = float(plan.get("amount", 0))
        frequency = plan.get("frequency", "monthly")
        
        # Map old frequency values to fee_type
        fee_type_map = {
            "monthly": "fixed",
            "quarterly": "fixed",
            "annually": "fixed",
            "per_meeting": "per_meeting",
            "hourly": "hourly",
        }
        fee_type = fee_type_map.get(frequency, "fixed")
        
        # Derive year from effective_date
        effective_date = plan.get("effective_date", "")
        try:
            year = int(effective_date[:4])
        except (ValueError, TypeError, IndexError):
            year = 2025
        
        update_doc = {
            "$set": {
                "annual_fee": amount,
                "annual_amount": amount,
                "annual_approved_amount": amount,
                "fee_type": fee_type,
                "year": year,
                "is_primary": False,
            },
            "$unset": {
                "amount": "",
                "frequency": "",
                "status": "",
            }
        }
        
        await db.compensation_plans.update_one(
            {"plan_id": plan.get("plan_id")},
            update_doc
        )
        print(f"  Migrated plan {plan.get('plan_id')}: {amount}/yr {fee_type}")
    
    return count


async def main():
    dry_run = "--apply" not in sys.argv
    mode = "DRY RUN" if dry_run else "APPLYING"
    print(f"[{mode}] Migrating chat-created compensation plans with wrong fields...")
    
    count = await migrate(dry_run=dry_run)
    
    if dry_run:
        print(f"\nFound {count} plans to migrate. Run with --apply to execute.")
    else:
        print(f"\nMigrated {count} plans.")
    
    # Verify: count remaining bad plans
    remaining = await db.compensation_plans.count_documents(
        {"amount": {"$exists": True}, "annual_amount": {"$exists": False}}
    )
    print(f"Remaining plans with old fields: {remaining}")


if __name__ == "__main__":
    asyncio.run(main())