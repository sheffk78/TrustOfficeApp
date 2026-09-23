#!/usr/bin/env python3
"""
Live prod probe: Trust Assistant chat → action card → approve → DB read-back.

Drives the REAL deployed pipeline (chat approval → action_layer.call_action →
record creation) against https://api.trustoffice.app using the demo account.
Creates one draft minutes record, verifies read-back, deletes it.

Credentials come from env (never hardcode):
  TO_PROBE_EMAIL  demo account email
  TO_PROBE_PASS   demo account password
  TO_PROBE_TRUST  trust id to scope the chat to

Run: backend/.venv/bin/python tests/prod_chat_action_probe.py
Demo creds historically documented in Kit/life/brands/TrustOffice/SUPPORT-NOTES.md.
"""
import json
import os
import sys

import httpx

BASE = "https://api.trustoffice.app/api"
EMAIL = os.environ.get("TO_PROBE_EMAIL", "")
PW = os.environ.get("TO_PROBE_PASS", "")
TRUST = os.environ.get("TO_PROBE_TRUST", "")
if not (EMAIL and PW and TRUST):
    sys.exit("Set TO_PROBE_EMAIL / TO_PROBE_PASS / TO_PROBE_TRUST first")

c = httpx.Client(timeout=90)
r = c.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PW})
assert r.status_code == 200, f"login {r.status_code} {r.text[:200]}"
H = {"Authorization": f"Bearer {r.json()['token']}"}
print("login: 200")

r = c.post(f"{BASE}/ai/chat", headers=H, json={
    "message": ("Log general minutes for our annual meeting today. The trustees present "
                "were Jane Doe and John Smith, and we approved the annual budget review."),
    "trust_id": TRUST,
})
assert r.status_code == 200, r.text[:400]
data = r.json()
conv_id = data.get("conversation_id")
assert conv_id, "no conversation_id: " + json.dumps(data)[:300]

# The card index must come from the STORED conversation (confirm's source of truth)
rc = c.get(f"{BASE}/ai/chat/conversations/{conv_id}", headers=H)
assert rc.status_code == 200, f"conv fetch {rc.status_code}"
stored = rc.json().get("messages", [])
card, idx = None, None
for i, m in enumerate(stored):
    ac = m.get("action_card") if isinstance(m, dict) else None
    if ac and ac.get("confirmation_status") in (None, "pending") and (
        "minutes_preview" in str(ac.get("type", "")) or str(ac.get("type", "")) == "create_minutes"
    ):
        card, idx = ac, i
assert card, "no pending minutes card in stored conversation"
print(f"card: {card.get('type')} idx: {idx} of {len(stored)}")

r = c.post(f"{BASE}/ai/chat/actions/{conv_id}/{idx}/confirm", headers=H, json={"action": "approve"})
assert r.status_code == 200, r.text[:400]
ex = r.json().get("execution_result", {})
print("execution_result:", json.dumps(ex)[:300])
assert ex.get("success") is True, "execution failed"

rid = ex.get("record_id")
r = c.get(f"{BASE}/minutes/{rid}", headers=H)
print("readback:", r.status_code, r.json().get("status") if r.status_code == 200 else r.text[:120])
assert r.status_code == 200

d = c.delete(f"{BASE}/minutes/{rid}", headers=H)
print("cleanup:", d.status_code)
print("PROBE-OK")