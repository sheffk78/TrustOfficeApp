#!/usr/bin/env python3
"""
TA Evaluation Harness — measures intent classification and extraction accuracy.

Usage:
  python backend/scripts/ta_eval.py                 # intent/extraction mode (live API + LLM)
  python backend/scripts/ta_eval.py --mode knowledge  # knowledge golden-set mode (deterministic)

Requires (intent mode only):
  - .env with TEST_EMAIL and TEST_PASSWORD for the demo account
  - Backend running or accessible at API_BASE

What it does:
  1. Logs into the test account (demovideo@trustoffice.app)
  2. For each test scenario in ta_test_scenarios.py:
     a. Sends the query to TA's chat endpoint
     b. Records the returned intent, confidence, and extracted fields
     c. Compares against expected values
  3. Reports: pass/fail per test, overall accuracy, field-level extraction rates
  4. Saves detailed results to ta_eval_results.json

KNOWLEDGE MODE (--mode knowledge, 2026-10-30 Phase A-2):
  Deterministic, NO LLM and NO login: runs the 40-question golden set
  (ta_golden_knowledge.GOLDEN_SET) against services.trust_knowledge.retrieve_passages()
  and asserts (a) expected source lands top-2, (b) key facts present in top-4 passages,
  (c) wingpoint-tier isolation (fail-closed) for granted questions. This is the
  pre-merge gate for any prompts/*.md or retrieval-scoring change (council spec 2026-10-30).
"""

import os
import sys
import json
import re
import asyncio
from datetime import datetime

# Add parent dir to path so we can import from backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import httpx

API_BASE = os.getenv("API_BASE", "https://api.trustoffice.app")
TEST_EMAIL = os.getenv("TEST_EMAIL", "demovideo@trustoffice.app")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "DemoRecord2026!")

from scripts.ta_test_scenarios import SCENARIOS


def score_intent(expected: str, actual: str) -> bool:
    """Check if the actual intent matches expected (case-insensitive)."""
    return expected.lower() == actual.lower()


def score_fields(expected: dict, actual: dict, required_keys: list) -> dict:
    """
    Score field-level extraction accuracy.
    Returns {field: {expected, actual, match}} for each required field.
    """
    results = {}
    for key in required_keys:
        exp_val = expected.get(key)
        act_val = actual.get(key)
        # Normalize: both None or both match
        if exp_val is None and act_val is None:
            match = True
        elif exp_val is None:
            match = True  # expected didn't specify, skip
        elif act_val is None:
            match = False
        elif isinstance(exp_val, (int, float)) and isinstance(act_val, (int, float)):
            match = abs(float(exp_val) - float(act_val)) < 0.01
        else:
            match = str(exp_val).lower() in str(act_val).lower()
        results[key] = {
            "expected": exp_val,
            "actual": act_val,
            "match": match,
        }
    return results


