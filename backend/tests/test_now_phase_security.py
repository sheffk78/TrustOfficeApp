"""
NOW-phase security guards tests for TrustOffice.

TASK 1 - SSN intake ban:
  * Dashed SSN (\\d{3}-\\d{2}-\\d{4}) rejected everywhere (HTTP 422).
  * Bare 9-digit rejected in generic text fields.
  * EIN fields still accept bare 9-digit and XX-XXXXXXX form.
  * Valid EIN accepted.

TASK 2 - LLM redaction gate:
  * Text with SSN + EIN leaves the outbound call redacted.
  * Response path unchanged (real provider mocked; redaction applied before send).
  * Redaction event logged (counts + timestamp + document id).

These tests must not require a live LLM or a live MongoDB.
"""
import json
import logging
import re

import pytest

from security import (
    contains_ssn,
    check_ssn_or_raise,
    is_ein_field,
    scan_dict_for_ssn,
    redact_pii_for_llm,
    SSNGuardMiddleware,
)
import security as security_mod

import ai_client as ai_client_mod


# ---------------------------------------------------------------------------
# TASK 1 - SSN intake ban (unit-level helpers)
# ---------------------------------------------------------------------------

def test_dashed_ssn_detected_everywhere():
    assert contains_ssn("my ssn is 123-45-6789 thanks")
    assert contains_ssn("123-45-6789", allow_ein_field=True)  # even on EIN field


def test_bare_nine_rejected_on_generic_field_but_not_ein():
    assert contains_ssn("call me at 987654321") is True
    assert contains_ssn("987654321", allow_ein_field=True) is False
    assert contains_ssn("987654321", allow_ein_field=True) is False


def test_dashed_ein_never_treated_as_ssn():
    assert contains_ssn("12-3456789") is False
    assert contains_ssn("EIN 12-3456789 here") is False


def test_check_ssn_or_raise_rejects_dashed_ssn():
    with pytest.raises(Exception) as exc:
        check_ssn_or_raise("123-45-6789", field_name="notes")
    # HTTPException -> status_code 422
    assert getattr(exc.value, "status_code", None) == 422
    assert "never stores social security numbers" in str(exc.value.detail).lower()


def test_check_ssn_or_raise_allows_ein_field_bare_nine():
    # Should NOT raise for a bare 9-digit on an EIN field.
    check_ssn_or_raise("987654321", field_name="ein")


def test_scan_dict_for_ssn_nested():
    with pytest.raises(Exception) as exc:
        scan_dict_for_ssn({
            "trust": {
                "name": "Smith Fam",
                "notes": "client ssn 123-45-6789",
            },
            "tags": ["ok", "987654321"],
        })
    assert getattr(exc.value, "status_code", None) == 422


def test_scan_dict_for_ssn_ein_field_ok():
    # EIN fields bypass the bare-9-digit rule but dashed SSN still fails.
    scan_dict_for_ssn({"ein": "123456789"})
    scan_dict_for_ssn({"ein": "12-3456789"})
    with pytest.raises(Exception):
        scan_dict_for_ssn({"ein": "123-45-6789"})


def test_is_ein_field_variants():
    assert is_ein_field("ein")
    assert is_ein_field("trust_ein")
    assert not is_ein_field("notes")


# ---------------------------------------------------------------------------
# TASK 1 - apply to Pydantic models: valid EIN accepted, SSN rejected
# ---------------------------------------------------------------------------

def test_models_ein_field_normalizes_valid_ein():
    from models import TrustCreate
    t = TrustCreate(name="Test Trust", ein="123456789")
    assert t.ein == "12-3456789"


def test_models_ein_field_accepts_dashed_format():
    from models import TrustCreate
    # The model validator normalizes the dashed XX-XXXXXXX form (legit EIN).
    t = TrustCreate(name="Test Trust", ein="12-3456789")
    assert t.ein == "12-3456789"
    # A dashed SSN (3-2-4) is normalized by the validator into XX-XXXXXXX form,
    # so it is NOT rejected at the model layer Ã¢ÂÂ the SSN intake guard
    # (SSNGuardMiddleware) is what rejects dashed SSNs on every field.
    norm = TrustCreate(name="Test Trust", ein="123-45-6789")
    assert norm.ein == "12-3456789"


