#!/usr/bin/env python3
"""
Migration script: Backfill message_count on chat_conversations.

For every conversation document that lacks a `message_count` field
(or has it set to 0 while messages exist), count the length of the
`messages` array and set `message_count` accordingly.

Usage:
    python migrate_conversation_message_count.py              # live run
    python migrate_conversation_message_count.py --dry-run     # preview only

Environment variables:
    MONGO_URL   — MongoDB connection string (default: mongodb://localhost:27017)
    DB_NAME     — Database name (default: trust_office)
"""

import argparse
import os
import sys

from pymongo import MongoClient


def get_db():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "trust_office")
    client = MongoClient(mongo_url)
    return client[db_name]


def migrate(dry_run=False):
    db = get_db()
    col = db["chat_conversations"]

    # Find conversations without message_count, or with message_count=0 and non-empty messages
    query = {
        "$or": [
            {"message_count": {"$exists": False}},
            {"$and": [
                {"message_count": 0},
                {"messages.0": {"$exists": True}},
            ]},
        ]
    }

    cursor = col.find(query, {"messages": 1, "message_count": 1})
    total = 0
    updated = 0
    skipped = 0

    for doc in cursor:
        total += 1
        messages = doc.get("messages", [])
        actual_count = len(messages)
        current_count = doc.get("message_count", 0)

        if current_count == actual_count:
            skipped += 1
            continue

        if dry_run:
            print(
                f"  [DRY-RUN] conversation {doc['_id']}: "
                f"message_count {current_count} → {actual_count}"
            )
        else:
            col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"message_count": actual_count}},
            )

        updated += 1

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"\n[{mode}] Migration complete.")
    print(f"  Scanned: {total}")
    print(f"  Updated: {updated}")
    print(f"  Skipped (already correct): {skipped}")

    return updated


def main():
    parser = argparse.ArgumentParser(
        description="Backfill message_count on chat_conversations"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the database",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("Running in DRY-RUN mode — no writes will be performed.\n")
    else:
        print("Running in LIVE mode — database will be updated.\n")

    try:
        count = migrate(dry_run=args.dry_run)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    if count > 0 and not args.dry_run:
        print(f"\n{count} conversation(s) updated successfully.")
    elif count == 0:
        print("\nNo conversations needed updating.")


if __name__ == "__main__":
    main()