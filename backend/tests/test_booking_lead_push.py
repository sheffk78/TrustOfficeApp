"""2026-09-09 directive: booking webhook contract for the per-brand booking app.

The booking app (booking-trustoffice) now pushes at BOOKING time
(booking_confirmed absent/False) and on email confirm (booking_confirmed=True).
Confirmed push must bump the lead score; booking-time push must create a
stage=booked lead without the bump.
"""
import sys
import types
import importlib.util
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# leads.py does `from routers.admin import require_admin`, which pulls the whole
# routers package (py3.10+ syntax in email_templates breaks on local py3.9).
# Stub the package + admin + email_service first; the deployed image (py3.11+)
# is unaffected — this is a local-runner workaround only.
_routers_pkg = types.ModuleType("routers")
_routers_pkg.__path__ = [str(BACKEND / "routers")]
_admin_stub = types.ModuleType("routers.admin")
_admin_stub.require_admin = lambda *a, **k: None
sys.modules["routers"] = _routers_pkg
sys.modules["routers.admin"] = _admin_stub

_email_svc_mod = types.ModuleType("email_service")
_email_svc_mod.email_service = types.SimpleNamespace(send_email=lambda *a, **k: None)
sys.modules["email_service"] = _email_svc_mod

_SPEC = importlib.util.spec_from_file_location(
    "leads_isolated",
    BACKEND / "routers" / "leads.py",
)
leads_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(leads_mod)
tidycal_webhook = leads_mod.tidycal_webhook


async def _noop(*a, **k):
    return None


def _fake_request(body):
    class _Req:
        async def json(self):
            return body

    return _Req()


def _booking_body(confirmed=False, email="booking.app@test.io", start="2026-10-05T16:00:00+00:00"):
    return {
        "event": "booked_call",
        "brand": "trustoffice",
        "email": email,
        "name": "Book App Test",
        "start": start,
        "event_type": "governance-consultation",
        "event_id": "bh-test-123",
        "booking_confirmed": confirmed,
        "phone": "8125551234",
        "notes": "irrevocable trust approvals",
    }


@pytest.mark.asyncio
async def test_booking_time_push_creates_booked_lead(monkeypatch):
    """Unconfirmed push → lead exists, stage=booked, NO score bump marker."""
    inserted = {}

    class _Leads:
        async def find_one(self, q):
            return None

        async def insert_one(self, doc):
            inserted["doc"] = doc

        def update_one(self, *a, **k):  # pragma: no cover
            raise AssertionError("no update expected on create path")

    class _Acts:
        async def insert_one(self, doc):
            inserted.setdefault("activities", []).append(doc)

    class _DB:
        leads = _Leads()
        lead_activities = _Acts()

    monkeypatch.setattr(leads_mod, "db", _DB())
    monkeypatch.setattr(leads_mod, "notify_new_lead", _noop)
    monkeypatch.setattr(leads_mod, "record_lead_capture", _noop)

    res = await tidycal_webhook(_fake_request(_booking_body(confirmed=False)))
    assert res["success"] is True
    doc = inserted["doc"]
    assert doc["stage"] == "booked"
    assert doc["booked_call"] is True
    assert doc["booking_confirmed"] is False
    assert doc["source"] == "booking-trustoffice-direct"
    assert doc["phone"] == "8125551234"
    assert doc["meeting_date"] == "2026-10-05T16:00:00+00:00"


@pytest.mark.asyncio
async def test_confirmed_push_bumps_existing_lead_score(monkeypatch):
    updates = {}

    class _Leads:
        async def find_one(self, q):
            return {"lead_id": "lead_existing", "email": q["email"], "score": 40}

        async def update_one(self, q, update):
            updates["q"], updates["set"] = q, update["$set"]

    class _Acts:
        async def insert_one(self, doc):
            updates.setdefault("activities", []).append(doc)

    class _DB:
        leads = _Leads()
        lead_activities = _Acts()

    monkeypatch.setattr(leads_mod, "db", _DB())
    monkeypatch.setattr(leads_mod, "notify_new_lead", _noop)
    monkeypatch.setattr(leads_mod, "record_lead_capture", _noop)

    res = await tidycal_webhook(_fake_request(_booking_body(confirmed=True)))
    assert res["success"] is True
    assert res["is_returning"] is True
    s = updates["set"]
    assert s["booking_confirmed"] is True
    assert s["booking_confirmed_at"]
    assert s["score"] == 55, "40 + 15 (same weight the scorer gives booked_call)"
    confirmed_logs = [a for a in updates["activities"] if "confirmed" in a.get("content", "")]
    assert confirmed_logs, "confirm must log the score bump as an activity"