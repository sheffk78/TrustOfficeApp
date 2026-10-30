"""On-demand retrieval layer for the Trust Assistant (Layer 2).

Council-approved two-layer architecture (2026-09-14): the Trust Brief
(trust_brief.py) is always in context; everything beyond it is fetched here,
per turn, only when the question needs it. Detail enters context for that
turn and is discarded — flat cost regardless of account size.

Design constraints:
- ai_client has no native function-calling, so retrieval is triggered by
  deterministic patterns (intent + regex), not an agentic loop. The public
  surface (RetrievalBlock) is designed so an agentic loop can replace the
  trigger logic later without changing call sites.
- All queries are trust-scoped (trust_id + user_id) — strict multi-trust
  isolation, matching the conversation-pinning fix.
- Retrieval results carry citation metadata (meeting date, doc title + date)
  so the assistant cites sources, per the citation-integrity protocol.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

MAX_RETRIEVAL_CHARS = 3500  # per-turn cap on all injected retrieval blocks

# --------------------------------------------------------------------------- #
# Layer 2b — doctrine retrieval (2026-10-23, P2a)
#
# The doctrine corpus is backend/knowledge/*.md, indexed by the FTS5 index in
# services/trust_knowledge.py. A doctrine question triggers a deterministic
# keyword/regex match; the matching concepts become an FTS query; the TOP
# matching passages come back and are injected with their source file, so the
# assistant can cite them.
#
# The corpus is entirely reviewed material: the Trustee-101 course (6 legal
# review rounds) and the in-repo knowledge base. Nothing here adds legal
# text — it only selects which reviewed passage to show.
# --------------------------------------------------------------------------- #

# Doctrine concept -> the regex patterns that mean "this member is asking
# about that concept". Keys are concept names; values are (regex, extra FTS
# query terms).
DOCTRINE_TRIGGERS: dict[str, tuple[str, ...]] = {
    "duties": (
        r"\bmy\s+dut(y|ies)\b",
        r"\btrustee\s+dut(y|ies)\b",
        r"\bfiduciary\s+dut(y|ies)\b",
        r"\bwhat\s+(am\s+i|do\s+i)\s+(supposed|required|obligated)\b",
        r"\bwhat\s+are\s+my\s+(obligations|responsibilit)",
        r"\bam\s+i\s+allowed\s+to\b",
        r"\bcan\s+i\s+(as\s+a\s+trustee|self-deal|deal\s+with)",
    ),
    "utc": (
        r"\buniform\s+trust\s+code\b",
        r"\butc\b",
        r"\btrust\s+code\b",
        r"\bqualified\s+beneficiar",
        r"\bterms\s+of\s+(a|the)\s+trust\b",
        r"\bascertainable\s+standard\b",
        r"\bwhat\s+law\s+governs\b",
        r"\bwhich\s+(state's\s+)?law\s+(applies|governs)\b",
        r"\bwhere\s+is\s+(my|the)\s+trust\s+(administered|run|located)\b",
        r"\bdoes\s+the\s+(utc|trust\s+code)\s+apply\b",
        r"\bis\s+my\s+trust\s+(covered|subject)\b",
        r"\bgoverning\s+law\b",
        r"\bprincipal\s+place\s+of\s+administration\b",
    ),
    "amendment": (
        r"\bamend(ment|ments|ing)?\b",
        r"\bmodify\s+(the\s+)?trust\b",
        r"\bchange\s+the\s+trust\b",
        r"\bmodification\b",
    ),
    "successor_trustee": (
        r"\bsuccessor\s+trustee\b",
        r"\bsuccession\b",
        r"\bnext\s+trustee\b",
        r"\breplace\s+(me|my\s+trustee|the\s+trustee)\b",
        r"\bresign(ation)?\b",
        r"\bstep\s+down\s+as\s+trustee\b",
    ),
    "distribution_standard": (
        r"\bdistribution\s+standard\b",
        r"\bhems\b",
        r"\bsole\s+discretion\b",
        r"\bstandard\s+of\s+care\b",
        r"\bwhat\s+can\s+i\s+(give|distribute|distribute\s+to)\b",
        r"\bhow\s+(much|many)\s+can\s+i\s+(give|distribute)\b",
        r"\bcan\s+i\s+distribute\s+(to|any|some)\b",
        r"\bhow\s+much\s+(can|should)\s+i\s+distribute\b",
        r"\bdiscretion\b",
        r"\bdiscretionary\s+(distribution|trust|payment)\b",
        r"\bpower\s+of\s+withdrawal\b",
        r"\bwhat\s+discretion\b",
        r"\bmandatory\s+distribution\b",
        r"\bevery\s+distribution\b",
        r"\bbefore\s+(every|each|a|the)\s+distribution\b",
        r"\bdistribution\s+memo\b",
        r"\b(four|4)[\s-]*question\s+(test|checklist|framework)\b",
    ),
    "accounting": (
        r"\baccounting\b",
        r"\bhow\s+often\b",
        r"\bhow\s+frequently\b",
        r"\bannual\s+report\s+to\s+beneficiar",
        r"\bbeneficiar(y|ies)\s+(notice|report)",
        r"\bkeep\s+(trust\s+)?records\b",
        r"\brecord-?keeping\b",
        r"\btrust\s+records\b",
        r"\bwhat\s+records\b",
        r"\bformal\s+accounting\b",
        r"\binformal\s+accounting\b",
        r"\bwritten\s+accounting\b",
        r"\baccounting\s+to\s+(my|our|the)\s+beneficiar",
        r"\bannual\s+accounting\b",
    ),
    "termination": (
        r"\bterminat(e|ion|ing)\b",
        r"\bwind\s*-?\s*down\b",
        r"\bclose\s+the\s+trust\b",
        r"\bfinal\s+distribution\b",
    ),
    "beneficiary_communication": (
        r"\bnotify\s+(the\s+)?beneficiar",
        r"\btell\s+(the\s+)?beneficiar",
        r"\bbeneficiar(y|ies)\s+(letter|communication|notice)",
        r"\bletter\s+to\s+(my\s+)?beneficiar",
    ),
    "commingling": (
        r"\bcommingl",
        r"\bseparation\b",
        r"\bpersonal\s+(funds|money|account)",
        r"\btrust\s+funds?\b.*\bmy\s+own\b",
    ),
    "investment": (
        r"\bprudent\s+investor\b",
        r"\binvestment\s+policy\b",
        r"\bhow\s+should\s+i\s+invest\b",
        r"\bwhat\s+can\s+i\s+invest\s+in\b",
    ),
    "tax": (
        r"\bform\s+1041\b",
        r"\bk-?1\b",
        r"\btrust\s+tax\b",
        r"\bestimated\s+tax\b",
    ),
    "minutes": (
        r"\bminutes\b",
        r"\bresolution\b",
        r"\bmeeting\s+notes\b",
    ),
    "co_trustee": (
        r"\bco-?\s*trustee\b",
        r"\bjoint\s+trustee\b",
        r"\bother\s+trustee\b",
    ),
    "compromise": (
        r"\bconflict\s+of\s+interest\b",
        r"\bself-?deal",
        r"\brecuse\b",
    ),
    # ---- UTC doctrine pack (2026-10-24, P2b) --------------------------- #
    # The nine approved Uniform Trust Code files answer questions the
    # concepts above do not cover. Each new concept below is anchored to
    # the file that answers it.
    "spendthrift": (
        r"\bspendthrift\b",
        r"\bcreditor\s+protection\b",
        r"\bprotect\w*\s+(the\s+)?(trust\s+)?assets\b",
        r"\bcan\s+(a\s+)?creditor\s+(reach|come\s+after)\b",
        r"\bcreditors?\s+(reach|claim|take)\b",
        r"\bmy\s+(family's\s+)?money\s+(is\s+)?protected\b",
        r"\bprotected\s+from\s+creditors\b",
        r"\basset\s+protection\b",
        r"\bjudgment\s+creditor\b",
    ),
    "revocation": (
        r"\brevoke\b",
        r"\brevocation\b",
        r"\bcan\s+i\s+(change|revoke|cancel)\s+(my|our|the)\s+trust\b",
        r"\bchange\s+or\s+revoke\b",
        r"\birrevocable\b",
        r"\bundo\s+(the|my)\s+trust\b",
    ),
    "trust_termination": (
        r"\bhow\s+does\s+(a|my|the)\s+trust\s+(end|terminate)",
        r"\bhow\s+(do|can|would)\s+(i|we)\s+(end|terminate|close)\s+(the|my|a|our)\s+trust",
        r"\bwhen\s+does\s+(a|my|the)\s+trust\s+(end|terminate)",
        r"\b(end|terminate|terminating|close|closing)\s+(the|my|a|our)\s+trust\b",
        r"\btrust\s+(end|ends|terminates|termination)\b",
        r"\bwhen\s+is\s+(my|the)\s+trust\s+over\b",
        r"\bafter\s+(the\s+)?settlor\s+(dies|death)\b",
        r"\bsettlor\s+(dies|death)\b",
        r"\bdissolve\b",
        r"\bfinal\s+report\b",
        r"\bexpeditious\w*\s+delivery\b",
    ),
    "beneficiary_notification": (
        r"\bnotify\s+(a|my|the|each|all)\s+beneficiar",
        r"\bnotif(y|ication|ications)\s+to\s+(a\s+)?beneficiar",
        r"\bnotification\s+register\b",
        r"\bregister\s+of\s+(notices|notifications)\b",
        r"\bdo\s+i\s+have\s+to\s+notify\b",
        r"\bwho\s+do\s+i\s+have\s+to\s+(tell|notify)\b",
        r"\bnotice\s+to\s+beneficiaries\b",
        r"\b(notices?|notification)\s+(i|we|do)\s+.{0,20}\bbeneficiar",
        r"\bwhat\s+(notices?|notifications)\b",
        r"\bnotify\b.*\bbeneficiar",
    ),
    "register_agent": (
        r"\bregister\b",
        r"\bregistration\b",
        r"\bappointment\s+of\s+agent\b",
        r"\bagent\s+to\s+accept\s+service\b",
        r"\bservice\s+of\s+process\b",
        r"\bprincipal\s+place\s+of\s+administration\b",
        r"\bchange\s+of\s+situs\b",
    ),
    "distribution_discretion": (
        r"\bhow\s+much\s+(discretion|freedom)\b",
        r"\bdiscretion\s+(do|does|can|when)\b",
        r"\bhow\s+much\s+(can|may)\s+i\s+decide\b",
        r"\bconstrain(ed|s)\s+.{0,25}distribution",
        r"\bwhat\s+happens\s+to\s+the\s+money\b",
        r"\bwhen\s+the\s+trust\s+ends\b",
    ),
    "trustee_removal": (
        r"\bremove\s+(me|my|our|the|a|an)\s+(as\s+)?trustee\b",
        r"\bremoval\s+of\s+(a|the|my|an)\s+trustee\b",
        r"\bcan\s+(i|the|they)\s+be\s+removed\b",
        r"\bfire\s+(my|the|a)\s+trustee\b",
        r"\bcompel\s+(a|the|my)\s+trustee\b",
        r"\bresign(ation)?\b",
        r"\bstep\s+down\s+as\s+trustee\b",
        r"\bvacancy\b",
        r"\b(trustee|trustees)\s+(removed|removal)",
    ),
}

# Concepts that are worth a doctrine fetch on their own. A question that
# matches ANY of these pulls the corpus; a question that matches none does
# not (so ordinary chat turns stay cheap).
DOCTRINE_CONCEPTS = tuple(DOCTRINE_TRIGGERS.keys())


def _match_doctrine_concepts(message: str) -> list[str]:
    """Return the doctrine concepts a message touches, in trigger order."""
    m = message.lower()
    hits: list[str] = []
    for concept, patterns in DOCTRINE_TRIGGERS.items():
        for pat in patterns:
            if re.search(pat, m):
                hits.append(concept)
                break
    return hits


# Words that carry no retrieval signal. A question's grammatical scaffolding
# ("what", "does", "how", "stand") matches everywhere and dilutes the query,
# so it is stripped before the FTS MATCH.
_DOCTRINE_QUERY_STOPWORDS = frozenset("""
a an and are as at be been but by can could did do does doing for from had
has have how i if in into is it its may me might my of on or our out so some
that the their them then there these they this those to too us was we were
what when where which who why will with would you your
""".split())


# Doctrine concept -> the canonical vocabulary of that concept. These terms
# are used as a RE-RANK BOOST, not as part of the FTS MATCH: adding a broad
# concept word to the MATCH would pull in every passage that mentions it and
# drown out the passage the member actually asked for.
DOCTRINE_VOCABULARY: dict = {
    "duties": ("duty", "duties", "fiduciary", "loyalty", "prudence", "care"),
    "utc": (
        "uniform",
        "trust",
        "code",
        "statute",
        "qualified",
        "beneficiary",
        "ascertainable",
        "definition",
        "defined",
        "article",
        "governing",
        "administered",
        "jurisdiction",
        "applies",
    ),
    "amendment": ("amend", "amendment", "modify", "modification"),
    "successor_trustee": ("successor", "succession", "resign", "resignation"),
    # NOTE: this vocabulary is shared with the pre-UTC corpus. Adding
    # broad legal nouns here ("discretion", "mandatory") re-ranks the
    # canonical 01-hems-standard answer out of first place on a plain
    # HEMS question — a P2a regression. The UTC distribution file (03) is
    # reached through its own concepts instead.
    "distribution_standard": ("hems", "standard", "discretion", "distribution"),
    "accounting": (
        "accounting",
        "account",
        "notice",
        "beneficiaries",
        "records",
        "record",
        "keeping",
        "report",
        "inform",
        "formal",
        "informal",
        "written",
        "quarterly",
        "annual",
    ),
    "termination": ("terminate", "termination", "final", "distribution"),
    "beneficiary_communication": ("beneficiary", "beneficiaries", "letter", "notice"),
    "commingling": ("commingle", "commingling", "separation", "personal"),
    "investment": ("prudent", "investment", "policy", "portfolio"),
    "tax": ("1041", "tax", "estimate", "filing"),
    "minutes": ("minutes", "resolution", "meeting", "documentation"),
    "co_trustee": ("trustee", "co", "joint"),
    "compromise": ("conflict", "interest", "recuse", "disqualify"),
    # ---- UTC doctrine pack boost vocabulary (2026-10-24, P2b) ---------- #
    # Distinctive noun phrases from the nine approved UTC files. These are
    # RE-RANK boosts only — they are deliberately NOT part of the FTS MATCH,
    # because broad legal nouns ("trust", "property", "notice") would pull in
    # every passage in the corpus and drown the answer.
    "spendthrift": (
        "spendthrift",
        "creditor",
        "creditors",
        "provision",
        "clause",
        "voluntary",
        "involuntary",
        "judgment",
        "claim",
        "claims",
        "extent",
        "discretion",
        "transfer",
        "personal",
        "spouse",
        "support",
        "distributed",
        "valid",
        "subject",
        "reach",
    ),
    "revocation": (
        "revocation",
        "revoke",
        "revocable",
        "amend",
        "amendment",
        "modification",
        "irrevocable",
        "settlor",
        "consent",
        "bracketed",
        "objectives",
        "instrument",
        "expressly",
        "convincing",
        "evidence",
        "proceeding",
        "method",
        "power",
    ),
    "trust_termination": (
        "termination",
        "terminate",
        "terminating",
        "final",
        "expeditious",
        "expeditiously",
        "receipt",
        "reserve",
        "claim",
        "release",
        "proposal",
        "window",
        "sequence",
        "debts",
        "taxes",
        "expenses",
        "compensation",
        "closing",
        "material",
        "informed",
    ),
    "distribution_discretion": (
        "discretion",
        "constrain",
        "constrained",
        "withdrawal",
        "ascertainable",
        "mandatory",
        "discretionary",
        "814",
        "817",
    ),
    "beneficiary_notification": (
        "notification",
        "notice",
        "notices",
        "register",
        "registration",
        "qualified",
        "beneficiary",
        "beneficiaries",
        "distributees",
        "delivery",
        "manner",
        "receipt",
        "report",
        "objection",
        "baseline",
        "acceptance",
        "deadline",
        "event",
        "rows",
        "period",
        "principal",
    ),
    "register_agent": (
        "administered",
        "governing",
        "defined",
        "definition",
        "article",
        "uniform",
        "purposes",
        "trusts",
        "requirement",
        "principal",
        "place",
        "administration",
        "agent",
    ),
    "trustee_removal": (
        "removal",
        "remove",
        "removed",
        "resign",
        "resignation",
        "vacancy",
        "vacant",
        "cotrustee",
        "co-trustee",
        "special",
        "fiduciary",
        "bond",
        "court",
        "successor",
        "designated",
        "trusteeship",
        "persistent",
        "administer",
        "serious",
        "breach",
        "omissions",
    ),
}


def _doctrine_query(message: str, concepts: list[str]) -> str:
    """Build the FTS query for a doctrine fetch.

    The member's own CONTENT words are the signal. Grammatical scaffolding
    is dropped: "what does HEMS stand for" becomes "hems stand", so the
    query is about HEMS instead of about the English of the question.

    The matched concepts' canonical vocabulary is returned separately as a
    BOOST, so a passage that genuinely covers the concept outranks one
    that merely happens to repeat a common word.
    """
    words = [
        w for w in re.findall(r"[a-z0-9'-]{3,}", (message or "").lower())
        if w not in _DOCTRINE_QUERY_STOPWORDS
    ]
    return " ".join(words)


def fetch_doctrine(
    message: str,
    *,
    limit: int = 6,
    max_chars: int = 3600,
    db_path: Optional[str] = None,
    allowed_audiences: Optional[list] = None,
) -> list:
    """Fetch the top KB passages for a doctrine question.

    Returns a list of dicts with the passage text plus its citation
    metadata (source file, section heading, title). Returns [] when the
    message does not raise a doctrine trigger, or when the index cannot be
    built — retrieval must never break the chat.

    AUDIENCE GATE (WingPoint isolation, 2026-10-30): `allowed_audiences` is
    the trust context's knowledge grant passed by the caller. Default empty
    denies every tiered document — universal corpus only. Fails closed.
    """
    concepts = _match_doctrine_concepts(message)
    if not concepts:
        return []
    try:
        from services import trust_knowledge
        info = trust_knowledge.ensure_index(db_path=db_path)
        resolved = info.get("db_path")
        if not resolved or not os.path.isfile(resolved):
            return []
        boost: list = []
        for concept in concepts:
            boost.extend(DOCTRINE_VOCABULARY.get(concept, ()))
        result = trust_knowledge.retrieve_passages(
            _doctrine_query(message, concepts),
            {
                "db_path": resolved,
                "boost_terms": boost,
                "allowed_audiences": list(allowed_audiences or []),
            },
            limit=limit,
            max_chars=max_chars,
        )
    except Exception as e:  # retrieval must never break the chat
        from logging import getLogger
        getLogger(__name__).warning(
            f"doctrine retrieval failed: {type(e).__name__}: {e}"
        )
        return []
    passages = []
    for item in result.get("results", []):
        text = item.get("text") or ""
        if not text.strip():
            continue
        passages.append({
            "title": item.get("title", ""),
            "section": item.get("section", ""),
            "text": text,
            "source_ref": item.get("source_ref", ""),
            "score": item.get("score", 0.0),
            "concepts": concepts,
        })
    return passages




_DOCTRINE_ANCHORS: dict = {}


def _doctrine_anchor(source_ref: str) -> str:
    """Fetch the '**UTC anchor:** ...' line from a 24-utc-*.md KB file (cached).

    UTC anchor lines live in the file preamble; section-level passage chunking
    can slice around them, so the renderer attaches the anchor explicitly to
    every UTC passage it renders.
    """
    if not _DOCTRINE_ANCHORS:
        import re

        from pathlib import Path
        kb = Path(__file__).resolve().parent / "knowledge"
        for f in sorted(kb.glob("24-utc-*.md")):
            try:
                m = re.search(r"\*\*UTC anchor:\*\*\s*(.+)", f.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if m:
                _DOCTRINE_ANCHORS[f.name] = m.group(1).strip()
    return _DOCTRINE_ANCHORS.get(source_ref, "")


def _render_doctrine(passages: list) -> str:
    """Render doctrine passages with their citations for prompt injection."""
    if not passages:
        return ""
    lines = ["## Retrieved Doctrine (cite the source file)"]
    for p in passages:
        title = p.get("title") or ""
        section = p.get("section") or ""
        source = p.get("source_ref") or ""
        label = " — ".join(x for x in (title, section) if x)
        lines.append(f"### {label}")
        if source:
            lines.append(f"Source: {source}")
            anchor = _doctrine_anchor(source)
            if anchor:
                lines.append(f"UTC anchor: {anchor}")
        lines.append(p.get("text", "").strip())
    return "\n".join(lines)


@dataclass
class RetrievalBlock:
    """Retrieved detail injected into the user content for this turn only."""
    minutes_matches: list = field(default_factory=list)
    asset_history: list = field(default_factory=list)
    vault_doc_detail: Optional[dict] = None
    doctrine: list = field(default_factory=list)
    extra: list = field(default_factory=list)

    def to_text(self) -> str:
        parts = []
        asset_text = _render_asset_timeline(self.asset_history)
        if asset_text:
            parts.append(asset_text)
        if self.minutes_matches:
            lines = ["## Retrieved Minutes (from search — cite meeting date)"]
            for m in self.minutes_matches[:5]:
                mtype = (m.get("minutes_type") or "Meeting").replace("_", " ").title()
                date = (m.get("meeting_date") or "")[:10]
                decisions = (m.get("decisions_text") or "").strip()
                if len(decisions) > 600:
                    decisions = decisions[:597] + "…"
                participants = (m.get("participants_text") or "").strip()
                lines.append(f"### {mtype} — {date}")
                if participants:
                    lines.append(f"Participants: {participants[:200]}")
                if decisions:
                    lines.append(f"Decisions: {decisions}")
                else:
                    lines.append("Decisions: (none recorded)")
            parts.append("\n".join(lines))
        if self.vault_doc_detail:
            d = self.vault_doc_detail
            lines = ["## Retrieved Vault Document (cite title + date)"]
            title = d.get("title") or d.get("file_name") or "Untitled"
            date = (d.get("date") or "")[:10]
            lines.append(f"{title}" + (f" — {date}" if date else ""))
            if d.get("category_label") or d.get("category"):
                lines.append(f"Category: {d.get('category_label') or d.get('category')}")
            desc = (d.get("description") or "").strip()
            if desc:
                lines.append(f"Description: {desc[:500]}")
            tags = d.get("tags") or []
            if tags:
                lines.append(f"Tags: {', '.join(str(t) for t in tags[:10])}")
            parts.append("\n".join(lines))
        if self.doctrine:
            rendered = _render_doctrine(self.doctrine)
            if rendered:
                parts.append(rendered)
        if self.extra:
            parts.extend(self.extra)
        if not parts:
            return ""
        text = "\n\n".join(parts)
        if len(text) > MAX_RETRIEVAL_CHARS:
            text = text[:MAX_RETRIEVAL_CHARS - 1] + "…"
        return text

    def is_empty(self) -> bool:
        return not (
            self.minutes_matches
            or self.asset_history
            or self.vault_doc_detail
            or self.doctrine
            or self.extra
        )


# ------------------------------------------------------------ trigger patterns ---

MINUTES_SEARCH_TRIGGERS = [
    r"\b(find|search|look\s*up|show|list|pull)\b.{0,40}\b(minutes|resolutions?|meeting)",
    r"\b(minutes|resolutions?)\b.{0,30}\b(where|that|which)\b",
    r"\bwhen\s+(did|have)\b.{0,40}\b(approv|distribut|authoriz|resolut)",
    r"\bwhat\s+(meetings?|minutes)\b",
    r"\b(all|past|previous|prior|every)\b.{0,20}\bminutes\b",
    r"\b(minutes|resolutions?)\b.{0,20}\b(for|about|on|regarding)\b.{0,40}\b(sale|sale of|distribut|loan|compensation|trustee|beneficiar|property|real estate|vehicle|tuition|education|purchase|truck)",
    r"\bminutes\b.{0,30}\b(approved?|authoriz|distribut|loan|tuition)\b",
    # Generic "what happened in our records" phrasings (2026-09-14 member
    # recall use case: "what did we say in our minutes", "what did we decide")
    r"\bwhat\s+(did|do)\s+we\s+(say|said|decide|decided|agree|agreed|approve|approv|resolve|record|vote)\b",
    r"\bwhat'?s\s+in\s+(the|our|my)\s+(minutes|meeting\s+records?)\b",
    r"\b(remember|recall)\b.{0,40}\b(resolution|minutes|decision|meeting)\b",
    r"\b(resolutions?|decisions?)\s+(did|have)\s+we\b",
    r"\bwhen\s+(did|have)\s+we\b.{0,40}\b(add|sold|sell|bought|buy|purchas|transfer|convey|contribut)",
]

VAULT_DOC_TRIGGERS = [
    r"\b(ein\s*(letter|number)|cp\s*575|cp575)\b",
    r"\b(certificate\s+of\s+trust|certification\s+of\s+trust)\b",
    r"\b(deed|title|grant\s+deed|quitclaim)\b",
    r"\b(statements?|bank\s+statement|brokerage\s+statement)\b",
    r"\b(insurance\s+policy|policy\s+document)\b",
    r"\b(my\s+)?(uploaded|vault)\s+(document|doc|file)s?\b",
    r"\bwhat\s+(documents?|files?)\b.{0,30}\b(vault|uploaded|do i have)\b",
]

MINUTES_KEYWORDS = ("minutes", "resolution", "meeting")
VAULT_KEYWORDS = ("vault", "document", "certificate", "deed", "statement", "ein")


def minutes_search_needed(intent: str, message: str) -> bool:
    m = message.lower()
    if intent == "log_minutes":
        return False
    if any(k in m for k in MINUTES_KEYWORDS):
        return any(re.search(p, m) for p in MINUTES_SEARCH_TRIGGERS)
    return any(re.search(p, m) for p in MINUTES_SEARCH_TRIGGERS)


def vault_detail_needed(intent: str, message: str) -> bool:
    if intent in ("upload_document", "review_document"):
        return False  # those intents already carry full doc context
    m = message.lower()
    if any(k in m for k in VAULT_KEYWORDS):
        return any(re.search(p, m) for p in VAULT_DOC_TRIGGERS)
    # EIN letter / specific doc names don't always contain "document"
    return bool(re.search(VAULT_DOC_TRIGGERS[0], m))


# ------------------------------------------------------------ DB fetchers ---

# Asset-history questions ("when did we add the property", "when did we sell
# the truck") — Schedule A carries date_conveyed / disposition_date and a
# minutes_ref that links the asset to the resolution that created it.
ASSET_TIMELINE_TRIGGERS = [
    r"\bwhen\s+(did|have)\s+we\b.{0,50}\b(add|added|buy|bought|purchase[d]?|contribut|convey|transfer|put\s+in|sell|sold|dispose[d]?|acquire[d]?)",
    r"\bwhen\s+(did|was)\b.{0,50}\b(property|house|car|truck|vehicle|asset|real\s+estate|land|parcel|rental|condo|cabin|account|brokerage)\b.{0,30}\b(add|buy|purchas|convey|transfer|contribut|sold|sell|acquir|dispos)",
    r"\bwhen\s+did\s+(the|that|this|our|my)\b.{0,40}\b(property|house|car|truck|vehicle|asset|land|account)\b.{0,20}\b(come|go|get)\b.{0,20}\b(into|in(to)?\s+the\s+trust)",
    r"\bwhat\s+assets?\b.{0,30}\b(did|have)\s+we\b",
    r"\b(how\s+long|what\s+date|which\s+date)\b.{0,40}\b(owned|held|in\s+the\s+trust)\b",
]


def asset_history_needed(intent: str, message: str) -> bool:
    if intent in ("add_asset", "contribute_asset", "update_asset", "add_investment"):
        return False  # write intents handle themselves
    m = message.lower()
    return any(re.search(p, m) for p in ASSET_TIMELINE_TRIGGERS)


async def search_asset_history(
    db,
    trust_id: str,
    user_id: str,
    message: str,
    limit: int = 5,
) -> list:
    """Schedule A timeline search for 'when did we...' questions. Returns
    assets whose description/identifier match extracted terms, with the
    conveyed/disposition dates and the minutes reference for citation.
    Falls back to the most recent assets when nothing matches the terms."""
    def _run(query: dict):
        return db.schedule_a_items.find(
            query,
            {"_id": 0, "item_id": 1, "category": 1, "description": 1, "identifier": 1,
             "approximate_value": 1, "date_conveyed": 1, "status": 1,
             "disposition_date": 1, "disposition_notes": 1, "minutes_ref": 1,
             "disposition_minutes_ref": 1, "created_at": 1},
        ).sort("created_at", -1).limit(limit).to_list(limit)

    terms = _extract_search_terms(message)
    query: dict = {"trust_id": trust_id, "user_id": user_id, "status": {"$ne": "deleted"}}
    if terms:
        # All-terms lookahead (same semantics as minutes search): every word
        # present anywhere in the field, any order. (?s) for .* across newlines.
        all_terms = "(?s)" + "".join(f"(?=.*{re.escape(w)})" for w in terms.split())
        query["$or"] = [
            {"description": {"$regex": all_terms, "$options": "i"}},
            {"identifier": {"$regex": all_terms, "$options": "i"}},
            {"category": {"$regex": all_terms, "$options": "i"}},
            {"notes": {"$regex": all_terms, "$options": "i"}},
        ]
    docs = await _run(query)
    if not docs and terms:
        base = {"trust_id": trust_id, "user_id": user_id, "status": {"$ne": "deleted"}}
        docs = await _run(base)
    return docs


def _render_asset_timeline(assets: list) -> str:
    if not assets:
        return ""
    lines = ["## Retrieved Asset History (from Schedule A — cite date + minutes reference)"]
    for a in assets[:5]:
        desc = (a.get("description") or "Unnamed asset").strip()
        cat = (a.get("category") or "").replace("_", " ").title()
        ident = (a.get("identifier") or "").strip()
        conveyed = (a.get("date_conveyed") or "")[:10]
        added = (a.get("created_at") or "")[:10]
        status = a.get("status") or "active"
        value = a.get("approximate_value")
        line = f"- {desc}" + (f" ({ident})" if ident else "")
        if status == "disposed":
            disp = (a.get("disposition_date") or "")[:10]
            line += f" — DISPOSED {disp}" if disp else " — disposed"
            dn = (a.get("disposition_notes") or "").strip()
            if dn:
                line += f": {dn[:150]}"
        elif conveyed:
            line += f" — conveyed into trust {conveyed}"
        elif added:
            line += f" — recorded {added}"
        if value:
            line += f", ~${value:,.0f}"
        mref = a.get("minutes_ref") or a.get("disposition_minutes_ref")
        if mref:
            line += f" [minutes ref: {mref}]"
        lines.append(line)
    return "\n".join(lines)


async def search_minutes(
    db,
    trust_id: str,
    user_id: str,
    message: str,
    limit: int = 5,
) -> list:
    """Full-text minutes search scoped to the trust. Extracts candidate
    search terms from the user's message; when nothing matches, falls back
    to the most recent minutes so the assistant can still answer from the
    record roster instead of 'I found nothing'."""
    def _run(query: dict):
        return db.minutes_records.find(
            query,
            {"_id": 0, "minutes_id": 1, "minutes_type": 1, "meeting_date": 1,
             "decisions_text": 1, "participants_text": 1},
        ).sort("meeting_date", -1).limit(limit).to_list(limit)

    query_text = _extract_search_terms(message)
    search_query: dict = {"trust_id": trust_id, "user_id": user_id}
    if query_text:
        # All-terms lookahead: every word present anywhere in the field, any
        # order — exact-phrase regex missed "pickup truck (blue)"-style text.
        # (?s) so .* spans newlines in multi-line decisions text.
        all_terms = "(?s)" + "".join(f"(?=.*{re.escape(w)})" for w in query_text.split())
        search_query["$or"] = [
            {"decisions_text": {"$regex": all_terms, "$options": "i"}},
            {"participants_text": {"$regex": all_terms, "$options": "i"}},
        ]
    docs = await _run(search_query)
    if not docs and query_text:
        docs = await _run({"trust_id": trust_id, "user_id": user_id})
    return docs


_TERM_STOP = {
    "find", "search", "lookup", "look", "up", "show", "list", "pull", "the",
    "a", "an", "minutes", "resolution", "resolutions", "meeting", "meetings",
    "when", "did", "have", "i", "we", "my", "our", "was", "were", "is",
    "are", "for", "about", "on", "in", "of", "to", "that", "which", "what",
    "where", "all", "past", "previous", "every", "any", "did", "approved",
    "approve", "approving", "trust", "trustee", "trustees", "and", "or",
    # Asking/action verbs — they describe the question, not the record text
    "say", "said", "decide", "decided", "agree", "agreed", "record", "vote",
    "remember", "recall", "talk", "talked", "mention", "mentioned",
    "discuss", "discussed", "add", "added", "buy", "bought", "sell", "sold",
    "purchase", "purchased", "transfer", "transferred", "convey", "conveyed",
    "contribute", "contributed", "into", "get", "got", "came", "went",
}


def _extract_search_terms(message: str) -> str:
    """Pull likely content words from a search-style question. Falls back to
    the raw message (regex anyway) when nothing extractable remains."""
    words = re.findall(r"[a-z0-9']+", message.lower())
    terms = [w for w in words if w not in _TERM_STOP and len(w) > 2]
    if not terms:
        return ""
    # Up to four content-bearing words — two is too brittle for real
    # questions ("when did we buy the blue pickup truck" loses "pickup truck").
    return " ".join(terms[:4])


async def get_vault_doc_detail(
    db,
    trust_id: str,
    user_id: str,
    message: str,
) -> Optional[dict]:
    """Match the question to a vault doc by title/category/tags and return its
    metadata (never file content — content retrieval is a deferred decision).
    Picks the best single match; None when nothing looks relevant."""
    m = message.lower()
    docs = await db.vault_documents.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "doc_id": 1, "title": 1, "file_name": 1, "category": 1,
         "category_label": 1, "date": 1, "description": 1, "tags": 1},
    ).sort("created_at", -1).to_list(100)

    if not docs:
        return None

    # Explicit "what documents do I have" → inventory-style answer; the Brief
    # already lists them, so return the most recent as a pointer.
    if re.search(r"\bwhat\s+(documents?|files?)\b", m):
        return docs[0]

    scored: list[tuple[int, dict]] = []
    for d in docs:
        score = 0
        title = (d.get("title") or "").lower()
        fname = (d.get("file_name") or "").lower()
        cat = (d.get("category") or "").lower()
        tags = [str(t).lower() for t in (d.get("tags") or [])]
        if re.search(r"ein|cp\s*575|cp575", m):
            if re.search(r"ein|cp\s*575|cp575", title + fname + cat + " ".join(tags)):
                score += 5
        if re.search(r"deed|title", m) and re.search(r"deed|title", title + fname + cat):
            score += 5
        if re.search(r"statement", m) and "statement" in cat + title + fname:
            score += 4
        if re.search(r"certificate", m) and "certif" in title + fname + cat + " ".join(tags):
            score += 5
        if re.search(r"insurance", m) and "insur" in title + fname + cat + " ".join(tags):
            score += 4
        # loose title-word overlap
        overlap = [w for w in re.findall(r"[a-z]{4,}", m) if w in title or w in fname]
        score += len(overlap)
        if score > 0:
            scored.append((score, d))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


# ------------------------------------------------------------ entry point ---

async def retrieve_for_message(
    db,
    trust_id: str,
    user_id: str,
    intent: str,
    message: str,
    allowed_audiences: Optional[list] = None,
) -> RetrievalBlock:
    """Main entry: decide what to fetch, fetch it, return the block.

    AUDIENCE GATE (WingPoint isolation, 2026-10-30): `allowed_audiences` is
    the requesting trust context's knowledge grant. Default/empty denies
    every tiered knowledge document — universal corpus only (fail closed).
    """
    block = RetrievalBlock()
    try:
        if minutes_search_needed(intent, message):
            block.minutes_matches = await search_minutes(db, trust_id, user_id, message)
    except Exception as e:  # retrieval must never break the chat
        from logging import getLogger
        getLogger(__name__).warning(f"minutes retrieval failed: {type(e).__name__}: {e}")
    try:
        if asset_history_needed(intent, message):
            block.asset_history = await search_asset_history(db, trust_id, user_id, message)
    except Exception as e:  # retrieval must never break the chat
        from logging import getLogger
        getLogger(__name__).warning(f"asset retrieval failed: {type(e).__name__}: {e}")
    if block.is_empty():
        try:
            if vault_detail_needed(intent, message):
                block.vault_doc_detail = await get_vault_doc_detail(db, trust_id, user_id, message)
        except Exception as e:
            from logging import getLogger
            getLogger(__name__).warning(f"vault retrieval failed: {type(e).__name__}: {e}")
    # Layer 2b — doctrine retrieval (2026-10-23, P2a). Runs regardless of
    # whether a trust-scoped block matched: a doctrine question is about the
    # law and the reviewed corpus, not about this member's records.
    # Audience-granted (2026-10-30): empty grant → universal corpus only.
    try:
        block.doctrine = fetch_doctrine(
            message, allowed_audiences=list(allowed_audiences or [])
        )
    except Exception as e:
        from logging import getLogger
        getLogger(__name__).warning(f"doctrine retrieval failed: {type(e).__name__}: {e}")
    return block


def inject_into_user_content(user_content: str, block: RetrievalBlock) -> str:
    """Append retrieval text to the user content for this turn."""
    rtext = block.to_text()
    if not rtext:
        return user_content
    return (
        f"{user_content}\n\n"
        "---\n"
        "RETRIEVED CONTEXT (on-demand, this turn only — cite it when you use it; "
        "it was matched by search, so verify it answers the question before citing):\n"
        f"{rtext}"
    )


__all__ = [
    "RetrievalBlock",
    "retrieve_for_message",
    "fetch_doctrine",
    "DOCTRINE_TRIGGERS",
    "DOCTRINE_CONCEPTS",
    "minutes_search_needed",
    "asset_history_needed",
    "vault_detail_needed",
    "search_minutes",
    "search_asset_history",
    "get_vault_doc_detail",
    "inject_into_user_content",
    "MAX_RETRIEVAL_CHARS",
]