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

import re
from dataclasses import dataclass, field
from typing import Optional

MAX_RETRIEVAL_CHARS = 3500  # per-turn cap on all injected retrieval blocks


@dataclass
class RetrievalBlock:
    """Retrieved detail injected into the user content for this turn only."""
    minutes_matches: list = field(default_factory=list)
    asset_history: list = field(default_factory=list)
    vault_doc_detail: Optional[dict] = None
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
        if self.extra:
            parts.extend(self.extra)
        if not parts:
            return ""
        text = "\n\n".join(parts)
        if len(text) > MAX_RETRIEVAL_CHARS:
            text = text[:MAX_RETRIEVAL_CHARS - 1] + "…"
        return text

    def is_empty(self) -> bool:
        return not (self.minutes_matches or self.asset_history or self.vault_doc_detail or self.extra)


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
) -> RetrievalBlock:
    """Main entry: decide what to fetch, fetch it, return the block."""
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
    "minutes_search_needed",
    "asset_history_needed",
    "vault_detail_needed",
    "search_minutes",
    "search_asset_history",
    "get_vault_doc_detail",
    "inject_into_user_content",
    "MAX_RETRIEVAL_CHARS",
]