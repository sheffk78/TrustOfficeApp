"""Tests for the on-demand retrieval layer (trust_retrieval.py).

Trigger-pattern accuracy matters: false positives inject noise into every
turn; false negatives leave questions unanswered. Pure trigger tests run in
CI without Mongo; DB fetchers tested with a fake async collection.
"""
import os
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
    def __init__(self, minutes_docs, vault_docs):
        self.minutes_records = _FakeCursor(minutes_docs)
        self.vault_documents = _FakeCursor(vault_docs)


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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
