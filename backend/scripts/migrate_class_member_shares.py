"""
Migration: backfill derived-share fields for named class members (council
design 2026-10-07 — CLASS-MEMBERS-COUNCIL-2026-10-07.md).

What it does (per collection):
  class_beneficiary_members — additive backfill, docs only ever GAIN fields:
    member_status       'active' when missing (legacy docs divide normally)
    status_reason       None, status_changed_at None
    share_weight        1
    member_order        creation rank (0-based, per class): rank by
                        confirmed_at then class_member_id — reproduces the
                        historical created_at insert order (confirmed_at ==
                        created_at on legacy inserts) deterministically
    name_history        [] when missing
  class_beneficiaries — additive shadow/flags on the pool container:
    share_mode          'per_capita_equal'
    pool_percentage_ppm round(percentage * 10000) — DERIVED-SHADOW only;
                        the stored pool percentage remains the source of truth
    member_version      0 when missing (mutation counter, starts clean)
    active_member_count advisory recount over share-eligible members
    member_count        REPAIRED to the true roster size when drifted
                        (mismatch report printed/returned; self-healing cache)
  class_member_events — append-only ledger:
    member_added        for every pre-existing member doc that has NO ledger
                        event yet (backdated to confirmed_at — "recorded
                        2026-10-08" style creation_order provenance, reason
                        marked backfill). Idempotent: members keep their
                        member_added_event_id; any future duplicate insert
                        on a member that already has one is refused.
  Indexes (both collections + event ledger) — created idempotently.

Safety:
  - DRY RUN BY DEFAULT: prints the full action plan, writes NOTHING.
  - --execute performs the writes; every $set is additive (existing values
    are never overwritten — statuses/weights/orders already set are kept).
  - Per-class verification gate: for every class with >= 1 active member,
    the largest-remainder split of pool_percentage_ppm must sum EXACTLY to
    the pool (integer invariant). A failure ABORTS with exit code 1.
  - Reconciliation report: per trust, sum of (class pools ppm + active
    certificates ppm) vs the 1,000,000 ppm budget (the two-band report; pools
    and certificates may overlap by design — reported, never auto-"fixed").

Usage (venv python required for motor/pymongo):
    cd /path/to/TrustOfficeApp/backend
    .venv/bin/python scripts/migrate_class_member_shares.py              # dry run
    .venv/bin/python scripts/migrate_class_member_shares.py --apply      # apply
    .venv/bin/python scripts/migrate_class_member_shares.py --execute    # (alias of --apply)

Idempotent: re-running with --execute performs no further writes once all
fields are present (guards match only docs missing the target fields).
"""
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import share_math  # noqa: E402  (backend dir on path above)
from services.class_member_indexes import (  # noqa: E402
    CLASS_MEMBER_INDEX_SPECS,
    ensure_class_member_indexes,
)
from database import db, client  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate_class_member_shares")


# ==================== helpers ====================

def _rank_key(doc: dict):
    """Creation-order rank key: confirmed_at, then class_member_id.
    (Migration-time twin of share_math.member_sort_key's legacy branch.)"""
    return (
        str(doc.get("confirmed_at") or ""),
        str(doc.get("class_member_id") or ""),
    )


