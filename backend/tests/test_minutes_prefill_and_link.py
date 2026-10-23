"""
Regression tests for the Trust Assistant minutes failure chain
(member complaint 2026-10-23, Jerel Kratt — trust_52799b4041b5).

Three defects are locked down here:

  (a) TYPE NORMALIZATION — a card whose minutes_type is the human wording
      "Quarterly Review" must produce a record of type "quarterly", NOT
      "general". The old code did ``MinutesType("Quarterly Review")`` which
      raised ValueError and was silently swallowed into MinutesType.general.

  (b) PREFILL — "fill out with my information on file" must produce a draft
      with populated sections and trustee participants drawn from the trust
      document, not an empty shell with sections=[].

  (c) LINK SURFACING — the assistant's post-approval confirmation must carry
      the real review_link, and the link must point at a route the frontend
      actually serves (App.js defines /minutes/:minutesId, NOT
      /minutes/:minutesId/edit).

These are true unit tests: mongomock-backed, no live server, no LLM, no
network. The module-level mongomock shim patches motor's client so
``routers.chat``/``routers.minutes`` see an in-memory database.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_minutes_prefill")
os.environ.setdefault("JWT_SECRET", "test-secret-for-minutes-prefill")
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


class _AsyncCollection:
    def __init__(self, coll):
        self._coll = coll

    def find(self, *a, **k):
        return _AsyncCursor(self._coll.find(*a, **k))

    async def find_one(self, *a, **k):
        return self._coll.find_one(*a, **k)

    async def insert_one(self, doc, *a, **k):
        return self._coll.insert_one(doc, *a, **k)

    async def insert_many(self, docs, *a, **k):
        return self._coll.insert_many(docs, *a, **k)

    async def update_one(self, *a, **k):
        return self._coll.update_one(*a, **k)

    async def update_many(self, *a, **k):
        return self._coll.update_many(*a, **k)

    async def delete_one(self, *a, **k):
        return self._coll.delete_one(*a, **k)

    async def delete_many(self, *a, **k):
        return self._coll.delete_many(*a, **k)

    async def count_documents(self, *a, **k):
        return self._coll.count_documents(*a, **k)

    async def distinct(self, *a, **k):
        return self._coll.distinct(*a, **k)


class _AsyncDB:
    """Motor-style async facade over a mongomock database.

    Collections are cached per-name so repeated attribute access returns the
    same wrapper (and the same underlying mongomock collection).
    """

    def __init__(self, client_db):
        self._db = client_db
        self._cols = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        if name not in self._cols:
            self._cols[name] = _AsyncCollection(self._db[name])
        return self._cols[name]


@pytest.fixture(scope="module")
def mongo_client():
    import mongomock
    return mongomock.MongoClient()


@pytest.fixture(scope="module")
def patched_db(mongo_client, monkeypatch_module):
    """
    Patch the `db` handle used by every module that imported it by name.

    Each router does `from database import db`, so patching database.db alone
    would not reach routers.chat / routers.minutes / dependencies — they hold
    their own reference. Patch them all.
    """
    import database
    import routers.chat
    import routers.minutes
    import dependencies

    fake = _AsyncDB(mongo_client["test_minutes_prefill"])
    for mod in (database, routers.chat, routers.minutes, dependencies):
        monkeypatch_module.setattr(mod, "db", fake, raising=False)
    return fake


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture
def seeded(patched_db, mongo_client):
    """Seed a user + trust with trustees on record (sync mongomock inserts)."""
    client_db = mongo_client["test_minutes_prefill"]
    client_db.users.insert_one({
        "user_id": "user_test_kratt",
        "email": "jerel@example.com",
        "name": "Jerel Kratt",
    })
    client_db.trusts.insert_one({
        "trust_id": "trust_test_kratt",
        "user_id": "user_test_kratt",
        "name": "Kratt Family Estate",
        "trustees": "Jerel Kratt, Morgan Kratt",
        "status": "active",
    })
    return patched_db


# --------------------------------------------------------------------------- #
# (a) Type normalization
# --------------------------------------------------------------------------- #
def test_normalizer_maps_quarterly_review_to_quarterly():
    """'Quarterly Review' (human wording) must resolve to the enum 'quarterly'."""
    from minutes_type_normalizer import resolve_minutes_type
    from models import MinutesType

    valid = tuple(m.value for m in MinutesType)
    resolved, caveat = resolve_minutes_type("Quarterly Review", valid_types=valid)

    assert resolved == "quarterly", (
        f"'Quarterly Review' must map to 'quarterly', got {resolved!r}"
    )
    assert resolved != "general", "must NOT silently downgrade to general"
    assert MinutesType(resolved).value == "quarterly"
    # The substitution is disclosed, never silent.
    assert caveat and "quarterly" in caveat


@pytest.mark.parametrize("raw,expected", [
    ("Quarterly Review", "quarterly"),
    ("quarterly review", "quarterly"),
    ("Quarterly Review Minutes", "quarterly"),
    ("quarterly", "quarterly"),
    ("  QUARTERLY  ", "quarterly"),
    ("annual meeting", "annual"),
    ("Annual Review", "annual"),
    ("annual review minutes", "annual"),
    ("trustee meeting", "general_meeting"),
    ("Trustee Meeting Minutes", "general_meeting"),
    ("compensation", "compensation"),
    ("Trustee Compensation", "compensation"),
    ("distribution", "distribution"),
    ("solvency", "solvency"),
])
def test_normalizer_alias_table(raw, expected):
    from minutes_type_normalizer import resolve_minutes_type
    from models import MinutesType

    valid = tuple(m.value for m in MinutesType)
    resolved, _caveat = resolve_minutes_type(raw, valid_types=valid)
    assert resolved == expected, f"{raw!r} -> {resolved!r}, expected {expected!r}"


def test_normalizer_trustee_meeting_maps_to_initial_when_context_says_initial():
    """'trustee meeting' + 'initial' context -> initial_trustee_meeting."""
    from minutes_type_normalizer import resolve_minutes_type
    from models import MinutesType

    valid = tuple(m.value for m in MinutesType)
    resolved, _ = resolve_minutes_type(
        "trustee meeting",
        context_text="hold our initial trustee meeting for the new trust",
        valid_types=valid,
    )
    assert resolved == "initial_trustee_meeting"


def test_normalizer_trustee_meeting_without_initial_context_is_general_meeting():
    from minutes_type_normalizer import resolve_minutes_type
    from models import MinutesType

    valid = tuple(m.value for m in MinutesType)
    resolved, _ = resolve_minutes_type(
        "trustee meeting",
        context_text="regular quarterly trustee business",
        valid_types=valid,
    )
    assert resolved == "general_meeting"


def test_normalizer_unresolvable_returns_none_not_general():
    """An unknown type must NOT resolve to 'general' behind the caller's back."""
    from minutes_type_normalizer import resolve_minutes_type
    from models import MinutesType

    valid = tuple(m.value for m in MinutesType)
    resolved, caveat = resolve_minutes_type("banana meeting", valid_types=valid)
    assert resolved is None
    assert caveat is None


