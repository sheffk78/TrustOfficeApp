#!/usr/bin/env python3
"""
Backfill initial trustee minutes for existing TrustOffice trusts.

Fixes records created while generate_initial_trustee_meeting_content had a
missing return statement (docs had header+adjournment but zero resolutions).

Tiers (per Kit/life/brands/TrustOffice/reports/initial-trustee-minutes-eval-2026-09-21.md):
  Tier 1: draft template minutes        -> regenerate generated_document (original_document untouched)
  Tier 2: final, not yet executed       -> REPORT ONLY (needs Jeff approval: unfinalize->regenerate->refinalize)
  Tier 3: executed (signed/used at bank)-> REPORT ONLY (needs corrective ratification minutes, new record)

Usage:
  python3 scripts/backfill_initial_minutes.py --dry-run   # counts + per-record verdicts, no writes
  python3 scripts/backfill_initial_minutes.py --apply     # Tier 1 regeneration only

Requires MONGO_URL/DB_NAME/JWT_SECRET env (same as app). Run inside backend venv.
Single event loop for the whole run (Motor binds its client to the first loop).
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "backfill-local")

BROKEN_MARKERS = [
    "RESOLUTION 1",  # missing when the None->"" bug hit
]

# Pre-cleanup documents: sovereign-citizen language + generic double-wrapper.
# These drafts DO contain "RESOLUTION 1" but must still be regenerated.
OLD_STYLE_MARKERS = [
    "Ecclesiastical",
    "Natural Law",
    "Common Law Copyright",
    "living men",
    "artificial PERSON",
    "CERTIFICATION AND AUTHENTICATION",  # generic wrapper section
]


def classify(doc: dict) -> str:
    """Classify a minutes_templates record into a remediation tier."""
    template_type = doc.get("template_type", "")
    if template_type != "initial_trustee_meeting":
        return "skip:not_initial_meeting"
    status = doc.get("status", "draft")
    generated = doc.get("generated_document") or ""
    is_empty = all(marker not in generated for marker in BROKEN_MARKERS)
    is_old_style = any(marker in generated for marker in OLD_STYLE_MARKERS)
    if not (is_empty or is_old_style):
        return "skip:healthy"
    if status == "final":
        return "tier2:final_needs_approval"
    return "tier1:regenerate"


async def run_backfill(args) -> int:
    from database import db  # noqa: E402  (app import style; client connects at import)
    from routers.minutes import generate_template_document  # noqa: E402

    query = {"template_type": "initial_trustee_meeting"}
    cursor = db.minutes_templates.find(query, {"_id": 0})
    if args.limit:
        cursor = cursor.limit(args.limit)

    counts = {"tier1": 0, "tier2": 0, "tier3": 0, "healthy": 0, "other": 0}
    tier1_docs = []
    tier2_docs = []

    docs = await cursor.to_list(length=args.limit or None)
    for doc in docs:
        verdict = classify(doc)
        if verdict.startswith("tier1"):
            counts["tier1"] += 1
            tier1_docs.append(doc)
        elif verdict.startswith("tier2"):
            counts["tier2"] += 1
            tier2_docs.append(doc)
        elif verdict.startswith("skip:healthy"):
            counts["healthy"] += 1
        else:
            counts["other"] += 1

    print("=== DRY-RUN CLASSIFICATION ===" if args.dry_run else "=== APPLY ===")
    print(f"tier1 (draft, will regenerate): {counts['tier1']}")
    print(f"tier2 (final, needs approval):  {counts['tier2']}")
    print(f"healthy (already complete):     {counts['healthy']}")
    print(f"other/skip:                     {counts['other']}")

    if tier2_docs:
        print("\n--- Tier 2 (needs Jeff approval before any change) ---")
        for doc in tier2_docs[:20]:
            print(f"  - {doc.get('minutes_id')} trust={doc.get('trust_id')} "
                  f"created={doc.get('created_at')}")

    if args.dry_run:
        print("\n--- Tier 1 preview (first 20) ---")
        for doc in tier1_docs[:20]:
            t = doc.get("template_data") or {}
            print(f"  - {doc.get('minutes_id')} trust={doc.get('trust_id')} "
                  f"created={doc.get('created_at')} trustees={t.get('trustees_present')}")
        print("\nNo writes performed. Re-run with --apply to regenerate Tier 1 drafts.")
        return 0

    # --- APPLY: Tier 1 only ---
    fixed, failed = 0, 0
    for doc in tier1_docs:
        minutes_id = doc.get("minutes_id")
        try:
            trust = await db.trusts.find_one({"trust_id": doc.get("trust_id")}, {"_id": 0})
            if not trust:
                print(f"  SKIP {minutes_id}: trust not found")
                failed += 1
                continue
            new_doc = generate_template_document(
                trust,
                doc.get("template_type"),
                doc.get("template_data") or {},
            )
            if not new_doc or "RESOLUTION 1" not in new_doc:
                print(f"  FAIL {minutes_id}: regeneration empty/incomplete")
                failed += 1
                continue
            await db.minutes_templates.update_one(
                {"minutes_id": minutes_id},
                {"$set": {
                    "generated_document": new_doc,
                    # original_document deliberately NOT overwritten (audit trail)
                    "backfill": {
                        "date": datetime.now(timezone.utc).isoformat(),
                        "reason": "generator return-statement defect; resolutions missing",
                        "script": "backfill_initial_minutes.py",
                    },
                }},
            )
            fixed += 1
            print(f"  FIXED {minutes_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR {minutes_id}: {exc}")
            failed += 1

    print(f"\nDone: {fixed} fixed, {failed} failed")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--apply", action="store_true", help="Regenerate Tier 1 records")
    parser.add_argument("--limit", type=int, default=0, help="Max records to process")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("Choose --dry-run or --apply")

    return asyncio.run(run_backfill(args))


if __name__ == "__main__":
    raise SystemExit(main())