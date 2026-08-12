"""
Data migration: trust_unit_settings (singular) → trust_units_settings (plural)

Problem:
  The demo seeder writes to `trust_unit_settings` (singular), but the app reads
  from `trust_units_settings` (plural). This causes the 'hidden certificate'
  beneficiary error because the app creates fresh default settings instead
  of finding the seeded ones.

Behavior:
  - Scans all documents in `trust_unit_settings`.
  - For each (trust_id, user_id) pair, checks if a doc already exists in
    `trust_units_settings`.
  - If the plural doc exists, it is preferred (skipped).
  - If the plural doc does NOT exist, the singular doc is copied into the
    plural collection (minus MongoDB _id).
  - The singular collection is left untouched (safe; can be cleaned up later).
  - Idempotent: re-running produces no duplicates.

Usage:
    cd /path/to/TrustOfficeApp
    python -m backend.scripts.migrate_trust_unit_settings
"""
import asyncio
import logging
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def migrate_trust_unit_settings():
    singular = db.trust_unit_settings
    plural = db.trust_units_settings

    # Before counts
    before_singular = await singular.count_documents({})
    before_plural = await plural.count_documents({})
    logger.info(f"BEFORE — trust_unit_settings: {before_singular}, trust_units_settings: {before_plural}")

    moved = 0
    skipped = 0
    errors = 0

    # Iterate all docs in singular collection
    cursor = singular.find({})
    async for doc in cursor:
        trust_id = doc.get("trust_id")
        user_id = doc.get("user_id")

        if not trust_id or not user_id:
            logger.warning(f"Skipping doc with missing trust_id/user_id: _id={doc.get('_id')}")
            skipped += 1
            continue

        # Check if plural already has this (trust_id, user_id)
        existing_plural = await plural.find_one(
            {"trust_id": trust_id, "user_id": user_id},
        )

        if existing_plural:
            # Conflict reconciliation: the app may have already created a
            # default row in trust_units_settings (total_authorized_units=100,
            # no is_demo, allow_fractional=False) before migration could run.
            # If the singular doc differs, the singular (seeded) settings are
            # correct — overwrite the stale default.
            singular_is_demo = doc.get("is_demo", False)
            plural_is_demo = existing_plural.get("is_demo", False)

            plural_is_default = (
                existing_plural.get("total_authorized_units") == 100
                and existing_plural.get("allow_fractional") is False
                and existing_plural.get("unit_label")
                in ("Certificate Unit", "Unitypia")
            )
            settings_differ = (
                existing_plural.get("is_demo") != singular_is_demo
                or existing_plural.get("total_authorized_units")
                    != doc.get("total_authorized_units")
                or existing_plural.get("allow_fractional")
                    != doc.get("allow_fractional")
                or existing_plural.get("unit_label")
                    != doc.get("unit_label")
            )

            if plural_is_default and settings_differ:
                # Reconcile: overwrite the stale app-default with seeded data
                reconciled = {
                    k: v
                    for k, v in doc.items()
                    if k != "_id"
                }
                reconciled["updated_at"] = datetime.now(timezone.utc).isoformat()
                await plural.update_one(
                    {"_id": existing_plural["_id"]},
                    {"$set": reconciled},
                )
                moved += 1
                logger.info(
                    f"Reconciled trust_id={trust_id}, user_id={user_id} "
                    f"(overwrote stale app-default plural doc with singular)"
                )
            else:
                logger.debug(
                    f"Plural doc already exists for trust_id={trust_id}, "
                    f"user_id={user_id} — no conflict, skipping"
                )
            skipped += 1
            continue

        # Prepare doc for insertion (remove _id, ensure updated_at)
        new_doc = {k: v for k, v in doc.items() if k != "_id"}
        if "updated_at" not in new_doc or new_doc.get("updated_at") is None:
            new_doc["updated_at"] = datetime.now(timezone.utc).isoformat()

        try:
            result = await plural.insert_one(new_doc)
            logger.info(f"Moved doc trust_id={trust_id}, user_id={user_id} → plural _id={result.inserted_id}")
            moved += 1
        except Exception as exc:
            logger.error(f"Failed to insert doc for trust_id={trust_id}, user_id={user_id}: {exc}")
            errors += 1

    # After counts
    after_singular = await singular.count_documents({})
    after_plural = await plural.count_documents({})
    logger.info(f"AFTER  — trust_unit_settings: {after_singular}, trust_units_settings: {after_plural}")
    logger.info(f"Summary — moved: {moved}, skipped: {skipped}, errors: {errors}")

    return {
        "before_singular": before_singular,
        "before_plural": before_plural,
        "after_singular": after_singular,
        "after_plural": after_plural,
        "moved": moved,
        "skipped": skipped,
        "errors": errors,
    }


if __name__ == "__main__":
    result = asyncio.run(migrate_trust_unit_settings())
    print("\nMigration complete.")
    print(f"  trust_unit_settings (singular): {result['after_singular']} docs")
    print(f"  trust_units_settings (plural):  {result['after_plural']} docs")
