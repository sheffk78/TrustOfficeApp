"""Test-env alert gate (error_alerting._IS_TEST_ENV) — regression coverage.

Background (2026-10-18): local pytest runs fired real test-debt errors at the
Hermes webhook, which paged Discord for issues already tracked in the repo.
Gate semantics: when ENVIRONMENT=test|testing|ci (or HERMES_WEBHOOK_URL=""),
report_error() still LOGS and STORES the error in error_logs (nothing lost)
but sends NO webhook and NO Discord fanout. Prod (Railway) never sets these,
so the gate is off there.
"""
import importlib
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def _restore_alerting_module():
    """Reload error_alerting with the ambient env after every test. The suite
    reloads the module under monkeypatched env vars, which leaves the module's
    alert-gate state (e.g. _IS_TEST_ENV=True) poisoned for later suites running
    in the same pytest process — restore the ambient env + recompute per test."""
    ambient = {k: os.environ.get(k) for k in ("ENVIRONMENT", "HERMES_WEBHOOK_URL")}
    yield
    for k, v in ambient.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import error_alerting
    importlib.reload(error_alerting)


def _reload_with_env(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import error_alerting
    importlib.reload(error_alerting)
    return error_alerting


def test_default_is_alerting_on(monkeypatch):
    for var in ("ENVIRONMENT", "HERMES_WEBHOOK_URL"):
        monkeypatch.delenv(var, raising=False)
    mod = _reload_with_env(monkeypatch)
    assert mod._IS_TEST_ENV is False


def test_environment_test_gates(monkeypatch):
    mod = _reload_with_env(monkeypatch, ENVIRONMENT="test")
    assert mod._IS_TEST_ENV is True


def test_ci_and_testing_variants_gate(monkeypatch):
    for val in ("ci", "testing", "CI"):
        mod = _reload_with_env(monkeypatch, ENVIRONMENT=val)
        assert mod._IS_TEST_ENV is True, val


def test_empty_webhook_url_gates(monkeypatch):
    mod = _reload_with_env(monkeypatch, HERMES_WEBHOOK_URL="")
    assert mod._IS_TEST_ENV is True


def test_prod_environment_stays_on(monkeypatch):
    mod = _reload_with_env(monkeypatch, ENVIRONMENT="production")
    assert mod._IS_TEST_ENV is False


@pytest.mark.asyncio
async def test_report_error_test_env_no_fanout(monkeypatch):
    """In a test env: error still logged + stored, but no webhook/Discord send."""
    mod = _reload_with_env(monkeypatch, ENVIRONMENT="test")

    called = {"notify": 0, "hermes": 0}

    async def _no_notify(**kwargs):
        called["notify"] += 1
        return True

    async def _no_hermes(payload):
        called["hermes"] += 1
        return True

    monkeypatch.setattr(mod, "notify_alert", _no_notify)
    monkeypatch.setattr(mod, "_trigger_hermes_agent", _no_hermes)

    result = await mod.report_error(
        source="server",
        error_type="TestEnvProbe",
        error_message="gate unit probe — not a real failure",
        alert=True,
    )
    assert result["test_env_suppressed"] is True
    assert result["alerted"] is False
    assert called["notify"] == 0 and called["hermes"] == 0


@pytest.mark.asyncio
async def test_local_dev_traceback_never_pages(monkeypatch):
    """Local dev-server errors (workstation paths in the traceback) must log +
    store but NEVER page agents/Discord (2026-10-18: one local bridge dev
    error paged six agent sessions while production was healthy)."""
    mod = _reload_with_env(monkeypatch)  # prod-like: alerting ON

    called = {"notify": 0, "hermes": 0}

    async def _no_notify(**kwargs):
        called["notify"] += 1
        return True

    async def _no_hermes(payload):
        called["hermes"] += 1
        return True

    monkeypatch.setattr(mod, "notify_alert", _no_notify)
    monkeypatch.setattr(mod, "_trigger_hermes_agent", _no_hermes)

    local_tb = (
        "Traceback (most recent call last):\n"
        '  File "/Users/socializerender/.openclaw/workspace/TrustOfficeApp/backend/routers/x.py", line 1\n'
        '  File "/opt/homebrew/Cellar/python@3.14/3.14.7/.../asyncio/runners.py", line 205\n'
        "RuntimeError: Event loop is closed"
    )
    result = await mod.report_error(
        source="server",
        error_type="RuntimeError",
        error_message="Event loop is closed",
        traceback_str=local_tb,
        request_path="/api/bridge/admin/tokens",
        alert=True,
    )
    assert result.get("local_dev_traceback") is True
    assert result["alerted"] is False
    assert called["notify"] == 0 and called["hermes"] == 0


@pytest.mark.asyncio
async def test_container_traceback_still_pages(monkeypatch):
    """Deployed-container tracebacks (/app/...) keep normal alerting — the
    local-dev gate must not swallow real production incidents."""
    mod = _reload_with_env(monkeypatch)

    called = {"notify": 0, "hermes": 0}

    async def _no_notify(**kwargs):
        called["notify"] += 1
        return True

    async def _yes_hermes(payload):
        called["hermes"] += 1
        return True

    monkeypatch.setattr(mod, "notify_alert", _no_notify)
    monkeypatch.setattr(mod, "_trigger_hermes_agent", _yes_hermes)

    container_tb = (
        "Traceback (most recent call last):\n"
        '  File "/app/backend/routers/x.py", line 1, in handler\n'
        "TypeError: 'NoneType' object is not subscriptable"
    )
    result = await mod.report_error(
        source="server",
        error_type="TypeError",
        error_message="real prod failure shape",
        traceback_str=container_tb,
        request_path="/api/trusts",
        alert=True,
    )
    assert result.get("local_dev_traceback", False) is False
    assert result.get("hermes_triggered") is True
    assert called["hermes"] == 1


def test_local_dev_detector_path_prefixes(monkeypatch):
    tb_users = 'File "/Users/jeff/project/app.py", line 1'
    tb_linux = 'File "/home/dev/project/app.py", line 1'
    tb_win = 'File "C:\\Users\\dev\\project\\app.py", line 1'
    tb_container = 'File "/app/backend/app.py", line 1'
    tb_rel = 'File "app.py", line 1'
    mod = _reload_with_env(monkeypatch)
    assert mod._is_local_dev_traceback(tb_users) is True
    assert mod._is_local_dev_traceback(tb_linux) is True
    assert mod._is_local_dev_traceback(tb_win) is True
    assert mod._is_local_dev_traceback(tb_container) is False
    assert mod._is_local_dev_traceback(tb_rel) is False
    assert mod._is_local_dev_traceback("") is False