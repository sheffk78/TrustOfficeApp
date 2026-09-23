#!/usr/bin/env python3
"""
Chat action-unification test (2026-09-22) — fully isolated.

Proves the new unified execution path end-to-end WITHOUT prod contact:
- local mongod 127.0.0.1:27999 (db trustoffice_chat_unify)
- real FastAPI app via TestClient; no LLM (cards are hand-planted)

Covers:
  1. /api/actions manifest still exposes ONLY the 5 seed actions
     (20 chat-intent actions are surfaces=("chat",) → hidden from HTTP)
  2. Full chat approve pipeline → action_layer.call_action → DB read-back
     (beneficiary + governance-task intents)
  3. minutes intent keeps the legacy dedicated handler (draft status)
  4. List-valued card fields coerce (["A","B"] → "A, B")
  5. Error mapping: missing required field → success=False + readable error
Run: .venv/bin/python tests/test_chat_action_unify.py
"""
import os
import sys
import uuid

os.environ["MONGO_URL"] = "mongodb://127.0.0.1:27999"
os.environ["DB_NAME"] = "trustoffice_chat_unify"
os.environ["RATE_LIMIT_DISABLED"] = "1"
if not os.environ.get("JWT_SECRET"):
    os.environ["JWT_SECRET"] = "chat-unify-test-secret-not-used-in-prod"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ["MAILERCLOUD_API_KEY"] = ""
