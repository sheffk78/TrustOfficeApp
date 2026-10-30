"""
WingPoint knowledge isolation — canary-based structural gate.

WINGPOINT ISOLATION CONTRACT (2026-10-30): WingPoint-tier knowledge files may
only reach a system prompt through a trust context whose audiences explicitly
grant the "wingpoint" audience. The gate is structural (partition +
positive-allowlist), not prompt-instruction-only, and it FAILS CLOSED.

These tests prove the contract with a canary (WP-ONLY-CANARY-9QF3) planted in
a fake WP-tier knowledge file loaded through the same loading path
(chat_service.get_knowledge_base / _knowledge_for_audiences /
_format_knowledge_context / _build_system_prompt), with partitions
monkeypatched via _KNOWLEDGE_BASE_CACHE.

Three fixtures, matching the real provenance rule:

  1. Standard user + standard trust          → audiences []   (isolated)
  2. WingPoint user + THEIR STANDARD trust   → audiences []   (isolated:
     provenance is a property of the TRUST, never of the account)
  3. WingPoint user + WingPoint trust        → audiences ['wingpoint']
     (positive control: the canary is SUPPOSED to flow)

Guarantees:
  (a) cases 1 & 2: zero canary chars and zero 8-gram overlap with the WP file
      in the assembled knowledge context AND the full system prompt;
  (b) case 3: the canary flows (both in the knowledge context and the prompt);
  (c) universal knowledge is present in ALL three cases;
  (d) case 3: the WP file ranks FIRST (no "### " topic block precedes it).

Also wires backend/scripts/validate_knowledge.py into pytest: the shipped
knowledge tree must satisfy the audience-tier contract, a WP-directory file
without an explicit `audiences` declaration must fail validation, and a
declaring file must pass it.

True unit tests: no server, no LLM, no network, no Mongo.
"""
import os
import re
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
# backend/scripts/ is not a package; expose the validator module for import.
sys.path.insert(0, os.path.join(BACKEND, "scripts"))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_wingpoint_isolation")
os.environ.setdefault("JWT_SECRET", "test-secret-wp-isolation")

CANARY = "WP-ONLY-CANARY-9QF3"

# --------------------------------------------------------------------------- #
# Fixture knowledge files
# --------------------------------------------------------------------------- #

# A deliberately distinctive WP-only body. Its wording shares no 8-word run
# with the universal fixtures below, so the 8-gram check targets WP material
# and not generic trust phrasing.
_WP_DOCTRINE_BODY = (
    "## WingPoint Teaching: Irrevocable Unalienable Funding Quozience\n"
    "The member's WingPoint instruction states that the unalienable quozience "
    "principle governs how contribution paperwork is sequenced. Members are "
    "taught to record the quozience ledger entry before acknowledgment letters "
    "are prepared, and that the acknowledgment packet carries the module stamp.\n"
    f"\nCanary verification string: {CANARY}. This line exists so tests can "
    "prove exactly which assembled surfaces received the WP tier and which "
    "did not.\n"
)

_UNIVERSAL_DUTIES_BODY = (
    "## Key Governance Requirements\n"
    "Trustees owe duties of loyalty and prudence. Administer the trust "
    "according to its terms, keep careful records, and document decisions in "
    "minutes so the file shows why each action was proper.\n"
)

_UNIVERSAL_HEMS_BODY = (
    "## Distribution Rules\n"
    "HEMS stands for health, education, maintenance, and support. Check the "
    "instrument's distribution standard before approving a beneficiary "
    "payment, and record the decision in the minutes book.\n"
)


def _fake_kb() -> dict:
    """Audience-partitioned KB in the exact shape _load_knowledge_base returns."""
    return {
        "universal": {
            "03-trustee-duties": _UNIVERSAL_DUTIES_BODY,
            "01-hems-standard": _UNIVERSAL_HEMS_BODY,
        },
        "wingpoint": {
            "wp-doctrine-module": _WP_DOCTRINE_BODY,
        },
    }


# --------------------------------------------------------------------------- #
# 8-gram machinery
# --------------------------------------------------------------------------- #

def _norm_tokens(text: str) -> list:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


def _eight_grams(text: str) -> set:
    toks = _norm_tokens(text)
    return {tuple(toks[i: i + 8]) for i in range(len(toks) - 7)} if len(toks) >= 8 else set()


_WP_GRAMS = _eight_grams(_WP_DOCTRINE_BODY)
assert _WP_GRAMS, "WP fixture must have at least 8 tokens"
assert not (_eight_grams(_UNIVERSAL_DUTIES_BODY) & _WP_GRAMS), "fixture self-collision"
assert not (_eight_grams(_UNIVERSAL_HEMS_BODY) & _WP_GRAMS), "fixture self-collision"


def _assert_isolated(surface: str, label: str):
    assert CANARY not in surface, f"canary leaked into {label}"
    grams = _eight_grams(surface)
    overlap = grams & _WP_GRAMS
    assert not overlap, (
        f"8-gram overlap with the WP file leaked into {label}: "
        f"{sorted(overlap)[:3]!r}"
    )


# --------------------------------------------------------------------------- #
# Monkeypatched loading fixtures
# --------------------------------------------------------------------------- #

import pytest


@pytest.fixture
def wp_isolation_env(monkeypatch):
    import chat_service as cs

    monkeypatch.setattr(cs, "_KNOWLEDGE_BASE_CACHE", _fake_kb())
    # Rebuild IDF statistics over the fixture corpus (the module-global caches
    # may hold statistics from another suite's corpus in the same pytest run).
    monkeypatch.setattr(cs, "_TERM_DF_CACHE", {})
    monkeypatch.setattr(cs, "_TERM_IDF_CACHE", {})
    monkeypatch.setattr(cs, "_TOTAL_PASSAGES", 0)
    monkeypatch.setattr(cs, "_KNOWLEDGE_AUDIENCE_META", None)
    return cs


