"""Recalculate all health snapshots with the v3 applicable-criteria engine."""
import asyncio, sys
sys.path.insert(0, ".")
from database import db


async def main():
    from routers.governance import calculate_health_score
    trusts = await db.trusts.find({}, {"_id": 0, "trust_id": 1, "user_id": 1, "name": 1}).to_list(500)
    print(f"Recalculating {len(trusts)} snapshots with v3 scoring...")
    justin = None
    for t in trusts:
        try:
            r = await calculate_health_score(t["trust_id"], t["user_id"], save_snapshot=True)
            if t["trust_id"] == "trust_84fee966981d":
                justin = r
            print(f"  {t.get('name','?')[:40]:42} {r['total_score']:>3}/100 {r['color']:8} base={r['base_score']:>3} appl_max={r.get('applicable_max')} penalty={r['risk_penalty']:>4}")
        except Exception as e:
            print(f"  {t.get('name','?')[:40]:42} FAILED {type(e).__name__}: {str(e)[:80]}")
    if justin:
        print("\nJUSTIN (Life and Legacy Fund):")
        print(f"  score={justin['total_score']}/100 color={justin['color']} base={justin['base_score']} applicable_max={justin['applicable_max']} penalty={justin['risk_penalty']}")
        for c in justin["criteria"]:
            state = 'no_data' if c.get('no_data') else ('OK' if c['achieved'] else 'MISSING')
            print(f"    {c['name']:32} {c['points']:>3}/{c['max_points']:<3} {state}")


if __name__ == "__main__":
    asyncio.run(main())