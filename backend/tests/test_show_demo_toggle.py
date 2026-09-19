"""Show-demo-trusts toggle tests (TO-F14 fix, 2026-09-19).

Pure in-process (FakeDB per suite convention — no real MongoDB, no motor loop
contention). Patches routers.trusts.db and routers.preferences.db with the
fake and drives get_trusts / update_user_preferences directly via asyncio.run.

Covers:
  1. Demo-only account: demo trusts always visible (unchanged legacy behavior).
  2. Real + demo, toggle OFF (default): demo trusts hidden — the Sept 4
     privacy fix stays the default.
  3. Real + demo, toggle ON: demo trusts appended AFTER the real trusts.
  4. Preference PUT accepts show_demo_trusts and persists it.
  5. Preference GET backfills show_demo_trusts=False for legacy docs.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

import pytest

import dependencies
import routers.preferences as preferences
import routers.trusts as trusts
from models import UserPreferencesUpdate


class _FakeCollection:
    """Minimal async mongo-collection double: find/insert_one/find_one."""

    def __init__(self):
        self.documents = []

    def _matches(self, doc, query):
        for key, cond in query.items():
            if isinstance(cond, dict):
                if "$in" in cond and doc.get(key) not in cond["$in"]:
                    return False
                if "$ne" in cond and doc.get(key) == cond["$ne"]:
                    return False
            elif doc.get(key) != cond:
                return False
        return True

    def find(self, query, projection=None):
        docs = [dict(d) for d in self.documents if self._matches(d, query)]
        if projection and "_id" in projection and projection["_id"] == 0:
            docs = [{k: v for k, v in d.items() if k != "_id"} for d in docs]
        return _FakeCursor(docs)

    def find_one(self, query, projection=None):
        result = self._find_one_sync(query, projection)

        async def _awaitable():
            return result
        return _awaitable()

    def _find_one_sync(self, query, projection=None):
        for d in self.documents:
            if self._matches(d, query):
                doc = dict(d)
                if projection and "_id" in projection and projection["_id"] == 0:
                    doc = {k: v for k, v in doc.items() if k != "_id"}
                return doc
        return None

    async def insert_one(self, doc):
        self.documents.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.documents:
            if self._matches(d, query):
                d.update(update.get("$set", {}))
                return
        if upsert:
            self.documents.append(dict(update.get("$set", {}), **query))

    def delete_many(self, query):
        self.documents = [d for d in self.documents if not self._matches(d, query)]


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length):
        return self._docs[:length]


class _CopyResult:
    def __init__(self, doc):
        self._doc = doc

    def get(self, key, default=None):
        return (self._doc or {}).get(key, default)

    def __bool__(self):
        return self._doc is not None


class _FakeDB:
    def __init__(self):
        self.trusts = _FakeCollection()
        self.user_preferences = _FakeCollection()


USER = {"user_id": "u_toggle", "email": "u_toggle@test.local", "name": "T"}


def _trust(tid, demo):
    return {"trust_id": tid, "user_id": "u_toggle", "name": tid.upper(),
            "is_demo": demo, "trustees": [], "created_at": "2026-01-01T00:00:00+00:00"}


def _seed(fake_db, tid, demo):
    # FakeDB's insert_one is async; seed synchronously for test brevity.
    fake_db.trusts.documents.append(_trust(tid, demo))


@pytest.fixture
def fake_db():
    db = _FakeDB()
    old_trusts, old_prefs = trusts.db, preferences.db
    trusts.db = db
    preferences.db = db
    # calculate_health_score hits MongoDB deep inside; return a fixed score.
    async def _fixed_score(trust_id, user_id, save_snapshot=False):
        return {"total_score": 75}
    old_score = dependencies.calculate_health_score
    trusts.calculate_health_score = _fixed_score
    yield db
    trusts.db, preferences.db = old_trusts, old_prefs
    trusts.calculate_health_score = old_score


def test_demo_only_account_still_sees_demo_trusts(fake_db):
    _seed(fake_db, "t_demo_only", True)
    result = asyncio.run(trusts.get_trusts(USER))
    assert [t.trust_id for t in result] == ["t_demo_only"]


def test_real_plus_demo_toggle_off_hides_demo(fake_db):
    _seed(fake_db, "t_real_1", False)
    _seed(fake_db, "t_demo_1", True)
    result = asyncio.run(trusts.get_trusts(USER))  # no preference doc → OFF
    assert [t.trust_id for t in result] == ["t_real_1"]


def test_real_plus_demo_toggle_on_shows_demo_last(fake_db):
    _seed(fake_db, "t_real_1", False)
    _seed(fake_db, "t_demo_1", True)
    fake_db.user_preferences.documents.append({"user_id": "u_toggle", "show_demo_trusts": True})
    result = asyncio.run(trusts.get_trusts(USER))
    assert [t.trust_id for t in result] == ["t_real_1", "t_demo_1"]


def test_preferences_put_persists_show_demo_trusts(fake_db):
    resp = asyncio.run(preferences.update_user_preferences(
        UserPreferencesUpdate(show_demo_trusts=True), USER))
    saved = fake_db.user_preferences.documents[-1]
    assert saved.get("show_demo_trusts") is True
    assert "preferences" in resp


def test_preferences_get_backfills_false_for_legacy_docs(fake_db):
    fake_db.user_preferences.documents.append({"user_id": "u_toggle", "hide_watermark": True})
    resp = asyncio.run(preferences.get_user_preferences(USER))
    assert resp.get("show_demo_trusts") is False