"""Seed a demo user + trust for LOCAL live-server tests (trustoffice_local_live DB).

Never pointed at production: the DB name is fixed and the caller must run
this against a local mongod. Creates demo@trustoffice.com / demopassword with
the exact doc shape the login path needs, and two class beneficiaries the
P2 dashboard + members suites exercise.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ["DB_NAME"] = os.environ.get("SEED_DB_NAME", "trustoffice_local_live")
os.environ.setdefault("JWT_SECRET", "local-test-only")

import bcrypt  # noqa: E402
import motor.motor_asyncio  # noqa: E402
import mongomock_motor  # noqa: E402  (NOT used here — real mongod wanted)

# do NOT patch motor: this seeder wants the REAL local mongod
from pymongo import MongoClient  # noqa: E402


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


async def seed():
    import database
    db = database.db
    user_id = "user_demo_local"
    await db.users.delete_many({"email": "demo@trustoffice.com"})
    await db.users.insert_one({
        "user_id": user_id,
        "email": "demo@trustoffice.com",
        "name": "Demo User",
        "password_hash": _hash("demopassword"),
        "is_admin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # subscription row so require_write_access passes (subscription is active)
    await db.subscriptions.replace_one(
        {"user_id": user_id},
        {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user_id, "plan_type": "estate", "status": "active",
            "trial_start_date": None, "trial_end_date": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        upsert=True,
    )
    await db.trusts.delete_many({"user_id": user_id})
    await db.trusts.insert_one({
        "trust_id": "trust_b753cb8fe07f",
        "user_id": user_id,
        "name": "Demo Family Trust",
        "trust_type": "revocable",
        "jurisdiction": "UT",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_demo": True,
    })
    await db.class_beneficiaries.delete_many({"user_id": user_id})
    await db.class_beneficiaries.insert_many([
        {
            "class_beneficiary_id": "cb_demo_children",
            "trust_id": "trust_b753cb8fe07f", "user_id": user_id,
            "class_type": "children", "class_type_label": "Children (including after-born)",
            "description": "Demo children class", "percentage": 100.0,
            "notes": "", "distribution_convention": "per_capita",
            "member_count": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_demo": True,
        },
    ])
    await db.class_beneficiary_members.delete_many({"user_id": user_id})
    now = datetime.now(timezone.utc)
    for i in range(3):
        t = now.timestamp() - (3 - i) * 60
        await db.class_beneficiary_members.insert_one({
            "class_member_id": f"cm_demo{i:02d}",
            "class_beneficiary_id": "cb_demo_children",
            "trust_id": "trust_b753cb8fe07f", "user_id": user_id,
            "name": f"Demo Child {i+1}",
            "confirmed_by_user_id": user_id,
            "confirmed_at": datetime.fromtimestamp(t, timezone.utc).isoformat(),
            "created_at": datetime.fromtimestamp(t, timezone.utc).isoformat(),
        })
    await db.trust_unit_certificates.delete_many({"user_id": user_id})
    for i in range(4):
        await db.trust_unit_certificates.insert_one({
            "certificate_id": f"cert_demo_{i}",
            "trust_id": "trust_b753cb8fe07f", "user_id": user_id,
            "certificate_number": f"CERT-{i+1:03d}",
            "holder_name": f"Holder {i+1}",
            "holder_identifier": None, "holder_type": "individual",
            "units": 25.0,
            "issue_date": datetime.now(timezone.utc).isoformat(),
            "status": "active", "notes": "", "email": None, "phone": None,
            "supersedes_certificate_id": None,
            "replaced_by_certificate_id": None,
            "version": 1,
            "replacement_reason": None,
            "effective_date": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
        })
    print("seeded demo user + trust in", os.environ["DB_NAME"])


if __name__ == "__main__":
    asyncio.run(seed())