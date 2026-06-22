#!/usr/bin/env python3
"""
TA Evaluation Harness — measures intent classification and extraction accuracy.

Usage:
  python backend/scripts/ta_eval.py

Requires:
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
"""

import os
import sys
import json
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


if __name__ == "__main__":
    asyncio.run(run_eval())
