#!/usr/bin/env python3
"""
Integration test: TrustOffice shared action layer, fully isolated.

- Local mongod on 127.0.0.1:27999 (db: trustoffice_actiontest)
- Real FastAPI app via TestClient (httpx) — no prod contact
- Seeds: 1 user (+subscription write plan) + 1 trust + 1 beneficiary cert
- Exercises the real HTTP surface: /api/actions/*

Run: .venv/bin/python tests/test_action_layer_integration.py
"""
import os
import sys
import uuid

os.environ["MONGO_URL"] = "mongodb://127.0.0.1:27999"
os.environ["DB_NAME"] = "trustoffice_actiontest"
os.environ["RATE_LIMIT_DISABLED"] = "1"
if not os.environ.get("JWT_SECRET"):
    os.environ["JWT_SECRET"] = "action-layer-test-secret-not-used-in-prod"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ["MAILERCLOUD_API_KEY"] = ""   # isolation: no external email API calls in tests
os.environ["DISCORD_WEBHOOK_URL"] = ""   # isolation: no external Discord posts
os.environ["TIDYCAL_API_TOKEN"] = ""
os.environ["POSTMARK_SERVER_TOKEN"] = ""   # isolation: no external email sends

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Fresh test DB
from pymongo import MongoClient

_SYNC_URL = "mongodb://127.0.0.1:27999"
TEST_DB = "trustoffice_actiontest"

def _sync():
    """Sync pymongo handle for test-side seeding/verification (app itself uses motor)."""
    return MongoClient(_SYNC_URL)[TEST_DB]

# pytest-safe: when collected by CI pytest (no mongod on 27999), skip the
# pre-clean silently instead of erroring collection — this script runs standalone.
try:
    MongoClient(_SYNC_URL, serverSelectionTimeoutMS=3000).drop_database(TEST_DB)
except Exception:
    pass

import secrets

TEST_USER_ID = f"user_{uuid.uuid4().hex[:10]}"
TEST_EMAIL = f"actiontest-{uuid.uuid4().hex[:8]}@example.com"
TEST_PASSWORD = "ActionTest#2026"
TEST_TRUST_ID = f"trust_{uuid.uuid4().hex[:10]}"


def seed():
    db = _sync()
    from dependencies import hash_password as get_password_hash

    now = "2026-09-21T00:00:00+00:00"
    db.users.insert_one({
        "user_id": TEST_USER_ID,
        "email": TEST_EMAIL,
        "name": "Action Layer Test",
        "password_hash": get_password_hash(TEST_PASSWORD),
        "is_admin": False,
        "created_at": now,
    })
    db.subscriptions.insert_one({
        "user_id": TEST_USER_ID,
        "plan_type": "trustee",
        "status": "active",
        "current_period_end": "2027-09-21T00:00:00+00:00",
        "is_legacy_price": False,
    })
    db.trusts.insert_one({
        "trust_id": TEST_TRUST_ID,
        "user_id": TEST_USER_ID,
        "name": "Action Layer Test Trust",
        "status": "active",
        "created_at": now,
    })
    db.trust_unit_certificates.insert_one({
        "certificate_id": f"cert_{uuid.uuid4().hex[:8]}",
        "trust_id": TEST_TRUST_ID,
        "user_id": TEST_USER_ID,
        "holder_name": "Jane Beneficiary",
        "status": "active",
    })