os.environ["DISCORD_WEBHOOK_URL"] = ""
os.environ["TIDYCAL_API_TOKEN"] = ""
os.environ["POSTMARK_SERVER_TOKEN"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pymongo import MongoClient

URL = "mongodb://127.0.0.1:27999"
TEST_DB = "trustoffice_chat_unify"
try:
    MongoClient(URL, serverSelectionTimeoutMS=3000).drop_database(TEST_DB)
except Exception:
    pass

UID = f"user_{uuid.uuid4().hex[:10]}"
EMAIL = f"chatunify-{uuid.uuid4().hex[:8]}@example.com"
PASSWORD = "ChatUnify#2026"
TRUST = f"trust_{uuid.uuid4().hex[:10]}"


def seed():
    db = MongoClient(URL)[TEST_DB]
    from dependencies import hash_password as get_password_hash
    now = "2026-09-22T00:00:00+00:00"
    db.users.insert_one({
        "user_id": UID, "email": EMAIL, "name": "Chat Unify Test",
        "password_hash": get_password_hash(PASSWORD), "is_admin": False,
        "created_at": now,
    })
    db.subscriptions.insert_one({
        "user_id": UID, "plan_type": "trustee", "status": "active",
        "current_period_end": "2027-09-22T00:00:00+00:00", "is_legacy_price": False,
    })
    db.trusts.insert_one({
        "trust_id": TRUST, "user_id": UID, "name": "Chat Unify Trust",
        "status": "active", "created_at": now,
    })


def plant(db, conv_id, card):
    """Insert a conversation with a pending action card at message index 1."""
    db.chat_conversations.insert_one({
        "conversation_id": conv_id, "user_id": UID, "trust_id": TRUST,
        "created_at": "2026-09-22T00:00:00+00:00",
        "messages": [
            {"role": "user", "content": "please do the thing"},
            {"role": "assistant", "content": "Here is the card.", "action_card": card},
        ],
    })


def main() -> int:
    seed()
    db = MongoClient(URL)[TEST_DB]
    from fastapi.testclient import TestClient
    from server import app

    passed, failed = [], []
    def check(name, cond, detail=""):
        (passed if cond else failed).append((name, detail))
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if not cond and detail else ""))

    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
        h = {"Authorization": f"Bearer {r.json()['token']}"}

        # ---------- 1. HTTP surface isolation ----------
        r = client.get("/api/actions", headers=h)
        names = {a["name"] for a in r.json().get("actions", [])}
        check("manifest exposes only the 5 seed actions",
              r.status_code == 200 and "create-beneficiary" not in names and len(names) == 5,
              f"count={len(names)} sample={sorted(names)[:8]}")
        r = client.post("/api/actions/create-beneficiary", headers=h, json={
            "trust_id": TRUST, "params": {"holder_name": "X"}})
        check("chat-only action NOT callable over HTTP (404)",
              r.status_code == 404, f"got {r.status_code}")

        # ---------- 2. chat approve pipeline → call_action → DB read-back ----------
        conv_id = f"conv_{uuid.uuid4().hex[:10]}"
        plant(db, conv_id, {"type": "beneficiary_preview", "data": {
            "name": "Pipeline Beneficiary", "email": "pb@example.com",
            "allocation_pct": 25, "phone": "5550001111",
        }, "confirmation_status": "pending"})
        # NOTE: chat router mounts at /api/ai (router prefix="/ai"), matching
        # the frontend's confirm call in useChatHistory.js.
        r = client.post(f"/api/ai/chat/actions/{conv_id}/1/confirm", headers=h,
                        json={"action": "approve"})
        body = r.json()
        ex = body.get("execution_result", {})
        check("chat approve → 200 + execution_result.success", r.status_code == 200 and ex.get("success") is True,
              f"{r.status_code} {str(body)[:300]}")
        db_cert = db.trust_unit_certificates.find_one({"holder_name": "Pipeline Beneficiary"})
        check("approved card wrote the real record (DB read-back)",
              db_cert is not None and str(db_cert.get("units")) == "25",
              str(db_cert)[:200] if db_cert else "not found")

        # governance-task intent (second handler, different router)
        conv1b = f"conv_{uuid.uuid4().hex[:10]}"
        plant(db, conv1b, {"type": "task_preview", "data": {
            "task_type": "filing", "description": "File annual registration",
            "due_date": "2026-10-01", "priority": "high",
        }, "confirmation_status": "pending"})
        r = client.post(f"/api/ai/chat/actions/{conv1b}/1/confirm", headers=h,
                        json={"action": "approve"})
        exb = r.json().get("execution_result", {})
        check("task intent approve → success", r.status_code == 200 and exb.get("success") is True,
              str(exb)[:300])
        task = db.governance_tasks.find_one({"description": "File annual registration"})
        check("task record readable in DB", task is not None, str(task)[:150] if task else "not found")

        # ---------- 3. minutes intent (legacy-handler path) ----------
        conv2 = f"conv_{uuid.uuid4().hex[:10]}"
        plant(db, conv2, {"type": "minutes_preview", "data": {
            "minutes_type": "annual", "meeting_date": "2026-09-22",
            "participants": ["Alice Trustee", "Bob Trustee"],
            "decisions": ["Approved budget", "Reviewed allocations"],
            "trust_name": "Chat Unify Trust",
        }, "confirmation_status": "pending"})
        r = client.post(f"/api/ai/chat/actions/{conv2}/1/confirm", headers=h,
                        json={"action": "approve"})
        ex2 = r.json().get("execution_result", {})
        check("minutes approve → success + draft status",
              r.status_code == 200 and ex2.get("success") is True and ex2.get("status") == "draft",
              str(ex2)[:300])
        mrec = db.minutes_records.find_one({"minutes_id": ex2.get("record_id")})
        check("minutes record in DB with status draft",
              mrec is not None and mrec.get("status") == "draft",
              str(mrec)[:200] if mrec else "not found")

        # ---------- 4. list-valued field coercion ----------
        conv3 = f"conv_{uuid.uuid4().hex[:10]}"
        plant(db, conv3, {"type": "entity_preview", "data": {
            "name": "Coerce LLC", "entity_type": "llc",
            "trustee_names": ["T1", "T2"], "member_names": ["M1", "M2"],
        }, "confirmation_status": "pending"})
        r = client.post(f"/api/ai/chat/actions/{conv3}/1/confirm", headers=h,
                        json={"action": "approve"})
        ex3 = r.json().get("execution_result", {})
        check("list-valued card fields coerced → success",
              r.status_code == 200 and ex3.get("success") is True, str(ex3)[:300])
        ent = db.entities.find_one({"name": "Coerce LLC"})
        check("entity created with joined names",
              ent is not None and ent.get("trustee_names") == "T1, T2",
              str(ent)[:200] if ent else "not found")

        # ---------- 5. error mapping ----------
        conv4 = f"conv_{uuid.uuid4().hex[:10]}"
        plant(db, conv4, {"type": "certificate_preview", "data": {
            "beneficiary_name": "No Email Person"}, "confirmation_status": "pending"})
        r = client.post(f"/api/ai/chat/actions/{conv4}/1/confirm", headers=h,
                        json={"action": "approve"})
        ex4 = r.json().get("execution_result", {})
        check("missing required field → readable success=False",
              r.status_code == 200 and ex4.get("success") is False and "email" in str(ex4.get("error", "")).lower(),
              str(ex4)[:200])

        # ---------- cleanup ----------
        MongoClient(URL).drop_database(TEST_DB)

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())