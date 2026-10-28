"""
Tests for the doctrine retrieval leg and the retrieval-ranked KB slice.

WHY (2026-10-23, P2a): the Trust Assistant's knowledge context was a blind
4,500-char truncation of an alphabetically-ordered blob, and the FTS5 index
that was supposed to provide relevance-ranked retrieval was inert in prod
because the branch that used it required a registry YAML that is not in the
deployed image. A member asking "how often should I do trustee accounting?"
could get the head of an unrelated file.

These tests lock down four guarantees:

  (a) A duties / UTC question retrieves REAL doctrine — the Trustee-101
      corpus or the in-repo reviewed knowledge — not an empty result.

  (b) The retrieval-ranked slice beats blind truncation on a crafted
      ordering case: the text that answers the question is chosen over
      whatever happened to be first in file order.

  (c) No output string anywhere in the retrieval path contains the stale
      "41 templates" claim that the old 2-month-old index embedded.

  (d) The budget guard holds: practice core + knowledge slice stays within
      the ~13K-char system-prompt bar set by the P1 work.

True unit tests: no live server, no LLM, no network.
"""
import math
import os
import re
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_doctrine_retrieval")
os.environ.setdefault("JWT_SECRET", "test-secret-for-doctrine-retrieval")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")
os.environ.setdefault("MAILERCLOUD_API_KEY", "")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "")
os.environ.setdefault("POSTMARK_SERVER_TOKEN", "")
os.environ.setdefault("TIDYCAL_API_TOKEN", "")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BACKEND = os.path.join(os.path.dirname(__file__), "..")
KNOWLEDGE_DIR = os.path.join(BACKEND, "knowledge")

# The prompt budget bar set by the P1 practice-core work.
PROMPT_CHAR_BUDGET = 13_000 * 4   # 13K tokens at the chars/4 heuristic


def _tok(text) -> int:
    """Same chars/4 heuristic the product uses (trust_brief.estimate_tokens)."""
    return max(1, math.ceil(len(text or "") / 4))


# --------------------------------------------------------------------------- #
# (a) A doctrine question retrieves real doctrine
# --------------------------------------------------------------------------- #

class TestDoctrineRetrievalFindsContent:
    """The doctrine leg must return substance, not an empty block."""

    def test_duties_question_returns_non_empty_doctrine(self):
        import trust_retrieval as tr

        passages = tr.fetch_doctrine("What are my duties as trustee?")
        assert passages, (
            "a duties question retrieved no doctrine — the FTS index is "
            "probably not being built"
        )
        body = " ".join(p["text"] for p in passages).lower()
        assert len(body) > 200, "doctrine block is too thin to be useful"
        assert any(
            word in body
            for word in ("duty", "duties", "fiduciary", "loyalty", "prudence")
        ), f"retrieved doctrine does not look like duties content: {body[:200]!r}"

    def test_utc_question_matches_the_utc_concept(self):
        import trust_retrieval as tr

        concepts = tr._match_doctrine_concepts(
            "Does the Uniform Trust Code apply to my trust?"
        )
        assert "utc" in concepts, (
            f"the UTC trigger did not fire; concepts matched: {concepts}"
        )

    def test_doctrine_triggers_fire_on_the_named_topics(self):
        import trust_retrieval as tr

        cases = {
            "What are my fiduciary duties?": "duties",
            "Does the Uniform Trust Code apply here?": "utc",
            "Can I amend my trust to add a beneficiary?": "amendment",
            "Can my successor trustee also be a beneficiary?": "successor_trustee",
            "What is the distribution standard, HEMS?": "distribution_standard",
            "How often should I do trustee accounting?": "accounting",
            "How do I terminate the trust?": "termination",
            "What should I put in a beneficiary letter?": "beneficiary_communication",
            "How do I avoid commingling trust money?": "commingling",
            "What is the prudent investor rule?": "investment",
        }
        for message, expected in cases.items():
            concepts = tr._match_doctrine_concepts(message)
            assert expected in concepts, (
                f"{message!r} should trigger the {expected!r} concept, "
                f"got {concepts}"
            )

    def test_off_topic_message_triggers_no_doctrine(self):
        import trust_retrieval as tr

        concepts = tr._match_doctrine_concepts("hello, good morning")
        assert not concepts, f"a greeting should not trigger doctrine: {concepts}"

    def test_doctrine_is_drawn_from_the_reviewed_corpus(self):
        """Every retrieved passage must name a file that exists in the KB."""
        import trust_retrieval as tr

        passages = tr.fetch_doctrine("How often should I do trustee accounting?")
        assert passages
        for p in passages:
            source = p.get("source_ref") or ""
            assert source, f"passage has no source citation: {p!r}"
            path = os.path.join(KNOWLEDGE_DIR, source)
            assert os.path.isfile(path), (
                f"retrieved passage cites {source!r}, which is not in the "
                f"knowledge directory"
            )

    def test_trustee101_corpus_is_retrievable(self):
        """The extracted Trustee-101 articles must be reachable.

        Canonical doctrine (01-hems-standard) correctly wins a plain
        'what is HEMS' question; the course articles must surface when the
        member uses the course's distinctive framing."""
        import trust_retrieval as tr

        canon = tr.fetch_doctrine(
            "What does HEMS stand for and how do I use it?",
            limit=6,
            max_chars=3000,
        )
        assert canon, "a plain HEMS question retrieved nothing"
        assert any("01-hems-standard" in (p.get("source_ref") or "") for p in canon), (
            f"canonical HEMS doctrine did not surface: {[p.get('source_ref') for p in canon]}"
        )
        course = tr.fetch_doctrine(
            "Walk me through the four-question test I should use before every distribution "
            "and the distribution memo the course recommends.",
            limit=6,
            max_chars=4500,
        )
        assert course, "course-framed distribution question retrieved nothing"
        assert any("trustee-101" in (p.get("source_ref") or "") for p in course), (
            f"the Trustee-101 corpus was not retrieved; sources: "
            f"{[p.get('source_ref') for p in course]}"
        )


