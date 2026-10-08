"""Production-safety gate for TrustOffice backend tests.

Background (2026-09-04 incident): test_auth_router.py / test_referrals.py /
test_password_reset.py were run against the LIVE prod API
(REACT_APP_BACKEND_URL=https://api.trustoffice.app), registering 14 throwaway
@example.com accounts in the production user list that Kenneth then saw in the
admin panel.

Rule: the ONLY suites allowed to run against production are the two sanctioned
nightly-suite files, which use the 3 designated QA accounts
(test.qa1/2/3@trustoffice.app) and self-clean any throwaways:
  - test_api_smoke.py
  - test_data_isolation.py

Every other test file is blocked from collection when the target URL is a
production host. Running against localhost / staging / no URL is unaffected.

Env vars checked (mirrors what the suites themselves read):
  REACT_APP_BACKEND_URL, BACKEND_URL, TEST_BASE_URL
"""

import os

import pytest

# PRISTINE motor capture (2026-10-07, class-members integration suites): any
# suite that mongomock-patches motor.motor_asyncio.AsyncIOMotorClient does it
# at MODULE IMPORT (pytest collection order) — a later suite's own capture then
# gets the MOCK and its replica-set fixture silently runs against an in-memory
# fake. conftest is imported before every test module, so this capture is the
# pristine real client class. Suites needing real motor MUST import it from
# here instead of re-capturing (fixes the admin-customers/... contamination).
from motor import motor_asyncio as _motor_aio
REAL_MOTOR_CLIENT_CLASS = _motor_aio.AsyncIOMotorClient

# Tier price IDs are read at module import in routers/subscriptions.py. CI never sets
# them, giving PRICE_IDS entries = None and 500s ("Price ID not configured") that fire
# BEFORE Stripe — which broke tests/test_trust_cap_checkout.py's pass-path detection
# (2026-10-07 CI emails: Backend Tests red since Oct 3). Placeholders make the
# pass-path deterministic in any env: placeholder key/price → Stripe error path.
# setdefault preserves real values in local/prod-shaped envs.
for _env in (
    "STRIPE_TRUSTEE_MONTHLY_PRICE_ID", "STRIPE_TRUSTEE_ANNUAL_PRICE_ID",
    "STRIPE_ESTATE_MONTHLY_PRICE_ID", "STRIPE_ESTATE_ANNUAL_PRICE_ID",
    "STRIPE_ADVISOR_MONTHLY_PRICE_ID", "STRIPE_ADVISOR_ANNUAL_PRICE_ID",
    "STRIPE_WINGPOINT_MONTHLY_PRICE_ID", "STRIPE_WINGPOINT_ANNUAL_PRICE_ID",
):
    os.environ.setdefault(_env, "price_test_placeholder")

PROD_HOST_MARKERS = ("api.trustoffice.app", "app.trustoffice.app", "trustoffice.app")

URL_ENV_VARS = ("REACT_APP_BACKEND_URL", "BACKEND_URL", "TEST_BASE_URL")

# Sanctioned prod suites (designated QA accounts, self-cleaning).
PROD_SANCTIONED_FILES = {"test_api_smoke.py", "test_data_isolation.py"}


def _target_url() -> str:
    for var in URL_ENV_VARS:
        val = (os.environ.get(var) or "").strip()
        if val:
            return val
    return ""


def _is_prod_url(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return any(marker in lowered for marker in PROD_HOST_MARKERS)


def pytest_collection_modifyitems(config, items):
    """Block non-sanctioned suites from collecting when pointed at prod."""
    url = _target_url()
    if not _is_prod_url(url):
        return

    offending = set()
    for item in items:
        filename = os.path.basename(str(item.fspath))
        if filename not in PROD_SANCTIONED_FILES:
            offending.add(filename)

    if not offending:
        return

    pytest.exit(
        (
            "\n\n*** BLOCKED: PRODUCTION URL + NON-SANCTIONED TEST SUITE ***\n"
            f"Target URL: {url}\n"
            f"Non-sanctioned files in this run: {', '.join(sorted(offending))}\n\n"
            "Only these suites may run against production (they reuse the 3\n"
            "designated QA accounts and self-clean throwaways):\n"
            "  - test_api_smoke.py\n"
            "  - test_data_isolation.py\n\n"
            "All other suites create throwaway accounts in the production user\n"
            "list. Run them against a local/staging backend instead:\n"
            "  REACT_APP_BACKEND_URL=http://localhost:8001 pytest backend/tests/<file>\n"
            "(Unset the URL env vars entirely if your local backend is the default.)\n"
        ),
        returncode=3,
    )