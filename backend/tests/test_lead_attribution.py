"""
Lead attribution tests (2026-09-07).

Verifies the Lead -> Registered -> Subscriber funnel stamping:

1. A new account provisioned for an email that matches an existing lead stamps
   lead.user_id + lead.registered_at + lead.stage='registered' and logs a
   'registered' activity.
2. A subscription becoming active for a matching lead stamps lead.converted_at
   + lead.stage='converted' and logs a 'converted' activity.
3. No matching lead must never raise (signup must not break on miss).

The tests use a self-contained in-memory fake of the `db` object so they run
without a live MongoDB. `stamp_lead_registered` / `mark_lead_as_subscribed`
are imported from routers.leads and exercised directly against the fake DB.
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from database import db as real_db  # noqa: E402
import routers.leads as leads_router  # noqa: E402


class FakeCollection:
    """Minimal in-memory MongoDB collection substitute."""

    def __init__(self):
        self.docs = {}
        self._seq = 0

    def _next_id(self):
        self._seq += 1
        return f"act_{self._seq:012x}"

    async def find_one(self, query):
        # Support {"lead_id": ...}, {"email": ...}, {"user_id": ...},
        # and {"$or": [{"email": e}, {"user_id": u}]}.
        if "$or" in query:
            for sub in query["$or"]:
                doc = await self.find_one(sub)
                if doc:
                    return doc
            return None
        for doc in self.docs.values():
            match = all(doc.get(k) == v for k, v in query.items())
            if match:
                return dict(doc)
        return None

    async def insert_one(self, doc):
        if "lead_id" in doc:
            self.docs[doc["lead_id"]] = dict(doc)
        elif "activity_id" in doc:
            self.docs[doc["activity_id"]] = dict(doc)
        else:
            _id = self._next_id()
            self.docs[_id] = dict(doc)
        return MagicMock()

    async def update_one(self, query, update):
        doc = await self.find_one(query)
        if doc is None:
            return MagicMock()
        for k, v in update.get("$set", {}).items():
            doc[k] = v
        self.docs[doc.get("lead_id", doc.get("activity_id", "_"))] = dict(doc)
        return MagicMock()

    def to_list(self, _limit):
        return [dict(d) for d in self.docs.values()]


@pytest.fixture
def fake_db(monkeypatch):
    """Install an in-memory fake DB into both database and routers.leads."""
    db = MagicMock()
    db.leads = FakeCollection()
    db.lead_activities = FakeCollection()

    monkeypatch.setattr("database.db", db)
    monkeypatch.setattr(leads_router, "db", db)
    # notify_* / create_notification hit Discord + DB; stub to avoid side effects
    from unittest.mock import AsyncMock
    monkeypatch.setattr(leads_router, "notify_lead_stage_change",
                        AsyncMock())
    monkeypatch.setattr(leads_router, "create_notification",
                        AsyncMock())
    return db


def _seed_lead(db, email, user_id=None, stage="new"):
    lead_id = f"lead_{email.split('@')[0]}"
    db.leads.docs[lead_id] = {
        "lead_id": lead_id,
        "email": email,
        "name": "Test Lead",
        "stage": stage,
        **({"user_id": user_id} if user_id else {}),
    }
    return lead_id


def test_new_user_with_matching_lead_stamps_registered(fake_db):
    lead_id = _seed_lead(fake_db, "match@example.com")
    result = asyncio.run(
        leads_router.stamp_lead_registered(email="match@example.com",
                                           user_id="user_abc")
    )
    assert result is True
    lead = fake_db.leads.docs[lead_id]
    assert lead["user_id"] == "user_abc"
    assert lead["stage"] == "registered"
    assert lead["registered_at"] is not None
    acts = [a for a in fake_db.lead_activities.docs.values()
            if a["action_type"] == "registered"]
    assert acts, "expected a 'registered' activity to be logged"
    assert lead_id == acts[0]["lead_id"]


def test_subscription_active_stamps_converted(fake_db):
    lead_id = _seed_lead(fake_db, "conv@example.com", user_id="user_xyz")
    asyncio.run(
        leads_router.mark_lead_as_subscribed(email="conv@example.com",
                                            user_id="user_xyz")
    )
    lead = fake_db.leads.docs[lead_id]
    assert lead["stage"] == "converted"
    assert lead["converted_at"] is not None
    assert lead["subscription_status"] == "active"
    acts = [a for a in fake_db.lead_activities.docs.values()
            if a["action_type"] == "converted"]
    assert acts, "expected a 'converted' activity to be logged"


def test_no_matching_lead_does_not_crash(fake_db):
    # Neither function should raise when no lead exists.
    r1 = asyncio.run(
        leads_router.stamp_lead_registered(email="nobody@example.com",
                                           user_id="user_nope")
    )
    asyncio.run(
        leads_router.mark_lead_as_subscribed(email="nobody@example.com",
                                             user_id="user_nope")
    )
    assert r1 is False
    # No leads, no activities created.
    assert len(fake_db.lead_activities.docs) == 0


def test_empty_args_are_safe(fake_db):
    r1 = asyncio.run(leads_router.stamp_lead_registered(email="", user_id=""))
    assert r1 is False
