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