# --------------------------------------------------------------------------- #
# (b) The ranked slice beats blind truncation
# --------------------------------------------------------------------------- #

class TestRankedSliceBeatsBlindTruncation:
    """A crafted ordering case where position and relevance disagree."""

    def test_relevant_file_wins_over_first_in_file_order(self):
        """The file that answers the question must be chosen, not the first.

        The crafted case: "zz-craft-relevant" sorts LAST by file name but is
        the file that actually answers the question. "aa-craft-noise" sorts
        FIRST and is irrelevant. Blind truncation would fill the budget with
        the noise file and never reach the relevant one.
        """
        import chat_service as cs

        relevant = (
            "# Craft Relevant\n\n"
            "## Successor Trustee Appointment\n\n"
            "A successor trustee may also be a beneficiary where the trust "
            "document permits, but the conflict must be addressed and "
            "documented. Successor trustee appointment and beneficiary "
            "designation are separate decisions.\n"
        )
        noise = (
            "# Craft Noise\n\n"
            "## Widget Calibration\n\n"
            "Widget calibration uses a torque wrench and a calibrated "
            "torque reference. Adjust the widget until the torque gauge "
            "reads green. Widgets are not beneficiaries. Torque is not "
            "fiduciary duty. Calibrate quarterly.\n"
            * 20
        )
        crafted_kb = {
            "aa-craft-noise": noise,
            "zz-craft-relevant": relevant,
        }
        message = "Can my successor trustee also be a beneficiary?"

        ranked = cs._ranked_knowledge_slice(
            message, "ask_knowledge", crafted_kb, [], budget=900
        )
        assert ranked, "the ranked slice returned nothing for a crafted case"
        assert "successor trustee" in ranked.lower(), (
            "the ranked slice did not choose the relevant file over the "
            f"first file in name order. Got:\n{ranked[:600]}"
        )
        assert "widget" not in ranked.lower(), (
            "the ranked slice spent its budget on the irrelevant first file"
        )

    def test_ranked_slice_respects_the_char_budget(self):
        import chat_service as cs

        kb = cs.get_knowledge_base()
        for message in (
            "What are my duties as trustee?",
            "How often should I do trustee accounting?",
            "Can my successor trustee also be a beneficiary?",
        ):
            slice_text = cs._ranked_knowledge_slice(
                message, "ask_knowledge", kb, [], budget=cs.KNOWLEDGE_SLICE_BUDGET
            )
            assert len(slice_text) <= cs.KNOWLEDGE_SLICE_BUDGET + 40, (
                f"slice for {message!r} is {len(slice_text)} chars, over the "
                f"{cs.KNOWLEDGE_SLICE_BUDGET} budget"
            )

    def test_ranked_slice_uses_relevance_not_position(self):
        """A later-sorting file must be able to outrank an earlier one."""
        import chat_service as cs

        kb = {
            "aaa-first": "## Widgets\n\nWidget widget widget widget widget.",
            "zzz-last": "## Successor Trustee\n\nSuccessor trustee succession.",
        }
        ranked = cs._ranked_knowledge_slice(
            "Who is the successor trustee?", "ask_knowledge", kb, [], budget=600
        )
        assert "successor trustee" in ranked.lower()
        assert "widget" not in ranked.lower()

    def test_blanket_truncation_is_gone_from_the_prompt_path(self):
        """The prompt must not truncate the knowledge slice blind again."""
        import chat_service as cs

        src = open(
            os.path.join(BACKEND, "chat_service.py"), "r", encoding="utf-8"
        ).read()
        assert "knowledge_context[:4500]" not in src, (
            "the blind 4,500-char truncation is back in _build_system_prompt"
        )


# --------------------------------------------------------------------------- #
# (c) The stale "41 templates" claim can never surface
# --------------------------------------------------------------------------- #

STALE_CLAIM = re.compile(r"\b41\s+(minutes\s+)?templates?\b", re.I)


