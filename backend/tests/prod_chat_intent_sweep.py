#!/usr/bin/env python3
"""
Prod intent sweep: drive EVERY Trust Assistant action-card intent through the
LIVE deployed pipeline — chat message → action card → approve → execution
result → record existence (via cleanup endpoint) → cleanup.

Covers all 20 mutating chat intents + minutes (dedicated handler). Folded-in
edge cases: reject path, missing-field degradation, double-approve race.

Order matters: dependency-chained intents (asset→asset_update,
distribution→distribution_cancel, beneficiary→update→certificate→removal,
class_beneficiary→removal) run in sequence; independents run in between.

Credentials: env TO_PROBE_EMAIL/PASS/TRUST, else parsed from the demo
verification line in Kit/life/brands/TrustOffice/SUPPORT-NOTES.md (never
printed). Run: backend/.venv/bin/python tests/prod_chat_intent_sweep.py
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx

BASE = "https://api.trustoffice.app/api"
EMAIL = os.environ.get("TO_PROBE_EMAIL", "")
PW = os.environ.get("TO_PROBE_PASS", "")
TRUST = os.environ.get("TO_PROBE_TRUST", "")
if not (EMAIL and PW and TRUST):
    pass  # filled by load_creds() from SUPPORT-NOTES.md (never printed)


def notes_path():
    return os.path.expanduser(
        "~/.openclaw/workspace/Kit/life/brands/TrustOffice/SUPPORT-NOTES.md")


def load_creds():
    global EMAIL, PW, TRUST
    if EMAIL and PW and TRUST:
        return
    line = next(l for l in open(notes_path()) if "demovideo@trustoffice.app" in l)
    email = re.search(r"([\w.+-]+@[\w-]+\.[\w.]+)", line).group(1)
    pw = re.search(r"/\s*([^,`\s]+)", line).group(1)
    trust = re.search(r"`(trust_[0-9a-f]+)`", line).group(1)
    EMAIL, PW, TRUST = email, pw, trust


c = httpx.Client(timeout=120)
H = {}

RESULTS = []
CONVERSATIONS = []


def log(step, status, detail=""):
    line = {"t": datetime.now(timezone.utc).isoformat(), "step": step,
            "status": status, "detail": str(detail)[:400]}
    RESULTS.append(line)
    print(json.dumps(line), flush=True)


def chat(message):
    """Post via the SSE streaming route — the path real users (frontend) hit.
    Cards are generated server-side with PINNED types there; the non-streaming
    /ai/chat route lets the LLM freestyle the type (unpinned) and is not the
    user-facing path."""
    r = c.post(f"{BASE}/ai/chat/stream", headers=H,
               json={"message": message, "trust_id": TRUST})
    assert r.status_code == 200, f"chat {r.status_code}: {r.text[:300]}"
    conv_id = None
    for line in r.text.split("\n"):
        if line.startswith("data:"):
            try:
                ev = json.loads(line[5:].strip())
            except Exception:
                continue
            if ev.get("conversation_id"):
                conv_id = ev["conversation_id"]
    assert conv_id, "no conversation_id in SSE stream"
    CONVERSATIONS.append(conv_id)
    return conv_id


LAST_STORED = []


def find_pending_card(conv_id, type_variants):
    global LAST_STORED
    rc = c.get(f"{BASE}/ai/chat/conversations/{conv_id}", headers=H)
    assert rc.status_code == 200, f"conv fetch {rc.status_code}"
    stored = rc.json().get("messages", [])
    LAST_STORED = stored
    for i, m in enumerate(stored):
        if not isinstance(m, dict):
            continue
        ac = m.get("action_card")
        if ac and ac.get("confirmation_status") in (None, "pending"):
            t = str(ac.get("type", ""))
            if any(v in t or t in v for v in type_variants):
                return ac, i
    return None, None


def approve(conv_id, idx, action="approve", edited=None):
    body = {"action": action}
    if edited:
        body["edited_data"] = edited
    r = c.post(f"{BASE}/ai/chat/actions/{conv_id}/{idx}/confirm", headers=H, json=body)
    return r


def cleanup(endpoint, rid, method="DELETE", body=None, expect_404_ok=False):
    if not rid:
        return ("skip", "no record_id")
    try:
        if method == "DELETE":
            r = c.delete(f"{BASE}/{endpoint}/{rid}", headers=H)
        else:
            r = c.patch(f"{BASE}/{endpoint}/{rid}", headers=H, json=body)
        return (r.status_code, r.text[:120])
    except Exception as e:
        return ("err", str(e)[:120])


SWEEP = [
    # (key, message, type_variants, expect_success)
    ("distribution",
     "Create a distribution of $500 to Jordan Blake from the trust today for expenses.",
     ["distribution_preview", "add_distribution", "create_distribution"], True),
    ("asset",
     "Add an asset to Schedule A: a 2024 Honda Accord worth $28,000, acquired today.",
     ["asset_preview", "add_asset"], True),
    ("asset_update",  # runs after asset — references it
     "Update the Schedule A asset '2024 Honda Accord' with a new value of $26,500 as of today.",
     ["asset_update_preview", "update_asset_value", "update_asset"], True),
    ("contribute_asset",
     "Contribute my wine collection worth $12,000 to the trust. Grantor is John Smith, "
     "contribution meeting today with trustees Jordan Blake and John Smith.",
     ["contribute_asset", "contribute_asset_to_trust", "accept_asset_contribution"], True),
    ("beneficiary",
     "Add Jordan Blake as a beneficiary with a 25% allocation, email jordan.blake@example.com.",
     ["beneficiary_preview", "add_beneficiary", "create_beneficiary"], True),
    ("beneficiary_update",  # after beneficiary
     "Update beneficiary Jordan Blake's email to jane2@example.com and add a note that she "
     "confirmed her mailing address.",
     ["beneficiary_update_preview", "update_beneficiary_contact", "update_beneficiary"], True),
    ("send_certificate",  # after beneficiary (active cert required); self-addressed email
     "Email Jordan Blake's certificate notice to demovideo@trustoffice.app.",
     ["certificate_preview", "send_certificate_notice", "send_certificate"], True),
    ("beneficiary_removal",  # after certificate (soft-deletes the cert)
     "Remove beneficiary Jordan Blake — she is no longer eligible under the trust terms.",
     ["beneficiary_removal_preview", "remove_beneficiary", "delete_beneficiary"], True),
    ("distribution_cancel",  # after distribution
     "Cancel the $500 distribution to Jordan Blake dated today.",
     ["distribution_cancel_preview", "cancel_distribution", "delete_distribution"], True),
    ("document_upload",
     "Upload a vault document titled 'Sweep Test Deed 2026' to the vault with category deed.",
     ["document_upload_preview", "upload_vault_document", "upload_document"], True),
    ("compensation_plan",
     "Set up a compensation plan for trustee John Smith at $3,000 per year, effective today.",
     ["compensation_plan_preview", "create_compensation_plan", "setup_compensation"], True),
    ("compensation_payment",
     "Record a compensation payment of $250 to trustee John Smith today.",
     ["compensation_payment_preview", "record_compensation_payment"], True),
    ("investment",
     "Add an investment: 10 shares of Vanguard S&P 500 ETF (VOO), cost basis $4,500, "
     "purchased today, custodian Fidelity.",
     ["investment_preview", "add_investment"], True),
    ("task",
     "Schedule a governance task of type tax_filing: review annual tax filings, due next month, high priority.",
     ["task_preview", "add_governance_task", "schedule_task"], True),
    ("transaction",
     "Record a transaction: expense of $250 for accounting software today.",
     ["transaction_preview", "record_transaction", "add_transaction"], True),
    ("entity",
     "Create an LLC named Sweep Test Properties LLC, formed in Utah on 2026-09-22.",
     ["entity_preview", "create_entity", "add_entity"], True),
    ("class_beneficiary",
     "Add a class of beneficiaries: descendants of John Smith, 30 percent.",
     ["class_beneficiary_preview", "add_beneficiary_class", "create_class_beneficiary"], True),
    ("class_beneficiary_removal",  # after class_beneficiary
     "Remove the descendants of John Smith class of beneficiaries.",
     ["class_beneficiary_removal_preview", "remove_beneficiary_class", "remove_class_beneficiary"], True),
    ("alert_dismiss",
     "Dismiss the Quarterly Minutes governance alert for this trust.",
     ["alert_dismiss", "dismiss_governance_alert_criterion", "dismiss_alert"], True),
    ("settings_update",
     "Change the trust's jurisdiction to Nevada.",
     ["settings_update_preview", "update_trust_jurisdiction", "update_trust_settings"], True),
    ("minutes",
     "Log general minutes for our annual meeting today. Trustees present were Jordan Blake "
     "and John Smith, and we approved the annual budget review.",
     ["minutes_preview", "log_minutes", "create_minutes"], True),
]


def main():
    load_creds()
    r = c.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PW})
    for _ in range(4):
        if r.status_code == 200:
            break
        wait = (r.json() or {}).get("retry_after", 10) if r.status_code == 429 else 10
        time.sleep(min(wait + 1, 65))
        r = c.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200, f"login {r.status_code}"
    H.update({"Authorization": f"Bearer {r.json()['token']}"})
    log("login", "ok")

    # Save original jurisdiction for settings restore
    r = c.get(f"{BASE}/trusts/{TRUST}", headers=H)
    orig = r.json() if r.status_code == 200 else {}
    orig_jurisdiction = orig.get("jurisdiction")
    log("settings-snapshot", "ok", f"jurisdiction={orig_jurisdiction!r}")

    passed = failed = 0
    rid_by_key = {}

    # --- pre-seed dependent records via the UI API (chat intents that need targets) ---
    seed_beneficiary_id = None
    seed_beneficiary_keys = []
    try:
        r = c.post(f"{BASE}/beneficiaries/create", headers=H, json={
            "trust_id": TRUST, "name": "Jordan Blake", "email": "jane.doe@example.com",
            "allocation_pct": 10})
        if r.status_code in (200, 201):
            rj = r.json() or {}
            seed_beneficiary_id = rj.get("beneficiary_id") or rj.get("certificate_id")
            seed_beneficiary_keys = sorted(rj.keys())
        if seed_beneficiary_id:
            log("seed/beneficiary", "ok", f"id={seed_beneficiary_id} code={r.status_code}")
        else:
            log("seed/beneficiary", "warn", f"code={r.status_code} body_keys={seed_beneficiary_keys[:12]} body={r.text[:180]}")
    except Exception as e:
        log("seed/beneficiary", "ERROR", f"{type(e).__name__}: {e}")
    seed_entity_id = None
    try:
        r = c.post(f"{BASE}/entities", headers=H, json={
            "trust_id": TRUST, "name": "Sweep Seed Entity", "entity_type": "Trust",
            "legal_name": "Sweep Seed Entity LLC", "formation_date": "2020-01-15",
            "governing_law": "CA"})
        if r.status_code in (200, 201):
            seed_entity_id = (r.json() or {}).get("entity_id")
        if seed_entity_id:
            log("seed/entity", "ok", f"id={seed_entity_id} code={r.status_code}")
        else:
            log("seed/entity", "warn", f"code={r.status_code} body={r.text[:180]}")
    except Exception as e:
        log("seed/entity", "ERROR", f"{type(e).__name__}: {e}")
    seed_distribution_id = None
    try:
        r = c.post(f"{BASE}/distributions", headers=H, json={
            "trust_id": TRUST, "beneficiary_name": "Jordan Blake", "amount": 500,
            "purpose_classification": "distribution", "date": "2026-09-22"})
        if r.status_code in (200, 201):
            rj = r.json() or {}
            seed_distribution_id = rj.get("distribution_id")
        if seed_distribution_id:
            log("seed/distribution", "ok", f"id={seed_distribution_id} code={r.status_code}")
        else:
            log("seed/distribution", "warn", f"code={r.status_code} body={r.text[:180]}")
    except Exception as e:
        log("seed/distribution", "ERROR", f"{type(e).__name__}: {e}")

    for key, msg, variants, expect_ok in SWEEP:
        try:
            conv_id = chat(msg)
            card, idx = find_pending_card(conv_id, variants)
            if not card:
                types = [str((m.get("action_card") or {}).get("type", ""))
                         for m in LAST_STORED if isinstance(m, dict) and m.get("action_card")]
                log(key, "NO-CARD", f"conv={conv_id} card_types={types}")
                failed += 1
                continue
            r = approve(conv_id, idx)
            if r.status_code != 200:
                log(key, "FAIL", f"confirm {r.status_code}: {r.text[:200]}")
                failed += 1
                continue
            ex = r.json().get("execution_result") or {}
            ok = ex.get("success") is expect_ok
            rid = ex.get("record_id") or ex.get("schedule_a_id") or ""
            extra = {k: ex.get(k) for k in ("minutes_id", "endpoint", "error") if k in ex}
            log(key, "PASS" if ok else "FAIL",
                f"success={ex.get('success')} rid={rid} {json.dumps(extra)[:200]}")
            passed += ok
            failed += (not ok)

            rid_by_key[key] = rid  # remember for deferred/end cleanup
            # cleanup per endpoint — chains (asset→asset_update, beneficiary→…→removal,
            # class→removal) clean up at END so dependent cases keep their targets
            DEFER = {"asset", "beneficiary", "beneficiary_update", "send_certificate",
                     "class_beneficiary", "distribution"}
            ep = ex.get("endpoint", "")
            if key in DEFER and ok:
                log(key + "/cleanup", "ok", "deferred to end-of-run")
            elif key == "contribute_asset" and ok:
                a = c.delete(f"{BASE}/schedule-a/{ex.get('schedule_a_id')}", headers=H)
                m = c.delete(f"{BASE}/minutes/{ex.get('minutes_id')}", headers=H)
                log(key + "/cleanup", "ok", f"asset={a.status_code} minutes={m.status_code}")
            elif ep == "investments" and ok:
                p = c.patch(f"{BASE}/investments/{rid}", headers=H, json={"is_active": False})
                log(key + "/cleanup", "ok", f"patch={p.status_code}")
            elif key == "settings_update" and ok:
                rest = c.put(f"{BASE}/trusts/{TRUST}", headers=H,
                              json={"jurisdiction": orig_jurisdiction})
                log(key + "/restore", "ok", f"put={rest.status_code}")
            elif key == "alert_dismiss" and ok:
                res = c.post(f"{BASE}/governance/insights/restore", headers=H,
                             json={"trust_id": TRUST, "criterion_name": "Quarterly Minutes"})
                log(key + "/restore", "ok", f"restore={res.status_code}")
            elif ep and rid and ep != "trusts":
                allow_404 = (key == "beneficiary_removal")
                code, body_ = cleanup(ep, rid, expect_404_ok=allow_404)
                log(key + "/cleanup", "ok" if code == 200 or allow_404 else "WARN",
                    f"{code} {body_}")
            # conversation tidy-up
            c.delete(f"{BASE}/ai/chat/conversations/{conv_id}", headers=H)
            time.sleep(2)
        except Exception as e:
            log(key, "ERROR", f"{type(e).__name__}: {e}")
            failed += 1
            time.sleep(2)

    # --- edge: reject path (transaction message, reject the card) ---
    try:
        conv_id = chat("Record a transaction: expense of $75 for office supplies today.")
        card, idx = find_pending_card(conv_id, ["transaction_preview", "add_transaction"])
        assert card, "no transaction card for reject test"
        r = approve(conv_id, idx, action="reject")
        status = r.json().get("action_status")
        log("reject-path", "PASS" if (r.status_code == 200 and status == "rejected") else "FAIL",
            f"status={status}")
        passed += (r.status_code == 200 and status == "rejected")
        failed += not (r.status_code == 200 and status == "rejected")
        c.delete(f"{BASE}/ai/chat/conversations/{conv_id}", headers=H)
        time.sleep(2)
    except Exception as e:
        log("reject-path", "ERROR", f"{type(e).__name__}: {e}")
        failed += 1

    # --- edge: double-approve race (task) ---
    try:
        conv_id = chat("Schedule a governance task of type custom: sweep race test, due 2026-10-01.")
        card, idx = find_pending_card(conv_id, ["task_preview", "schedule_task"])
        assert card, "no task card for race test"
        r1 = approve(conv_id, idx)
        ex1 = r1.json().get("execution_result") or {}
        rid1 = ex1.get("record_id")
        r2 = approve(conv_id, idx)
        ex2 = (r2.json() or {}).get("execution_result") or {}
        rid2 = ex2.get("record_id")
        dupe = ex2.get("success") is True and rid2 and rid2 != rid1
        log("double-approve",
            "DUP-BUG" if dupe else "GUARDED",
            f"first={rid1} second={rid2} second_success={ex2.get('success')}")
        for rid in {rid1, rid2}:
            if rid:
                c.delete(f"{BASE}/tasks/{rid}", headers=H)
        c.delete(f"{BASE}/ai/chat/conversations/{conv_id}", headers=H)
        time.sleep(2)
    except Exception as e:
        log("double-approve", "ERROR", f"{type(e).__name__}: {e}")
        failed += 1

    # --- edge: missing-field degradation (vague task) ---
    try:
        conv_id = chat("Schedule a task.")
        card, idx = find_pending_card(conv_id, ["task_preview", "schedule_task"])
        if not card:
            log("missing-field", "PASS", "assistant asked clarification (no card) — graceful")
            passed += 1
        else:
            r = approve(conv_id, idx)
            ex = r.json().get("execution_result") or {}
            graceful = (r.status_code == 200 and ex.get("success") is False
                        and ex.get("error"))
            log("missing-field", "PASS" if graceful else "FAIL",
                f"approved→success={ex.get('success')} error={ex.get('error')}")
            passed += int(bool(graceful))
            failed += int(not graceful)
            if ex.get("record_id"):
                c.delete(f"{BASE}/tasks/{ex['record_id']}", headers=H)
        c.delete(f"{BASE}/ai/chat/conversations/{conv_id}", headers=H)
    except Exception as e:
        log("missing-field", "ERROR", f"{type(e).__name__}: {e}")
        failed += 1

    # --- sweep any leftover test certificates (chat-created certs survive beneficiary deletes) ---
    try:
        rc_ = c.get(f"{BASE}/trust-units/certificates", headers=H, params={"trust_id": TRUST})
        for cert in (rc_.json() or []):
            holder = str(cert.get("holder_name", ""))
            if cert.get("status") != "cancelled" and ("Jordan Blake" in holder or "Sweep" in holder):
                c.delete(f"{BASE}/trust-units/certificates/{cert['certificate_id']}", headers=H)
                log("cleanup/stray-cert", "ok", f"cancelled {cert['certificate_id']}")
    except Exception as e:
        log("cleanup/stray-cert", "WARN", f"{type(e).__name__}: {e}")

    # --- cleanup deferred (chain) records ---
    for dkey in ("asset_update", "asset", "beneficiary_removal", "send_certificate",
                 "beneficiary_update", "beneficiary", "class_beneficiary_removal",
                 "class_beneficiary", "distribution_cancel", "distribution"):
        d_rid = rid_by_key.get(dkey)
        if not d_rid:
            continue
        ep_map = {"asset": "schedule-a", "asset_update": None,
                  "beneficiary": "beneficiaries", "beneficiary_update": "beneficiaries",
                  "send_certificate": None, "beneficiary_removal": None,
                  "class_beneficiary": "class-beneficiaries",
                  "class_beneficiary_removal": None,
                  "distribution": "distributions", "distribution_cancel": None}
        ep_ = ep_map.get(dkey)
        if not ep_:
            continue
        rd_ = c.delete(f"{BASE}/{ep_}/{d_rid}", headers=H)
        log("cleanup/" + dkey, "ok", f"code={rd_.status_code}")

    # --- cleanup seeded records ---
    if seed_entity_id:
        re_ = c.delete(f"{BASE}/entities/{seed_entity_id}", headers=H)
        log("cleanup/seed-entity", "ok", f"code={re_.status_code}")
    if seed_distribution_id:
        rd = c.delete(f"{BASE}/distributions/{seed_distribution_id}", headers=H)
        log("cleanup/seed-distribution", "ok", f"code={rd.status_code}")
    if seed_beneficiary_id:
        rb = c.delete(f"{BASE}/beneficiaries/{seed_beneficiary_id}", headers=H)
        log("cleanup/seed-beneficiary", "ok", f"code={rb.status_code}")

    summary = {"passed": passed, "failed": failed,
               "total": passed + failed,
               "when": datetime.now(timezone.utc).isoformat()}
    log("SUMMARY", "DONE", json.dumps(summary))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())