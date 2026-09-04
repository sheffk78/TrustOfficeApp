"""
Recalculate health snapshots for all trusts using the REAL scoring engine
(routers.governance.calculate_health_score) so stored snapshots match what
users see. Run from the backend/ dir with prod MONGO_URL/DB_NAME exported.
"""

import asyncio
import os
import sys

sys.path.insert(0, ".")

from database import db  # noqa: E402  (uses MONGO_URL env — point at public proxy)


async def main():
    from routers.governance import calculate_health_score

    trusts = await db.trusts.find({}, {"_id": 0, "trust_id": 1, "user_id": 1, "name": 1}).to_list(500)
    print(f"Recalculating {len(trusts)} trust snapshots...")
    results = []
    for t in trusts:
        try:
            r = await calculate_health_score(t["trust_id"], t["user_id"], save_snapshot=True)
            results.append((t.get("name"), r["total_score"], r["max_score"], r["color"], r["base_score"], r["risk_penalty"]))
            print(f"  {t.get('name', '?')[:40]:42} score={r['total_score']:>3}/{r['max_score']} base={r['base_score']:>3} penalty={r['risk_penalty']:>3} {r['color']}")
        except Exception as e:
            print(f"  {t.get('name', '?')[:40]:42} FAILED: {type(e).__name__}: {e}")

    scores = [r[1] for r in results]
    print(f"\nDone: {len(results)} ok. avg={sum(scores)/len(scores):.1f} min={min(scores)} max={max(scores)}")


if __name__ == "__main__":
    asyncio.run(main())