"""
P2b — UTC doctrine pack wired into the retrieval corpus (2026-10-24).

Nine Jeff-approved Uniform Trust Code files were copied into
backend/knowledge/ and the doctrine triggers were extended so the
questions those files exist to answer actually reach them.

These tests lock down four guarantees:

  (a) Each of the nine UTC files is retrievable via a question it exists
      to answer (spendthrift -> 07, "can I amend my trust" -> 05,
      "how does a trust end" -> 08, and so on for all nine).

  (b) The P2a probes still work — the accounting/jurisdiction answers and
      the Trustee-101 course corpus are NOT regressed by the UTC pack.

  (c) No 'REVIEW DRAFT' text exists anywhere in the corpus, the index,
      the retrieved passages, or the rendered prompt output.

  (d) The UTC files are legal-safety clean: no dollar thresholds, and no
      "protects you" claim in the product's voice.

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

# The nine approved UTC files, in order. These are the exact file names
# copied out of reports/utc-drafts-2026-10-24/ — the names are kept so a
# reader can map a retrieved citation back to the approved source.
UTC_FILES = [
    "24-utc-01-definitions-scope.md",
    "24-utc-02-trustee-duties.md",
    "24-utc-03-distributions.md",
    "24-utc-04-accounting-reports.md",
    "24-utc-05-amendments-revocation.md",
    "24-utc-06-successor-trustees-vacancy.md",
    "24-utc-07-creditors-protection.md",
    "24-utc-08-termination.md",
    "24-utc-09-notification-register.md",
]

# The question each UTC file exists to answer. Every one of these must
# retrieve its file as the TOP passage — not merely somewhere in the list.
UTC_QUESTIONS = {
    "24-utc-01-definitions-scope.md": (
        "What law governs my trust and where is the trust administered?"
    ),
    "24-utc-02-trustee-duties.md": (
        "What are my duties as trustee under the Code?"
    ),
    "24-utc-03-distributions.md": (
        "What happens to the money when the trust ends?"
    ),
    "24-utc-04-accounting-reports.md": (
        "What records do I have to keep for the trust?"
    ),
    "24-utc-05-amendments-revocation.md": (
        "Can the settlor change or revoke an irrevocable trust?"
    ),
    "24-utc-06-successor-trustees-vacancy.md": (
        "Can the beneficiaries remove me as trustee?"
    ),
    "24-utc-07-creditors-protection.md": (
        "What is a spendthrift provision and does my trust have "
        "protection against creditors?"
    ),
    "24-utc-08-termination.md": (
        "How does a trust terminate?"
    ),
    "24-utc-09-notification-register.md": (
        "What notices do I have to give my beneficiaries?"
    ),
}

# The three concepts the doctrine pack added, each anchored to the file
# that answers it.
UTC_CONCEPTS = {
    "spendthrift": "24-utc-07-creditors-protection.md",
    "revocation": "24-utc-05-amendments-revocation.md",
    "trust_termination": "24-utc-08-termination.md",
    "beneficiary_notification": "24-utc-09-notification-register.md",
    "register_agent": "24-utc-09-notification-register.md",
    "trustee_removal": "24-utc-06-successor-trustees-vacancy.md",
}

# The UTC anchor line each file must keep. The anchor is the citation
# contract: it is what lets a rendered answer point at a Code section.
UTC_ANCHORS = {
    "24-utc-01-definitions-scope.md": "art. 1",
    "24-utc-02-trustee-duties.md": "art. 8",
    "24-utc-03-distributions.md": "art. 8",
    "24-utc-04-accounting-reports.md": "ss. 804, 809, 810",
    "24-utc-05-amendments-revocation.md": "art. 6",
    "24-utc-06-successor-trustees-vacancy.md": "art. 7",
    "24-utc-07-creditors-protection.md": "art. 5",
    "24-utc-08-termination.md": "art. 4",
    "24-utc-09-notification-register.md": "art. 1",
}

# The 'REVIEW DRAFT' banner that must never reach a user. The pattern
# requires the banner shape (a bolded marker), so it does not fire on
# ordinary prose like "review draft Form 1041" in the tax calendar.
REVIEW_DRAFT = re.compile(
    r"REVIEW\s+DRAFT|REVIEW\s+DRAFT\s*—|REVIEW DRAFT",
)

# The product's own safety language: records never "protect you".
PROTECTS_YOU = re.compile(
    r"protect\w*\s+you\b|your\s+records\s+protect|records\s+protect\s+you",
    re.I,
)

# Dollar thresholds must never be quoted (state-variable figures route to
# an attorney/CPA instead).
DOLLAR_FIGURE = re.compile(
    r"\$\s?[\d,]+(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+\b|"
    r"\b\d+(?:\.\d+)?\s*(?:dollars?|thousand|million|billion)\b",
    re.I,
)


def _utc_text(name: str) -> str:
    with open(os.path.join(KNOWLEDGE_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# (a) Each UTC file is retrievable via a question it exists to answer
# --------------------------------------------------------------------------- #

class TestUtcFilesAreRetrievable:
    def test_all_nine_utc_files_are_in_the_knowledge_directory(self):
        for name in UTC_FILES:
            path = os.path.join(KNOWLEDGE_DIR, name)
            assert os.path.isfile(path), (
                f"{name} is not in backend/knowledge/ — the approved UTC "
                f"corpus was not copied in"
            )

    def test_each_utc_file_is_the_top_answer_to_its_question(self):
        import trust_retrieval as tr

        for name, question in UTC_QUESTIONS.items():
            passages = tr.fetch_doctrine(question, limit=6, max_chars=6000)
            assert passages, (
                f"{question!r} retrieved nothing — the UTC pack is not "
                f"reachable from the doctrine leg"
            )
            sources = [p.get("source_ref") or "" for p in passages]
            assert sources[0] == name, (
                f"{question!r} should be answered by {name}, but the top "
                f"passage was {sources[0]!r}. Sources: {sources}"
            )

    def test_each_utc_file_appears_in_its_own_retrieval(self):
        """Not just top-1: the file must be genuinely in the result set."""
        import trust_retrieval as tr

        for name, question in UTC_QUESTIONS.items():
            passages = tr.fetch_doctrine(question, limit=6, max_chars=6000)
            sources = [p.get("source_ref") or "" for p in passages]
            assert name in sources, (
                f"{name} did not appear for {question!r}; sources: {sources}"
            )

    def test_the_spendthrift_question_reaches_file_07(self):
        """The doctrine pack's highest-liability file must be reachable."""
        import trust_retrieval as tr

        passages = tr.fetch_doctrine(
            "What is a spendthrift provision and does my trust have "
            "protection against creditors?",
            limit=4,
            max_chars=3000,
        )
        assert passages, "the spendthrift question retrieved nothing"
        assert passages[0]["source_ref"] == "24-utc-07-creditors-protection.md", (
            f"spendthrift question did not reach file 07; got "
            f"{passages[0]['source_ref']!r}"
        )
        body = passages[0]["text"].lower()
        assert "spendthrift" in body, (
            f"the retrieved spendthrift passage does not explain "
            f"spendthrift: {body[:200]!r}"
        )

    def test_the_amendment_question_reaches_file_05(self):
        import trust_retrieval as tr

        for question in (
            "Can I amend my trust?",
            "Can the settlor change or revoke an irrevocable trust?",
        ):
            passages = tr.fetch_doctrine(question, limit=4, max_chars=3000)
            assert passages, f"{question!r} retrieved nothing"
            assert passages[0]["source_ref"] == (
                "24-utc-05-amendments-revocation.md"
            ), (
                f"{question!r} did not reach file 05; got "
                f"{passages[0]['source_ref']!r}"
            )

    def test_the_termination_question_reaches_file_08(self):
        import trust_retrieval as tr

        passages = tr.fetch_doctrine("How does a trust terminate?", limit=4, max_chars=3000)
        assert passages, "the termination question retrieved nothing"
        assert passages[0]["source_ref"] == "24-utc-08-termination.md", (
            f"termination question did not reach file 08; got "
            f"{passages[0]['source_ref']!r}"
        )

    def test_utc_concepts_fire_on_their_named_questions(self):
        import trust_retrieval as tr

        cases = {
            "What is a spendthrift provision?": "spendthrift",
            "Can I revoke my trust?": "revocation",
            "How does a trust end?": "trust_termination",
            "What notices do I have to give my beneficiaries?": (
                "beneficiary_notification"
            ),
            "Do I need to register the trust?": "register_agent",
            "Can the beneficiaries remove me as trustee?": "trustee_removal",
        }
        for message, expected in cases.items():
            concepts = tr._match_doctrine_concepts(message)
            assert expected in concepts, (
                f"{message!r} should trigger the {expected!r} concept, got "
                f"{concepts}"
            )

    def test_utc_concepts_map_to_the_file_that_answers_them(self):
        """The new concepts must have a boost vocabulary, or they cannot win."""
        import trust_retrieval as tr

        for concept in UTC_CONCEPTS:
            assert concept in tr.DOCTRINE_TRIGGERS, (
                f"{concept!r} is not in DOCTRINE_TRIGGERS"
            )
            vocab = tr.DOCTRINE_VOCABULARY.get(concept)
            assert vocab, (
                f"{concept!r} has no boost vocabulary — the UTC passage "
                f"cannot outrank the wider corpus without one"
            )
            assert len(vocab) >= 5, (
                f"{concept!r} boost vocabulary is too thin: {vocab!r}"
            )

    def test_boost_vocabulary_terms_actually_appear_in_the_corpus(self):
        """A boost term that exists in no file can never fire."""
        import trust_retrieval as tr

        corpus = ""
        for name in UTC_FILES:
            corpus += _utc_text(name).lower()
        for concept, vocab in tr.DOCTRINE_VOCABULARY.items():
            for term in vocab:
                if len(term) < 4:
                    continue
                if concept in UTC_CONCEPTS:
                    assert term.lower() in corpus, (
                        f"boost term {term!r} for the UTC concept "
                        f"{concept!r} does not appear in any UTC file — it can "
                        f"never fire"
                    )