async def run_eval():
    print(f"\n{'='*60}")
    print(f"TA Evaluation Harness — {datetime.now().isoformat()}")
    print(f"{'='*60}")
    print(f"API: {API_BASE}")
    print(f"Account: {TEST_EMAIL}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"{'='*60}\n")

    # 1. Login
    async with httpx.AsyncClient(timeout=30) as client:
        print("Logging in...")
        login_resp = await client.post(f"{API_BASE}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        })
        if login_resp.status_code != 200:
            print(f"❌ Login failed: {login_resp.status_code} {login_resp.text[:200]}")
            sys.exit(1)
        
        token = login_resp.json().get("token")
        if not token:
            print(f"❌ No token in response: {login_resp.text[:200]}")
            sys.exit(1)
        print(f"✅ Logged in (token: {token[:20]}...)\n")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # 2. Get the demo trust ID
        print("Getting trust list...")
        trusts_resp = await client.get(
            f"{API_BASE}/api/trusts",
            headers=headers,
        )
        if trusts_resp.status_code != 200:
            print(f"❌ Failed to get trusts: {trusts_resp.status_code} {trusts_resp.text[:200]}")
            sys.exit(1)
        
        trusts = trusts_resp.json()
        if not trusts:
            print("❌ No trusts found for test account")
            sys.exit(1)
        
        trust_id = trusts[0].get("trust_id") or trusts[0].get("id")
        trust_name = trusts[0].get("name", "Unknown")
        print(f"✅ Using trust: {trust_name} ({trust_id})\n")

        # 3. Run each scenario
        results = []
        passed = 0
        failed = 0

        for scenario in SCENARIOS:
            sid = scenario["id"]
            query = scenario["query"]
            exp_intent = scenario["expected_intent"]
            exp_fields = scenario["expected_fields"]
            required_keys = scenario["required_fields_present"]

            print(f"  [{sid}] {query[:60]}...", end=" ")

            try:
                resp = await client.post(
                    f"{API_BASE}/api/ai/chat",
                    headers=headers,
                    json={
                        "message": query,
                        "trust_id": trust_id,
                    },
                )

                if resp.status_code != 200:
                    print(f"❌ API error: {resp.status_code}")
                    results.append({
                        "id": sid,
                        "query": query,
                        "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                        "passed": False,
                    })
                    failed += 1
                    continue

                data = resp.json()
                msg = data.get("message", {})
                content = msg.get("content", "")
                action_card = msg.get("action_card")

                # Extract intent from the response
                # The chat endpoint doesn't return the raw intent — it returns a response.
                # We need to check the action_card type to infer the intent.
                actual_intent = None
                actual_fields = {}

                if action_card:
                    actual_intent = action_card.get("type", "").replace("_preview", "")
                    # Map action card types back to intent names
                    intent_map = {
                        "distribution": "create_distribution",
                        "asset": "add_asset",
                        "minutes": "log_minutes",
                        "beneficiary": "create_beneficiary",
                        "beneficiary_update": "update_beneficiary",
                        "beneficiary_removal": "remove_beneficiary",
                        "distribution_cancel": "cancel_distribution",
                        "document_upload": "upload_document",
                        "compensation_plan": "setup_compensation",
                        "task": "schedule_task",
                        "transaction": "add_transaction",
                        "settings_update": "change_settings",
                        "alert_dismiss": "dismiss_alert",
                    }
                    actual_intent = intent_map.get(actual_intent, actual_intent)
                    actual_fields = action_card.get("data", {})
                else:
                    # Read-only response — check content for intent clues
                    actual_intent = "ask_knowledge"  # default for read-only
                    if "deadline" in content.lower() or "due" in content.lower():
                        actual_intent = "check_deadlines"
                    elif "score" in content.lower() or "health" in content.lower() or "defensibility" in content.lower():
                        actual_intent = "health_check"
                    elif "recommend" in content.lower() or "next step" in content.lower():
                        actual_intent = "recommend_action"
                    elif "emergency" in content.lower() or "worried" in content.lower() or "concern" in content.lower():
                        actual_intent = "emergency"
                    elif "hello" in content.lower() or "hi" in content.lower() or "welcome" in content.lower():
                        actual_intent = "general_chat"

                # Score
                intent_pass = score_intent(exp_intent, actual_intent)
                field_results = score_fields(exp_fields, actual_fields, required_keys)
                field_pass = all(r["match"] for r in field_results.values()) if field_results else True
                scenario_pass = intent_pass and field_pass

                if scenario_pass:
                    print("✅")
                    passed += 1
                else:
                    print("❌")
                    if not intent_pass:
                        print(f"     Intent: expected={exp_intent}, got={actual_intent}")
                    for key, r in field_results.items():
                        if not r["match"]:
                            print(f"     Field '{key}': expected={r['expected']}, got={r['actual']}")
                    failed += 1

                results.append({
                    "id": sid,
                    "query": query,
                    "expected_intent": exp_intent,
                    "actual_intent": actual_intent,
                    "intent_pass": intent_pass,
                    "expected_fields": exp_fields,
                    "actual_fields": actual_fields,
                    "field_results": field_results,
                    "field_pass": field_pass,
                    "passed": scenario_pass,
                })

            except Exception as e:
                print(f"❌ Exception: {e}")
                results.append({
                    "id": sid,
                    "query": query,
                    "error": str(e),
                    "passed": False,
                })
                failed += 1

        # 4. Summary
        total = len(SCENARIOS)
        intent_accuracy = sum(1 for r in results if r.get("intent_pass")) / total * 100
        field_accuracy = sum(1 for r in results if r.get("field_pass", True)) / total * 100
        overall = passed / total * 100

        print(f"\n{'='*60}")
        print(f"RESULTS")
        print(f"{'='*60}")
        print(f"  Total scenarios:  {total}")
        print(f"  Passed:           {passed}")
        print(f"  Failed:           {failed}")
        print(f"  Intent accuracy:  {intent_accuracy:.1f}%")
        print(f"  Field accuracy:   {field_accuracy:.1f}%")
        print(f"  Overall:          {overall:.1f}%")
        print(f"{'='*60}\n")

        # 5. Save results
        output = {
            "timestamp": datetime.now().isoformat(),
            "api_base": API_BASE,
            "account": TEST_EMAIL,
            "trust": trust_name,
            "total": total,
            "passed": passed,
            "failed": failed,
            "intent_accuracy_pct": round(intent_accuracy, 1),
            "field_accuracy_pct": round(field_accuracy, 1),
            "overall_accuracy_pct": round(overall, 1),
            "results": results,
        }

        output_path = os.path.join(os.path.dirname(__file__), "ta_eval_results.json")
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"Detailed results saved to: {output_path}")

        # 6. Print failures for quick reference
        failures = [r for r in results if not r.get("passed")]
        if failures:
            print(f"\nFAILURES ({len(failures)}):")
            for f in failures:
                print(f"  [{f['id']}] {f['query'][:50]}...")
                if not f.get("intent_pass"):
                    print(f"    Intent: {f.get('expected_intent')} → {f.get('actual_intent')}")
                field_fails = {k: v for k, v in f.get("field_results", {}).items() if not v.get("match")}
                if field_fails:
                    for k, v in field_fails.items():
                        print(f"    Field '{k}': {v['expected']} → {v['actual']}")

        return overall


# ═══════════════════════════════════════════════════════════════════
# KNOWLEDGE MODE — deterministic golden-set eval (Phase A-2, 2026-10-30)
# ═══════════════════════════════════════════════════════════════════

def run_knowledge_eval() -> int:
    """Run the 40-question golden set against the PRODUCTION knowledge surface.

    Deterministic: no LLM, no login, no network. Returns 0 iff every check passes.

    What is measured — exactly what a member's chat prompt receives:
      - the prompt knowledge slice: chat_service._format_knowledge_context(
        user_message, intent="ask_knowledge", audiences=grant)
      - the retrieval block: trust_retrieval.fetch_doctrine(message,
        allowed_audiences=grant) — production defaults (limit=6, max_chars=3600),
        trigger-gated exactly as in prod.

    Per question (scripts/ta_golden_knowledge.py):
      - source hit (top-2): one of expected_sources appears among the first two
        topic blocks / retrieved sources of that union
      - key facts: every phrase present verbatim (case-insensitive) in the union
        text of the two surfaces (what the LLM would actually see)
      - isolation: for wingpoint-tier questions, the same message with an EMPTY
        grant must contain ZERO wingpoint-tier sources on either surface
      - education_not_advice: course/education questions must not be topped by a
        product doc (12/13/14/15-*) among the first two surfaces
    """
    from scripts.ta_golden_knowledge import GOLDEN_SET

    backend_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    os.chdir(backend_root)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "ta_golden_eval")
    os.environ.setdefault("JWT_SECRET", "ta-golden-eval")

    import importlib
    import chat_service as cs
    import trust_retrieval as tr
    importlib.reload(cs)  # pick up the real corpus AFTER chdir (cache safety)
    importlib.reload(tr)

    # Ensure the FTS index exists so fetch_doctrine's ensure_index() hits the
    # same built index the intent mode verifies.
    from services import trust_knowledge
    db_path = trust_knowledge.default_db_path()
    if not os.path.exists(db_path):
        build = trust_knowledge.build_index(
            trust_knowledge.default_registry_path(),
            trust_knowledge.default_knowledge_dir(),
            db_path,
        )
        print(f"(built index: {build['documents']} docs / {build['passages']} passages)")

    print(f"\n{'=' * 60}")
    print(f"TA Knowledge Golden Set — {datetime.now().isoformat()}")
    print(f"{'=' * 60}")
    print(f"Surface: prompt knowledge slice + fetch_doctrine (production path)")
    print(f"Index:   {db_path}")
    print(f"Questions: {len(GOLDEN_SET)}")
    print(f"{'=' * 60}\n")

    results = []
    n_pass = 0
    n_fail = 0
    for g in GOLDEN_SET:
        gid = g["id"]
        aud = g.get("audience") or ""
        grant = [aud] if isinstance(aud, str) and aud else list(aud)

        # Surface 1 — the prompt knowledge slice (member-facing prompt).
        try:
            slice_text = cs._format_knowledge_context(
                user_message=g["query"], intent="ask_knowledge", audiences=grant
            )
        except Exception as e:
            slice_text = f"(slice error: {e})"

        # Surface 2 — the doctrine retrieval block (trigger-gated in prod).
        try:
            doctrine = tr.fetch_doctrine(g["query"], allowed_audiences=grant) or []
        except Exception as e:
            doctrine = []
        doctrine_sources = [p.get("source_ref") or "" for p in doctrine]

        # Union sources: slice topic headers first, then doctrine source refs.
        # WP-granted topics render as `wingpoint/<stem>` — strip the prefix
        # so the stem comparison is uniform across universals and tiered.
        slice_topics = [
            t.split("/", 1)[-1]
            for t in re.findall(r"(?m)^### (?:wingpoint/)?([0-9][^\n]*)", slice_text or "")
        ]
        union_sources = slice_topics + doctrine_sources
        union_text = (slice_text or "") + "\n" + " ".join(
            (p.get("text") or "") for p in doctrine
        )
        union_lower = union_text.lower()

        checks = {}

        # 1. expected source among the first two surfaced sources. Golden
        # expected_sources are FILENAMES ("24-utc-02-trustee-duties.md"); the
        # prompt slice emits STEM headers ("24-utc-02-trustee-duties — Loyalty").
        # Compare on the stem so the check tests retrieval, not formatting.
        def _stem_of(src: str) -> str:
            base = os.path.basename((src or "").split(" — ")[0].strip())
            return base[:-3] if base.endswith(".md") else base

        expected_stems = [os.path.basename(e)[:-3] if e.endswith(".md") else e
                          for e in g["expected_sources"]]
        checks["source_top2"] = any(
            exp in _stem_of(s) for exp in expected_stems for s in union_sources[:2]
        )

        # 2. key facts verbatim in the union text the model would see
        missing = [k for k in g.get("key_facts", []) if k.lower() not in union_lower]
        checks["key_facts"] = not missing

        # 3. isolation — same message, empty grant, no WP-tier content anywhere
        if g.get("forbidden_for_no_grant"):
            try:
                ng_slice = cs._format_knowledge_context(
                    user_message=g["query"], intent="ask_knowledge", audiences=[]
                )
            except Exception:
                ng_slice = ""
            try:
                ng_doctrine = tr.fetch_doctrine(g["query"], allowed_audiences=[]) or []
            except Exception:
                ng_doctrine = []
            leak = (
                "wingpoint" in (ng_slice or "").lower()
                or any("wingpoint" in (p.get("source_ref") or "").lower() for p in ng_doctrine)
            )
            checks["isolation_fail_closed"] = not leak
        else:
            checks["isolation_fail_closed"] = True  # universal question, N/A

        # 4. education_not_advice — product docs must not top course questions
        if g.get("education_not_advice"):
            top = union_sources[0] if union_sources else ""
            checks["education_not_advice"] = not re.match(
                r"^(12|13|14|15)-", os.path.basename(top or "")
            )
        else:
            checks["education_not_advice"] = True  # N/A

        passed = all(checks.values())
        n_pass += passed
        n_fail += (not passed)

        mark = "✅" if passed else "❌"
        print(f"  [{gid}] {mark} {g['query'][:58]}")
        if not passed:
            for name, ok in checks.items():
                if not ok:
                    if name == "source_top2":
                        print(f"      source_top2: expected any-of {[os.path.basename(x) for x in g['expected_sources']]} | got {union_sources[:2]}")
                    elif name == "key_facts":
                        print(f"      key_facts missing: {missing}")
                    elif name == "isolation_fail_closed":
                        print(f"      ISOLATION LEAK: empty-grant surface contains wingpoint material")
                    elif name == "education_not_advice":
                        print(f"      education_not_advice: product doc topped the course question: {union_sources[0]}")

        results.append({
            "id": gid,
            "category": g["category"],
            "query": g["query"],
            "audience": grant,
            "union_sources": union_sources[:6],
            "doctrine_triggered": bool(doctrine),
            "checks": checks,
            "missing_key_facts": missing,
            "passed": passed,
        })

    total = len(GOLDEN_SET)
    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total golden questions: {total}")
    print(f"  Passed:                 {n_pass}")
    print(f"  Failed:                 {n_fail}")
    print(f"  Accuracy:               {n_pass / total * 100:.1f}%")
    tri = sum(1 for r in results if r["doctrine_triggered"])
    print(f"  Doctrine-triggered:     {tri}/{total}")
    print(f"{'=' * 60}\n")

    output = {
        "timestamp": datetime.now().isoformat(),
        "mode": "knowledge",
        "surface": "prompt_slice+fetch_doctrine",
        "total": total,
        "passed": n_pass,
        "failed": n_fail,
        "accuracy_pct": round(n_pass / total * 100, 1),
        "results": results,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ta_golden_results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"Detailed results saved to: {out_path}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    import argparse
    _parser = argparse.ArgumentParser(description="TA evaluation harness")
    _parser.add_argument("--mode", choices=["intent", "knowledge"], default="intent",
                         help="intent = live API intent/extraction eval; knowledge = deterministic golden-set eval")
    _args = _parser.parse_args()
    if _args.mode == "knowledge":
        sys.exit(run_knowledge_eval())
    asyncio.run(run_eval())
