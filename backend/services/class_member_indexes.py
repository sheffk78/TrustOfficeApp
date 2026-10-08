# Class-member collection indexes — single shared definition (session 1)
"""Idempotent index definitions for class_beneficiary_members and
class_member_events (named class members, 2026-10-07 council design).

One definition, two call sites:
  - backend/server.py startup_event()  (every deploy)
  - scripts/migrate_class_member_shares.py  (existing-data migration)

Idempotent: MongoDB create_index with the same explicit name + same key
spec is a no-op, so startup and migration can both run in any order.
Explicit names (not Mongo auto-names) keep the definitions stable across
refactors and make the deploy log greppable. These indexes have never
reached a persisted database (no deploy has carried them), so naming them
now costs nothing downstream.

Council defect this fixes: class_beneficiary_members previously had ZERO
indexes — every roster and dashboard read was a multi-tenant collection
scan. Every query pattern filters the authenticated user_id first, so
user_id leads every compound key.

Event ledger (append-only) reads are owner-scoped class feeds + per-member
audit walks; the three keys below cover both access paths.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

# Index registry: (name, keys, kwargs) — kept as data so the migrate script
# can print/verify the exact index list it created.
CLASS_MEMBER_INDEX_SPECS = {
    "class_beneficiary_members": [
        {
            "name": "cbm_class_user_status",
            "keys": [("class_beneficiary_id", 1), ("user_id", 1), ("member_status", 1)],
            "kwargs": {},
        },
        {
            "name": "cbm_user_trust",
            "keys": [("user_id", 1), ("trust_id", 1)],
            "kwargs": {},
        },
        {
            "name": "cbm_member_id_unique",
            "keys": [("class_member_id", 1)],
            "kwargs": {"unique": True},
        },
        {
            "name": "cbm_class_order",
            "keys": [("class_beneficiary_id", 1), ("member_order", 1)],
            "kwargs": {},
        },
    ],
    "class_member_events": [
        {
            "name": "cme_event_id_unique",
            "keys": [("event_id", 1)],
            "kwargs": {"unique": True},
        },
        {
            "name": "cme_user_class_created",
            "keys": [("user_id", 1), ("class_beneficiary_id", 1), ("created_at", -1)],
            "kwargs": {},
        },
        {
            "name": "cme_user_member",
            "keys": [("user_id", 1), ("class_member_id", 1)],
            "kwargs": {},
        },
    ],
}


async def ensure_class_member_indexes(db: AsyncIOMotorDatabase) -> int:
    """Create all class-member indexes idempotently. Returns count ensured.

    Safe to call on every startup and after every migration. Self-healing
    against the two ways this registry can collide with a pre-existing DB
    (reproduceable in throwaway test DBs; would otherwise be a one-time
    deploy blocker):

      1. Same keys under a DIFFERENT (legacy/auto-generated) name — e.g. a
         database created before names were standardized, carrying Mongo
         auto-names like ``class_beneficiary_id_1_user_id_1_member_status_1``.
         MongoDB refuses to create our name over the same keys (code 85
         IndexOptionsConflict), so the legacy index is dropped and
         re-created under the canonical name. Same keys, same instant —
         atomic enough for these small collections; nothing else changed.
      2. Race with a concurrent creator — the same code-85 fallback on the
         create call itself (drop name, retry once).

    A create that fails for any OTHER reason (e.g. 11000 duplicate key when
    introducing a unique index over dirty data) propagates loudly — data
    problems must block, never be papered over.
    """
    from pymongo.errors import OperationFailure

    ensured = 0
    for collection, specs in CLASS_MEMBER_INDEX_SPECS.items():
        coll = db[collection]
        existing = await coll.index_information()
        # Key-signature → legacy index name (ignoring the implicit _id_ index).
        existing_by_key = {}
        for iname, info in existing.items():
            if iname == "_id_":
                continue
            key_sig = tuple((f, d) for f, d in info.get("key", []))
            existing_by_key.setdefault(key_sig, iname)
        for spec in specs:
            want_key = tuple((f, d) for f, d in spec["keys"])
            if spec["name"] in existing:
                info = existing[spec["name"]]
                have_key = tuple((f, d) for f, d in info.get("key", []))
                if have_key == want_key and bool(info.get("unique", False)) == bool(
                    spec["kwargs"].get("unique", False)
                ):
                    ensured += 1  # exact match — already in place
                    continue
                await coll.drop_index(spec["name"])  # name squat: recreate to spec
            elif want_key in existing_by_key and existing_by_key[want_key] != spec["name"]:
                # Legacy auto-named index over identical keys: adopt by
                # renaming (drop + recreate under the canonical name).
                await coll.drop_index(existing_by_key[want_key])
            try:
                result = await coll.create_index(
                    spec["keys"], name=spec["name"], **spec["kwargs"]
                )
                if result == spec["name"]:
                    ensured += 1
            except OperationFailure as exc:
                if getattr(exc, "code", None) == 85:
                    await coll.drop_index(spec["name"])
                    await coll.create_index(
                        spec["keys"], name=spec["name"], **spec["kwargs"]
                    )
                    ensured += 1
                else:
                    raise
    return ensured