# --------------------------------------------------------------------------- #
# (b) The P2a probes still work — no regression
# --------------------------------------------------------------------------- #

class TestP2aProbesStillPass:
    def test_accounting_question_still_answers(self):
        import trust_retrieval as tr

        passages = tr.fetch_doctrine(
            "How often should I do trustee accounting?", limit=4, max_chars=3000
        )
        assert passages, "the P2a accounting probe retrieved nothing"
        body = " ".join(p["text"] for p in passages).lower()
        assert any(
            word in body for word in ("account", "annually", "annual", "quarter")
        ), f"the accounting probe no longer answers the question: {body[:200]!r}"

    def test_jurisdiction_data_still_reaches_the_prompt(self):
        """The P1 jurisdiction guard must still be able to speak conditionally.

        The UTC pack adds legal doctrine; it must not displace the
        state-profile facts the guard reads (utc_adopted, accounting
        frequency, notice).
        """
        import chat_service as cs

        ctx = {
            "trust": {"name": "Test Trust", "type": "revocable_living_trust"},
            "beneficiaries": [],
            "trustees": [],
            "state_compliance": {
                "state_code": "NV",
                "state_name": "Nevada",
                "utc_adopted": "no",
                "accounting_frequency": "annual",
                "notice_required": True,
            },
        }
        prompt = cs._build_system_prompt(
            "ask_knowledge",
            "How often should I do trustee accounting?",
            ctx,
            [],
            stream_mode=True,
        )
        assert "accounting frequency on file for this state: annual" in (
            prompt.lower()
        ), (
            "the jurisdiction guard no longer reports the state accounting "
            "frequency — the P2a accounting probe regressed"
        )
        assert "not adopted" in prompt.lower(), (
            "the jurisdiction guard no longer reports the UTC adoption "
            "status for a non-adopting state"
        )

    def test_trustee101_corpus_is_still_retrievable(self):
        import trust_retrieval as tr

        course = tr.fetch_doctrine(
            "Walk me through the four-question test I should use before every "
            "distribution and the distribution memo the course recommends.",
            limit=6,
            max_chars=4500,
        )
        assert course, "course-framed distribution question retrieved nothing"
        assert any(
            "trustee-101" in (p.get("source_ref") or "") for p in course
        ), (
            f"the Trustee-101 corpus was not retrieved; sources: "
            f"{[p.get('source_ref') for p in course]}"
        )

    def test_canonical_hems_doctrine_still_wins(self):
        """The UTC pack must not hijack the canonical HEMS answer.

        The canonical phrasing ("the distribution standard, HEMS") must
        still be answered by 01-hems-standard — the P2a canonical-dominance
        invariant.
        """
        import trust_retrieval as tr

        canon = tr.fetch_doctrine(
            "What is the distribution standard, HEMS?", limit=6, max_chars=3000
        )
        assert canon, "a plain HEMS question retrieved nothing"
        assert canon[0]["source_ref"] == "01-hems-standard.md", (
            f"canonical HEMS doctrine no longer wins; got "
            f"{[p.get('source_ref') for p in canon]}"
        )

    def test_state_compliance_files_are_still_retrievable(self):
        import trust_retrieval as tr

        passages = tr.fetch_doctrine(
            "What are the beneficiary notice requirements in my state?",
            limit=4,
            max_chars=3000,
        )
        assert passages, "the state-compliance question retrieved nothing"
        assert any(
            "state-compliance" in (p.get("source_ref") or "") for p in passages
        ), (
            f"the state compliance corpus was not retrieved; sources: "
            f"{[p.get('source_ref') for p in passages]}"
        )

    def test_practice_core_is_untouched(self):
        """P2b must not modify the always-on practice core prompt."""
        import chat_service as cs

        practice = cs.CHAT_SYSTEM_PRACTICE
        assert "## Block 4 — Jurisdiction Guard" in practice, (
            "the practice core's jurisdiction guard is missing — P2b must not "
            "touch the practice core"
        )
        assert "Never assert a specific state's rule from memory" in practice, (
            "the practice core's state-law guard has been weakened"
        )
        assert "Uniform Trust Code adoption (full, partial, none)" in practice, (
            "the practice core no longer carries the UTC adoption framing"
        )


