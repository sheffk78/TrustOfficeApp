"""
Migration-script tests for backend/scripts/migrate_class_member_shares.py

mongomock-motor (in-process, no live Mongo) — mirrors test_trust_cap_checkout.py
style: patch AsyncIOMotorClient BEFORE importing database, then drive the real
migrate() function against seeded collections.

Covers (council migration spec):
  1. backfill: legacy member docs gain member_status='active'/share_weight=1/
     member_order (rank by confirmed_at then class_member_id)/name_history —
     additively (existing values never overwritten)
  2. class backfill: share_mode='per_capita_equal', pool_percentage_ppm
     shadow (pool pct*10000), member_version=0
  3. member_count drift repair + mismatch report entry
  4. verification gate: sum-check exact per nonempty class
  5. idempotency: second execute run performs zero further writes
  6. dry-run writes NOTHING (counts unchanged)
  7. indexes created on execute
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# Real local mongod, dedicated throwaway DB (never prod — MONGO_URL default is
# localhost). NOTE: deliberately NOT mongomock. Sibling suites capture the
# REAL motor client class at import time and mongomock-patching at module
# import here contaminates their fixture (established failure, see
# test_class_member_mutations.py's mock-capture guard).
os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["DB_NAME"] = "trustoffice_test_migrate_shares"
os.environ.setdefault("JWT_SECRET", "test-jwt-migrate-shares")

import pytest
import pytest_asyncio

# Standalone-only, sibling-gated like test_class_member_mutations.py /
# test_class_member_dashboard.py. Motor binds database.db's client to the
# FIRST loop that awaits anywhere in the pytest process; in a combined run a
# LATER suite (e.g. test_trust_cap_checkout.py's TestClient portals) then hits
# closed-loop futures (established 2026-10-07). Run:
#   TR_MIGRATE_SHARES_SUITE=1 .venv/bin/python -m pytest tests/test_migrate_class_member_shares.py

# motor futures bind to the loop running at first use; with pytest-asyncio's
# default function-scoped loop the SECOND test's loop gets futures created on
# the first test's loop → "attached to a different loop" teardown errors.
# One loop for the whole module keeps the real-motor client coherent.
pytestmark = [
    pytest.mark.skipif(
        os.environ.get("TR_MIGRATE_SHARES_SUITE", "") != "1",
        reason="real-mongo suite sharing database.db — run standalone with TR_MIGRATE_SHARES_SUITE=1",
    ),
    pytest.mark.asyncio(loop_scope="module"),
]


import database
import share_math
import scripts.migrate_class_member_shares as mig

db = database.db


_FROZEN = None  # set once by the fixture so asserts see the same timestamps


def _now(i=0):
    from datetime import datetime, timedelta, timezone
    base = _FROZEN or datetime.now(timezone.utc)
    return (base + timedelta(seconds=i)).isoformat()


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def seeded():
    global _FROZEN
    from datetime import datetime, timezone
    _FROZEN = datetime.now(timezone.utc)
    for coll in ("class_beneficiaries", "class_beneficiary_members",
                 "class_member_events", "trust_unit_certificates"):
        await db[coll].delete_many({})
    # Legacy-style class (no share_mode/pool_percentage_ppm/member_version)
    await db.class_beneficiaries.insert_one({
        "class_beneficiary_id": "cb_mig1", "trust_id": "trust_mig",
        "user_id": "u_mig", "class_type": "children",
        "class_type_label": "Children (including after-born)",
        "description": "", "percentage": 100.0, "notes": "",
        "distribution_convention": "per_capita", "member_count": 5,  # drifted: actual 3
        "created_at": _now(),
    })
    # Legacy members: bare docs, missing member_status/share_weight/member_order.
    # confirmed_at order: cm_c < cm_a < cm_b  => ranks 0,1,2
    for cm_id, confirmed in (("cm_c", _now(0)), ("cm_a", _now(10)), ("cm_b", _now(20))):
        await db.class_beneficiary_members.insert_one({
            "class_member_id": cm_id, "class_beneficiary_id": "cb_mig1",
            "trust_id": "trust_mig", "user_id": "u_mig",
            "name": f"Member {cm_id}", "confirmed_by_user_id": "u_mig",
            "confirmed_at": confirmed, "created_at": confirmed,
        })
    # A second class, already migrated + a drifted count too
    await db.class_beneficiaries.insert_one({
        "class_beneficiary_id": "cb_mig2", "trust_id": "trust_mig",
        "user_id": "u_mig", "class_type": "descendants",
        "class_type_label": "Descendants", "description": "",
        "percentage": 0.0, "notes": "",
        "distribution_convention": "per_capita",
        "share_mode": "per_capita_equal", "pool_percentage_ppm": 0,
        "member_version": 3, "member_count": 7,  # drifted: actual 1 (deceased)
        "created_at": _now(),
    })
    await db.class_beneficiary_members.insert_one({
        "class_member_id": "cm_old", "class_beneficiary_id": "cb_mig2",
        "trust_id": "trust_mig", "user_id": "u_mig",
        "name": "Elder", "confirmed_by_user_id": "u_mig",
        "confirmed_at": _now(5), "created_at": _now(5),
        "member_status": "deceased", "share_weight": 1, "member_order": 2,
        "name_history": [],
    })
    # Active certificate on the same trust → reconciliation band
    await db.trust_unit_certificates.insert_one({
        "certificate_id": "cert_mig1", "trust_id": "trust_mig",
        "user_id": "u_mig", "units": 25.0, "status": "active",
    })
    # Other user's certificate — must NOT leak into trust_mig's band? (band is
    # per-trust; units from a different user's same-trust cert still aggregate —
    # trust_id keys the band, matching the dashboard's query pattern.)
    return {"user_id": "u_mig", "trust_id": "trust_mig"}


# ==================== DRY RUN ====================

@pytest.mark.asyncio(loop_scope="module")
async def test_dry_run_writes_nothing(seeded):
    stats = await mig.migrate(dry_run=True)
    assert stats["mode"] == "DRY RUN"
    assert stats["members_scanned"] == 4
    assert stats["member_docs_updated"] == 4  # 3 bare docs + cm_old (event back-pointer only)
    assert stats["classes_scanned"] == 2
    assert stats["class_docs_updated"] == 2   # both classes need fields
    # nothing actually written
    fresh = await db.class_beneficiary_members.find_one({"class_member_id": "cm_a"})
    assert "member_status" not in fresh
    assert "member_order" not in fresh
    fresh_class = await db.class_beneficiaries.find_one({"class_beneficiary_id": "cb_mig1"})
    assert "pool_percentage_ppm" not in fresh_class
    # drift detected but report-only
    assert any(r[0] == "cb_mig1" and r[1] == 5 and r[2] == 3
               for r in stats["member_count_repairs"])
    assert not stats["sum_check_failures"]
    # backdated ledger events: PLANNED in stats but never written (session-2)
    assert stats["events_backfilled"] == 4   # cm_a, cm_b, cm_c, cm_old
    assert stats["events_skipped_existing"] == 0
    assert await db.class_member_events.count_documents({}) == 0


# ==================== EXECUTE ====================

@pytest.mark.asyncio(loop_scope="module")
async def test_execute_backfills_and_repairs(seeded):
    stats = await mig.migrate(dry_run=False)
    assert stats["mode"] == "EXECUTE"
    assert stats["member_docs_updated"] == 4  # 3 bare docs + cm_old pointer-only
    assert stats["class_docs_updated"] == 2

    cm = await db.class_beneficiary_members.find(
        {"class_beneficiary_id": "cb_mig1", "user_id": "u_mig"},
    ).to_list(None)
    fields = {m["class_member_id"]: m for m in cm}
    # rank by confirmed_at: cm_c(0) < cm_a(1) < cm_b(2)
    assert fields["cm_c"]["member_order"] == 0
    assert fields["cm_a"]["member_order"] == 1
    assert fields["cm_b"]["member_order"] == 2
    for mid in ("cm_a", "cm_b", "cm_c"):
        assert fields[mid]["member_status"] == "active"
        assert fields[mid]["share_weight"] == 1
        assert fields[mid]["name_history"] == []
        assert fields[mid]["status_reason"] is None

    cls1 = await db.class_beneficiaries.find_one({"class_beneficiary_id": "cb_mig1"})
    assert cls1["share_mode"] == "per_capita_equal"
    assert cls1["pool_percentage_ppm"] == 1_000_000
    assert cls1["member_version"] == 0
    assert cls1["member_count"] == 3          # repaired 5 -> 3
    assert cls1["active_member_count"] == 3

    cls2 = await db.class_beneficiaries.find_one({"class_beneficiary_id": "cb_mig2"})
    assert cls2["member_count"] == 1          # repaired 7 -> 1
    assert cls2["active_member_count"] == 0   # sole member is deceased
    assert cls2["share_mode"] == "per_capita_equal"
    assert cls2["member_version"] == 3        # untouched (pre-existing value)

    # drift reports cover both classes
    repaired = {r[0]: (r[1], r[2]) for r in stats["member_count_repairs"]}
    assert repaired["cb_mig1"] == (5, 3)
    assert repaired["cb_mig2"] == (7, 1)

    # verification gate passed, reconciliation band present
    assert stats["sum_check_failures"] == []
    recon = {r["trust_id"]: r for r in stats["reconciliation"]}
    band = recon["trust_mig"]
    assert band["class_pools_ppm"] == 1_000_000
    assert band["certificates_ppm"] == 250_000
    assert band["combined_ppm"] == 1_250_000
    assert band["within_budget"] is False  # pools overlap certs by design — REPORTED

    # ===== session-2: backdated ledger events (council migration step 2) =====
    assert stats["events_backfilled"] == 4   # cm_a, cm_b, cm_c, cm_old
    assert stats["events_skipped_existing"] == 0
    events = await db.class_member_events.find(
        {"event_type": "member_added"}, {"_id": 0}
    ).to_list(None)
    assert len(events) == 4
    ev_by_member = {e["class_member_id"]: e for e in events}
    # backdated to confirmed_at, honestly labeled, full provenance
    assert ev_by_member["cm_c"]["created_at"] == _now(0)
    assert ev_by_member["cm_b"]["created_at"] == _now(20)
    for mid in ("cm_a", "cm_b", "cm_c", "cm_old"):
        ev = ev_by_member[mid]
        assert ev["backdated"] is True
        assert ev["recorded_at"] == stats["started_at"]
        assert ev["before"] is None
        assert ev["after"]["backfill"] is True
        assert ev["after"]["name"] == (f"Member {mid}" if mid != "cm_old" else "Elder")
        assert ev["trust_id"] == "trust_mig" and ev["user_id"] == "u_mig"
        assert "predates the ledger" in ev["reason"]
    # deceased member's backdated event records its true (non-active) status
    assert ev_by_member["cm_old"]["after"]["member_status"] == "deceased"
    # member docs carry the back-pointer to their event
    doc = await db.class_beneficiary_members.find_one({"class_member_id": "cm_a"})
    assert doc["member_added_event_id"] == ev_by_member["cm_a"]["event_id"]


@pytest.mark.asyncio(loop_scope="module")
async def test_execute_creates_indexes(seeded):
    await mig.migrate(dry_run=False)
    member_indexes = await db.class_beneficiary_members.index_information()
    event_indexes = await db.class_member_events.index_information()

    def _has_key(indexes, *fields):
        return any(
            all(f in [k for k, _ in v.get("key", [])] for f in fields)
            for v in indexes.values()
        )

    assert _has_key(member_indexes, "class_beneficiary_id", "user_id", "member_status")
    # Canonical named registry (services/class_member_indexes.py, shared with
    # server.py startup) — event_id unique index carries the registry name.
    assert event_indexes["cme_event_id_unique"]["unique"] is True
    assert _has_key(event_indexes, "event_id")
    assert _has_key(event_indexes, "user_id", "class_beneficiary_id", "created_at")
    assert _has_key(event_indexes, "user_id", "class_member_id")


# ==================== IDEMPOTENCE ====================

@pytest.mark.asyncio(loop_scope="module")
async def test_rerun_is_noop(seeded):
    await mig.migrate(dry_run=False)
    member_docs = await db.class_beneficiary_members.count_documents({})
    class_docs = await db.class_beneficiaries.count_documents({})
    event_docs = await db.class_member_events.count_documents({})
    stats2 = await mig.migrate(dry_run=False)
    assert stats2["member_docs_updated"] == 0
    assert stats2["class_docs_updated"] == 0
    assert stats2["member_count_repairs"] == []
    # ledger backfill is idempotent too: no duplicate member_added events.
    # Every member is covered by the ledger sweep on every run, so a rerun
    # skips all 4 (each already has its member_added event).
    assert stats2["events_backfilled"] == 0
    assert stats2["events_skipped_existing"] == 4
    assert await db.class_member_events.count_documents({}) == event_docs
    assert await db.class_beneficiary_members.count_documents({}) == member_docs
    assert await db.class_beneficiaries.count_documents({}) == class_docs


# ==================== EXISTING VALUES NEVER OVERWRITTEN ====================

@pytest.mark.asyncio(loop_scope="module")
async def test_existing_fields_are_preserved(seeded):
    # a partially-migrated member keeps its already-set order/status
    await db.class_beneficiary_members.insert_one({
        "class_member_id": "cm_partial", "class_beneficiary_id": "cb_mig1",
        "trust_id": "trust_mig", "user_id": "u_mig",
        "name": "Partial", "confirmed_by_user_id": "u_mig",
        "confirmed_at": _now(1), "created_at": _now(1),
        "member_status": "inactive", "share_weight": 2, "member_order": 9,
    })
    await mig.migrate(dry_run=False)
    doc = await db.class_beneficiary_members.find_one({"class_member_id": "cm_partial"})
    assert doc["member_status"] == "inactive"  # NOT forced back to active
    assert doc["share_weight"] == 2
    assert doc["member_order"] == 9            # NOT re-ranked over existing orders
    assert doc["name_history"] == []           # missing field still backfilled