"""Regression tests for the Call-now ping sanity gate (JOB-20261026-TO-RHONDA-FAKEPHONE).

Rhonda (2026-10-25) submitted the sequential 12345678910 and still fired a
Kenneth ping. notify_new_lead must downgrade calling-implausible numbers to a
non-pinging flagged card while keeping real numbers on the Call-now path.
"""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

import pytest  # noqa: E402

import discord_service  # noqa: E402


@pytest.fixture
def captured(monkeypatch):
    """Capture send_discord_message payload; fake the webhook as configured."""
    sent = {}

    async def fake_send(webhook_url, content, embeds=None, **kwargs):
        sent["content"] = content
        sent["embeds"] = embeds
        return {"success": True}

    monkeypatch.setattr(discord_service, "DISCORD_LEADS_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(discord_service, "send_discord_message", fake_send)
    return sent


KIRK = "+16124758285"          # real line (dialed 2026-10-23)
RHONDA_JUNK = "+12345678910"   # the submitted sequential value


@pytest.mark.asyncio
async def test_good_number_fires_call_now_ping(captured):
    await discord_service.notify_new_lead(
        name="Kirk", email="kirk@example.test", source="web-form",
        lead_stage="new", phone=KIRK, ping_on_phone=True)
    assert "Call now" in captured["content"]
    assert captured["content"].startswith("<@1479298864539373702>")


@pytest.mark.asyncio
async def test_junk_number_downgraded_no_ping(captured):
    await discord_service.notify_new_lead(
        name="Rhonda", email="rhonda@example.test", source="facebook-lead-ad",
        lead_stage="new", phone=RHONDA_JUNK, ping_on_phone=True)
    assert "failed sanity check" in captured["content"]
    assert "Call now" not in captured["content"]
    assert "<@1479298864539373702>" not in captured["content"]
    assert RHONDA_JUNK in captured["content"]  # number stays visible for verification


@pytest.mark.asyncio
async def test_no_phone_basics_path_intact(captured):
    await discord_service.notify_new_lead(
        name="NoPhone", email="np@example.test", source="web-form",
        lead_stage="new", phone=None, ping_on_phone=False)
    assert "New lead" in captured["content"]
    assert "failed sanity check" not in captured["content"]