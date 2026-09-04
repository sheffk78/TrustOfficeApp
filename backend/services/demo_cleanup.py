# Shared demo-data purge service.
#
# Single source of truth for removing demo (is_demo: True) data from a user's
# account. Used by:
#   - routers/demo.py        DELETE /demo/data (Settings → "Remove demo data")
#   - routers/trusts.py      auto-cleanup on first real trust creation
#   - routers/external.py    WingPoint/external provisioning (trust insert paths)
#   - routers/admin_api.py   admin trust creation + POST /admin/users/{id}/purge-demo-data
#
# Semantics: only records with is_demo: True (or records orphaned to demo
# trust_ids) are removed. User-created data referencing real trusts is
# always preserved.

import logging
from database import db

logger = logging.getLogger(__name__)

# Collections seeded by the demo seeder (records carry is_demo: True).
_DEMO_SEEDED_COLLECTIONS = [
    "chat_conversations",
    "trust_document_analysis",
    "vault_documents",
    "class_beneficiaries",
    "trust_unit_certificates",
    "trust_unit_transfers",
    "trust_units_settings",
    "compensation_payments",
    "compensation_plans",
    "benevolence_records",
    "distribution_records",
    "schedule_a_items",
    "minutes_records",
    "governance_tasks",
    "entity_relationships",
    "entities",
    "transactions",
    "tax_calendar",
    "health_score_snapshots",
    "trusts",
]

# trust_id-keyed collections auto-created by the app when a trust exists
# (records lack is_demo: True — identified by demo trust_ids instead).
_TRUST_ID_ORPHAN_COLLECTIONS = [
    "deadlines",
    "separation_alerts",
    "trust_state_compliance",
    "benevolence_policies",
    "benevolence_policy_versions",
    "notifications",
    "dismissed_insights",
    "risk_findings_cache",
    "state_compliance_profiles",  # global table — no-op, kept for documentation
]

# user_id-keyed collections that may contain demo-era records.
_USER_ID_ORPHAN_COLLECTIONS = [
    "bank_accounts",
    "expenses",
    "investments",
    "meeting_agendas",
    "minutes_templates",
    "personal_vendors",
    "external_provisions",
    "trust_admin_kits",
]


async def collect_demo_trust_ids(user_id: str) -> list[str]:
    """Return the trust_ids of all demo trusts owned by the user."""
    return [
        t["trust_id"]
        async for t in db.trusts.find(
            {"user_id": user_id, "is_demo": True},
            {"_id": 0, "trust_id": 1},
        )
    ]


async def purge_demo_data_for_user(user_id: str) -> dict:
    """Delete all demo data for a user. Returns {collection: deleted_count}.

    Removes:
      1. All is_demo: True records across the 20 seeded collections.
      2. Orphaned trust_id-keyed records pointing at demo trust_ids.
      3. Demo-era records in user_id-keyed collections (is_demo: True OR
         trust_id referencing a demo trust).

    user_onboarding is deliberately NOT touched: it is the user's global
    checklist state, not per-trust demo data.
    """
    deleted_counts: dict[str, int] = {}

    demo_trust_ids = await collect_demo_trust_ids(user_id)

    # 1. Demo-seeded collections (is_demo: True only)
    for collection_name in _DEMO_SEEDED_COLLECTIONS:
        result = await db[collection_name].delete_many(
            {"user_id": user_id, "is_demo": True}
        )
        if result.deleted_count > 0:
            deleted_counts[collection_name] = result.deleted_count

    # 2. Orphaned records keyed by demo trust_id
    if demo_trust_ids:
        for collection_name in _TRUST_ID_ORPHAN_COLLECTIONS:
            result = await db[collection_name].delete_many(
                {"trust_id": {"$in": demo_trust_ids}}
            )
            if result.deleted_count > 0:
                deleted_counts[collection_name] = result.deleted_count

        # 3. Demo-era records in user_id-keyed collections
        for collection_name in _USER_ID_ORPHAN_COLLECTIONS:
            result = await db[collection_name].delete_many(
                {
                    "user_id": user_id,
                    "$or": [
                        {"is_demo": True},
                        {"trust_id": {"$in": demo_trust_ids}},
                    ],
                }
            )
            if result.deleted_count > 0:
                deleted_counts[collection_name] = result.deleted_count

    total_deleted = sum(deleted_counts.values())
    if total_deleted > 0:
        logger.info(
            f"Demo purge for user {user_id}: removed {total_deleted} records "
            f"across {len(deleted_counts)} collections "
            f"({len(demo_trust_ids)} demo trusts)"
        )

    return deleted_counts


async def cleanup_demo_on_first_real_trust(user_id: str, new_trust_id: str) -> dict:
    """Purge demo data if this user just created their first REAL trust.

    Called after a real (non-demo) trust is inserted anywhere in the app.
    No-op if the user already had other real trusts.
    """
    existing_real = await db.trusts.count_documents({
        "user_id": user_id,
        "is_demo": {"$ne": True},
        "trust_id": {"$ne": new_trust_id},
    })
    if existing_real > 0:
        return {}

    return await purge_demo_data_for_user(user_id)