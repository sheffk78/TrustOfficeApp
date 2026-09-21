"""Tests for error_classifier (Jeff noise-reduction mandate, 2026-09-21).

Every real error that hit the queue on 2026-09-21 morning is represented here
as a test case, with its verified classification. Real errors (the classes we
must NEVER silence) are asserted to stay None.

Source data: mongo error_logs 2026-09-19..21 sweep (1,447 unresolved, all
path/UA/status verified against live DB).
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import pytest

from error_classifier import classify


# ---------------------------------------------------------------------------
# Scanner probes — verified: 100% return 404, sweep bursts 09-20/09-21 00:06
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/.env",
    "/.env.local",
    "/.env.production",
    "/staging/.env",
    "/wp/.env",
    "/@fs/.env",
    "/@fs/app/.env",
    "/@fs/src/.env",
    "/.git/config",
    "/.ssh/authorized_keys",
    "/.pypirc",
    "/.gradle/gradle.properties",
    "/phpinfo.php",
    "/pi.php",
    "/info.php",
    "/test.php",
    "/_ignition/health-check",
    "/_debugbar/open",
    "/_profiler/open",
    "/telescope/requests",
    "/wp-login.php",
    "/index.php",
    "/userfiles",
    "/userfiles/x",
    "/laravel/.env",
    "/graphql",
    "/v1/graphql",
    "/api/graphql",
    "/api/config",
    "/api/v1/config",
    "/api/v1/keys",
    "/api/v1/env",
    "/api/v2/settings",
    "/api/settings",
    "/api/account",
    "/api/health",
    "/actuator/loggers",
    "/debug/vars",
    "/server-status.php",
    "/read-document",
    "/firebase-adminsdk.json",
    "/sa.json",
    "/gcp-credentials.json",
    "/key.json",
    "/google-credentials.json",
    "/config.env",
    "/Dockerfile",
    "/swagger.json",
    "/serverless.yaml",
    "/.gitlab-ci.yml",
    "/id_rsa",
    "/proc/self/cgroup",
    "/api/w/admins/jobs_u/get_log_file/../../../../proc/self/environ",
    "/api/api/trust-admin-service/scheduling",
    "/api/console/api_server",
    "/api/designer/v1/file-content",
    "/api/v1/validate/code",
    "/z9x8c7v6b5-debug-trigger-api.trustoffice.app",
    "/__vite_rsc_findSourceMapURL",
    "/admin/.env",
    "/.env.bak",
    "/prestashop/.env",
    "/mandrill/.env",
    "/kafka/.env",
    "/redis/.env",
])
def test_scanner_probes_classified(path):
    assert classify(404, "Not Found", path) == "scanner"


# ---------------------------------------------------------------------------
# API root pings
# ---------------------------------------------------------------------------
def test_api_root_ping_classified():
    assert classify(404, "Not Found", "/") == "api_root"
    assert classify(404, "Not Found", "") == "api_root"


# ---------------------------------------------------------------------------
# Test-suite signatures (nightly suite, 09:01 UTC window, live API)
# ---------------------------------------------------------------------------
def test_register_410_is_test_suite():
    assert classify(
        410,
        "Direct signup is disabled. TrustOffice is subscribe-first — please "
        "choose a plan at /pricing to create your account.",
        "/api/auth/register",
    ) == "test_suite"


def test_empty_name_422_is_test_suite():
    # test_api_smoke.py test_missing_required_fields POSTs {} to /api/trusts
    assert classify(422, "name: ", "/api/trusts") == "test_suite"
    # request_validation_error variant carries "name: " message too
    assert classify(422, "name: ", "/api/trusts") == "test_suite"


def test_audit_trail_old_path_404_is_test_suite():
    # Suite exercises /api/audit-trail (old spelling); route is /api/audit-logs
    assert classify(404, "Not Found", "/api/audit-trail") == "test_suite"


def test_minutes_trust_not_found_404_is_test_suite():
    assert classify(
        404,
        "Trust not found. Please refresh the page or check your trust selection.",
        "/api/minutes",
    ) == "test_suite"
    assert classify(
        404,
        "Trust not found. Please refresh the page or check your trust selection.",
        "/api/distributions",
    ) == "test_suite"


def test_calendar_events_trust_not_found_is_test_suite():
    assert classify(404, "Trust not found", "/api/calendar/events") == "test_suite"


def test_governance_dead_qa_trust_404_is_test_suite():
    # Smoke-suite governance probes on fixture/dead trust ids
    assert classify(404, "Trust not found", "/api/governance/trust_f4321000dd26") == "test_suite"
    assert classify(404, "Trust not found", "/api/governance/trust_6044a663dc5d") == "test_suite"
    # Documented suite probe: explicit nonexistent id
    assert classify(404, "Trust not found", "/api/governance/nonexistent_trust_id") == "test_suite"


# ---------------------------------------------------------------------------
# Business-empty: documented empty answers, never defects
# ---------------------------------------------------------------------------
def test_lookup_user_found_false_is_business_empty():
    # WingPoint provisioning asks "does this email exist?" — {"found": false}
    # is the documented answer (routers/external.py:1621).
    assert classify(404, "{'found': False}", "/api/external/lookup-user") == "business_empty"


# ---------------------------------------------------------------------------
# REAL errors — these must NEVER be classified as noise
# ---------------------------------------------------------------------------
def test_enum_drift_422_stays_real():
    # The TO-F13 class of bug (minutes-template enum drift, live 38 days).
    # A 422 WITH a real message on /api/minutes-templates is REAL — only the
    # empty-template_type fixture probe (message "template_type: ") is suite.
    assert classify(422, "value is not a valid enumeration member", "/api/minutes-templates") is None


def test_bare_404_generic_miss_is_scanner():
    # POLICY (2026-09-21 sweep): a bare "Not Found" 404 with NO app detail is
    # indistinguishable from probe traffic — 1,377 of 1,449 backlog docs were
    # exactly this shape (no UA, no session, burst timing), and the frontend
    # never issues a fetch that surfaces as a bare-404 detail. Supersedes the
    # old "typo'd route stays real" stance for the BARE-detail case.
    assert classify(404, "Not Found", "/api/trusts-new-endpoint") == "scanner"


def test_404_with_real_detail_on_api_path_stays_real():
    # A 404 carrying a real app-level message is never a generic probe miss.
    assert classify(404, "Trust not found", "/api/trusts-new-endpoint") is None
    assert classify(404, "Entity not found: trust_abc123", "/api/trusts/xyz") is None


def test_400_real_validation_stays_real():
    assert classify(400, "Invalid trust state", "/api/trusts/abc/terminate") is None


def test_governance_real_miss_stays_real():
    # A real user's trust id 404ing is REAL — not suite traffic.
    assert classify(404, "Trust not found", "/api/governance/trust_abc123realid") is None


def test_minutes_405_method_stays_real():
    # 405 = wrong method on a real route — keep real (one-off manual probes
    # get resolved by hand; a recurring 405 means a client is misusing an API).
    assert classify(405, "Method Not Allowed", "/api/minutes/generate") is None


def test_frontend_real_error_paths_stay_real():
    assert classify(404, "Load failed", "/course") is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
def test_empty_string_path_is_root():
    assert classify(404, "Not Found", "") == "api_root"


def test_none_detail_with_scanner_path():
    assert classify(404, None, "/.env") == "scanner"


def test_case_insensitive_scanner():
    assert classify(404, "Not Found", "/.ENV") == "scanner"
    assert classify(404, "Not Found", "/PHPINFO.php") == "scanner"


# ---------------------------------------------------------------------------
# 2026-09-21 sweep additions — generic probe misses (post-review wordlist)
# Bare "Not Found" 404s with no app detail are probe tools, not app traffic.
# Verified live 2026-09-21: no UA, no session, burst timing; the frontend
# never issues a fetch that surfaces as a bare-404 detail. 1,377 of the
# 1,449 backlog docs were exactly this shape.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status,message,path", [
    ("404", "Not Found", "/api/vault"),
    ("404", "Not Found", "/api/admin/error-logs"),
    ("404", "Not Found", "/api/env"),
    ("404", "Not Found", "/api/inngest"),
    ("404", "Not Found", "/api/fs/exec"),
    ("404", "Not Found", "/api/sysConfig/getAll"),
    ("404", "Not Found", "/api/v1/models"),
    ("404", "Not Found", "/api/openapi.json"),
    ("404", "Not Found", "/favicon.ico"),
    ("404", "Not Found", "/console"),
    ("404", "Not Found", "/mcp"),
    ("404", "Not Found", "/info"),
    ("404", "Not Found", "/inngest"),
    ("404", "Not Found", "/metrics"),
    ("404", "Not Found", "/functionRouter"),
    ("404", "Not Found", "/.bash_profile"),
    ("404", "Not Found", "/.zshrc"),
    ("404", "Not Found", "/.profile"),
    ("404", "Not Found", "/.npmrc"),
    ("404", "Not Found", "/.htpasswd"),
    ("404", "Not Found", "/.s3cfg"),
    ("404", "Not Found", "/.boto"),
    ("404", "Not Found", "/.dockerenv"),
    ("404", "Not Found", "/.vscode/launch.json"),
    ("404", "Not Found", "/.idea/WebServers.xml"),
    ("404", "Not Found", "/config/runtime.exs"),
    ("404", "Not Found", "/config.toml"),
    ("404", "Not Found", "/config.yaml"),
    ("404", "Not Found", "/config.py"),
    ("404", "Not Found", "/config.json"),
    ("404", "Not Found", "/config.js"),
    ("404", "Not Found", "/env.js"),
    ("404", "Not Found", "/env.json"),
    ("404", "Not Found", "/settings.json"),
    ("404", "Not Found", "/settings.py"),
    ("404", "Not Found", "/appsettings.json"),
    ("404", "Not Found", "/application.properties"),
    ("404", "Not Found", "/application.yml"),
    ("404", "Not Found", "/docker-compose.yml"),
    ("404", "Not Found", "/serverless.yml"),
    ("404", "Not Found", "/terraform.tfstate"),
    ("404", "Not Found", "/.aws/config"),
    ("404", "Not Found", "/.well-known/jwks.json"),
    ("404", "Not Found", "/google-services.json"),
    ("404", "Not Found", "/firebase.json"),
    ("404", "Not Found", "/firebase-config.json"),
    ("404", "Not Found", "/amplifyconfiguration.json"),
    ("404", "Not Found", "/aws-exports.js"),
    ("404", "Not Found", "/awsconfiguration.json"),
    ("404", "Not Found", "/rclone.conf"),
    ("404", "Not Found", "/id_ed25519"),
    ("404", "Not Found", "/id_ecdsa"),
    ("404", "Not Found", "/id_dsa"),
    ("404", "Not Found", "/key.pem"),
    ("404", "Not Found", "/privatekey.key"),
    ("404", "Not Found", "/host.key"),
    ("404", "Not Found", "/localhost.key"),
    ("404", "Not Found", "/auth.json"),
    ("404", "Not Found", "/local.settings.json"),
    ("404", "Not Found", "/web.config"),
    ("404", "Not Found", "/nginx_status"),
    ("404", "Not Found", "/server-info"),
    ("404", "Not Found", "/trace.axd"),
    ("404", "Not Found", "/elmah.axd"),
    ("404", "Not Found", "/debug/pprof"),
    ("404", "Not Found", "/debug/pprof/cmdline"),
    ("404", "Not Found", "/__debug__"),
    ("404", "Not Found", "/__debugger__"),
    ("404", "Not Found", "/manage/env"),
    ("404", "Not Found", "/v1/onboarding/config"),
    ("404", "Not Found", "/horizon/api/stats"),
    ("404", "Not Found", "/private-key"),
    ("404", "Not Found", "/service-worker.js"),
    ("404", "Not Found", "/sw.js"),
    ("404", "Not Found", "/ngsw.json"),
    ("404", "Not Found", "/manifest.webmanifest"),
    ("404", "Not Found", "/runtime-config.js"),
    ("404", "Not Found", "/runtime.js"),
    ("404", "Not Found", "/configuration.js"),
    ("404", "Not Found", "/constants.js"),
    ("404", "Not Found", "/app-config.json"),
    ("404", "Not Found", "/firebase-config.json"),
    ("404", "Not Found", "/push_config.json"),
    ("404", "Not Found", "/__env.js"),
    ("404", "Not Found", "/_environment"),
    ("404", "Not Found", "/public/env.js"),
    ("404", "Not Found", "/public/admin.json"),
    ("404", "Not Found", "/public/env.js"),
    ("404", "Not Found", "/awsConfig.js"),
    ("404", "Not Found", "/aws-config.js"),
    ("404", "Not Found", "/gcp-service.json"),
    ("404", "Not Found", "/gc-service.json"),
    ("404", "Not Found", "/gcp-service.json"),
    ("404", "Not Found", "/keyfile.json"),
    ("404", "Not Found", "/host.key"),
    ("404", "Not Found", "/_payload.json"),
    ("404", "Not Found", "/account/_payload.json"),
    ("404", "Not Found", "/settings/_payload.json"),
    ("404", "Not Found", "/dashboard/_payload.json"),
    ("404", "Not Found", "/pages/index.astro.mjs.map"),
    ("404", "Not Found", "/_astro/pages/index.astro.mjs.map"),
    ("404", "Not Found", "/pages/api/index.astro.mjs.map"),
    ("404", "Not Found", "/icecoder/lib/terminal-xhr.php"),
    ("404", "Not Found", "/lib/terminal-xhr.php"),
    ("404", "Not Found", "/document.php"),
    ("404", "Not Found", "/debug.php"),
    ("404", "Not Found", "/p.php"),
    ("404", "Not Found", "/pinfo.php"),
    ("404", "Not Found", "/php.php"),
    ("404", "Not Found", "/phpversion.php"),
    ("404", "Not Found", "/app_dev.php"),
    ("404", "Not Found", "/values.yaml"),
    ("404", "Not Found", "/bootstrap.yml"),
    ("404", "Not Found", "/bootstrap.properties"),
    ("404", "Not Found", "/gradle.properties"),
    ("404", "Not Found", "/.htpasswd"),
])
def test_generic_probe_misses_are_scanner(status, message, path):
    assert classify(int(status), message, path) == "scanner"


def test_405_on_live_endpoints_stays_real():
    # 405 = a client called a LIVE route with the wrong method. Probe tools do
    # this (verified /api/auth/session), but it's also exactly what client/API
    # drift looks like — kept real by design (drift is the bug class TO-F13
    # lived for 38 days).
    assert classify(405, "Method Not Allowed", "/api/auth/session") is None
    assert classify(405, "Method Not Allowed", "/api/minutes-templates/generate") is None


def test_genuine_frontend_error_never_classified():
    # The one real error in the 1,449 sweep (frontend load_trusts, /course,
    # iPad CriOS UA). Never silence this shape.
    assert classify(0, "Load failed", "/course") is None