def main() -> int:
    seed()
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as client:
        # Login via the real endpoint
        r = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}

        passed, failed = [], []

        def check(name, cond, detail=""):
            (passed if cond else failed).append((name, detail))
            print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if not cond and detail else ""))

        # ---------- Manifest ----------
        r = client.get("/api/actions", headers=h)
        check("GET /api/actions → 200", r.status_code == 200, r.text[:200])
        names = {a["name"] for a in r.json().get("actions", [])}
        expected = {"generate-minutes", "evaluate-distribution", "book-consult", "submit-distribution", "chat-assistant"}
        check("manifest contains all 5 seed actions", expected <= names, f"got {sorted(names)}")

        # ---------- generate-minutes (happy path) ----------
        r = client.post("/api/actions/generate-minutes", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {
                "minutes_type": "annual",
                "meeting_date": "2026-09-21",
                "participants": ["Kit Tester"],
                "decisions": ["Approved test budget"],
            },
        })
        body = r.json()
        check("generate-minutes → ok", r.status_code == 200 and body.get("ok") is True, str(body)[:300])
        check("minutes record created in draft", body.get("result", {}).get("status") == "draft", str(body.get("result"))[:200])
        minutes_id = body.get("result", {}).get("record_id")

        # Verify the write landed in the real collection
        db = _sync()
        doc = None
        if minutes_id:
            doc = db.minutes_records.find_one({"minutes_id": minutes_id})
        check("minutes doc readable in db.minutes", doc is not None and doc.get("status") == "draft")

        # ---------- schema validation (422-shape via ok=false) ----------
        r = client.post("/api/actions/generate-minutes", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {"minutes_type": "annual", "meeting_date": "2026-09-21",
                        "participants": ["X"], "decisions": ["Y"], "evil_field": "inject"},
        })
        body = r.json()
        check("unknown param rejected", body.get("ok") is False and body.get("error", {}).get("code") == "action_params_invalid", str(body)[:200])

        r = client.post("/api/actions/generate-minutes", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {"meeting_date": "2026-09-21", "participants": ["X"], "decisions": ["Y"]},
        })
        body = r.json()
        check("missing required field rejected", body.get("ok") is False and "minutes_type" in str(body.get("error")), str(body)[:200])

        # ---------- trust-ownership enforcement ----------
        r = client.post("/api/actions/evaluate-distribution", headers=h, json={
            "trust_id": "trust_doesnotexist",
            "params": {"beneficiary_name": "Jane Beneficiary"},
        })
        body = r.json()
        check("foreign trust_id rejected (action_forbidden)", body.get("ok") is False and body.get("error", {}).get("code") == "action_forbidden", str(body)[:200])

        # ---------- evaluate-distribution ----------
        r = client.post("/api/actions/evaluate-distribution", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {"beneficiary_name": "jane beneficiary", "amount": 500},
        })
        body = r.json()
        res = body.get("result", {})
        check("evaluate-distribution → ok", body.get("ok") is True, str(body)[:300])
        check("case-insensitive beneficiary match", res.get("known_beneficiary") is True, str(res)[:200])
        check("lifetime total starts at 0", res.get("lifetime_total") == 0.0, str(res)[:120])

        # ---------- submit-distribution ----------
        r = client.post("/api/actions/submit-distribution", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {"beneficiary_name": "Jane Beneficiary", "amount": 500, "purpose": "other"},
        })
        body = r.json()
        res = body.get("result", {})
        check("submit-distribution → ok", body.get("ok") is True, str(body)[:300])
        check("created in review status", res.get("status") == "review" and res.get("requires_solvency_confirmation") is True, str(res)[:200])
        dist_id = res.get("record_id")

        dist_doc = db.distribution_records.find_one({"distribution_id": dist_id}) if dist_id else None
        check("distribution doc in db with review status", dist_doc is not None and dist_doc.get("status") == "review")

        # evaluate now reflects the new distribution
        r = client.post("/api/actions/evaluate-distribution", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {"beneficiary_name": "Jane Beneficiary"},
        })
        res2 = r.json().get("result", {})
        check("evaluate reflects lifetime total after write", res2.get("lifetime_total") == 500.0 and res2.get("distribution_count") == 1, str(res2)[:200])

        # ---------- book-consult ----------
        book_email = f"lead_{uuid.uuid4().hex[:8]}@example.com"
        r = client.post("/api/actions/book-consult", headers=h, json={
            "params": {"name": "Consult Tester", "email": book_email, "phone": "5551234567", "notes": "integration test"},
        })
        body = r.json()
        res3 = body.get("result", {})
        check("book-consult → ok", body.get("ok") is True, str(body)[:300])
        check("lead created with booked-call source", (db.leads.find_one({"lead_id": res3.get("lead_id")}) or {}).get("source") == "booked-call")

        # ---------- chat-assistant (LLM-free path: invalid message → clean error) ----------
        r = client.post("/api/actions/chat-assistant", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {"message": "Hello assistant"},
        })
        body = r.json()
        chat_resp = (body.get("result", {}).get("chat_response", {}) or {}).get("message", {})
        check("chat-assistant returned a structured assistant message", chat_resp.get("role") == "assistant" and isinstance(chat_resp.get("content"), str) and len(chat_resp["content"]) > 0, str(chat_resp)[:200])
        check("chat-assistant graceful AI-offline fallback", "trouble connecting" in chat_resp.get("content", "").lower() or "try again" in chat_resp.get("content", "").lower(), str(chat_resp)[:120])

        # ---------- write gate (read-only subscription) ----------
        _db = _sync()
        _db.subscriptions.update_one({"user_id": TEST_USER_ID}, {"$set": {"plan_type": "expired", "status": "expired"}})
        r = client.post("/api/actions/generate-minutes", headers=h, json={
            "trust_id": TEST_TRUST_ID,
            "params": {"minutes_type": "general", "meeting_date": "2026-09-21",
                        "participants": ["X"], "decisions": ["Y"]},
        })
        body = r.json()
        check("read-only plan blocked from write action (403)", r.status_code == 403 and "subscribe" in str(body.get("detail", "")).lower(), f"got {r.status_code} {str(body)[:150]}")
        _db.subscriptions.update_one({"user_id": TEST_USER_ID}, {"$set": {"plan_type": "trustee", "status": "active"}})

        # ---------- auth required ----------
        r = client.get("/api/actions")
        check("manifest requires auth (401)", r.status_code in (401, 403), f"got {r.status_code}")

        # ---------- unknown action ----------
        r = client.post("/api/actions/no-such-action", headers=h, json={})
        check("unknown action → 404", r.status_code == 404, f"got {r.status_code}")

        # ---------- audit trail ----------
        audits = list(db.audit_logs.find({"user_id": TEST_USER_ID, "action": "action_call"}))
        check("audit trail captured action calls", len(audits) >= 6, f"count={len(audits)}")

        # cleanup
        MongoClient(_SYNC_URL).drop_database(TEST_DB)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())