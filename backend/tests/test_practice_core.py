"""
Tests for the always-on Trust Practice Core (P1, 2026-10-23).

Four guarantees are locked down here:

  (a) ALWAYS-ON — the practice core is present in the assembled system prompt
      for BOTH a knowledge intent (ask_knowledge) and an action intent
      (log_minutes). It must not be gated on ACTION_INTENTS: a member asking
      "what are my duties as trustee?" needs the fiduciary frame exactly as
      much as one asking for a minutes card.

  (b) STATE DATA PASSTHROUGH — build_trust_context() populates
      ctx["state_compliance"] with the trust's state's compliance profile
      facts (utc_adopted / accounting_frequency / notice_required), so the
      jurisdiction guard has data to read instead of guessing.

  (c) BUDGET GUARD — the total system prompt token estimate stays under the
      13K-token-with-core ceiling for both intents.

  (d) BLOCK STRUCTURE — the practice file parses into its 4 blocks, so a
      future edit that breaks a header cannot silently ship.

The practice file's PROSE is deliberately kept out of the assertions: only
header structure and presence are checked. A copy edit must not fail a test.

These are true unit tests: mongomock-backed, no live server, no LLM, no
network.
"""
import os
import re
import sys
import math
import asyncio

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_practice_core")
os.environ.setdefault("JWT_SECRET", "test-secret-for-practice-core")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")
os.environ.setdefault("MAILERCLOUD_API_KEY", "")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "")
os.environ.setdefault("POSTMARK_SERVER_TOKEN", "")
os.environ.setdefault("TIDYCAL_API_TOKEN", "")

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --------------------------------------------------------------------------- #
# Async mongomock shim (motor-style API over sync mongomock)
# --------------------------------------------------------------------------- #
class _AsyncCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._cursor)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        items = list(self._cursor)
        return items if length is None else items[:length]

    def sort(self, *args, **kwargs):
        self._cursor = self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self._cursor = self._cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self._cursor = self._cursor.limit(*args, **kwargs)
        return self


class _AsyncCollection:
    def __init__(self, coll):
        self._c = coll

    async def find_one(self, *args, **kwargs):
        return self._c.find_one(*args, **kwargs)

    def find(self, *args, **kwargs):
        return _AsyncCursor(self._c.find(*args, **kwargs))

    def aggregate(self, *args, **kwargs):
        return _AsyncCursor(self._c.aggregate(*args, **kwargs))

    async def insert_one(self, doc):
        return self._c.insert_one(doc)

    async def insert_many(self, docs):
        return self._c.insert_many(docs)

    async def update_one(self, *args, **kwargs):
        return self._c.update_one(*args, **kwargs)

    async def update_many(self, *args, **kwargs):
        return self._c.update_many(*args, **kwargs)

    async def delete_one(self, *args, **kwargs):
        return self._c.delete_one(*args, **kwargs)

    async def delete_many(self, *args, **kwargs):
        return self._c.delete_many(*args, **kwargs)

    async def count_documents(self, *args, **kwargs):
        return self._c.count_documents(*args, **kwargs)

    async def find_one_and_update(self, *args, **kwargs):
        return self._c.find_one_and_update(*args, **kwargs)

    async def distinct(self, *args, **kwargs):
        return self._c.distinct(*args, **kwargs)

    def create_index(self, *args, **kwargs):
        return self._c.create_index(*args, **kwargs)


class _AsyncDatabase:
    def __init__(self, db):
        self._db = db

    def __getitem__(self, name):
        return _AsyncCollection(self._db[name])

    def __getattr__(self, name):
        return _AsyncCollection(self._db[name])

    def get_collection(self, name):
        return _AsyncCollection(self._db[name])

    async def list_collection_names(self):
        return self._db.list_collection_names()


class _AsyncMongoClient:
    def __init__(self, client):
        self._c = client

    def __getitem__(self, name):
        return _AsyncDatabase(self._c[name])

    def __getattr__(self, name):
        return getattr(self._c, name)

    def close(self):
        return self._c.close()


@pytest.fixture(scope="module", autouse=True)
def _patch_motor():
    """Patch motor's client factory so the app sees an in-memory mongomock."""
    import mongomock
    from unittest.mock import patch

    client = mongomock.MongoClient()

    class _FakeAsyncIOMotorClient:
        def __init__(self, *args, **kwargs):
            self._client = client

        def __getitem__(self, name):
            return _AsyncDatabase(client[name])

        def __getattr__(self, name):
            return getattr(client, name)

    with patch("motor.motor_asyncio.AsyncIOMotorClient", _FakeAsyncIOMotorClient):
        yield client


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
USER_ID = "user_practicecore_test"
TRUST_ID = "trust_practicecore_test"