def test_normalizer_logs_warning_on_unresolvable(caplog):
    """Every fallback must be logged at WARNING (never a quiet drop)."""
    import logging
    from minutes_type_normalizer import resolve_minutes_type
    from models import MinutesType

    valid = tuple(m.value for m in MinutesType)
    with caplog.at_level(logging.WARNING):
        resolve_minutes_type("banana meeting", valid_types=valid)
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
    assert any("MINUTES_TYPE_UNRESOLVED" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_exec_minutes_records_quarterly_not_general(seeded):
    """(a) The exec path stores minutes_type == 'quarterly' for a 'Quarterly Review' card."""
    from routers.chat import _exec_minutes

    result = await _exec_minutes(
        {
            "minutes_type": "Quarterly Review",
            "meeting_date": "2026-10-20",
            "participants_text": "Jerel Kratt",
            "decisions_text": "Reviewed quarterly financials.",
        },
        "trust_test_kratt",
        "user_test_kratt",
    )

    assert result.get("success") is True, result
    assert result.get("minutes_type") == "quarterly", (
        f"expected 'quarterly', got {result.get('minutes_type')!r} — silent downgrade"
    )
    assert result.get("minutes_type") != "general"

    rec = await seeded.minutes_records.find_one({"minutes_id": result["record_id"]})
    assert rec is not None, "minutes record was not persisted"
    assert rec["minutes_type"] == "quarterly"


@pytest.mark.asyncio
async def test_exec_minutes_unresolvable_type_falls_back_with_caveat(seeded):
    """An unrecognizable type must produce a caveat, never a quiet 'general'."""
    from routers.chat import _exec_minutes

    result = await _exec_minutes(
        {"minutes_type": "banana meeting", "meeting_date": "2026-10-20"},
        "trust_test_kratt",
        "user_test_kratt",
    )

    assert result.get("success") is True
    assert result.get("minutes_type") == "general"
    # The member is told the type was substituted.
    assert result.get("caveat"), "an unresolvable type must carry a caveat"
    assert "banana meeting" in result["caveat"]


# --------------------------------------------------------------------------- #
# (b) Prefill from trust data on file
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_exec_minutes_prefills_sections_from_trust_data(seeded):
    """(b) The draft must carry populated sections + trustee participants."""
    from routers.chat import _exec_minutes

    result = await _exec_minutes(
        {
            "minutes_type": "Quarterly Review",
            "meeting_date": "2026-10-20",
            "decisions_text": "Reviewed the quarterly financial report.",
        },
        "trust_test_kratt",
        "user_test_kratt",
    )

    assert result.get("success") is True, result
    assert result.get("prefilled") is True, "draft was not prefilled"

    rec = await seeded.minutes_records.find_one({"minutes_id": result["record_id"]})
    assert rec is not None

    # Sections must NOT be an empty shell.
    sections = rec.get("sections") or []
    assert len(sections) >= 1, "sections is empty — draft is a shell"
    assert sections[0].get("content"), "section content is empty"
    # The content must be real minutes text built from the trust on file.
    content = sections[0]["content"]
    assert "Kratt Family Estate" in content, "trust name on file missing from minutes"
    assert "Jerel Kratt" in content, "trustee on file missing from minutes"

    # template_data must be populated too.
    assert rec.get("template_data"), "template_data is empty"
    assert rec["template_data"].get("trust_name") == "Kratt Family Estate"
    assert rec.get("template_type") == "quarterly_review"


@pytest.mark.asyncio
async def test_exec_minutes_participants_default_to_trustees_on_record(seeded):
    """(b) Participants default to the trustee(s) on record."""
    from routers.chat import _exec_minutes

    result = await _exec_minutes(
        {
            "minutes_type": "Quarterly Review",
            "meeting_date": "2026-10-20",
        },
        "trust_test_kratt",
        "user_test_kratt",
    )

    assert result.get("success") is True
    rec = await seeded.minutes_records.find_one({"minutes_id": result["record_id"]})
    participants = rec.get("participants_text") or ""
    assert "Jerel Kratt" in participants, (
        f"trustee on file not used as participant: {participants!r}"
    )
    assert "Morgan Kratt" in participants, (
        f"second trustee on file not used as participant: {participants!r}"
    )


@pytest.mark.asyncio
async def test_exec_minutes_general_type_is_not_prefilled(seeded):
    """'general' has no template — the draft stays un-prefilled (no crash)."""
    from routers.chat import _exec_minutes

    result = await _exec_minutes(
        {"minutes_type": "general", "meeting_date": "2026-10-20"},
        "trust_test_kratt",
        "user_test_kratt",
    )
    assert result.get("success") is True
    assert result.get("prefilled") is not True


# --------------------------------------------------------------------------- #
# (c) Link surfacing
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_exec_minutes_success_carries_review_link(seeded):
    """(c) A successful exec must carry the review_link."""
    from routers.chat import _exec_minutes

    result = await _exec_minutes(
        {"minutes_type": "Quarterly Review", "meeting_date": "2026-10-20"},
        "trust_test_kratt",
        "user_test_kratt",
    )

    assert result.get("success") is True
    link = result.get("review_link")
    assert link, "successful exec must carry a review_link"
    assert result["record_id"] in link


@pytest.mark.asyncio
async def test_review_link_points_at_a_real_frontend_route(seeded):
    """
    The link must resolve to a route the SPA actually serves.

    App.js defines /minutes/:minutesId (MinutesDetailPage) and
    /minutes/create. There is NO /minutes/:minutesId/edit route — linking
    there 404s, which is part of why the member could never find the draft.
    """
    from routers.chat import _exec_minutes

    result = await _exec_minutes(
        {"minutes_type": "Quarterly Review", "meeting_date": "2026-10-20"},
        "trust_test_kratt",
        "user_test_kratt",
    )
    link = result["review_link"]
    assert not link.endswith("/edit"), (
        f"{link!r} ends in /edit — no such frontend route; member gets a 404"
    )
    assert link == f"/minutes/{result['record_id']}"


def test_success_message_includes_review_link():
    """The post-approval confirmation must contain the review_link."""
    from approval_handler import build_success_message

    msg = build_success_message(
        "minutes",
        {"success": True, "review_link": "/minutes/minutes_abc123"},
    )
    assert "/minutes/minutes_abc123" in msg
    assert "Open it:" in msg


def test_success_message_includes_caveat():
    """A type substitution caveat must reach the member's reply."""
    from approval_handler import build_success_message

    msg = build_success_message(
        "minutes",
        {
            "success": True,
            "review_link": "/minutes/minutes_abc123",
            "caveat": "Minutes type 'Quarterly Review' was saved as 'quarterly'.",
        },
    )
    assert "Quarterly Review" in msg
    assert "quarterly" in msg


def test_success_message_without_link_has_no_open_it():
    """No link -> no dangling 'Open it:' fragment."""
    from approval_handler import build_success_message

    msg = build_success_message("beneficiary", {"success": True})
    assert "Open it:" not in msg
    assert msg.startswith("Done — beneficiary has been created.")


@pytest.mark.asyncio
async def test_approval_reply_text_carries_the_link(seeded, monkeypatch):
    """The text-approval path (member types 'yes') must carry the link."""
    from approval_handler import handle_text_approval
    import routers.chat as chat_router

    # Minimal conversation with a pending minutes card.
    conv_id = "conv_test_link"
    await seeded.chat_conversations.insert_one({
        "conversation_id": conv_id,
        "user_id": "user_test_kratt",
        "trust_id": "trust_test_kratt",
        "messages": [
            {"role": "user", "content": "create quarterly minutes"},
            {"role": "assistant", "content": "Here is the card.", "action_card": {
                "type": "minutes_preview",
                "data": {"minutes_type": "Quarterly Review"},
                "confirmation_status": "pending",
            }},
        ],
    })

    # Avoid the subscription write-gate in the test env.
    async def _fake_sub_state(user_id):
        class _S:
            is_read_only = False
        return _S()

    monkeypatch.setattr(chat_router, "get_subscription_state", _fake_sub_state)

    out = await handle_text_approval(
        conversation_id=conv_id,
        message_index=1,
        action_card={
            "type": "minutes_preview",
            "data": {"minutes_type": "Quarterly Review"},
            "confirmation_status": "pending",
        },
        user_id="user_test_kratt",
    )

    assert out.get("success") is True, out
    msg = out.get("message") or ""
    assert "Open it:" in msg, f"confirmation does not carry the link: {msg!r}"
    assert "/minutes/minutes_" in msg, f"confirmation link missing: {msg!r}"
    assert out["execution_result"].get("review_link")
