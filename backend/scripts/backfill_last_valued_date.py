"""One-time backfill: set last_valued_date = date_conveyed for Schedule A items missing it.

Run once after deploying the last_valued_date field. Preserves the pre-fix scoring
semantics for existing data (they scored off conveyance date) while letting the new
'Mark valued' flow take over going forward. Safe to re-run (skips items that have it).

Usage: python3 backend/scripts/backfill_last_valued_date.py
Supports MONGODB_URI env var, falls back to local default.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import db  # noqa: E402


async def backfill() -> tuple:
    query = {"$or": [{"last_valued_date": {"$exists": False}}, {"last_valued_date": None}]}
    cursor = db.schedule_a_items.find(query, {"_id": 0, "item_id": 1, "date_conveyed": 1})
    docs = await cursor.to_list(10000)
    fixed = 0
    for d in docs:
        fallback = d.get("date_conveyed")
        if not fallback:
            continue  # leave truly dateless items alone; scoring treats them stale
        await db.schedule_a_items.update_one(
            {"item_id": d["item_id"]}, {"$set": {"last_valued_date": fallback}}
        )
        fixed += 1
    return fixed, len(docs)


if __name__ == "__main__":
    fixed, total = asyncio.run(backfill())
    print(f"Backfilled last_valued_date on {fixed} of {total} schedule_a_items missing it.")