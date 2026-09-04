"""
One-time cleanup: purge tax-calendar entries from benevolence-enabled trusts.

Benevolence (508c3) trusts are tax-exempt — they file no Form 1041, make no
estimated payments, and issue no K-1s — so the tax calendar items that were
auto-generated before this policy existed must be removed. The generator
(utils/tax_calendar_math._generate_entries) now returns [] for benevolence
trusts, and update_trust purges entries when benevolence is enabled; this
script cleans up trusts that were seeded before those fixes.

Idempotent: only removes entries whose trust has benevolence_enabled=True.
Dry-run by default.
Run:  python3 scripts/purge_benevolence_tax_entries.py [--execute]
"""

import asyncio
import os
import sys

sys.path.insert(0, ".")

# Connect directly via MONGO_URL (public proxy) — do not import database.py,
# which points at the Railway-internal hostname. DB_NAME defaults to trustoffice.
import motor.motor_asyncio  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "trustoffice")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=20000)
db = client[DB_NAME]

DRY_RUN = "--execute" not in sys.argv


async def main():
    # 1. Find benevolence-enabled trusts
    benevolence_trusts = await db.trusts.find(
        {"benevolence_enabled": True},
        {"trust_id": 1, "name": 1, "user_id": 1, "_id": 0}
    ).to_list(1000)
    trust_ids = [t["trust_id"] for t in benevolence_trusts]
    print(f"Benevolence-enabled trusts: {len(trust_ids)}")
    for t in benevolence_trusts:
        print(f"  - {t['trust_id']} | {t.get('name', '?')} | user={t.get('user_id', '?')}")

    if not trust_ids:
        print("Nothing to do — no benevolence-enabled trusts found.")
        return

    # 2. Count their tax-calendar entries
    count = await db.tax_calendar.count_documents({"trust_id": {"$in": trust_ids}})
    print(f"Tax-calendar entries on benevolence trusts: {count}")

    # Per-trust breakdown (shows what will be removed for each account)
    for t in benevolence_trusts:
        n = await db.tax_calendar.count_documents({"trust_id": t["trust_id"]})
        if n:
            types = await db.tax_calendar.distinct("deadline_type", {"trust_id": t["trust_id"]})
            print(f"  {t.get('name', t['trust_id'])}: {n} entries -> {', '.join(sorted(types))}")

    if DRY_RUN:
        print("\nDRY RUN — re-run with --execute to delete these entries.")
        return

    result = await db.tax_calendar.delete_many({"trust_id": {"$in": trust_ids}})
    print(f"\nDeleted {result.deleted_count} tax-calendar entries from benevolence trusts.")

    # 3. Verify
    remaining = await db.tax_calendar.count_documents({"trust_id": {"$in": trust_ids}})
    print(f"Verification — remaining entries on benevolence trusts: {remaining}")


if __name__ == "__main__":
    asyncio.run(main())