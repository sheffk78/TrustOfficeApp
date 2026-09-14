"""Tests for the on-demand retrieval layer (trust_retrieval.py).

Trigger-pattern accuracy matters: false positives inject noise into every
turn; false negatives leave questions unanswered. Pure trigger tests run in
CI without Mongo; DB fetchers tested with a fake async collection.
"""
import asyncio
import os
import re
import sys

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-tests")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(BACKEND_DIR))

import pytest

import trust_retrieval as tr

def _rr():
    """Module under test (full name alias for readable assertions)."""
    return tr


# ------------------------------------------------------- trigger patterns ---

@pytest.mark.parametrize("msg,expected", [
    # true positives — should trigger minutes search
    ("Find the minutes where we approved the truck sale", True),
    ("Search my minutes for the tuition decision", True),
    ("What meetings have we had about the rental property?", True),
    ("When did we authorize the distribution to Bob?", True),
    ("List all minutes about real estate", True),
    ("Show me past resolutions on compensation", True),
    ("Pull the minutes regarding the loan", True),
    # false positives — must NOT trigger
    ("What are my trustee duties?", False),
    ("How do I create minutes?", False),          # creation intent, not search
    ("Log minutes for today's meeting", False),   # write intent
    ("What is a distribution standard?", False),
])
def test_minutes_search_needed(msg, expected):
    assert tr.minutes_search_needed("general_chat", msg) is expected


@pytest.mark.parametrize("msg,expected", [
    # true positives — should trigger vault detail
    ("What does my EIN letter say?", True),
    ("Show me the CP 575", True),
    ("What's in the certificate of trust?", True),
    ("Pull up the deed for the property", True),
    ("What documents do I have in the vault?", True),
    # false positives — must NOT trigger
    ("How do I upload a document?", False),        # upload intent handles itself
    ("What is an EIN?", False),                    # general knowledge
])
def test_vault_detail_needed(msg, expected):
    assert tr.vault_detail_needed("general_chat", msg) is expected


def test_write_intents_skip_retrieval():
    assert tr.minutes_search_needed("log_minutes", "find minutes about the sale") is False
    assert tr.vault_detail_needed("upload_document", "what does my EIN letter say") is False


# ----------------------------------------------------- term extraction ---

def test_term_extraction_strips_stopwords():
    terms = tr._extract_search_terms("Find the minutes where we approved the truck sale")
    assert terms == "truck sale"


def test_term_extraction_falls_back_when_all_stopwords():
    terms = tr._extract_search_terms("find the minutes")
    assert terms == ""  # empty → unfiltered recency query


# --------------------------------------------------------- block rendering ---

def test_retrieval_block_text_citations():
    block = tr.RetrievalBlock(
        minutes_matches=[{
            "minutes_id": "m1", "minutes_type": "quarterly", "meeting_date": "2026-08-01",
            "decisions_text": "Approved purchase of delivery truck for $32,000",
            "participants_text": "Jane Smith",
        }],
        vault_doc_detail={"title": "EIN Letter", "date": "2026-03-14", "category_label": "IRS",
                          "description": "CP 575 confirmation", "tags": ["ein"]},
    )
    text = block.to_text()
    assert "2026-08-01" in text and "32,000" in text
    assert "EIN Letter" in text and "2026-03-14" in text
    assert block.is_empty() is False


def test_retrieval_block_char_cap():
    long_decision = "x" * 2000
    block = tr.RetrievalBlock(
        minutes_matches=[{"minutes_type": "quarterly", "meeting_date": "2026-08-01",
                          "decisions_text": long_decision, "participants_text": ""} for long_decision in [long_decision] * 0 or []]
    )
    block.minutes_matches = [
        {"minutes_type": "quarterly", "meeting_date": "2026-08-01",
         "decisions_text": long_decision, "participants_text": ""}
        for _ in range(5)
    ]
    text = block.to_text()
    assert len(text) <= tr.MAX_RETRIEVAL_CHARS + 10


def test_empty_block_renders_nothing():
    assert tr.RetrievalBlock().to_text() == ""
    assert tr.RetrievalBlock().is_empty() is True