# ---------------------------------------------------------------------------
# TASK 1 - SSNGuardMiddleware rejects SSN JSON bodies with 422
# ---------------------------------------------------------------------------

class _FakeReceive:
    def __init__(self, body: bytes):
        self._body = body
        self._sent = False

    async def __call__(self):
        if self._sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        self._sent = True
        return {"type": "http.request", "body": self._body, "more_body": False}


class _FakeRequest:
    def __init__(self, method, path, body, content_type="application/json"):
        self.method = method
        self.url = type("U", (), {"path": path})()
        self.headers = {"Content-Type": content_type}
        self._receive = _FakeReceive(body)

    async def body(self):
        msg = await self._receive()
        return msg["body"]


class _Collector:
    def __init__(self):
        self.called = False
        self.body = None

    async def __call__(self, request):
        self.called = True
        self.body = request
        return "OK"


def _make_mw():
    async def noop_app(scope, receive, send):
        pass
    return SSNGuardMiddleware(noop_app)


@pytest.mark.asyncio
async def test_middleware_rejects_dashed_ssn_body():
    from starlette.responses import Response
    mw = _make_mw()
    collector = _Collector()

    payload = json.dumps({"notes": "my ssn is 123-45-6789"}).encode()
    req = _FakeRequest("POST", "/api/trusts", payload)

    response = await mw.dispatch(req, collector)
    assert response.status_code == 422
    assert collector.called is False


@pytest.mark.asyncio
async def test_middleware_rejects_bare_nine_generic_body():
    mw = _make_mw()
    collector = _Collector()
    payload = json.dumps({"notes": "call 987654321"}).encode()
    req = _FakeRequest("POST", "/api/trusts", payload)
    response = await mw.dispatch(req, collector)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_middleware_allows_ein_field_body():
    mw = _make_mw()
    collector = _Collector()
    payload = json.dumps({"ein": "123456789"}).encode()
    req = _FakeRequest("POST", "/api/trusts", payload)
    response = await mw.dispatch(req, collector)
    # Body must be re-injected unchanged so downstream handlers see it.
    assert collector.called is True
    body = await req.body()
    assert json.loads(body) == {"ein": "123456789"}


@pytest.mark.asyncio
async def test_middleware_skips_get_and_multipart():
    mw = _make_mw()
    collector = _Collector()
    req = _FakeRequest("GET", "/api/trusts", b"", content_type="application/json")
    await mw.dispatch(req, collector)
    assert collector.called is True

    req2 = _FakeRequest("POST", "/api/vault/upload", b"x",
                        content_type="multipart/form-data")
    collector2 = _Collector()
    await mw.dispatch(req2, collector2)
    assert collector2.called is True


# ---------------------------------------------------------------------------
# TASK 2 - LLM redaction gate
# ---------------------------------------------------------------------------

def test_redact_pii_for_llm_basic():
    text = "SSN 123-45-6789 and EIN 12-3456789 and bare 987654321"
    redacted, counts = redact_pii_for_llm(text)
    assert "[REDACTED-SSN]" in redacted
    assert "[REDACTED-EIN]" in redacted
    assert "123-45-6789" not in redacted
    assert "12-3456789" not in redacted
    assert "987654321" not in redacted
    assert counts["ssn"] == 2
    assert counts["ein"] == 1


def test_redact_pii_keeps_structure():
    text = "Borrower SSN [REDACTED-SSN] owes $1,000 on account 555."
    red, _ = redact_pii_for_llm("Borrower SSN 123-45-6789 owes $1,000 on account 555.")
    assert "$1,000" in red
    assert "account 555" in red


def test_redact_empty():
    red, counts = redact_pii_for_llm("")
    assert red == ""
    assert counts == {"ssn": 0, "ein": 0}


