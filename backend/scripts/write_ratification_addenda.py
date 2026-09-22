#!/usr/bin/env python3
"""
write_ratification_addenda.py — store generated ratification addenda into
production minutes_templates records (Tier-2 remediation, Jeff-approved
2026-09-21).

For each finalized initial-minutes record:
  - regenerates the addendum with build_addendum (council-approved wording)
  - sets additive fields only (no existing field is modified):
      ratification_addendum      text
      ratification_status        'awaiting_signature'
      ratification_generated_at  ISO UTC
      ratification_generator     version tag
  - idempotent: existing identical addendum -> skip; absent -> set;
    differing -> update (regeneration is deterministic)

Usage:
  MONGO_URL=... DB_NAME=trustoffice python3 scripts/write_ratification_addenda.py --dry-run
  MONGO_URL=... DB_NAME=trustoffice python3 scripts/write_ratification_addenda.py --apply
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_ratification_addenda import build_addendum  # same-dir import

GENERATOR_TAG = "generate_ratification_addenda.py v2 (council-approved 2026-09-21)"


async def run(db_url: str, db_name: str, apply: bool) -> int:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(db_url, serverSelectionTimeoutMS=30000)
    db = client[db_name]
    minutes = db.minutes_templates
    trusts = db.trusts

    cursor = minutes.find({"template_type": "initial_trustee_meeting",
                           "status": "final"})
    docs = await cursor.to_list(length=100)

    written, skipped, errors = [], [], []
    for doc in docs:
        mid = doc.get("minutes_id", "?")
        try:
            trust = await trusts.find_one({"trust_id": doc.get("trust_id")}) or {}
            corrected = doc.get("generated_document") or ""
            if not corrected.strip():
                errors.append(f"{mid}: empty generated_document, cannot build addendum")
                continue
            text = build_addendum(doc, trust, corrected)

            existing = doc.get("ratification_addendum")
            if existing == text and doc.get("ratification_status") == "awaiting_signature":
                skipped.append(mid)
                print(f"  SKIP {mid}: already current")
                continue

            if apply:
                res = await minutes.update_one(
                    {"minutes_id": mid},
                    {"$set": {
                        "ratification_addendum": text,
                        "ratification_status": "awaiting_signature",
                        "ratification_generated_at": datetime.now(timezone.utc).isoformat(),
                        "ratification_generator": GENERATOR_TAG,
                    }})
                if res.modified_count != 1:
                    errors.append(f"{mid}: update modified_count={res.modified_count}")
                    continue
                # read-back verification
                back = await minutes.find_one({"minutes_id": mid},
                                              {"ratification_addendum": 1,
                                               "ratification_status": 1,
                                               "generated_document": 1})
                ok = bool(back) and (
                    back.get("ratification_addendum") == text
                    and back.get("ratification_status") == "awaiting_signature"
                    and back.get("generated_document") == doc.get("generated_document"))
                (written if ok else errors).append(
                    mid if ok else f"{mid}: READ-BACK MISMATCH")
                print(f"  WROTE {mid} ({len(text)} chars) verified={ok}")
            else:
                print(f"  DRY {mid}: would write {len(text)} chars "
                      f"(existing: {'yes' if existing else 'no'})")
        except Exception as exc:  # noqa: BLE001 — per-record isolation
            errors.append(f"{mid}: {exc}")
            print(f"  ERROR {mid}: {exc}")

    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: "
          f"{len(written) if apply else 'n/a'} written, {len(skipped)} skipped-current, "
          f"{len(errors)} errors")
    if errors:
        print("ERRORS:", *errors, sep="\n  - ")
    client.close()
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", default=os.environ.get("MONGO_URL", ""))
    parser.add_argument("--db-name", default=os.environ.get("DB_NAME", "trustoffice"))
    parser.add_argument("--apply", action="store_true",
                        help="Write to production (default: dry-run)")
    args = parser.parse_args()
    if not args.db_url:
        print("MONGO_URL/--db-url required")
        return 2
    return asyncio.run(run(args.db_url, args.db_name, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())