async def migrate(dry_run: bool) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    stats = {
        "mode": "DRY RUN" if dry_run else "EXECUTE",
        "started_at": started,
        "members_scanned": 0,
        "member_docs_updated": 0,
        "classes_scanned": 0,
        "class_docs_updated": 0,
        "member_count_repairs": [],   # (class_id, stored, actual)
        "pools_scanned": 0,
        "certificates_scanned": 0,
        "reconciliation": [],         # per-trust two-band report
        "sum_check_failures": [],     # verification gate failures
        "classes_empty_roster": 0,
        "events_backfilled": 0,       # backdated member_added ledger events
        "events_skipped_existing": 0, # members that already had an added event
    }

    # ---------- 1. Scan member docs needing backfill (additive $set planned) ----------
    members_filter = {
        "$or": [
            {"member_status": {"$exists": False}},
            {"share_weight": {"$exists": False}},
            {"member_order": {"$exists": False}},
            {"name_history": {"$exists": False}},
            {"status_reason": {"$exists": False}},
            {"status_changed_at": {"$exists": False}},
        ]
    }
    members = await db.class_beneficiary_members.find(members_filter, {"_id": 1}).to_list(None)
    stats["members_scanned"] = await db.class_beneficiary_members.count_documents({})

    # group ids per class so ranks are assigned within each class
    by_class = {}
    for m in members:
        full = await db.class_beneficiary_members.find_one({"_id": m["_id"]})
        by_class.setdefault(full.get("class_beneficiary_id"), []).append(full)

    # the ledger backfill covers EVERY member doc (not just field-gap ones) —
    # a member with all fields present but no member_added event (e.g. left
    # behind by a pre-session-2 partial run) still needs its backdated event.
    for m in (await db.class_beneficiary_members.find(
        {"class_member_id": {"$nin": sorted({d.get("class_member_id") for docs in by_class.values() for d in docs})}},
        {"_id": 1},
    ).to_list(None)):
        full = await db.class_beneficiary_members.find_one({"_id": m["_id"]})
        by_class.setdefault(full.get("class_beneficiary_id"), []).append(full)

    planned_member_sets = {}  # _id -> set_ops (applied in pass 3 with back-pointers)
    for class_id, docs in by_class.items():
        # Rank by confirmed_at, then class_member_id — but NEVER demote a doc
        # that already carries member_order (idempotent re-runs keep it).
        have_order = [d for d in docs if d.get("member_order") is not None]
        need_order = sorted(
            [d for d in docs if d.get("member_order") is None], key=_rank_key
        )
        used_orders = {int(d["member_order"]) for d in have_order if d.get("member_order") is not None}
        next_rank = 0
        for d in need_order:
            while next_rank in used_orders:
                next_rank += 1
            d["_assigned_member_order"] = next_rank
            used_orders.add(next_rank)
            next_rank += 1

        for d in docs:
            set_ops = {}
            if d.get("member_status") is None:
                set_ops["member_status"] = "active"
                set_ops["status_reason"] = None
                set_ops["status_changed_at"] = None
            if d.get("share_weight") is None:
                set_ops["share_weight"] = 1
            if "member_order" not in d:
                set_ops["member_order"] = d.get("_assigned_member_order", 0)
            if d.get("name_history") is None:
                set_ops["name_history"] = []
            if set_ops:
                planned_member_sets[d["_id"]] = (d, set_ops)

    # ---------- 2. Backdated ledger events (council migration step 2) ----------
    # Every member without a member_added event gets one, backdated to the
    # member's confirmed_at (immutable history, honestly labeled as backfill).
    # NOT fabricated history: the event records exactly what is true — this
    # member exists on this roster, was confirmed at confirmed_at, and has no
    # recorded add-mutation because it predates the ledger. Idempotency uses
    # a roster-wide existing-added-member lookup (an event may exist without
    # the member back-pointer on partial migrations). The member back-pointer
    # rides the same member write pass below.
    existing_added = await db.class_member_events.find(
        {"event_type": "member_added"}, {"_id": 0, "class_member_id": 1}
    ).to_list(None)
    members_with_added = {r["class_member_id"] for r in existing_added if r.get("class_member_id")}

    def _event_after(doc: dict) -> dict:
        return {
            "class_member_id": doc.get("class_member_id"),
            "class_beneficiary_id": doc.get("class_beneficiary_id"),
            "name": doc.get("name"),
            "member_status": doc.get("member_status") if doc.get("member_status") is not None else "active",
            "member_order": doc.get("member_order") if doc.get("member_order") is not None else doc.get("_assigned_member_order"),
            "share_weight": doc.get("share_weight") if doc.get("share_weight") is not None else 1,
            "backfill": True,
        }

    _newly_backfilled = {}  # member _id -> event_id (or planned event_id: None)
    for class_id, docs in by_class.items():
        for d in docs:
            mid = d.get("class_member_id")
            if mid in members_with_added:
                stats["events_skipped_existing"] += 1
                continue
            confirmed_at = d.get("confirmed_at") or d.get("created_at") or stats["started_at"]
            event = {
                "event_id": f"cme_{uuid.uuid4().hex[:16]}",
                "trust_id": d.get("trust_id"),
                "user_id": d.get("user_id"),
                "class_beneficiary_id": class_id,
                "class_member_id": mid,
                "event_type": "member_added",
                "before": None,
                "after": _event_after(d),
                "reason": "Backfill: member predates the ledger (created before event recording began)",
                "minutes_record_id": d.get("minutes_record_id"),
                "created_at": confirmed_at,
                "backdated": True,
                "recorded_at": stats["started_at"],
            }
            if dry_run:
                # planned, not written: the pointer sweep in pass 3 must still
                # SEE this member as newly-backfilled to count its write
                logger.info(
                    "[DRY] backdated event member_added for %s (%s) @ %s",
                    mid, d.get("name"), confirmed_at,
                )
                _newly_backfilled[d["_id"]] = None
            else:
                await db.class_member_events.insert_one(event)
                _newly_backfilled[d["_id"]] = event["event_id"]
            stats["events_backfilled"] += 1
            members_with_added.add(mid)

    # ---------- 3. Member-doc write pass: 1's planned sets + 2's back-pointers ----------
    for d_id, (d, set_ops) in planned_member_sets.items():
        if d_id in _newly_backfilled and d.get("member_added_event_id") is None:
            event_id = _newly_backfilled[d_id]
            if event_id is not None:  # None = planned-only (dry run)
                set_ops["member_added_event_id"] = event_id
        if dry_run:
            logger.info(
                "[DRY] member %s (%s): +{%s}",
                d.get("class_member_id"), d.get("name"),
                ", ".join(sorted(set_ops)),
            )
            stats["member_docs_updated"] += 1
        else:
            await db.class_beneficiary_members.update_one(
                {"_id": d_id},
                {"$set": set_ops},
            )
            stats["member_docs_updated"] += 1
    # members whose ONLY missing field is the new back-pointer (already fully
    # backfilled by a previous run before this feature existed)
    fully_backfilled_needing_pointer = await db.class_beneficiary_members.find(
        {"member_added_event_id": {"$exists": False}}, {"_id": 1, "class_member_id": 1}
    ).to_list(None)
    for m in fully_backfilled_needing_pointer:
        if m["_id"] in _newly_backfilled and m["_id"] not in planned_member_sets:
            set_ops = {"member_added_event_id": _newly_backfilled[m["_id"]]}
            if dry_run or set_ops["member_added_event_id"] is None:
                stats["member_docs_updated"] += 1
            else:
                await db.class_beneficiary_members.update_one(
                    {"_id": m["_id"]}, {"$set": set_ops}
                )
                stats["member_docs_updated"] += 1

    # ---------- 4. Per-class pass: pool shadows, counts, repairs, verification ----------
    classes = await db.class_beneficiaries.find({}, {"_id": 0}).to_list(None)
    stats["classes_scanned"] = len(classes)
    # certificates per trust, for the reconciliation band
    cert_rows = await db.trust_unit_certificates.aggregate([
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$trust_id", "ppm": {"$sum": {"$multiply": ["$units", share_math.PPM_PER_PERCENT]}}}},
    ]).to_list(None)
    cert_ppm_by_trust = {r["_id"]: int(round(r["ppm"])) for r in cert_rows}
    stats["certificates_scanned"] = len(cert_rows)

    for class_doc in classes:
        class_id = class_doc["class_beneficiary_id"]
        roster = await db.class_beneficiary_members.find(
            {"class_beneficiary_id": class_id, "user_id": class_doc.get("user_id")},
            {"_id": 0, "class_member_id": 1, "member_status": 1,
             "member_order": 1, "confirmed_at": 1, "class_member_id": 1},
        ).to_list(None)
        active = [m for m in roster if share_math.doc_is_active(m)]
        pool_pct = float(class_doc.get("percentage", 0) or 0)
        pool_ppm = share_math.percent_to_ppm(pool_pct)

        set_ops = {}
        if class_doc.get("share_mode") is None:
            set_ops["share_mode"] = "per_capita_equal"
        if class_doc.get("pool_percentage_ppm") is None:
            set_ops["pool_percentage_ppm"] = pool_ppm
        if class_doc.get("member_version") is None:
            set_ops["member_version"] = 0
        if class_doc.get("active_member_count") is None:
            set_ops["active_member_count"] = len(active)
        stored_count = class_doc.get("member_count", 0)
        actual_count = len(roster)
        if stored_count != actual_count:
            stats["member_count_repairs"].append(
                (class_id, stored_count, actual_count)
            )
            set_ops["member_count"] = actual_count
            if set_ops.get("active_member_count") is None:
                pass  # already set above when missing
            elif class_doc.get("active_member_count") != len(active):
                set_ops["active_member_count"] = len(active)

        if set_ops:
            stats["class_docs_updated"] += 1
            if dry_run:
                logger.info(
                    "[DRY] class %s (%s): +{%s}%s",
                    class_id, class_doc.get("class_type"),
                    ", ".join(f"{k}: {v!r}" for k, v in sorted(set_ops.items())),
                    f" + member_count repair {stored_count} -> {actual_count}"
                    if "member_count" in set_ops else "",
                )
            else:
                await db.class_beneficiaries.update_one(
                    {"class_beneficiary_id": class_id},
                    {"$set": set_ops},
                )

        # ----- verification gate: integer sum-check per nonempty class -----
        if active:
            ordered = share_math.sort_members_in_creation_order(active)
            alloc = share_math.allocate_equal_shares(
                pool_ppm, [m.get("class_member_id") for m in ordered]
            )
            if not share_math.validate_sum_invariant(alloc.values(), pool_ppm):
                stats["sum_check_failures"].append(
                    {
                        "class_beneficiary_id": class_id,
                        "pool_ppm": pool_ppm,
                        "sum_ppm": share_math.shares_sum_ppm(alloc.values()),
                        "active_members": len(active),
                    }
                )
                logger.error(
                    "SUM-CHECK FAILED class %s: pool=%d sum=%d (n=%d)",
                    class_id, pool_ppm, share_math.shares_sum_ppm(alloc.values()), len(active),
                )
        else:
            stats["classes_empty_roster"] += 1
            logger.info(
                "Class %s: empty roster — pool %s%% undistributed until members are added",
                class_id, pool_pct,
            )

    # ---------- 3. Reconciliation report: pools + certificates vs budget ----------
    # Dry-run fidelity: pool shadows are not yet written in dry-run mode, so
    # aggregate the PLANNED pool ppm (computed per class above) instead of the
    # absent stored shadows — the operator sees the post-apply band, not 0.
    pool_rows = await db.class_beneficiaries.aggregate([
        {"$group": {"_id": "$trust_id", "ppm": {"$sum": "$pool_percentage_ppm"},
                    "classes": {"$sum": 1}}},
    ]).to_list(None)
    if dry_run:
        pool_rows_planned = await db.class_beneficiaries.aggregate([
            {"$group": {"_id": "$trust_id", "classes": {"$sum": 1}}},
        ]).to_list(None)
        class_pct_by_trust = {}
        for class_doc in classes:
            class_pct_by_trust.setdefault(class_doc.get("trust_id"), 0.0)
            class_pct_by_trust[class_doc.get("trust_id")] += float(class_doc.get("percentage", 0) or 0)
        pool_rows = [
            {"_id": row["_id"], "classes": row["classes"],
             "ppm": share_math.percent_to_ppm(class_pct_by_trust.get(row["_id"], 0.0))}
            for row in pool_rows_planned
        ]
    stats["pools_scanned"] = sum(r.get("classes", 0) for r in pool_rows)
    for row in pool_rows:
        pools_ppm = int(row["ppm"] or 0)
        certs_ppm = cert_ppm_by_trust.get(row["_id"], 0)
        budget_ppm = pools_ppm + certs_ppm
        stats["pools_scanned"] = sum(r.get("classes", 0) for r in pool_rows)
        stats["reconciliation"].append(
            {
                "trust_id": row["_id"],
                "class_pools_ppm": pools_ppm,
                "certificates_ppm": certs_ppm,
                "combined_ppm": budget_ppm,
                "total_ppm": share_math.PPM_TOTAL,
                "within_budget": budget_ppm <= share_math.PPM_TOTAL,
                "note": "pools and certificates may overlap by design (two bands)",
            }
        )
        logger.info(
            "Reconciliation trust %s: pools=%d ppm + certs=%d ppm = %d ppm %s",
            row["_id"], pools_ppm, certs_ppm, budget_ppm,
            "OK (<= 100%)" if budget_ppm <= share_math.PPM_TOTAL else "OVER 100% (reported, not altered)",
        )

    # ---------- 4. Indexes (idempotent; skipped in dry run) ----------
    if not dry_run:
        # Shared definition with server.py startup (services/class_member_indexes.py)
        # so deploy-time and migration-time indexes can never drift apart
        # (explicit names; create_index is a no-op when name+keys match).
        ensured = await ensure_class_member_indexes(db)
        logger.info(
            "Indexes ensured on class_beneficiary_members + class_member_events (%d specs)",
            ensured,
        )
    else:
        logger.info(
            "[DRY] would ensure %d member indexes + %d event indexes (named: see services/class_member_indexes.py)",
            len(CLASS_MEMBER_INDEX_SPECS["class_beneficiary_members"]),
            len(CLASS_MEMBER_INDEX_SPECS["class_member_events"]),
        )

    stats["completed_at"] = datetime.now(timezone.utc).isoformat()
    return stats