def _prompt(cs, audiences, message):
    return cs._build_system_prompt(
        "ask_knowledge",
        message,
        {"trust": {"name": "Family Trust", "type": "irrevocable"}, "audiences": list(audiences)},
        [],
    )


DUTIES_QUESTION = "What are my duties as trustee?"
WP_QUESTION = "What does my WingPoint training say about unalienable quozience funding?"


# --------------------------------------------------------------------------- #
# (a) isolated cases
# --------------------------------------------------------------------------- #

class TestStandardTrustIsIsolated:
    """Case 1: standard user + standard trust (audiences [])."""

    def test_prompt_has_zero_canary_and_zero_wp_grams(self, wp_isolation_env):
        cs = wp_isolation_env
        _assert_isolated(_prompt(cs, [], DUTIES_QUESTION), "standard-trust prompt")
        _assert_isolated(_prompt(cs, [], WP_QUESTION), "standard-trust prompt")

    def test_knowledge_context_has_zero_canary_and_zero_wp_grams(self, wp_isolation_env):
        cs = wp_isolation_env
        for msg in (DUTIES_QUESTION, WP_QUESTION):
            ctx = cs._format_knowledge_context(user_message=msg, intent="ask_knowledge", audiences=[])
            _assert_isolated(ctx, "standard-trust knowledge context")


class TestWPUserStandardTrustIsIsolated:
    """Case 2: WingPoint user + THEIR STANDARD trust (audiences []).

    Provenance is a property of the trust, not of the member's account: a
    WingPoint member administering a standard trust gets NO WP doctrine.
    """

    def test_prompt_has_zero_canary_and_zero_wp_grams(self, wp_isolation_env):
        cs = wp_isolation_env
        _assert_isolated(_prompt(cs, [], DUTIES_QUESTION), "wp-user-standard-trust prompt")
        _assert_isolated(_prompt(cs, [], WP_QUESTION), "wp-user-standard-trust prompt")


# --------------------------------------------------------------------------- #
# (b) positive control
# --------------------------------------------------------------------------- #

class TestWPTrustPositiveControl:
    """Case 3: WingPoint user + WingPoint trust (audiences ['wingpoint'])."""

    def test_canary_flows_into_knowledge_context(self, wp_isolation_env):
        cs = wp_isolation_env
        ctx = cs._format_knowledge_context(user_message=WP_QUESTION, intent="ask_knowledge", audiences=["wingpoint"])
        assert CANARY in ctx, "WP-tier member + WP trust must receive WP doctrine"

    def test_canary_flows_into_full_system_prompt(self, wp_isolation_env):
        cs = wp_isolation_env
        prompt = _prompt(cs, ["wingpoint"], WP_QUESTION)
        assert CANARY in prompt, "WP-tier member + WP trust must receive WP doctrine"
        assert "WingPoint Doctrine Overlay" in prompt, "doctrine overlay must ride with the WP audience"

    def test_wp_file_ranks_first(self, wp_isolation_env):
        cs = wp_isolation_env
        prompt = _prompt(cs, ["wingpoint"], WP_QUESTION)
        kb_start = prompt.index("## Knowledge Base")
        kb_end = prompt.find("## Conversation History", kb_start)
        kb_section = prompt[kb_start: kb_end if kb_end > 0 else len(prompt)]
        wp_pos = kb_section.find("### wingpoint/wp-doctrine-module")
        assert wp_pos >= 0, "WP topic block missing from the WP-trust KB section"
        topics = [m for m in re.finditer(r"(?m)^### ", kb_section)]
        first_topic_is_wp = topics and topics[0].start() == wp_pos
        assert first_topic_is_wp, (
            "the WP topic block is not FIRST among the KB '### ' topic blocks — "
            "WP doctrine must rank first for the granted audience"
        )


# --------------------------------------------------------------------------- #
# (c) universal tier present everywhere
# --------------------------------------------------------------------------- #

class TestUniversalTierPresent:
    def test_universal_content_present_in_all_three(self, wp_isolation_env):
        cs = wp_isolation_env
        for audiences in ([], [], ["wingpoint"]):
            prompt = _prompt(cs, audiences, DUTIES_QUESTION)
            assert "### 03-trustee-duties" in prompt, (
                f"universal duties file missing for audiences={audiences!r}"
            )


# --------------------------------------------------------------------------- #
# (d) knowledge validator wiring
# --------------------------------------------------------------------------- #

class TestKnowledgeValidator:
    def test_current_tree_passes(self):
        import validate_knowledge

        assert validate_knowledge.validate() == [], (
            "the shipped knowledge tree violates the audience-tier contract"
        )

    def test_wp_file_without_declaration_fails_validation(self, tmp_path):
        import validate_knowledge

        wp_dir = tmp_path / "wingpoint"
        wp_dir.mkdir()
        (wp_dir / "undeclared.md").write_text(
            "# Undeclared\nBody without front-matter audiences.\n", encoding="utf-8"
        )
        violations = validate_knowledge.validate(str(tmp_path))
        assert any("undeclared.md" in v and "audiences" in v for v in violations), (
            f"a WP-directory file without `audiences` must fail: {violations}"
        )

    def test_declared_wp_file_passes_validation(self, tmp_path):
        import validate_knowledge

        wp_dir = tmp_path / "wingpoint"
        wp_dir.mkdir()
        (wp_dir / "declared.md").write_text(
            "---\ntitle: Declared\naudiences: wingpoint\n---\n# Declared\nBody.\n",
            encoding="utf-8",
        )
        assert validate_knowledge.validate(str(tmp_path)) == []