# A state profile that is NOT full adoption, so the guard has a reason to
# speak conditionally. Mirrors the shape in routers/state_compliance.py.
CA_PROFILE = {
    "_id": "CA",
    "state_code": "CA",
    "state_name": "California",
    "utc_adopted": "no",
    "notice_required": True,
    "notice_timing_days": 60,
    "accounting_frequency": "annual",
    "trustee_removal_standard": "breach of trust",
    "spendthrift_default": True,
}

UT_PROFILE = {
    "_id": "UT",
    "state_code": "UT",
    "state_name": "Utah",
    "utc_adopted": "full",
    "notice_required": True,
    "notice_timing_days": 60,
    "accounting_frequency": "annual",
    "trustee_removal_standard": "breach of trust",
    "spendthrift_default": True,
}


@pytest.fixture
def seeded(_patch_motor):
    """Seeded in-memory DB: a user, a CA trust, a UT trust, and state profiles.

    The app's db handle is REBOUND to this seeded database rather than relying
    on the DB_NAME env var. database.py binds `db` at import time
    (`db = client[os.environ["DB_NAME"]]`), so whichever test module is
    collected first wins the DB_NAME race — a suite that trusts the env var
    passes alone and fails in the full run. Rebinding makes this file
    order-independent. The original handle is restored on teardown so later
    modules are unaffected.
    """
    client = _patch_motor
    client.drop_database("test_practice_core")
    raw = client["test_practice_core"]

    raw.users.insert_one({
        "_id": "u1", "user_id": USER_ID, "email": "practicecore@example.test",
        "name": "Practice Core Tester", "is_admin": False,
    })
    raw.trusts.insert_one({
        "_id": "t1", "trust_id": TRUST_ID, "user_id": USER_ID,
        "name": "Practice Core Test Trust", "trust_type": "revocable",
        "jurisdiction": "California", "state_code": "CA",
        "trustees": "Practice Core Tester", "status": "active",
    })
    raw.trusts.insert_one({
        "_id": "t2", "trust_id": "trust_practicecore_ut", "user_id": USER_ID,
        "name": "Practice Core UT Trust", "trust_type": "revocable",
        "jurisdiction": "Utah", "state_code": "UT",
        "trustees": "Practice Core Tester", "status": "active",
    })
    raw.state_compliance_profiles.insert_one(dict(CA_PROFILE))
    raw.state_compliance_profiles.insert_one(dict(UT_PROFILE))
    raw.health_score_snapshots.insert_one({
        "_id": "h1", "trust_id": TRUST_ID, "user_id": USER_ID,
        "score_value": 78, "color": "green", "base_score": 78, "risk_penalty": 0,
        "calculated_at": "2026-10-23T00:00:00+00:00",
    })

    # Rebind the app's db handle to THIS seeded database, and restore the
    # previous handle on teardown. See the docstring above for why the
    # DB_NAME env var cannot be relied on.
    import chat_service as cs
    import database as database_module

    previous_db = cs.db
    cs.db = _AsyncDatabase(raw)
    database_module.db = _AsyncDatabase(raw)
    try:
        yield raw
    finally:
        cs.db = previous_db
        database_module.db = previous_db


def _ctx(minimal=True):
    """A minimal trust context for prompt assembly."""
    return {
        "trust": {
            "name": "Practice Core Test Trust",
            "type": "revocable",
            "jurisdiction": "California",
            "state_code": "CA",
            "trustees": "Practice Core Tester",
            "status": "active",
        },
        "state_compliance": {
            "state_code": "CA",
            "state_name": "California",
            "utc_adopted": "no",
            "accounting_frequency": "annual",
            "notice_required": True,
        },
        "health_score": {"total": 78, "color": "green", "base_score": 78, "risk_penalty": 0},
        "trust_document": {},
    }


