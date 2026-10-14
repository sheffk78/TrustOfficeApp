#!/usr/bin/env python3
"""Local QA fixture for TrustOffice UI work.

Provisions a QA user + active subscription in the local `to_qa` Mongo database
by calling the REAL production provisioning function
(_provision_guest_account — the Stripe checkout.session.completed path),
then sets a known login password and mints a fresh access token via the real
login endpoint (start backend first).

Run with the backend venv interpreter:
  backend/.venv/bin/python scripts/local_qa_seed.py

Requires: local mongod on :27017. Backend must run with:
  MONGO_URL=mongodb://localhost:27017 DB_NAME=to_qa JWT_SECRET=qa-local-secret
  CORS_ORIGINS=http://localhost:3000
"""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, "/Users/socializerender/Projects/TrustOfficeApp/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "to_qa")
os.environ.setdefault("JWT_SECRET", "qa-local-secret")

EMAIL = "kit.qa@trustoffice-qa.dev"
PASSWORD = "KitQa-2026-visual-pass"


async def main():
    import server  # noqa: F401  (sets up db handle from env)
    from routers.subscriptions import _provision_guest_account
    from dependencies import hash_password

    session = SimpleNamespace(
        id="cs_test_kit_qa_001",
        customer="cus_test_kit_qa",
        customer_details=SimpleNamespace(email=EMAIL, address=None),
        amount_total=18900,
        metadata={
            "guest_checkout": "1",
            "guest_email": EMAIL,
            "guest_name": "Kit QA",
        },
    )
    user_id = await _provision_guest_account(session, session.metadata, "estate", "monthly")
    if not user_id:
        print("PROVISION FAILED")
        return 1

    await server.db.users.update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": hash_password(PASSWORD)}},
    )

    user = await server.db.users.find_one({"user_id": user_id}, {"_id": 0})
    sub = await server.db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    print(f"USER_ID={user_id}")
    print(f"EMAIL={EMAIL}")
    print(f"PLAN={sub and sub.get('plan_type')} STATUS={sub and sub.get('status')}")
    print(f"PASSWORD_SET={bool(user.get('password_hash'))}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))