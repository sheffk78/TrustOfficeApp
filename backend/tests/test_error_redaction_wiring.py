"""
WingPoint isolation: knowledge context must never ride an error out.

The chat system prompt embeds an injected knowledge slice. When a chat
handler crashes, report_error() carries error_message / traceback / extra
context into the Mongo error_logs store, the Discord embed, and the Hermes
webhook payload — surfaces gated by nobody's audience grant. So
report_error() redacts every knowledge-context section before anything is
stored or forwarded.

These tests use the canary string WP-ONLY-CANARY-9QF3 planted inside a
fake "## Knowledge Base" section: after report_error() has touched the
values, the canary must be gone everywhere, while non-knowledge content
(e.g. the traceback's raising line) stays byte-identical (negative control).

The Mongo store and the Discord/Hermes fanout are captured with
monkeypatched stand-ins — no network, no real Mongo.
"""
import asyncio
import importlib
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "scratch")

CANARY = "WP-ONLY-CANARY-9QF3"
REDACT_MARKER = "[KNOWLEDGE-CONTEXT REDACTED"


@pytest.fixture(autouse=True)
def _restore_alerting_module():
    """Mirror test_error_alerting_gate.py: the suite reloads error_alerting
    under test-env env vars; restore the ambient env + recompute per test so
    the module's alert-gate state can't poison other suites."""
    ambient = {k: os.environ.get(k) for k in ("ENVIRONMENT", "HERMES_WEBHOOK_URL")}
    yield
    for k, v in ambient.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import error_alerting
    importlib.reload(error_alerting)


def _knowledge_prompt_with_canary() -> str:
    """An assembled system prompt shaped like _build_system_prompt's output,
    with the canary inside the knowledge slice only."""
    return (
        "## Trust Constitution\n"
        "Normal rules content stays visible.\n"
        "\n"
        "## Knowledge Base\n"
        "### wp-doctrine-fiduciary\n"
        f"Secret doctrine text {CANARY} and more secret lines follow.\n"
        "Second paragraph of the WP-only slice.\n"
        "\n"
        "## Conversation History\n"
        "user: hello\n"
    )


def _reload_test_env(monkeypatch):
    """Reload error_alerting with alerting fully gated (test env): report_error
    must still build the redacted outbound pieces, which the captures below
    intercept."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("HERMES_WEBHOOK_URL", raising=False)
    import error_alerting
    importlib.reload(error_alerting)
    return error_alerting


@pytest.fixture
def captured(monkeypatch):
    """Capture every outbound surface of report_error with stand-ins."""
    import error_alerting
    mod = _reload_test_env(monkeypatch)

    captured_store = []
    captured_discord = []
    captured_hermes = []

    class _FakeResult:
        inserted_id = "fake"

        def __await__(self):
            return self

        def __iter__(self):
            return self

    async def fake_insert_one(doc):
        captured_store.append(doc)
        return _FakeResult()

    # Motor collections are re-created per attribute access, so patch the
    # module's db handle itself (report_error resolves `db` as a module global).
    class _FakeErrorLogs:
        insert_one = staticmethod(fake_insert_one)

    class _FakeDB:
        error_logs = _FakeErrorLogs()

    monkeypatch.setattr(mod, "db", _FakeDB())

    async def fake_notify_alert(**kwargs):
        captured_discord.append(kwargs)
        return True

    monkeypatch.setattr(mod, "notify_alert", fake_notify_alert)

    async def fake_trigger_hermes(payload):
        captured_hermes.append(payload)
        return False

    monkeypatch.setattr(mod, "_trigger_hermes_agent", fake_trigger_hermes)
    return {
        "mod": mod,
        "store": captured_store,
        "discord": captured_discord,
        "hermes": captured_hermes,
    }


def _report(captured, **kwargs):
    return asyncio.run(captured["mod"].report_error(source="server", **kwargs))


def test_store_and_alert_paths_redact_knowledge_from_message(captured):
    """error_message carrying the KB section: the canary must not appear in
    the Mongo error_logs document (and the same redacted string is what the
    Discord/Hermes paths receive)."""
    msg = _knowledge_prompt_with_canary()
    _report(
        captured,
        error_type="RunTimeError",
        error_message=msg,
        traceback_str="Traceback ... chat_service.py line 1 ... boom",
        extra_context={"knowledge": _knowledge_prompt_with_canary()},
        alert=True,
        severity="critical",
    )
    assert captured["store"], "error_logs doc was not captured"
    doc = captured["store"][0]
    assert CANARY not in json_dumps(doc), "canary leaked into error_logs"
    assert REDACT_MARKER in doc["error_message"], "knowledge section not redacted"

    # Non-knowledge content untouched
    assert "Normal rules content stays visible." in doc["error_message"]
    assert doc["stack_trace"] == "Traceback ... chat_service.py line 1 ... boom"


def test_traceback_carrying_knowledge_is_redacted(captured):
    # Real-world shape: the exception text embeds the assembled system prompt,
    # so the traceback carries the KB section between other ## headings.
    prompt = _knowledge_prompt_with_canary()
    tb = (
        "Traceback (most recent call last):\n"
        "  File \"chat_service.py\", line 99, in generate_response\n"
        f"{prompt}"
        "RuntimeError: boom\n"
    )
    _report(
        captured,
        error_type="RuntimeError",
        error_message="boom",
        traceback_str=tb,
        alert=True,
        severity="critical",
    )
    doc = captured["store"][0]
    assert CANARY not in (doc.get("stack_trace") or ""), "canary leaked via traceback"
    assert REDACT_MARKER in doc["stack_trace"]
    # The traceback head (file/line frame) and tail (exception line) survive
    assert "Traceback (most recent call last):" in doc["stack_trace"]
    assert "RuntimeError: boom" in doc["stack_trace"]


def test_extra_context_canary_redacted_plain_value_untouched(captured):
    plain = "plain context value"
    _report(
        captured,
        error_type="RuntimeError",
        error_message="boom",
        traceback_str=None,
        extra_context={
            "knowledge_block": _knowledge_prompt_with_canary(),
            "plain": plain,
        },
        alert=True,
        severity="critical",
    )
    doc = captured["store"][0]
    metadata = doc["metadata"]
    assert CANARY not in json_dumps(metadata), "canary leaked via extra_context"
    assert metadata["plain"] == plain, "non-knowledge extra_context was touched"


def test_non_knowledge_error_untouched_negative_control(captured):
    """Negative control: an ordinary error (no knowledge sections anywhere)
    passes through with message/traceback/context byte-identical."""
    msg = "trust not found for user u_1"
    tb = "Traceback (most recent call last):\n  File \"t.py\", line 3\nValueError: no trust\n"
    ctx = {"operation": "trust_lookup", "location": "/api/trusts"}
    res = _report(
        captured,
        error_type="ValueError",
        error_message=msg,
        traceback_str=tb,
        extra_context=dict(ctx),
        alert=True,
        severity="critical",
    )
    doc = captured["store"][0]
    assert doc["error_message"] == msg, "redaction touched a non-knowledge message"
    assert doc["stack_trace"] == tb, "redaction touched a non-knowledge traceback"
    # extra_context dict identity/shape survives; redaction is a no-op here
    assert doc["metadata"]["operation"] == ctx["operation"]
    assert doc["url"] == ctx["location"]  # location lifts to url by design
    assert res["alerted"] in (True, False)  # path completed


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, default=str)


def json_dumps(obj) -> str:
    return _json_dumps(obj)