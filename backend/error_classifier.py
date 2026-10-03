"""Error noise classification for TrustOffice.

Jeff directive 2026-09-21 (morning review, noise-reduction mandate): the
morning digest reported 27 "errors" — all of which were test-suite traffic,
bot scanner probes, or documented business responses. Zero real failures.
This module is the SINGLE SOURCE OF TRUTH for classifying captured errors
into noise classes, shared by BOTH layers so they can never drift apart:

  1. Backend capture layer (http_4xx_capture.py) — classifies at capture
     time and tags the error doc with metadata.noise_class.
  2. Orchestrator (agent-side, ~/.hermes/scripts/): trusts the stored
     noise_class, falls back to classify() for legacy docs.

Noise classes (metadata.noise_class):
  - "scanner"      — credential/path-probe sweeps (/.env, /.git/config,
                     /phpinfo.php, /wp-login.php, ...). 404 + probe path.
                     Verified: 100% of these return 404; nothing leaks.
  - "api_root"     — bare pings to / (the API has no root page).
  - "test_suite"   — 410 Direct-signup-disabled, empty-name 422 on
                     /api/trusts, /api/audit-trail 404, /api/minutes
                     "Trust not found" 404, governance "Trust not found"
                     on known QA/nonexistent trust ids (09:01 UTC window).
  - "business_empty" — documented empty-result responses: external
                     lookup-user 404 {"found": false} (WingPoint
                     provisioning asking "does this email exist?").
  - "drift_probe"  — scanner probing API-ish paths (/_ignition, /graphql,
                     /api/console/...) — same as scanner but API-prefixed.

A classed error is STILL STORED in error_logs (forensics intact) but never
pages Discord and never enters the fixer queue. The orchestrator marks it
resolved via the --noise path on the next cycle.

Everything that does NOT classify as noise keeps flowing exactly as today:
real fixer work, Discord alerting, escalation deadlines.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Scanner probe-path patterns (case-insensitive, matched against the path)
# ---------------------------------------------------------------------------
_SCANNER_RE = re.compile(
    r"(?i)"
    r"(\.env"                      # .env, .env.local, /staging/.env, /@fs/.env
    r"|\.git"                      # /.git/config, /.github/.env
    r"|\.svn"
    r"|\.ssh"
    r"|\.pypirc"
    r"|\.gradle"
    r"|\.swp"
    r"|\.bak"
    r"|\.save"
    r"|phpinfo"
    r"|\bpi\.php\b|\bi\.php\b|\binfo\.php\b|\btest\.php\b|\badmin\.php\b"
    r"|/index\.php\b|\bindex\.php\b"
    r"|read-document"
    r"|debug-trigger"
    r"|\bwp[-_]"
    r"|wp-login|xmlrpc"
    r"|_ignition|_debugbar|_profiler|telescope|laravel"
    r"|actuator|server-status|debug/vars"
    r"|userfiles|/console/api_server|designer/v1/file-content"
    r"|graphql|/v1/config|/v1/keys|/v1/env|/v1/settings|/v2/settings|/v1/validate"
    r"|/api/4/config|/api/account\b|/api/settings\b|/api/config\b|/api/health\b"
    r"|/api/w/|/api/console|proc/self|/environ"
    r"|templates/preview"
    r"|credentials|secret|credential"
    r"|(sa|service|gcp|google|firebase)[-_]?(admin|account|credentials?)"
    r"|key\.json|sa\.json|config\.env"
    r"|dockerfile|serverless\.yaml|swagger\.json|\.gitlab-ci|\.github"
    r"|prestashop|mandrill|kafka|redis"
    r"|/id_rsa|authorized_keys|server\.key|ssl/"
    r"|/debug-trigger"
    r"|/_image|/__vite_rsc|/_fs/|@fs"
    r"|trust-admin-service"        # generic third-party path probe
    r"|/starter/|/jobs_u/"
    r")"
)

# ---------------------------------------------------------------------------
# Test-suite signatures (nightly suite traffic, ~09:01 UTC)
# ---------------------------------------------------------------------------
_TEST_410_MESSAGES = (
    "direct signup is disabled",
)
_TEST_422_PATHS = ("/api/trusts", "/api/minutes-templates")  # empty-name / empty-template_type 422 from fixture probing
_TEST_404_PATHS = (
    "/api/audit-trail",                      # old path; suite exercises both spellings
)
# "Trust not found" on these collection endpoints = fixture trust missing in
# prod (suite runs against live API; the QA fixture trust doesn't exist there).
_TEST_404_TRUST_NOT_FOUND_PATHS = (
    "/api/minutes",
    "/api/distributions",
    "/api/calendar/events",
    "/api/governance/",
)
_TEST_404_MESSAGES = (
    "trust not found",
)
# Known QA / nonexistent trust ids the suite and manual probes reference.
_KNOWN_DEAD_TRUST_IDS = (
    "6044a663dc5d",
    "f4321000dd26",
    "nonexistent",  # smoke suite's explicit nonexistent-id probe
    "trust_bc8af93378d2",  # deleted-trust probe traffic (2026-10-01 fixture churn)
    "trust_bf8f97c6151c",
)

# Rich-capture 422 fixture variants (2026-10-01): pydantic v2 now surfaces
# "<field>: Field required" instead of the bare field name.
_TEST_422_RICH_RE = re.compile(
    r"^(name|template_type|template_name)\s*:\s*Field required(?!\w)", re.IGNORECASE
)

# Client-validation 422 shapes (2026-10-01): bad USER-entered data correctly
# rejected. Not backend defects — capture keeps them queryable, the fixer
# never pages on them, and the real fix is frontend form guards.
_CLIENT_422_NOISE_RE = (
    re.compile(r"invalid_email|invalid_role|valid email address", re.IGNORECASE),
    # Anonymous credential probes (2026-10-03): bots POST empty JSON to
    # /api/auth/login — "email: Field required; password: Field required".
    # Field-required shapes from real app flows are form-guarded client-side
    # and carry richer pydantic details on app paths; a bare Field-required
    # 422 on an auth path is probe traffic (API answer correct).
    re.compile(r"^(email|password|username)\s*:\s*Field required", re.IGNORECASE),
    re.compile(r"Input should be '(viewer|preparer)'", re.IGNORECASE),
    re.compile(r"Input should be '(real_property|personal_property)'\]", re.IGNORECASE),
    re.compile(r"^Trust not found\. Please refresh", re.IGNORECASE),
)

# Negative-path probe ids in paths (2026-10-01): suites intentionally request
# obviously-missing resources; the literal slug names make them unambiguous.
_NEGATIVE_PROBE_ID_RE = re.compile(
    r"(nonexistent|does_no\w*|fake|removed|missing|bogus)", re.IGNORECASE
)

# Structured client-side 404 rejections (2026-10-01): the API's own handled
# "resource not available to you" answers, not missing backend routes.
_CLIENT_404_MESSAGES = (
    "invite not found",
    "member_not_in_org",
    "grant_not_found",
    "grant not found",
    "category: input should be",
)

# QA fixture trust/org ids exercised by test.qa1–qa3 sessions and isolation
# negative paths (2026-10-01 DB attribution), appended to the tuple above.
_KNOWN_DEAD_TRUST_IDS = _KNOWN_DEAD_TRUST_IDS + (
    "trust_4dc7fc7227a8",
    "trust_60d4c8577af3",
    "trust_be1335a726c3",
    "trust_a43430161d2b",
    "trust_140c1ac1e13d",
    "trust_121ad71a8f59",
    "trust_92af9e198a66",
    "trust_c72e3bac4b3a",
    "org_682d79d69043",
    "org_2eb093dbefe9",
    # 2026-10-01 712ca38 added three "qa fixture" ids here; reverted below:
    # trust_087db3afba55 is a LIVE client trust (I AM MINISTRIES, Ben Barlow,
    # verified in prod org listing + audit trail 22:25-22:31Z same day).
    # trust_ba6ecd1c99a4 / trust_65eff8784570: unverified against prod — the
    # failure mode of wrongly noise-tagging live-client errors (TO-F13
    # blindness) outweighs backlog hygiene. Add ids only after a prod-truth
    # check AND a pinned-suite case.
)

# ---------------------------------------------------------------------------
# Business-empty responses (documented empty answers, not defects)
# ---------------------------------------------------------------------------
_BUSINESS_EMPTY_PATHS = (
    "/api/external/lookup-user",             # {"found": false} — WingPoint provisioning
)


def classify(status_code: int, detail: object, path: str) -> Optional[str]:
    """Classify a 4xx rejection into a noise class, or None if it's real.

    Order matters: business-empty is checked before test-suite (a lookup-user
    404 is never test traffic), then test-suite, then scanner probes.

    Returns one of: "scanner", "api_root", "test_suite", "business_empty",
    "drift_probe", or None (= real error, full pipeline unchanged).
    """
    path_str = str(path or "")
    detail_str = str(detail or "")

    # --- API root pings: the API serves no root page ---
    if path_str == "/" or path_str == "":
        return "api_root"

    # --- Documented empty-result business responses ---
    if status_code == 404 and any(p in path_str for p in _BUSINESS_EMPTY_PATHS):
        return "business_empty"

    # --- Test-suite signatures ---
    if status_code == 410 and any(m in detail_str.lower() for m in _TEST_410_MESSAGES):
        return "test_suite"
    if status_code == 422:
        # Empty-field fixture probes ("name: ", "template_type: ") on the
        # suite's collection endpoints — the suite POSTs {} to assert 422.
        # A 422 with a REAL message (enum drift etc.) stays real.
        if detail_str.strip().rstrip(":").strip() in ("name", "template_type"):
            base_path = path_str.split("?")[0].rstrip("/")
            if any(base_path == p.rstrip("/") for p in _TEST_422_PATHS):
                return "test_suite"
        # Rich-capture variant (2026-10-01): FastAPI 422s now store the full
        # pydantic detail ("name: Field required", "template_type: Field
        # required", "template_name: Field required") — same fixture probes,
        # same endpoints, richer storage. Match the FIELD prefix.
        if _TEST_422_RICH_RE.match(detail_str.strip()):
            base_path = path_str.split("?")[0].rstrip("/")
            if any(base_path == p.rstrip("/") for p in _TEST_422_PATHS):
                return "test_suite"
        # Client validation noise (2026-10-01 sweep): user-entered bad data
        # that the API correctly rejects with 422 — email typos, enum picks,
        # duplicate-signup shapes. The API is WORKING when it returns these;
        # they log an error but are not backend defects. Frontend guards are
        # the real fix (tracked separately); until then they must not churn
        # the fixer queue 5-per-run.
        for pat in _CLIENT_422_NOISE_RE:
            if pat.search(detail_str):
                return "client_validation"
    # NOTE: 405 stays REAL by design (pinned by test_error_classifier):
    # /api/auth/session, /api/minutes-templates/generate etc. — a 405 on a
    # live route is exactly what client/API drift looks like (TO-F13 lived
    # 38 days). Blanket-noise-classifying them (4346bd6, 2026-10-01) broke
    # the drift detector; the anon-probe 405 backlog gets cleared by
    # batch-resolve instead, and any future bot filter must key on
    # request signatures captured at capture time, not status+path alone.
    if status_code == 404:
        if any(p.rstrip("/") == path_str.rstrip("/") for p in _TEST_404_PATHS):
            return "test_suite"
        msg_lower = detail_str.lower()
        # Explicit negative-path probes (any 404 message): the smoke/isolation
        # suites and manual API checks intentionally request ids named
        # nonexistent*/does_no*/fake*/removed* (verified 2026-10-01).
        if _NEGATIVE_PROBE_ID_RE.search(path_str):
            return "test_suite"
        if any(m in msg_lower for m in _TEST_404_MESSAGES):
            # Governance misses on documented dead QA trust ids (suite/fixture).
            if path_str.startswith("/api/governance/") and _known_dead_trust(path_str):
                return "test_suite"
            # Fixture-trust misses on known collection endpoints (suite runs
            # against live API; the QA fixture trust doesn't exist in prod).
            if any(path_str.split("?")[0].rstrip("/") == p.rstrip("/") for p in _TEST_404_TRUST_NOT_FOUND_PATHS):
                return "test_suite"
            # QA fixture ids anywhere in the path (2026-10-01): the qa1–qa3
            # sessions and isolation negative paths exercise these ids on any
            # trust endpoint, not just the ones enumerated above.
            if _known_dead_trust(path_str):
                return "test_suite"
        # Structured client-side rejections (2026-10-01 sweep): expired
        # invites, non-member access, missing grants/categories — the API's
        # own handled "not available to you" answers, not missing routes.
        if any(m in msg_lower for m in _CLIENT_404_MESSAGES):
            return "client_validation"
    if status_code == 0:
        # Server-side ValidationError docs (capture stores them without a
        # 4xx status; source:"server"): when their content is client-bad-data
        # (bad email, missing form fields on user-driven submits), the API
        # rejecting them is correct behavior (2026-10-01 sweep).
        m = detail_str.lower()
        if any(p.search(detail_str) for p in _CLIENT_422_NOISE_RE):
            return "client_validation"
        if any(k in m for k in ("field required", "value is not a valid email")):
            return "client_validation"
    # NOTE: no 422 catch-all (reverted 712ca38's): "field required"/
    # "Input should be" bundles are covered by the pinned _CLIENT_422_NOISE_RE
    # patterns above; a blanket catch would also silence REAL enum-drift 422s
    # — exactly the drift class TO-F13 sat on for 38 days.

    # --- Scanner probes (catch-all for credential/path sweeps) ---
    if status_code in (404, 400) and _SCANNER_RE.search(path_str):
        return "scanner"

    # --- Generic probe miss inside the API namespace (2026-09-21 sweep) ---
    # A bare "Not Found" 404 on an /api/* path is a tool probing routes that
    # don't exist (verified 2026-09-21: /api/vault, /api/admin/error-logs,
    # /api/env, /api/inngest... all bare 'Not Found', no UA, no session).
    # Every frontend fetch is ${API}/... or /api/...; app failures inside the
    # namespace carry real detail (enum drift, validation text, "Trust not
    # found"), so a generic miss with a generic message is not app traffic.
    # Outside /api (favicon.ico, /console, /mcp, /info, .env-style probes) the
    # API has nothing at all — any bare-404 hit is a probe.
    if (
        status_code == 404
        and detail_str.strip().lower() in ("not found", "no reply", "{}")
    ):
        base = path_str.split("?")[0]
        if base == "/api" or base.startswith("/api/"):
            return "scanner"
        if not base.startswith("/api"):
            return "scanner"

    return None


def _known_dead_trust(path_str: str) -> bool:
    return any(tid in path_str for tid in _KNOWN_DEAD_TRUST_IDS)


def classify_and_alert(status_code: int, detail: object, path: str) -> Tuple[Optional[str], bool]:
    """Return (noise_class, alert_flag) for a captured 4xx.

    alert_flag=False means: store it, never page. Real errors keep today's
    behavior (alert per existing drift heuristics).
    """
    nc = classify(status_code, detail, path)
    return (nc, nc is None)