#!/usr/bin/env python3
"""
migrate_subscribers.py — TrustOffice 3-tier pricing migration
=============================================================

One-time MongoDB migration script. Converts existing subscriber documents
from the legacy 2-plan system ("monthly" / "annual") to the new 3-tier
system, grandfathering them into the "trustee" tier with a 10-trust limit.

WHAT IT DOES
------------
For every subscription document where `plan_type` ∈ {"monthly", "annual"}:

    plan_type           → "trustee"
    billing_period      → old plan_type value ("monthly" or "annual")
    legacy_trust_limit  → 10   (grandfathered users keep their 10-trust limit)
    stripe_subscription_id  → unchanged (Stripe subscription stays as-is)
    all other fields    → unchanged

No Stripe API calls are made. The Stripe subscription continues to bill
at the legacy price; the migration only normalizes the MongoDB document
so the application's new 3-tier logic applies correctly.

ENVIRONMENT VARIABLES
---------------------
    MONGO_URL   MongoDB connection string (required)
    DB_NAME     MongoDB database name (required)

Both are loaded from a local `.env` file if present (same pattern as the
backend's database.py).

USAGE
-----
    # Dry run — show what WOULD be changed, make no writes
    python3 migrate_subscribers.py --dry-run

    # Full migration
    python3 migrate_subscribers.py

    # Migrate a single user (for testing)
    python3 migrate_subscribers.py --user-id <user_id>

    # Dry run for a single user
    python3 migrate_subscribers.py --dry-run --user-id <user_id>

EXIT CODES
----------
    0  success (or dry-run completed with no errors)
    1  configuration / connection error
    2  one or more document updates failed (partial migration)
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Load .env from the backend directory (same as the app's database.py)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # dotenv not installed — env vars must be set externally

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:
    print("ERROR: pymongo is not installed. Install with:  pip install pymongo",
          file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LEGACY_PLAN_TYPES = ("monthly", "annual")
NEW_PLAN_TYPE = "trustee"
GRANDFATHERED_TRUST_LIMIT = 10


def get_collection():
    """Connect to MongoDB using the same env vars as the backend and return
    the `subscriptions` collection."""
    mongo_url = os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URL") or os.environ.get("MONGO_URI")
    db_name = os.environ.get("DB_NAME")

    if not mongo_url:
        print("ERROR: MONGO_URL environment variable is required.", file=sys.stderr)
        sys.exit(1)
    if not db_name:
        print("ERROR: DB_NAME environment variable is required.", file=sys.stderr)
        sys.exit(1)

    client = MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
    )
    # Fail fast if the server is unreachable
    client.admin.command("ping")
    db = client[db_name]
    return db["subscriptions"], client


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

def build_update(old_plan_type: str) -> dict:
    """Build the $set update document for a single subscription."""
    return {
        "$set": {
            "plan_type": NEW_PLAN_TYPE,
            "billing_period": old_plan_type,        # "monthly" or "annual"
            "legacy_trust_limit": GRANDFATHERED_TRUST_LIMIT,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    }


def migrate(dry_run: bool, user_id: str | None) -> int:
    """Run the migration. Returns process exit code."""
    collection, client = get_collection()
    now_label = datetime.now(timezone.utc).isoformat()

    print("=" * 70)
    print(f"TrustOffice subscriber migration — {now_label}")
    print(f"  Mode      : {'DRY RUN (no writes)' if dry_run else 'LIVE (writes enabled)'}")
    print(f"  Database  : {os.environ.get('DB_NAME')}")
    print(f"  Collection: subscriptions")
    if user_id:
        print(f"  User filter: {user_id}")
    print("=" * 70)

    # Build the query: legacy plan_types, optionally scoped to one user
    query = {"plan_type": {"$in": list(LEGACY_PLAN_TYPES)}}
    if user_id:
        query["user_id"] = user_id

    cursor = collection.find(query, {"_id": 0})
    docs = list(cursor)

    found = len(docs)
    updated = 0
    errors = 0

    print(f"\nFound {found} subscription document(s) with legacy plan_type "
          f"({', '.join(LEGACY_PLAN_TYPES)}).\n")

    if found == 0:
        print("Nothing to migrate.")
        client.close()
        return 0

    # Print a table of what will change
    print(f"{'user_id':<40} {'plan_type':<10} -> {'new':<10} {'billing_period':<16} {'stripe_sub_id'}")
    print("-" * 100)

    for doc in docs:
        uid = doc.get("user_id", "<missing>")
        old_plan = doc.get("plan_type", "<missing>")
        stripe_sub = doc.get("stripe_subscription_id", "")

        new_billing = old_plan  # billing_period takes the old plan_type value
        print(f"{uid:<40} {old_plan:<10} -> {NEW_PLAN_TYPE:<10} {new_billing:<16} {stripe_sub or '(none)'}")

        if dry_run:
            # Dry run — don't touch the database
            updated += 1
            continue

        # Live mode — perform the update
        update_doc = build_update(old_plan)
        try:
            result = collection.update_one(
                {"user_id": uid, "plan_type": old_plan},
                update_doc,
            )
            if result.matched_count == 1:
                updated += 1
            else:
                # Race condition: plan_type changed between find and update
                errors += 1
                print(f"  WARNING: document for {uid} was not updated "
                      f"(matched_count={result.matched_count}). It may have "
                      f"changed since the scan.", file=sys.stderr)
        except PyMongoError as exc:
            errors += 1
            print(f"  ERROR updating {uid}: {exc}", file=sys.stderr)

    # Summary
    print("\n" + "=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"  Documents found : {found}")
    if dry_run:
        print(f"  Would update     : {updated}")
        print(f"  Errors           : {errors}")
        print("\nDry run complete — no changes were written to MongoDB.")
    else:
        print(f"  Documents updated: {updated}")
        print(f"  Errors           : {errors}")
        if errors:
            print("\nSome documents failed to update. See warnings above.")
        else:
            print("\nAll matching documents updated successfully.")

    client.close()

    if errors and not dry_run:
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Migrate TrustOffice subscribers from legacy 2-plan "
                    "system (monthly/annual) to the new 3-tier trustee plan.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 migrate_subscribers.py --dry-run\n"
            "  python3 migrate_subscribers.py\n"
            "  python3 migrate_subscribers.py --user-id abc123 --dry-run\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making any writes.",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default=None,
        help="Migrate only the subscription for this user_id (for testing).",
    )
    args = parser.parse_args()

    try:
        exit_code = migrate(dry_run=args.dry_run, user_id=args.user_id)
    except PyMongoError as exc:
        print(f"FATAL: MongoDB error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()