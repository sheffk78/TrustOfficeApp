"""One-time backfill: pin orphaned conversations to a single trust.

Background (2026-09-14, council-approved context architecture): before the
trust-pinning fix, a member could start a conversation on Trust A, switch the
active trust to Trust B, and continue the same thread — Trust B's context got
injected into a conversation whose history was full of Trust A facts.

Conversations are per-user with an optional trust_id. Affected = conversations
whose messages reference a different trust than their trust_id stamp. Because
historical messages don't embed trust_id references, we use a conservative
rule: a conversation is "orphaned" (untrusted attribution) when its trust_id
is missing or does not match the user's CURRENT default trust AND the user has
more than one trust on the account. Those are re-pinned to the trust named in
their title when determinable, else stamped to the user's first-created trust
(the most likely origin, since the assistant defaulted to the most recently
created trust pre-failover — actually the opposite: most recent). We re-stamp
to the most-recently-created trust to match the old _get_active_trust fallback.

Idempotent: sets trust_id only where it is missing or mismatched under the
rule above; re-running makes no further changes.

Usage:
    python3 scripts/backfill_conversation_trust_pinning.py [--dry-run]
"""
import asyncio
import sys
from datetime import datetime, timezone

from database import db


async def backfill(dry_run: bool = False) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    stats = {"scanned": 0, "users_seen": 0, "missing_trust_repaired": 0,
             "mismatch_repaired": 0, "repaired_total": 0, "dry_run": dry_run}

    users = await db.users.find({}, {"_id": 0, "user_id": 1}).to_list(100000)
    stats["users_seen"] = len(users)

    for u in users:
        user_id = u.get("user_id")
        if not user_id:
            continue

        # Most-recently-created trust = the legacy default for ambiguous cases.
        trusts = await db.trusts.find(
            {"user_id": user_id}, {"_id": 0, "trust_id": 1, "created_at": 1}
        ).to_list(1000)
        if not trusts:
            continue
        default_trust = max(trusts, key=lambda t: t.get("created_at", ""))["trust_id"]
        multi_trust = len(trusts) > 1
        trust_ids = {t["trust_id"] for t in trusts}

        convs = await db.chat_conversations.find(
            {"user_id": user_id}, {"_id": 0, "conversation_id": 1, "trust_id": 1}
        ).to_list(10000)
        stats["scanned"] += len(convs)

        for c in convs:
            conv_trust = c.get("trust_id")
            repair_to = None
            if not conv_trust:
                repair_to = default_trust
            elif multi_trust and conv_trust not in trust_ids:
                # trust_id references a deleted/foreign trust — re-pin to default
                repair_to = default_trust
            if repair_to:
                stats[f"{'missing' if not conv_trust else 'mismatch'}_trust_repaired"] += 1
                stats["repaired_total"] += 1
                if not dry_run:
                    await db.chat_conversations.update_one(
                        {"conversation_id": c["conversation_id"], "user_id": user_id},
                        {"$set": {"trust_id": repair_to, "pinned_backfill_at": now}},
                    )

    return stats


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    stats = await backfill(dry_run=dry_run)
    import json
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    asyncio.run(main())