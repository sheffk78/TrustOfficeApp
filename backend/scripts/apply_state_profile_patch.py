"""Apply the source-verified state-profile delta table (2026-10-29).

Verifies 2026-10-29 state-profile deltas against MongoDB (two-stage):
1. Dry-run: reads current prod profiles for every state in the delta table,
   compares utc_adopted / utc_adoption_year / notice fields against the
   verified values, and prints the plan.
2. --apply: writes $set updates (values + verification metadata) to
   state_compliance_profiles, and appends every change to
   knowledge/state_profile_changelog.json.

Sources for every delta (recorded per state in the delta JSON):
  - ULC enactment list (36 states/jurisdictions, cross-checked 2026-10-29)
  - ACTEC/COBAR "States that Adopted the UTC" survey (Nelson)
  - mytrusts.us statutes table (compiled 2026-07-05)
  - Primary state sources fetched 2026-10-29: ncleg.gov ch. 36C, Iowa
    legislature ch. 633A + Begleiter Drake L. Rev. 2011, OK SB444/Westlaw,
    NRS ch. 163, Farr Law 2024 NOT-ENACTED list.
Data file: Kit/life/brands/TrustOffice/specs/2026-10-29-state-profile-deltas.json
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

DELTA_PATH = Path(
    "/Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/"
    "specs/2026-10-29-state-profile-deltas.json"
)
CHANGELOG_PATH = Path(
    "/Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/"
    "projects/TrustOfficeApp/backend/knowledge/state_profile_changelog.json"
)

VERIFY_TAG = "kit-two-source-2026-10-29"


def main() -> None:
    apply = "--apply" in sys.argv
    deltas = json.loads(DELTA_PATH.read_text())
    print(f"Loaded {len(deltas)} state deltas (apply={apply})")

    from database import db  # async Mongo handle used across the backend

    changed: list[dict] = []

    async def run() -> None:
        for code, d in sorted(deltas.items()):
            cur = await db.state_compliance_profiles.find_one({"_id": code})
            if cur is None:
                print(f"  !! {code}: no profile in Mongo — seed first, skipping")
                continue
            plan = {}
            for field in ("utc_adopted", "utc_adoption_year", "utc_note"):
                if field in d and d[field] is not None and cur.get(field) != d[field]:
                    plan[field] = d[field]
            # verified marker always set on patched states
            plan["state_profile_verified"] = True
            plan["state_profile_verified_at"] = VERIFY_TAG
            if plan == {"state_profile_verified": True, "state_profile_verified_at": VERIFY_TAG}:
                print(f"  = {code}: already matches verified values, mark only")
            print(f"  {code}: {json.dumps(plan, ensure_ascii=False)[:220]}")
            if apply:
                await db.state_compliance_profiles.update_one(
                    {"_id": code}, {"$set": plan}
                )
                changed.append({"state": code, "changes": plan})

    import asyncio

    asyncio.run(run())

    if apply and changed:
        CHANGELOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "verified_by": VERIFY_TAG,
            "changes": changed,
        }
        log = json.loads(CHANGELOG_PATH.read_text()) if CHANGELOG_PATH.exists() else []
        log.append(entry)
        CHANGELOG_PATH.write_text(json.dumps(log, indent=1))
        print(f"changelog appended -> {CHANGELOG_PATH} ({len(changed)} states patched)")
    elif not apply:
        print("dry-run only; re-run with --apply to write")


if __name__ == "__main__":
    main()