def _run(coro):
    """Run a coroutine on a fresh event loop.

    asyncio.get_event_loop() raises "There is no current event loop in thread
    'MainThread'" when an earlier test in the same process already closed the
    loop — which is exactly what happens in the full-suite run. A dedicated
    loop per call is order-independent.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def _tok(text):
    """Same chars/4 heuristic the product uses (trust_brief.estimate_tokens)."""
    return max(1, math.ceil(len(text or "") / 4))


# --------------------------------------------------------------------------- #
# (a) Practice core present on EVERY intent
# --------------------------------------------------------------------------- #
class TestPracticeCoreAlwaysOn:

    @pytest.mark.parametrize("intent", ["ask_knowledge", "log_minutes"])
    def test_practice_core_in_system_prompt(self, intent):
        import chat_service as cs

        prompt = cs._build_system_prompt(
            intent, "What are my duties as trustee?", _ctx(), [], stream_mode=True
        )
        # The practice core's own header must be present verbatim.
        assert "Trust Practice Core" in prompt, (
            f"practice core missing from system prompt for intent={intent}"
        )
        # Its four block headers must be present.
        for header in (
            "## Block 1 — Fiduciary Duty Frame",
            "## Block 2 — Trust Management Event Map",
            "## Block 3 — TrustOffice Capability Index",
            "## Block 4 — Jurisdiction Guard",
        ):
            assert header in prompt, f"{header!r} missing for intent={intent}"

    def test_practice_core_present_on_non_action_and_non_escalation_intents(self):
        """ask_knowledge is in ESCALATION_INTENTS but not ACTION_INTENTS —
        the core must ride on intents that get neither gated section."""
        import chat_service as cs

        assert "ask_knowledge" not in cs.ACTION_INTENTS
        for intent in ("ask_knowledge", "general_chat"):
            prompt = cs._build_system_prompt(
                intent, "hello", _ctx(), [], stream_mode=True
            )
            assert "Trust Practice Core" in prompt, (
                f"practice core must load on intent={intent} (not gated on ACTION_INTENTS)"
            )

    def test_practice_core_constant_is_loaded_from_pinned_file(self):
        """The practice core must be a pinned file, not an inline string."""
        import chat_service as cs

        assert cs.CHAT_SYSTEM_PRACTICE
        assert len(cs.CHAT_SYSTEM_PRACTICE) > 1000
        assert "Trust Practice Core" in cs.CHAT_SYSTEM_PRACTICE
        # Pinned-file mechanism: same loader shape as the other prompt files.
        prompts_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts"
        )
        assert os.path.isfile(os.path.join(prompts_dir, "chat_system_practice.md"))


# --------------------------------------------------------------------------- #
# (b) State data passthrough into ctx["state_compliance"]
# --------------------------------------------------------------------------- #
class TestStateCompliancePassthrough:

    def test_state_compliance_populated_for_trust_with_state_code(self, seeded):
        import chat_service as cs

        ctx = _run(
            cs.build_trust_context(USER_ID, TRUST_ID, intent="ask_knowledge")
        )
        sc = ctx.get("state_compliance")
        assert sc, "ctx['state_compliance'] must be populated for a trust with state_code"
        assert sc["state_code"] == "CA"
        assert sc["utc_adopted"] == "no"
        assert sc["accounting_frequency"] == "annual"
        assert sc["notice_required"] is True

    def test_state_compliance_populated_for_full_adoption_state(self, seeded):
        import chat_service as cs

        ctx = _run(
            cs.build_trust_context(USER_ID, "trust_practicecore_ut", intent="ask_knowledge")
        )
        sc = ctx.get("state_compliance")
        assert sc["state_code"] == "UT"
        assert sc["utc_adopted"] == "full"

    def test_state_compliance_present_on_action_intent_too(self, seeded):
        """The guard is always-on, so the data must be fetched on action
        intents as well as the lightweight knowledge path."""
        import chat_service as cs

        ctx = _run(
            cs.build_trust_context(USER_ID, TRUST_ID, intent="log_minutes")
        )
        sc = ctx.get("state_compliance")
        assert sc and sc["utc_adopted"] == "no"

    def test_state_compliance_empty_when_no_state_code(self, seeded):
        """A trust with no state on file must not get an invented profile."""
        import chat_service as cs

        seeded.trusts.insert_one({
            "_id": "t3", "trust_id": "trust_practicecore_nostate", "user_id": USER_ID,
            "name": "No State Trust", "trust_type": "revocable",
            "jurisdiction": "", "state_code": "", "status": "active",
        })
        ctx = _run(
            cs.build_trust_context(USER_ID, "trust_practicecore_nostate", intent="ask_knowledge")
        )
        sc = ctx.get("state_compliance")
        assert sc == {}, f"expected empty state_compliance, got {sc!r}"

    def test_state_compliance_unknown_when_profile_missing(self, seeded):
        """A state on file with no profile must NOT read as 'full'."""
        import chat_service as cs

        seeded.trusts.insert_one({
            "_id": "t4", "trust_id": "trust_practicecore_noprofile", "user_id": USER_ID,
            "name": "No Profile Trust", "trust_type": "revocable",
            "jurisdiction": "Nevada", "state_code": "NV", "status": "active",
        })
        ctx = _run(
            cs.build_trust_context(USER_ID, "trust_practicecore_noprofile", intent="ask_knowledge")
        )
        sc = ctx.get("state_compliance")
        assert sc, "state_compliance must still be present"
        assert sc["utc_adopted"] == "", "missing profile must not imply adoption"
        assert sc["utc_adopted"] != "full"

    def test_brief_surfaces_jurisdiction_facts(self, seeded):
        """The jurisdiction guard reads the brief — the brief must carry the
        governing-law facts."""
        from trust_brief import build_trust_brief

        ctx = _run(
            cs_ctx := __import__("chat_service").build_trust_context(
                USER_ID, TRUST_ID, intent="ask_knowledge"
            )
        )
        brief = build_trust_brief(ctx)
        assert "Jurisdiction" in brief["text"]
        assert "CA" in brief["text"]


# --------------------------------------------------------------------------- #
# (c) Budget guard
# --------------------------------------------------------------------------- #
# Ceiling: measured peak system prompt before the practice core was ~9.0K
# tokens (chat_service + brief + KB slice). The practice core adds ~2.4K, so
# the with-core ceiling is 13K tokens.
TOKEN_CEILING = 13000


class TestBudgetGuard:

    @pytest.mark.parametrize("intent", ["ask_knowledge", "log_minutes"])
    def test_system_prompt_under_ceiling(self, intent):
        import chat_service as cs

        prompt = cs._build_system_prompt(
            intent, "What are my duties as trustee?", _ctx(), [], stream_mode=True
        )
        est = _tok(prompt)
        assert est < TOKEN_CEILING, (
            f"system prompt for intent={intent} is {est} tokens, over the "
            f"{TOKEN_CEILING} ceiling"
        )

    def test_practice_core_alone_within_budget(self):
        """The practice file itself must stay inside its own ~2,400-token
        design budget (cap 2,500)."""
        import chat_service as cs

        est = _tok(cs.CHAT_SYSTEM_PRACTICE)
        assert est <= 2500, f"practice core is {est} tokens, over the 2,500 cap"

    def test_brief_stays_within_its_budget_with_jurisdiction(self):
        from trust_brief import build_trust_brief

        brief = build_trust_brief(_ctx())
        assert brief["stats"]["total_tokens"] <= brief["stats"]["budget_tokens"]


# --------------------------------------------------------------------------- #
# (d) Block structure
# --------------------------------------------------------------------------- #
EXPECTED_BLOCK_HEADERS = [
    "## Block 1 — Fiduciary Duty Frame",
    "## Block 2 — Trust Management Event Map",
    "## Block 3 — TrustOffice Capability Index",
    "## Block 4 — Jurisdiction Guard",
]


class TestPracticeFileStructure:

    @pytest.fixture
    def practice_text(self):
        import chat_service as cs
        return cs.CHAT_SYSTEM_PRACTICE

    def test_file_has_four_block_headers(self, practice_text):
        found = re.findall(r"^## Block \d+ .+$", practice_text, re.M)
        assert len(found) == 4, f"expected 4 block headers, found {len(found)}: {found}"

    def test_block_headers_match_expected_set(self, practice_text):
        found = re.findall(r"^## Block \d+ .+$", practice_text, re.M)
        assert found == EXPECTED_BLOCK_HEADERS, (
            f"block headers changed: {found}"
        )

    def test_block_headers_are_ordered(self, practice_text):
        positions = [practice_text.index(h) for h in EXPECTED_BLOCK_HEADERS]
        assert positions == sorted(positions), "block headers out of order"

    def test_every_block_has_body(self, practice_text):
        """A header with no body is an empty block — catch that."""
        for i, header in enumerate(EXPECTED_BLOCK_HEADERS):
            start = practice_text.index(header)
            end = (
                practice_text.index(EXPECTED_BLOCK_HEADERS[i + 1])
                if i + 1 < len(EXPECTED_BLOCK_HEADERS)
                else len(practice_text)
            )
            body = practice_text[start + len(header):end].strip()
            assert len(body) > 200, f"block {i + 1} body is suspiciously short"
