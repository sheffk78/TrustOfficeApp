"""
Retroactive backfill: create bank_account records for already-finalized minutes
that have bank info but no corresponding bank_account record.

This fixes the gap where initial_trustee_meeting and bank_account_authorization
minutes were finalized before the bank-account-creation feature was added.

Usage:
    cd backend
    python scripts/backfill_bank_accounts_from_minutes.py [--dry-run]

Requires MONGO_URL and DB_NAME env vars (or defaults to localhost).
"""
import asyncio
import os
import sys
import re
import uuid
from datetime import datetime, timezone

# Ensure backend dir is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "trustoffice"))
os.environ.setdefault("JWT_SECRET", "backfill-script")

from database import db

BANK_ACCOUNT_TEMPLATES = {"initial_trustee_meeting", "bank_account_authorization"}


def extract_bank_account_info(template_data: dict) -> dict | None:
    """Extract bank account fields from template_data if present and non-empty."""
    if not template_data:
        return None
    bank_name = (template_data.get("bank_name") or "").strip()
    if not bank_name or bank_name == "[Bank Name]":
        return None
    account_number = (template_data.get("account_number") or "").strip()
    digits_only = re.sub(r"\D", "", account_number)
    account_last4 = digits_only[-4:] if len(digits_only) >= 4 else (digits_only if digits_only else "")
    return {
        "institution": bank_name,
        "account_type": template_data.get("account_type", "checking"),
        "initial_deposit": template_data.get("initial_deposit"),
        "account_last4": account_last4,
    }


async def backfill(dry_run: bool = False):
    """Find finalized minutes with bank info and create missing bank_account records."""
    # Search both minutes_records and minutes_templates
    sources = [
        ("minutes_records", {"status": "finalized"}, "minutes_id", "template_data", "template_type", "trust_id", "meeting_date"),
        ("minutes_templates", {"status": "final"}, "minutes_id", "template_data", "template_type", "trust_id", "meeting_date"),
    ]

    created = 0
    skipped_no_entity = 0
    skipped_no_last4 = 0
    skipped_existing = 0
    errors = 0

    for collection_name, status_filter, id_field, data_field, type_field, trust_field, date_field in sources:
        collection = getattr(db, collection_name)
        cursor = collection.find(status_filter, {"_id": 0})
        async for doc in cursor:
            minutes_id = doc.get(id_field, "")
            template_type = doc.get(type_field, "")
            template_data = doc.get(data_field, {}) or {}
            trust_id = doc.get(trust_field, "")
            user_id = doc.get("user_id", "")
            meeting_date = doc.get(date_field)

            if template_type not in BANK_ACCOUNT_TEMPLATES:
                continue

            bank_info = extract_bank_account_info(template_data)
            if not bank_info:
                continue

            if not bank_info["account_last4"]:
                print(f"  SKIP (no last4): {minutes_id} — bank_name={bank_info['institution']}")
                skipped_no_last4 += 1
                continue

            # Check if bank account already exists for this minutes_id
            existing = await db.bank_accounts.find_one({
                "trust_id": trust_id,
                "user_id": user_id,
                "source_minutes_id": minutes_id,
            })
            if existing:
                print(f"  SKIP (exists): {minutes_id} — already has bank_account {existing.get('account_id')}")
                skipped_existing += 1
                continue

            # Find the trust's entity
            entity = await db.entities.find_one(
                {"trust_id": trust_id, "user_id": user_id},
                {"_id": 0, "entity_id": 1, "name": 1},
            )
            if not entity:
                print(f"  SKIP (no entity): {minutes_id} — trust_id={trust_id}")
                skipped_no_entity += 1
                continue

            # Map account type
            valid_types = {"checking", "savings", "investment", "brokerage", "cd", "other"}
            account_type = bank_info["account_type"]
            if account_type not in valid_types:
                account_type = "other"

            account_id = f"bac_{uuid.uuid4().hex[:12]}"
            now = datetime.now(timezone.utc).isoformat()
            nickname = f"{bank_info['institution']} ****{bank_info['account_last4']}"

            bank_doc = {
                "account_id": account_id,
                "trust_id": trust_id,
                "entity_id": entity["entity_id"],
                "user_id": user_id,
                "nickname": nickname,
                "institution_name": bank_info["institution"],
                "account_type": account_type,
                "last_four": bank_info["account_last4"],
                "is_archived": False,
                "source_minutes_id": minutes_id,
                "created_at": now,
                "updated_at": now,
            }

            if dry_run:
                print(f"  DRY RUN: Would create bank_account for {minutes_id}: {nickname} ({account_type})")
                created += 1
                continue

            try:
                await db.bank_accounts.insert_one(bank_doc)
                await db.audit_trail.insert_one({
                    "audit_id": f"bank_acct_backfill_{account_id}",
                    "user_id": user_id,
                    "trust_id": trust_id,
                    "action": "bank_account_backfill_from_minutes",
                    "entity_type": "bank_account",
                    "entity_id": account_id,
                    "details": {
                        "minutes_id": minutes_id,
                        "institution": bank_info["institution"],
                        "account_last4": bank_info["account_last4"],
                        "account_type": account_type,
                    },
                    "timestamp": now,
                })
                print(f"  CREATED: {account_id} for {minutes_id} — {nickname} ({account_type})")
                created += 1
            except Exception as e:
                print(f"  ERROR: Failed to create bank account for {minutes_id}: {e}")
                errors += 1

    print(f"\n=== Backfill complete ===")
    print(f"  Created:         {created}")
    print(f"  Skipped (exist): {skipped_existing}")
    print(f"  Skipped (no 4):  {skipped_no_last4}")
    print(f"  Skipped (no ent):{skipped_no_entity}")
    print(f"  Errors:          {errors}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    if dry:
        print("Running in DRY RUN mode — no changes will be made.\n")
    asyncio.run(backfill(dry_run=dry))