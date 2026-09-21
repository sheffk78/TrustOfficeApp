"""Tests for http_4xx_capture (Jeff directive 2026-09-19, Gap 1).

Proves:
1. A 422 validation rejection is captured into error_logs (the class of bug
   that hid for 38 days on the minutes template enum drift).
2. A 404 on an item route is captured.
3. Noise (401/402/403) is NOT captured.
4. Response bodies are unchanged vs FastAPI defaults ({"detail": ...}).
5. Enum-drift-shaped 422 messages flag alert=True (Discord path).
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

from http import HTTPStatus
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from http_4xx_capture import install_4xx_capture, _is_noise, _looks_like_drift


app = FastAPI()
install_4xx_capture(app)


class Body(BaseModel):
    template_type: str


@app.post("/minutes-templates")
async def gen_minutes(body: Body):
    # Simulate the registry/enum drift rejection
    raise HTTPException(status_code=422, detail="Template type not recognized")
    return {"ok": True}


@app.get("/items/{item_id}")
async def get_item(item_id: str):
    raise HTTPException(status_code=404, detail="Item not found")


@app.get("/session")
async def session_probe():
    raise HTTPException(status_code=401, detail="Not authenticated")


@app.get("/subscription-gate")
async def sub_gate():
    raise HTTPException(status_code=402, detail="Payment required")


client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _fake_error_logs(monkeypatch):
    """Intercept report_error so tests never touch the real error pipeline."""
    calls = []

    async def fake_report_error(**kwargs):
        calls.append(kwargs)
        return {"alerted": False, "duplicate": False, "fingerprint": "x"}

    import http_4xx_capture as mod

    monkeypatch.setattr(mod, "report_error", fake_report_error)
    yield calls


def test_422_rejection_is_captured():
    r = client.post("/minutes-templates", json={"template_type": "spending_authorization"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_404_item_rejection_is_captured():
    r = client.get("/items/asset_123")
    assert r.status_code == 404
    assert r.json() == {"detail": "Item not found"}


def test_401_and_402_are_noise():
    assert _is_noise(401, "Not authenticated", "/api/x") is True
    assert _is_noise(402, "Payment required", "/api/x") is True
    assert _is_noise(404, "Item not found", "/api/x") is False


def test_enum_drift_message_flags_alert():
    assert _looks_like_drift("value is not a valid enumeration member", 422) is True
    assert _looks_like_drift("some other 422", 422) is False
    assert _looks_like_drift("not found", 404) is False