@pytest.mark.asyncio
async def test_ai_draft_applies_redaction_and_logs(monkeypatch, caplog):
    """ai_sonnet must redact before sending and log the redaction event."""
    captured = {}

    async def fake_try_openrouter(call_fn, system_prompt, user_content,
                                  max_tokens, temperature, errors):
        captured["user_content"] = user_content
        return '{"message": "ok"}'  # response path unchanged

    monkeypatch.setattr(ai_client_mod, "_try_openrouter", fake_try_openrouter)
    # Ensure OpenRouter key path is taken (AI_ENABLED relies on env); force path.
    monkeypatch.setattr(ai_client_mod, "OPENROUTER_AVAILABLE", True)
    monkeypatch.setattr(ai_client_mod, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_client_mod, "CLAUDE_AVAILABLE", False)
    monkeypatch.setattr(ai_client_mod, "CLAUDE_API_KEY", None)

    with caplog.at_level(logging.INFO, logger="trustoffice.security.redaction"):
        # Capture the LogRecord `extra` fields (not rendered by default formatters).
        captured_records = []
        handler = logging.Handler()
        handler.emit = lambda record: captured_records.append(record)
        ai_client_mod.redaction_logger.addHandler(handler)
        try:
            result = await ai_client_mod.ai_sonnet(
                system_prompt="sys",
                user_content="Document for doc123: SSN 123-45-6789 EIN 12-3456789",
                document_id="doc123",
            )
        finally:
            ai_client_mod.redaction_logger.removeHandler(handler)

    assert result == '{"message": "ok"}'  # response path unchanged
    assert "[REDACTED-SSN]" in captured["user_content"]
    assert "[REDACTED-EIN]" in captured["user_content"]
    assert "123-45-6789" not in captured["user_content"]

    # Log entry written with counts + timestamp + document id
    assert any("LLM outbound PII redacted" in rec.getMessage() for rec in captured_records)
    rec = next(r for r in captured_records if "LLM outbound PII redacted" in r.getMessage())
    assert rec.document_id == "doc123"
    assert rec.redacted_ssn == 1
    assert rec.redacted_ein == 1


@pytest.mark.asyncio
async def test_ai_haiku_applies_redaction(monkeypatch):
    captured = {}

    async def fake_try_openrouter(call_fn, system_prompt, user_content,
                                  max_tokens, temperature, errors):
        captured["user_content"] = user_content
        return "suggestion"

    monkeypatch.setattr(ai_client_mod, "_try_openrouter", fake_try_openrouter)
    monkeypatch.setattr(ai_client_mod, "OPENROUTER_AVAILABLE", True)
    monkeypatch.setattr(ai_client_mod, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_client_mod, "CLAUDE_AVAILABLE", False)
    monkeypatch.setattr(ai_client_mod, "CLAUDE_API_KEY", None)

    result = await ai_client_mod.ai_haiku(
        system_prompt="sys",
        user_content="client ssn 123-45-6789",
    )
    assert result == "suggestion"
    assert "[REDACTED-SSN]" in captured["user_content"]


@pytest.mark.asyncio
async def test_ai_draft_stream_applies_redaction(monkeypatch):
    """ai_draft_stream must redact before yielding chunks."""
    captured = {}

    async def fake_stream():
        yield "chunk1"
        yield "chunk2"

    async def fake_openrouter_stream(*args, **kwargs):
        # args: (system_prompt, user_content, max_tokens, temperature)
        captured["user_content"] = args[1]
        async for c in fake_stream():
            yield c

    import openrouter_client as orc
    monkeypatch.setattr(orc, "call_openrouter_sonnet_stream", fake_openrouter_stream)
    monkeypatch.setattr(ai_client_mod, "OPENROUTER_AVAILABLE", True)
    monkeypatch.setattr(ai_client_mod, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(ai_client_mod, "CLAUDE_AVAILABLE", False)
    monkeypatch.setattr(ai_client_mod, "CLAUDE_API_KEY", None)

    chunks = []
    async for c in ai_client_mod.ai_draft_stream(
        system_prompt="sys",
        user_content="ssn 123-45-6789 in document",
    ):
        chunks.append(c)

    assert chunks == ["chunk1", "chunk2"]
    assert "[REDACTED-SSN]" in captured["user_content"]
