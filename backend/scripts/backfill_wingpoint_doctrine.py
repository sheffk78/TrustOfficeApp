"""
One-time backfill: stamp WingPoint-provisioned trusts with their doctrine state.

Background (2026-10-30, WP-aware assistant): the assistant's knowledge gate and
the Trust Brief are keyed off the trust's OWN doctrine state —
benevolence_enabled=True + tax_status='508' — and the WingPoint-connect flow
now sets those fields when it provisions a trust. Trusts provisioned BEFORE
that fix carry the provenance markers (source='wingpoint' or wingpoint_ref)
but are missing the doctrine stamps, so WingPoint members administering them
see no benevolence/508 doctrine line.

This script finds those trusts and stamps them. Idempotent: only trusts whose
fields are missing or wrong are updated — a second run reports 0 updates.
Dry-run by default; pass --apply to write.

Connections directly via MONGO_URL (public proxy) — do NOT import database.py,
which points at the Railway-internal hostname. Mirrors
scripts/purge_benevolence_tax_entries.py conventions.

Run:
    python3 scripts/backfill_wingpoint_doctrine.py           # dry run
    python3 scripts/backfill_wingpoint_doctrine.py --apply   # write
"""
import asyncio
import os
import sys

sys.path.insert(0, ".")

import motor.motor_asyncio  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "trustoffice")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=20000)
db = client[DB_NAME]

APPLY = "--apply" in sys.argv


async def backfill(dry_run: bool = True) -> dict:
    """Find WingPoint-provisioned trusts missing their doctrine state; stamp them."""
    # Provenance markers (wingpoint_identity.py): source == "wingpoint" (legacy
    # direct marking) or wingpoint_ref set (referral provisioning).
    query = {
        "$or": [
            {"source": "wingpoint"},
            {"wingpoint_ref": {"$exists": True, "$ne": None, "$ne": ""}},
        ],
    }
    wp_trusts = await db.trusts.find(
        query,
        {"_id": 0, "trust_id": 1, "name": 1, "user_id": 1, "source": 1,
         "wingpoint_ref": 1, "benevolence_enabled": 1, "tax_status": 1},
    ).to_list(1000)
    print(f"WingPoint-provisioned trusts: {len(wp_trusts)}")
    for t in wp_trusts:
        print(
            f"  - {t['trust_id']} | {t.get('name', '?')} | user={t.get('user_id', '?')}"
            f" | benevolence={t.get('benevolence_enabled')} | tax_status={t.get('tax_status')!r}"
        )

    # Needs the stamp when either field is missing or wrong.
    needs = [
        t for t in wp_trusts
        if t.get("benevolence_enabled") is not True
        or t.get("tax_status") != "508"
    ]
    print(f"Trusts needing the doctrine stamp: {len(needs)}")
    for t in needs:
        print(f"  - {t['trust_id']} | {t.get('name', '?')}")

    if dry_run:
        print("\nDRY RUN — re-run with --apply to stamp these trusts.")
        return {"found": len(wp_trusts), "to_update": len(needs), "updated": 0}

    updated = 0
    for t in needs:
        result = await db.trusts.update_one(
            {"trust_id": t["trust_id"]},
            {"$set": {"benevolence_enabled": True, "tax_status": "508"}},
        )
        updated += result.modified_count
    print(f"\nStamped {updated} trusts (benevolence_enabled=True, tax_status='508').")

    # Verify: re-run the finder — must come back empty.
    remaining = await db.trusts.count_documents(
        {
            "$and": [
                {"$or": [{"source": "wingpoint"},
                          {"wingpoint_ref": {"$exists": True, "$nin": [None, ""]}}]},
                {"$or": [{"benevolence_enabled": {"$ne": True}},
                          {"tax_status": {"$ne": "508"}}]},
            ],
        }
    )
    print(f"Verification — trusts still missing the stamp: {remaining}")
    return {"found": len(wp_trusts), "to_update": len(needs), "updated": updated}


async def main():
    await backfill(dry_run=not APPLY)


if __name__ == "__main__":
    asyncio.run(main())