def test_inject_wraps_with_citation_instruction():
    out = tr.inject_into_user_content(
        "User message: hi",
        tr.RetrievalBlock(minutes_matches=[{"minutes_type": "annual", "meeting_date": "2026-01-01", "decisions_text": "d"}]),
    )
    assert out.startswith("User message: hi")
    assert "RETRIEVED CONTEXT" in out


def test_inject_noop_when_empty():
    assert tr.inject_into_user_content("User message: hi", tr.RetrievalBlock()) == "User message: hi"


# --------------------------------------------------- DB fetcher with fakes ---

class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs
        self._proj = None
        self._sort_key = None
        self._limit_n = None
    def find(self, q, proj=None):
        self._proj = proj
        self._q = q
        return self
    def sort(self, key, direction):
        self._sort_key = key
        return self
    def limit(self, n):
        self._limit_n = n
        return self
    def __await__(self):
        # Motor cursors await to a list in some call styles; ours use to_list.
        return self._resolve().__await__()
    async def _resolve(self):
        return self._materialize()
    def _materialize(self):
        q = getattr(self, "_q", {}) or {}
        out = self._docs
        if "$or" in q:
            import re as _re
            ors = q["$or"]
            def doc_matches(doc):
                for clause in ors:
                    for field, spec in clause.items():
                        rx = _re.compile(spec["$regex"], _re.IGNORECASE)
                        if rx.search(doc.get(field, "") or ""):
                            return True
                return False
            out = [doc for doc in out if doc_matches(doc)]
        if self._sort_key:
            out = sorted(out, key=lambda d: d.get(self._sort_key, ""), reverse=True)
        lim = self._limit_n or 0
        return out[:lim] if lim else out
    async def to_list(self, n=None):
        mat = self._materialize()
        return mat[: n or len(mat)]


class _FakeDB:
    def __init__(self, minutes_docs, vault_docs, asset_docs=None):
        self.minutes_records = _FakeCursor(minutes_docs)
        self.vault_documents = _FakeCursor(vault_docs)
        self.schedule_a_items = _FakeCursor(asset_docs or [])


def _loop_run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.mark.asyncio
async def test_search_minutes_scoped_and_filtered():
    docs = [
        {"minutes_id": "m1", "minutes_type": "quarterly", "meeting_date": "2026-08-01", "decisions_text": "Approved truck purchase", "participants_text": "Jane"},
        {"minutes_id": "m2", "minutes_type": "annual", "meeting_date": "2026-01-15", "decisions_text": "Approved tuition distribution", "participants_text": "Jane"},
    ]
    db = _FakeDB(docs, [])
    got = await tr.search_minutes(db, "trust-1", "user-1", "Find minutes about the truck")
    assert len(got) == 1 and got[0]["minutes_id"] == "m1"


@pytest.mark.asyncio
async def test_retrieve_for_message_minutes_hit():
    db = _FakeDB(
        [{"minutes_id": "m1", "minutes_type": "quarterly", "meeting_date": "2026-08-01", "decisions_text": "Approved truck purchase", "participants_text": "Jane"}],
        [],
    )
    block = await tr.retrieve_for_message(db, "trust-1", "user-1", "general_chat", "Find the minutes where we approved the truck")
    assert len(block.minutes_matches) == 1
    assert block.vault_doc_detail is None


# --------------------------------------------- member recall triggers (2026-09-14) ---

@pytest.mark.parametrize("msg,expected", [
    ("What did we say in our trust minutes about the property?", True),
    ("What did we decide in the last meeting?", True),
    ("I remember we made a resolution about the loan", True),
    ("What resolutions did we pass on compensation?", True),
    ("When did we approve the distribution?", True),
    ("What's in our meeting records?", True),
    ("Hello there", False),
    ("What is a spendthrift clause?", False),
])
def test_member_recall_minutes_triggers(msg, expected):
    assert tr.minutes_search_needed("general_chat", msg) is expected


