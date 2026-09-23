#!/usr/bin/env python3
"""Backfill trust_parties from existing flat successor/protector fields.

Sources: successor_trustee_name/email and trust_protector_name/email fields
on existing trust docs; powers carried from trust_protector_powers.json.

Creates TrustParty rows with source="backfill", status="invited", NO grants.
Access stays zero until owner grants later.

Usage:
    python scripts/backfill_trust_parties.py --dry-run
    python scripts/backfill_trust_parties.py --write

Idempotent: re-run skips existing emails per trust.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# Bootstrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice")

from database import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _backfill(dry_run: bool):
    powers_path = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "trust_protector_powers.json")
    try:
        with open(powers_path) as f:
            allowed_powers = {p["value"] for p in json.load(f).get("powers", [])}
    except Exception:
        allowed_powers = set()

    cursor = db.trusts.find({}, {"_id": 0, "trust_id": 1, "user_id": 1, "successor_trustee_name": 1, "successor_trustee_email": 1, "secondary_successor_trustee_name": 1, "secondary_successor_trustee_email": 1, "trust_protector_name": 1, "trust_protector_email": 1, "trust_protector_powers": 1})
    inserts = []
    skipped = 0
    total = 0

    async for trust in cursor:
        trust_id = trust["trust_id"]
        existing_emails = {
            p["email"] async for p in db.trust_parties.find({"trust_id": trust_id}, {"_id": 0, "email": 1})
        }

        sources = [
            ("co_trustee", trust.get("successor_trustee_name"), trust.get("successor_trustee_email")),
            ("co_trustee", trust.get("secondary_successor_trustee_name"), trust.get("secondary_successor_trustee_email")),
            ("protector", trust.get("trust_protector_name"), trust.get("trust_protector_email")),
        ]

        for party_type, name, email in sources:
            if not email or not name:
                continue
            if email in existing_emails:
                skipped += 1
                continue
            total += 1
            doc = {
                "party_id": f"party_{trust_id}_{party_type}_{total}",
                "trust_id": trust_id,
                "party_type": party_type,
                "name": name,
                "email": email,
                "status": "invited",
                "powers": list({p for p in (trust.get("trust_protector_powers") or []) if p in allowed_powers}) if party_type == "protector" else [],
                "invited_at": _now(),
                "activated_at": None,
                "user_id": None,
                "source": "backfill",
            }
            inserts.append(doc)
            existing_emails.add(email)

    print(f"Would insert {len(inserts)} trust_parties (skipped {skipped} existing).")
    if dry_run:
        for doc in inserts:
            print(f"  DRY-RUN: {doc['party_type']} {doc['name']} <{doc['email']}> trust={doc['trust_id']}")
        return

    if inserts:
        await db.trust_parties.insert_many(inserts)
    print(f"Wrote {len(inserts)} trust_parties.")


def main():
    parser = argparse.ArgumentParser(description="Backfill trust_parties from flat successor/protector fields")
    parser.add_argument("--dry-run", action="store_true", help="Print only, do not write")
    parser.add_argument("--write", action="store_true", help="Actually write to MongoDB")
    args = parser.parse_args()

    if not args.dry_run and not args.write:
        print("Error: specify --dry-run or --write")
        sys.exit(1)

    asyncio.run(_backfill(dry_run=not args.write))


if __name__ == "__main__":
    main()
