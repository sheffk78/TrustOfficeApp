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