# TrustOffice Nightly QA Report — 2026-09-07 (MDT)

**Target:** https://api.trustoffice.app (live prod)  |  59 users in DB

## Suite Results

### test_api_smoke.py — ⚠️ 2 FAILED / 22 passed (24 total)
| Test | HTTP | Root cause |
|---|---|---|
| TestAuth::test_register | 410 | **Intentional.** API returns: *"Direct signup is disabled. TrustOffice is subscribe-first — please choose a plan at /pricing to create your account."* |
| TestAuth::test_login | 401 | Cascade of the above — test registers-then-logs-in a fresh account; register now 410s, so login has no account. |

Everything else passed (health, admin API health, users list, admin stats [xfail known revenue bug], admin unauth-blocked, gift-subscription, dashboard, auth/me, protected-endpoint auth gates, etc.) — 22/22.

### test_data_isolation.py — ✅ 14 passed / 14 total
Data isolation across tenants fully verified. No regressions.

## Prod Hygiene — ✅ CLEAN
- Users scanned: **59**
- Designated QA accounts (test.qa1/qa2/qa3@trustoffice.app): present & allowed
- Stray test-pattern accounts beyond the 3 QA: **0**
- No bulk-delete needed. Prod is clean.

## Failure Analysis — register 410 / login 401
Direct self-service signup has been **deliberately disabled** on prod (product decision: TrustOffice is now subscribe-first). The live API confirms this with a 410 and a message pointing to /pricing.

**These two failures are STALE TESTS, not a prod regression.** The smoke suite's `test_register` and `test_login` still assume open self-signup at `/api/auth/register`. They need to be updated to reflect the subscribe-first flow — either:
  (a) change both to expect 410 + the disable message, or
  (b) mark them `xfail` against prod with the reason, or
  (c) point them at the /pricing → plan → create-account flow.

No customer-facing impact. The 22/22 functional endpoints are healthy, isolation is clean, and the DB is spotless.

## Overall Verdict
**PASS WITH 2 STALE-TEST NOISE.** All functional prod endpoints healthy, data isolation clean, prod DB clean. The only 2 failures are tests that predate the intentional "subscribe-first / no direct signup" product change — **Jeff's call**: update those two tests to the new flow (I recommend option a, asserting 410 + the disable message, so we keep an explicit smoke check *that* signup is properly gated).

---
_report: /Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/TrustOfficeApp/qa-reports/nightly-qa-2026-09-07_nightly.md_