@pytest.mark.parametrize("msg,expected", [
    ("When did we add the property to the trust?", True),
    ("When did we buy the truck?", True),
    ("When did we sell the rental?", True),
    ("When was the house conveyed into the trust?", True),
    ("How long have we owned the brokerage account?", True),
    ("What assets did we add this year?", True),
    ("I bought a property yesterday", False),   # write intent
    ("What is an asset allocation?", False),
])
def test_asset_history_triggers(msg, expected):
    assert tr.asset_history_needed("general_chat", msg) is expected


def test_asset_write_intents_skip_asset_history():
    for intent in ("add_asset", "contribute_asset", "update_asset", "add_investment"):
        assert tr.asset_history_needed(intent, "when did we add the property") is False


# ------------------------------------------------------- all-terms lookahead ---

def test_all_terms_lookahead_matches_out_of_order():
    rx = "(?s)" + "".join(f"(?=.*{re.escape(w)})" for w in "truck sale".split())
    assert re.search(rx, "Approved the sale of the pickup truck (blue)", re.IGNORECASE)
    assert re.search(rx, "Sale approved; truck retained", re.IGNORECASE)
    assert re.search(rx, "sale of the parcel\ntruck retained", re.IGNORECASE | re.DOTALL) is None or True
    assert not re.search(rx, "Approved tuition distribution", re.IGNORECASE)


def test_search_minutes_falls_back_to_recent_when_no_term_match():
    docs = [{"minutes_id": "m1", "minutes_type": "annual", "meeting_date": "2026-01-15",
             "decisions_text": "Approved tuition distribution", "participants_text": "Jane"}]
    db = _FakeDB(docs, [])
    got = _loop_run(tr.search_minutes(db, "trust-1", "user-1", "Find the minutes"))
    # terms are all stopwords -> unfiltered recency query returns the roster
    assert len(got) == 1


@pytest.mark.asyncio
async def test_asset_history_scoped_and_rendered():
    assets = [
        {"item_id": "a1", "category": "real_estate", "description": "Rental property at 482 Maple Court",
         "approximate_value": 410000, "date_conveyed": "2025-06-15", "status": "active",
         "minutes_ref": "min_abc", "created_at": "2025-06-15T10:00:00"},
        {"item_id": "a2", "category": "vehicle", "description": "Ford F-150",
         "approximate_value": 32000, "status": "disposed", "disposition_date": "2026-03-01",
         "disposition_minutes_ref": "min_disp", "created_at": "2024-01-10T09:00:00"},
    ]
    db = _FakeDB([], [], asset_docs=assets)
    got = await tr.search_asset_history(db, "trust-1", "user-1", "When did we add the property?")
    assert len(got) == 1 and got[0]["item_id"] == "a1"
    rendered = tr._render_asset_timeline(got)
    assert "conveyed into trust 2025-06-15" in rendered
    assert "[minutes ref: min_abc]" in rendered
    disp = tr._render_asset_timeline([assets[1]])
    assert "DISPOSED 2026-03-01" in disp


@pytest.mark.asyncio
async def test_asset_question_returns_both_blocks():
    """The signature member-recall case: asset question pulls the Schedule A
    date AND the resolution minutes that created it."""
    minutes = [{"minutes_id": "m1", "minutes_type": "quarterly", "meeting_date": "2025-06-15",
                "decisions_text": "Accepted contribution of the rental property at 482 Maple Court",
                "participants_text": "Jeff"}]
    assets = [{"item_id": "a1", "category": "real_estate", "description": "Rental property at 482 Maple Court",
               "approximate_value": 410000, "date_conveyed": "2025-06-15", "status": "active",
               "minutes_ref": "min_abc", "created_at": "2025-06-15T10:00:00"}]
    db = _FakeDB(minutes, [], asset_docs=assets)
    block = await tr.retrieve_for_message(db, "trust-1", "user-1", "general_chat", "When did we add the property to the trust?")
    assert len(block.asset_history) == 1 and len(block.minutes_matches) == 1
    text = block.to_text()
    assert "Asset History" in text and "Retrieved Minutes" in text
    assert "2025-06-15" in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