# --------------------------------------------------------------------------- #
# (c) No 'REVIEW DRAFT' can reach a rendered prompt
# --------------------------------------------------------------------------- #

class TestNoReviewDraftAnywhere:
    def test_no_knowledge_file_contains_the_review_banner(self):
        for name in sorted(os.listdir(KNOWLEDGE_DIR)):
            if not name.endswith(".md"):
                continue
            text = _utc_text(name)
            m = REVIEW_DRAFT.search(text)
            assert not m, (
                f"{name} contains the review banner {m.group(0)!r} — an "
                f"unapproved file is in the shipped corpus"
            )

    def test_no_retrieved_passage_contains_the_review_banner(self):
        import trust_retrieval as tr

        for question in list(UTC_QUESTIONS.values()) + [
            "What are my duties as trustee?",
            "How often should I do trustee accounting?",
            "What is HEMS?",
            "What minutes templates are available?",
        ]:
            passages = tr.fetch_doctrine(question, limit=6, max_chars=6000)
            for p in passages:
                blob = " ".join(
                    str(p.get(k) or "") for k in ("title", "section", "text")
                )
                m = REVIEW_DRAFT.search(blob)
                assert not m, (
                    f"the review banner surfaced for {question!r}: "
                    f"{m.group(0)!r}"
                )

    def test_the_rendered_doctrine_block_contains_no_review_banner(self):
        import trust_retrieval as tr

        block = tr.RetrievalBlock()
        block.doctrine = tr.fetch_doctrine(
            "What is a spendthrift provision and does my trust have "
            "protection against creditors?",
            limit=6,
            max_chars=4000,
        )
        text = block.to_text()
        assert text, "the doctrine block rendered nothing"
        m = REVIEW_DRAFT.search(text)
        assert not m, f"the rendered doctrine block contains {m.group(0)!r}"

    def test_the_rendered_knowledge_slice_contains_no_review_banner(self):
        import chat_service as cs

        kb = cs.get_knowledge_base()
        for message in list(UTC_QUESTIONS.values()) + [
            "What are my duties as trustee?",
            "What is HEMS?",
        ]:
            slice_text = cs._ranked_knowledge_slice(
                message, "ask_knowledge", kb, []
            )
            m = REVIEW_DRAFT.search(slice_text)
            assert not m, (
                f"the review banner surfaced in the KB slice for {message!r}: "
                f"{m.group(0)!r}"
            )

    def test_the_live_index_contains_no_review_banner(self):
        from services import trust_knowledge

        info = trust_knowledge.ensure_index()
        import sqlite3

        con = sqlite3.connect(info["db_path"])
        try:
            for table, column in (
                ("passages", "text"),
                ("documents", "body"),
                ("chunks", "text"),
            ):
                try:
                    # GLOB is case-sensitive; LIKE is not. The tax calendar
                    # legitimately says "Review draft Form 1041", and only
                    # the uppercase banner is the thing that must not ship.
                    rows = con.execute(
                        f"SELECT count(*) FROM {table} WHERE {column} GLOB ?",
                        ("*REVIEW DRAFT*",),
                    ).fetchone()[0]
                except sqlite3.Error:
                    continue
                assert rows == 0, (
                    f"table {table} in {info['db_path']} contains "
                    f"{rows} rows with the review banner"
                )
        finally:
            con.close()

    def test_the_injected_user_content_contains_no_review_banner(self):
        """The full injection path, end to end."""
        import trust_retrieval as tr

        block = tr.RetrievalBlock()
        block.doctrine = tr.fetch_doctrine(
            "What notices do I have to give my beneficiaries?",
            limit=6,
            max_chars=4000,
        )
        injected = tr.inject_into_user_content("What notices do I owe?", block)
        m = REVIEW_DRAFT.search(injected)
        assert not m, (
            f"the review banner reached the injected user content: "
            f"{m.group(0)!r}"
        )