class TestNoStaleTemplateCount:
    def test_retrieved_passages_never_contain_the_stale_count(self):
        import trust_retrieval as tr

        for message in (
            "What are my duties as trustee?",
            "How often should I do trustee accounting?",
            "Can my successor trustee also be a beneficiary?",
            "What minutes templates are available?",
            "How do I create minutes?",
            "Tell me about the trust office",
            "What is HEMS?",
        ):
            passages = tr.fetch_doctrine(message, limit=6, max_chars=4000)
            for p in passages:
                blob = f"{p.get('title','')} {p.get('section','')} {p.get('text','')}"
                assert not STALE_CLAIM.search(blob), (
                    f"the stale template-count claim surfaced for {message!r}: "
                    f"{STALE_CLAIM.search(blob).group(0)!r}"
                )

    def test_knowledge_slice_never_contains_the_stale_count(self):
        import chat_service as cs

        kb = cs.get_knowledge_base()
        for message in (
            "What minutes templates do you support?",
            "How do I create minutes?",
            "What are my duties as trustee?",
        ):
            slice_text = cs._ranked_knowledge_slice(
                message, "ask_knowledge", kb, []
            )
            assert not STALE_CLAIM.search(slice_text), (
                f"the stale template-count claim surfaced in the KB slice for "
                f"{message!r}"
            )

    def test_the_live_index_does_not_contain_the_stale_count(self):
        """The index that prod actually uses must be clean."""
        from services import trust_knowledge

        info = trust_knowledge.ensure_index()
        db_path = info["db_path"]
        assert os.path.isfile(db_path), f"no index at {db_path}"
        import sqlite3

        con = sqlite3.connect(db_path)
        try:
            for table in ("passages", "registry_items", "documents"):
                try:
                    rows = con.execute(
                        f"SELECT count(*) FROM {table} WHERE "
                        f"(body LIKE '%41 template%' OR body LIKE '%41 minutes%' "
                        f"OR summary LIKE '%41 template%' OR text LIKE '%41 template%')"
                    ).fetchone()[0]
                except sqlite3.Error:
                    continue
                assert rows == 0, (
                    f"table {table} in {db_path} still contains the stale "
                    f"'41 templates' claim ({rows} rows)"
                )
        finally:
            con.close()

    def test_knowledge_files_themselves_are_clean(self):
        """No KB file may carry the stale count (the P1 drift gate's job)."""
        for name in sorted(os.listdir(KNOWLEDGE_DIR)):
            if not name.endswith(".md"):
                continue
            text = open(
                os.path.join(KNOWLEDGE_DIR, name), "r", encoding="utf-8"
            ).read()
            assert not STALE_CLAIM.search(text), (
                f"{name} contains the stale '41 templates' claim"
            )


# --------------------------------------------------------------------------- #
# (d) The budget guard holds
# --------------------------------------------------------------------------- #

class TestBudgetGuard:
    def test_slice_plus_practice_core_stays_within_the_bar(self):
        """practice core + slice <= ~13K chars of the system prompt.

        This is the P1 bar: the system prompt (core + actions/escalation +
        practice core + brief + knowledge slice) must not grow because the
        slice is now relevance-ranked rather than truncated.
        """
        import chat_service as cs

        for message in (
            "What are my duties as trustee?",
            "How often should I do trustee accounting?",
            "Can my successor trustee also be a beneficiary?",
        ):
            kb = cs.get_knowledge_base()
            slice_text = cs._ranked_knowledge_slice(
                message, "ask_knowledge", kb, []
            )
            practice = cs.CHAT_SYSTEM_PRACTICE
            combined = len(practice) + len(slice_text)
            assert combined <= PROMPT_CHAR_BUDGET, (
                f"practice core + knowledge slice for {message!r} is "
                f"{combined} chars, over the {PROMPT_CHAR_BUDGET} bar "
                f"(practice {len(practice)} + slice {len(slice_text)})"
            )

    def test_doctrine_block_respects_the_retrieval_cap(self):
        """The doctrine block goes through the same 3,500-char cap."""
        import trust_retrieval as tr

        block = tr.RetrievalBlock()
        block.doctrine = tr.fetch_doctrine(
            "What are my duties as trustee? and also tell me about "
            "accounting, distributions, amendments, termination, "
            "successor trustees and HEMS, in great detail"
        )
        text = block.to_text()
        assert len(text) <= tr.MAX_RETRIEVAL_CHARS + 1, (
            f"doctrine block is {len(text)} chars, over the "
            f"{tr.MAX_RETRIEVAL_CHARS} cap"
        )

    def test_system_prompt_stays_under_the_p1_token_ceiling(self):
        """The full assembled system prompt must stay under the P1 ceiling."""
        import chat_service as cs

        ctx = {
            "trust": {"name": "Test Trust", "type": "revocable_living_trust"},
            "beneficiaries": [],
            "trustees": [],
            "state_compliance": {
                "state": "CA",
                "utc_adopted": "no",
                "accounting_frequency": "annual",
                "notice_required": True,
                "notice_timing_days": 30,
            },
        }
        for intent in ("ask_knowledge", "log_minutes"):
            prompt = cs._build_system_prompt(
                intent,
                "What are my duties as trustee?",
                ctx,
                [],
                stream_mode=True,
            )
            est = _tok(prompt)
            assert est < 13_000, (
                f"system prompt for intent={intent} is {est} tokens, over the "
                f"13,000 ceiling"
            )
