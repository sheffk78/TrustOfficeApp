"""
One-time backfill for trusts missing governance seeds + bank-asset creation.

Fixes three production gaps (JOB 20260904-TO-HEALTH-SCORE-JUSTIN):
1. Trusts with zero governance tasks -> seed the 4 default tasks
   (same shape as dependencies.create_initial_governance_tasks).
2. Trusts with zero tax_calendar entries -> generate this/next year entries,
   marking pre-formation deadlines not_required (same as in-app creation).
3. Finalized bank-account minutes with no Schedule A item -> create the
   draft asset that _auto_create_draft_asset_from_minutes should have made.

Idempotent: only fills gaps, never duplicates. Dry-run by default.
Run:  python3 scripts/backfill_governance_seeds.py [--apply]
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

sys.path.insert(0, ".")

# Connect directly via MONGO_URL (public proxy) — do not import database.py,
# which points at the Railway-internal hostname. DB_NAME defaults to trustoffice.
import motor.motor_asyncio  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "trustoffice")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=20000)
db = client[DB_NAME]

DRY_RUN = "--execute" not in sys.argv

TASK_DESCRIPTIONS = {
    "annual_review": "Annual trust review and documentation",
    "quarterly_review": "Quarterly trust performance review",
    "compensation_review": "Review trustee compensation arrangements",
    "asset_revaluation": "Annual re-valuation of all Schedule A assets",
}

BANK_TEMPLATES = {"initial_trustee_meeting", "bank_account_authorization"}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def seed_tasks(trust: dict, now: datetime) -> int:
    trust_id, user_id = trust["trust_id"], trust["user_id"]
    if await db.governance_tasks.count_documents({"trust_id": trust_id}) > 0:
        return 0

    # Annual review due 1 year after formation (fallback: creation + 365d)
    start = trust.get("start_date")
    annual_due = None
    if start:
        try:
            formation = datetime.fromisoformat(str(start))
            annual_due = formation + relativedelta(years=1)
        except (ValueError, TypeError):
            pass
    if annual_due is None:
        annual_due = now + relativedelta(days=365)

    docs = [
        {
            "task_id": f"task_{__import__('uuid').uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "annual_review",
            "due_date": _iso(annual_due),
            "completed_at": None,
            "description": TASK_DESCRIPTIONS["annual_review"],
            "created_at": _iso(now),
        },
        {
            "task_id": f"task_{__import__('uuid').uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "quarterly_review",
            "due_date": _iso(now + relativedelta(days=90)),
            "completed_at": None,
            "description": TASK_DESCRIPTIONS["quarterly_review"],
            "created_at": _iso(now),
        },
        {
            "task_id": f"task_{__import__('uuid').uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "compensation_review",
            "due_date": _iso(now + relativedelta(days=180)),
            "completed_at": None,
            "description": TASK_DESCRIPTIONS["compensation_review"],
            "created_at": _iso(now),
        },
        {
            "task_id": f"task_{__import__('uuid').uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "asset_revaluation",
            "due_date": _iso(now + relativedelta(days=365)),
            "completed_at": None,
            "description": TASK_DESCRIPTIONS["asset_revaluation"],
            "created_at": _iso(now),
        },
    ]
    if DRY_RUN:
        print(f"  [DRY] would seed 4 tasks for {trust_id} ({trust.get('name')})")
        return 4
    await db.governance_tasks.insert_many([dict(t) for t in docs])
    return 4


async def seed_tax_calendar(trust: dict, now: datetime) -> int:
    trust_id = trust["trust_id"]
    if await db.tax_calendar.count_documents({"trust_id": trust_id}) > 0:
        return 0

    from utils.tax_calendar_math import CALENDAR_RULES, _seed_tax_year

    year = _seed_tax_year()
    entries = []
    for rule in CALENDAR_RULES:
        due = datetime(year, rule["month"], rule["day"], tzinfo=timezone.utc)
        if due < now:
            # deadline passed before trust existed / seeding — mark not_required
            # (mirrors routers/trusts._mark_past_tax_entries_not_required)
            status = "not_required"
            notes = "Not applicable — trust created after this deadline"
        else:
            status = "pending"
            notes = None
        entries.append({
            "entry_id": f"tax_{__import__('uuid').uuid4().hex[:12]}",
            "trust_id": trust_id,
            "tax_year": year,
            "deadline_type": rule["deadline_type"],
            "due_date": due.date().isoformat(),
            "filing_status": status,
            "filed_date": None,
            "description": rule["desc"],
            "notes": notes,
            "accountant_engaged": False,
            "created_at": _iso(now),
            "updated_at": _iso(now),
        })

    if DRY_RUN:
        print(f"  [DRY] would seed {len(entries)} tax entries ({year}) for {trust_id} ({trust.get('name')})")
        return len(entries)
    await db.tax_calendar.insert_many(entries)
    return len(entries)


def _extract_bank_info(template_data: dict):
    if not template_data:
        return None
    bank = template_data.get("bank_name")
    if not bank or not str(bank).strip():
        return None
    acct = str(template_data.get("account_number") or "")
    last4 = acct[-4:] if len(acct) >= 4 else ""
    return {
        "institution": str(bank).strip(),
        "account_type": template_data.get("account_type") or "",
        "initial_deposit": template_data.get("initial_deposit"),
        "account_last4": last4,
    }


def _to_float(v):
    """Parse a deposit value that may be a number or a formatted string ('$1,500')."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