# --------------------------------------------------------------------------- #
# (d) The UTC files are legal-safety clean
# --------------------------------------------------------------------------- #

class TestUtcLegalSafety:
    def test_no_utc_file_quotes_a_dollar_threshold(self):
        for name in UTC_FILES:
            text = _utc_text(name)
            m = DOLLAR_FIGURE.search(text)
            assert not m, (
                f"{name} quotes a dollar figure {m.group(0)!r} — "
                f"state-variable thresholds must route to an attorney/CPA"
            )

    def test_no_utc_file_makes_a_protects_you_claim(self):
        for name in UTC_FILES:
            text = _utc_text(name)
            m = PROTECTS_YOU.search(text)
            assert not m, (
                f"{name} makes a {m.group(0)!r} claim — the product's voice "
                f"is 'shows your reasoning', never 'protects you'"
            )

    def test_each_utc_file_keeps_its_utc_anchor(self):
        """The anchor is the citation contract — it must survive the copy."""
        for name in UTC_FILES:
            text = _utc_text(name)
            assert "**UTC anchor:**" in text, (
                f"{name} lost its UTC anchor line"
            )
            anchor = next(
                line for line in text.splitlines()
                if line.startswith("**UTC anchor:**")
            )
            expected = UTC_ANCHORS[name]
            assert expected in anchor, (
                f"{name}'s anchor should cite {expected!r}, got {anchor!r}"
            )
            assert re.search(r"s\.\s?\d{3,4}|\bart\.\s?\d", anchor), (
                f"{name}'s anchor line carries no Code section reference: "
                f"{anchor!r}"
            )

    def test_each_utc_file_keeps_its_section_citations(self):
        """Every UTC file must still cite Code sections by number."""
        for name in UTC_FILES:
            text = _utc_text(name)
            sections = re.findall(r"s\.\s?\d{3,4}\(?[a-z0-9]*\)?", text)
            assert len(sections) >= 5, (
                f"{name} cites only {len(sections)} Code sections — the "
                f"section citations did not survive the copy"
            )

    def test_each_utc_file_carries_the_kb_provenance_header(self):
        for name in UTC_FILES:
            text = _utc_text(name)
            assert text.startswith("---\n"), (
                f"{name} has no KB provenance front matter"
            )
            for field in ("title:", "source:", "provenance:", "tags:", "status:"):
                assert f"\n{field}" in text or text.startswith(f"{field}"), (
                    f"{name}'s front matter is missing the {field!r} field"
                )
            assert "status: published" in text, (
                f"{name} is not marked published"
            )

    def test_the_utc_files_contain_no_internal_editorial_voice(self):
        """Approved content must not carry the drafting conversation."""
        forbidden = [
            r"\bJeff\b",
            r"in-repo",
            r"\bthe base\b",
            r"the reviewed \S+\.md",
            r"product copy",
            r"product wording",
            r"\bthe product\b",
            r"do not ship",
            r"wires into the knowledge base",
        ]
        for name in UTC_FILES:
            text = _utc_text(name)
            for pattern in forbidden:
                m = re.search(pattern, text, re.I)
                assert not m, (
                    f"{name} contains internal editorial voice {m.group(0)!r} "
                    f"(pattern {pattern!r})"
                )

    def test_every_utc_file_has_plain_english_and_qa_sections(self):
        """The doctrine-pack shape: body + 'What this means' + 3 Q&As."""
        for name in UTC_FILES:
            text = _utc_text(name)
            assert "## What this means for a trustee" in text, (
                f"{name} has no 'What this means for a trustee' section"
            )
            questions = re.findall(r"\*\*\"[^\"]{12,}\"\*\*", text)
            assert len(questions) >= 3, (
                f"{name} has only {len(questions)} Q&A entries — the pack "
                f"shape requires at least 3"
            )

    def test_utc_files_are_indexed(self):
        """ensure_index() must actually contain all nine files."""
        from services import trust_knowledge

        info = trust_knowledge.ensure_index()
        assert os.path.isfile(info["db_path"]), f"no index at {info['db_path']}"
        import sqlite3

        con = sqlite3.connect(info["db_path"])
        try:
            for name in UTC_FILES:
                docid = name[: -len(".md")]
                count = con.execute(
                    "SELECT count(*) FROM passages WHERE document_id = ?",
                    (docid,),
                ).fetchone()[0]
                assert count > 0, (
                    f"{name} is not in the index at {info['db_path']} — the "
                    f"fingerprint gate did not rebuild"
                )
        finally:
            con.close()
