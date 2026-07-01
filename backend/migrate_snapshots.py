"""
One-time backfill script for health score snapshots.
Adds schema_version=1, base_score, risk_penalty, risk_findings_count to old snapshots.

Usage:
    python -m backend.migrate_snapshots

Or from within the backend directory:
    python migrate_snapshots.py
"""
import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


async def backfill_snapshots():
    """Add v2 schema fields to existing snapshots that lack schema_version."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    cursor = db.health_score_snapshots.find({"schema_version": {"$exists": False}})
    count = 0

    async for doc in cursor:
        score_value = doc.get("score_value", 0)
        await db.health_score_snapshots.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "schema_version": 1,
                "base_score": score_value,  # pre-penalty, score_value IS base_score
                "risk_penalty": 0,
                "risk_findings_count": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            }}
        )
        count += 1

    logger.info(f"Backfilled {count} snapshots with schema_version=1")
    client.close()
    return count


if __name__ == "__main__":
    result = asyncio.run(backfill_snapshots())
    print(f"Done. Backfilled {result} snapshots.")