async def create_missing_bank_assets(minutes_doc: dict, now: datetime) -> bool:
    """Create the Schedule A asset a finalized bank-minutes should have made.

    Minutes are already finalized (status='final'), which means the user
    completed the confirmation flow — so the asset is created ACTIVE
    (scoreable), not draft.
    """
    trust_id, user_id = minutes_doc["trust_id"], minutes_doc["user_id"]
    minutes_id = minutes_doc["minutes_id"]
    td = minutes_doc.get("template_data") or {}

    # Already has any Schedule A items for this trust? (incl. draft) -> skip
    if await db.schedule_a_items.count_documents({"trust_id": trust_id, "user_id": user_id}) > 0:
        return False

    bank = _extract_bank_info(td)
    if not bank:
        return False

    meeting_date = minutes_doc.get("meeting_date") or now.strftime("%Y-%m-%d")
    description = f"Bank Account — {bank['institution']}"
    if bank["account_last4"]:
        description += f" (ending {bank['account_last4']})"

    item_id = f"asset_{__import__('uuid').uuid4().hex[:12]}"
    doc = {
        "item_id": item_id,
        "trust_id": trust_id,
        "user_id": user_id,
        "category": "financial_accounts",
        "description": description,
        "identifier": f"****{bank['account_last4']}" if bank["account_last4"] else "",
        "location": bank["institution"],
        "approximate_value": _to_float(bank["initial_deposit"]),
        "date_conveyed": meeting_date,
        "notes": f"Backfill: auto-created from finalized minutes (type: {minutes_doc.get('template_type')}). Account type: {bank['account_type']}.",
        "status": "active",
        "source_minutes_id": minutes_id,
        "source_template_type": minutes_doc.get("template_type"),
        "minutes_ref": minutes_id,
        "disposition_minutes_ref": None,
        "disposition_date": None,
        "disposition_notes": None,
        "created_at": _iso(now),
        "updated_at": None,
    }

    if DRY_RUN:
        print(f"  [DRY] would create active asset '{description}' for {trust_id} from minutes {minutes_id}")
        return True

    await db.schedule_a_items.insert_one(doc)
    await db.audit_trail.insert_one({
        "audit_id": f"backfill_draft_asset_{item_id}",
        "user_id": user_id,
        "trust_id": trust_id,
        "action": "backfill_draft_asset_from_minutes",
        "entity_type": "schedule_a_item",
        "entity_id": item_id,
        "details": {"minutes_id": minutes_id, "reason": "template-finalize gap backfill 2026-09-04"},
        "created_at": _iso(now),
    })
    return True


async def main():
    now = datetime.now(timezone.utc)
    print(f"=== Governance seed backfill ({'EXECUTE' if DRY_RUN else 'DRY RUN'}) ===")

    trusts = await db.trusts.find({}, {"_id": 0, "trust_id": 1, "user_id": 1, "name": 1, "start_date": 1}).to_list(500)
    print(f"Trusts: {len(trusts)}")

    tasks_added = tax_added = assets_added = 0
    for t in trusts:
        n1 = await seed_tasks(t, now)
        n2 = await seed_tax_calendar(t, now)
        if n1 or n2:
            print(f" trust {t['trust_id']} ({t.get('name')}): +{n1} tasks, +{n2} tax entries")
        tasks_added += n1
        tax_added += n2

    finals = await db.minutes_templates.find(
        {"status": "final", "template_type": {"$in": list(BANK_TEMPLATES)}}, {"_id": 0}
    ).to_list(500)
    print(f"Finalized bank minutes: {len(finals)}")
    for m in finals:
        if await create_missing_bank_assets(m, now):
            assets_added += 1

    print(f"\nSUMMARY: +{tasks_added} governance tasks, +{tax_added} tax entries, +{assets_added} Schedule A draft assets")
    if DRY_RUN:
        print("DRY RUN — re-run with --execute to apply.")
    else:
        print("Done. Recalculate health snapshots next (per-trust force snapshot).")


if __name__ == "__main__":
    asyncio.run(main())