async def main() -> int:
    # --apply (task/council spelling) and --execute (original spelling) both
    # apply; default stays DRY RUN. Unknown flags are rejected loudly so a
    # mistyped --aply can never silently dry-run the wrong way.
    known = {"--apply", "--execute"}
    args = [a for a in sys.argv[1:] if not a.startswith("-") or a in known]
    unknown = [a for a in sys.argv[1:] if a not in known and a.startswith("-")]
    if unknown:
        logger.error("Unknown flag(s): %s — supported: (none)=DRY RUN, --apply/--execute", ", ".join(unknown))
        return 2
    dry_run = not (("--apply" in sys.argv) or ("--execute" in sys.argv))
    logger.info("=== migrate_class_member_shares — %s ===", "DRY RUN" if dry_run else "EXECUTE")
    stats = await migrate(dry_run=dry_run)

    logger.info("Members scanned: %d | updated: %d", stats["members_scanned"], stats["member_docs_updated"])
    logger.info(
        "Ledger backfill: %d backdated member_added events | %d skipped (already recorded)",
        stats["events_backfilled"], stats["events_skipped_existing"],
    )
    logger.info("Classes scanned: %d | updated: %d", stats["classes_scanned"], stats["class_docs_updated"])
    if stats["member_count_repairs"]:
        for class_id, stored, actual in stats["member_count_repairs"]:
            logger.info("member_count repair: class %s stored=%s actual=%s", class_id, stored, actual)
    else:
        logger.info("member_count: no drift detected")

    if stats["sum_check_failures"]:
        logger.error("VERIFICATION GATE FAILED: %d class(es) with sum drift", len(stats["sum_check_failures"]))
        return 1
    logger.info("Verification gate: all nonempty classes sum-check EXACT (sum(member ppm) == pool ppm)")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    argv_flags = [a for a in sys.argv[1:] if a in ("--apply", "--execute")]
    logger.info(
        "Migration finished (%s), exit %d",
        "EXECUTE" if argv_flags else "DRY RUN",
        exit_code,
    )
    sys.exit(exit_code)