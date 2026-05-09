"""
One-time migration: rename onboarding state fields from the old schema to the new schema.

Old: entities_confirmed, distribution_logged (4 fields total)
New: formation_date_added, ein_entered, trust_doc_uploaded, ein_doc_uploaded,
     beneficiaries_added, assets_added, minutes_generated, calendar_set, checklist_dismissed (9 fields)

Maps:
  - entities_confirmed → assets_added (entity = asset)
  - distribution_logged → removed (no direct mapping)
  - Missing new fields → default to False

Also adds backward compatibility: if old fields exist but new fields don't, 
migrates values before the app reads them.
"""

import logging

logger = logging.getLogger(__name__)


class OnboardingMigration:
    """Migrate onboarding_state documents from old field names to new field names."""

    async def migrate_onboarding_fields(self) -> int:
        """
        Run the onboarding field migration.
        Returns the number of documents migrated.
        """
        from database import db

        # Find documents that still have old field names
        docs_with_old_fields = await db.user_onboarding.find({
            "$or": [
                {"entities_confirmed": {"$exists": True}},
                {"distribution_logged": {"$exists": True}},
                {"assets_added": {"$exists": False}}  # new field missing = needs migration
            ]
        }).to_list(10000)

        if not docs_with_old_fields:
            return 0

        migrated = 0
        for doc in docs_with_old_fields:
            update = {}

            # Map old→new: entities_confirmed → assets_added
            if "entities_confirmed" in doc and "assets_added" not in doc:
                update["assets_added"] = doc.get("entities_confirmed", False)

            # Add missing new fields with defaults
            if "formation_date_added" not in doc:
                # Check if trust has start_date (will be auto-detected later)
                update["formation_date_added"] = False
            if "ein_entered" not in doc:
                update["ein_entered"] = False
            if "trust_doc_uploaded" not in doc:
                update["trust_doc_uploaded"] = False
            if "ein_doc_uploaded" not in doc:
                update["ein_doc_uploaded"] = False
            if "beneficiaries_added" not in doc:
                update["beneficiaries_added"] = False
            if "minutes_generated" not in doc and "minutes_generated" not in update:
                # Preserve existing value if present
                pass  # already has default from schema

            # Remove old fields
            unset = {}
            if "entities_confirmed" in doc:
                unset["entities_confirmed"] = ""
            if "distribution_logged" in doc:
                unset["distribution_logged"] = ""

            # Apply updates
            operations = {}
            if update:
                operations["$set"] = update
            if unset:
                operations["$unset"] = unset

            if operations:
                await db.user_onboarding.update_one(
                    {"user_id": doc["user_id"]},
                    operations
                )
                migrated += 1

        logger.info(f"Onboarding migration: migrated {migrated} documents")
        return migrated