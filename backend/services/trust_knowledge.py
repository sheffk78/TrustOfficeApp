"""Local SQLite FTS5 index and retrieval for TrustOffice knowledge.

Only the Python standard library and sqlite3 are required.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LAST_DB: str | None = None

# --------------------------------------------------------------------------- #
# Knowledge-only index support (2026-10-23, P2a)
#
# The canonical registry YAML (brand KNOWLEDGE/trustoffice-registry.yaml) is a
# PRODUCT catalogue. It is not in the deployed image and not tracked in the
# repo, which is why the FTS branch of chat_service has been inert in prod
# since it was written: the branch is guarded on the registry file existing.
#
# The corpus the assistant actually needs to retrieve doctrine from is
# backend/knowledge/*.md, and that IS in the image. So the index must be
# buildable from the knowledge directory ALONE, with the registry as an
# optional enrichment. Everything below implements that, plus passage-level
# (section-level) FTS so retrieval returns the exact section that answers the
# question instead of the head of a file.
# --------------------------------------------------------------------------- #

# Fingerprint cache TTL (seconds). The knowledge directory is static inside
# the container, so re-hashing 100 files on every chat turn is waste; a short
# TTL still picks up local edits.
_FINGERPRINT_TTL = 60.0
_FINGERPRINT_CACHE: dict[str, tuple[float, str]] = {}

# Section splitter: "## Heading" at the start of a line.
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)

# Minimal synonym expansion so member phrasing hits the indexed terms.
# Porter stemming already handles plurals; these cover the irregular cases
# and the domain abbreviations that appear in member questions.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "duty": ("duties", "fiduciary", "obligation", "obligations"),
    "duties": ("duty", "fiduciary", "obligation", "obligations"),
    "fiduciary": ("fiduciary", "duty", "duties"),
    "accounting": ("accounting", "accountings", "account", "accounts"),
    "account": ("accounting", "accountings"),
    "beneficiary": ("beneficiary", "beneficiaries"),
    "beneficiaries": ("beneficiary", "beneficiaries"),
    "distribution": ("distribution", "distributions", "distribute"),
    "distributions": ("distribution", "distribute"),
    "amendment": ("amendment", "amendments", "amend"),
    "amendments": ("amendment", "amend"),
    "successor": ("successor", "successorship", "succession"),
    "succession": ("successor", "successorship"),
    "trustee": ("trustee", "trustees", "fiduciary"),
    "trustees": ("trustee", "fiduciary"),
    "utc": ("utc", "uniform", "trust", "code"),
    "termination": ("termination", "terminate", "terminating"),
    "terminate": ("termination", "terminating"),
    "accounting_frequency": ("accounting", "frequency", "annually", "annual"),
    "hems": ("hems", "health", "education", "maintenance", "support"),
    "conflict": ("conflict", "interest", "disqualif"),
    "resign": ("resign", "resignation"),
    "resignation": ("resign", "resignation"),
    "commingle": ("commingle", "commingling", "separation", "separate"),
    "separation": ("separation", "commingling", "separate", "commingle"),
}


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in ("null", "~"): return None
    if value.lower() in ("true", "yes"): return True
    if value.lower() in ("false", "no"): return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner: return []
        # YAML permits unquoted words in flow lists; ast.literal_eval does not.
        return [_scalar(part.strip()) for part in inner.split(",") if part.strip()]
    if value.startswith("{") and value.endswith("}"):
        try: return ast.literal_eval(value)
        except Exception: pass
    if value[:1] == "'" and value[-1:] == "'":
        try: return ast.literal_eval(value)
        except Exception: pass
    if value.startswith('"') and value.endswith('"'):
        try: return json.loads(value)
        except Exception: return value[1:-1]
    return value


def _yaml_load(path: Path) -> dict[str, Any]:
    """Load a YAML registry. Prefers PyYAML if available; falls back to a
    small hand-rolled reader for scalar/list/mapping subsets when PyYAML is
    not installed."""
    if not path.exists(): return {}
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        if data is None:
            return {}
        return {}
    except Exception:
        pass
    lines = path.read_text(encoding="utf-8").splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"): continue
        indent = len(raw) - len(raw.lstrip(" ")); text = raw.strip()
        while stack and indent <= stack[-1][0]: stack.pop()
        parent = stack[-1][1]
        if text.startswith("- "):
            if isinstance(parent, list):
                item = text[2:].strip()
                if ":" in item and not item.startswith(("http:", "https:")):
                    obj: dict[str, Any] = {}; parent.append(obj)
                    k, v = item.split(":", 1); obj[k.strip()] = _scalar(v)
                    stack.append((indent, obj))
                else: parent.append(_scalar(item))
            continue
        if ":" not in text or not isinstance(parent, dict): continue
        key, val = text.split(":", 1); key = key.strip(); val = val.strip()
        if val: parent[key] = _scalar(val)
        else:
            # Look ahead to decide whether the child is a list.
            child_is_list = False
            for nxt in lines[lines.index(raw)+1:]:
                if nxt.strip() and not nxt.lstrip().startswith("#"):
                    child_is_list = nxt.strip().startswith("-") and len(nxt)-len(nxt.lstrip()) > indent; break
            parent[key] = [] if child_is_list else {}
            stack.append((indent, parent[key]))
    return root


def _front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"): return {}, text
    parts = text.split("---", 2)
    if len(parts) != 3: return {}, text
    # Parse front matter using the same intentionally small YAML subset.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
        f.write(parts[1]); name = f.name
    try: meta = _yaml_load(Path(name))
    finally: Path(name).unlink(missing_ok=True)
    return meta, parts[2].lstrip()


def _as_list(value: Any) -> list[str]:
    if value is None: return []
    if isinstance(value, list): return [str(x) for x in value]
    return [str(value)]


# --------------------------------------------------------------------------- #
# Passage (section) splitting
# --------------------------------------------------------------------------- #

def _split_sections(body: str, doc_title: str) -> list[tuple[str, str]]:
    """Split a knowledge document into (section_title, section_text) pairs.

    A document that has no "## " heading is a single passage. Each passage
    keeps the document title as its first line so a retrieved passage is
    self-describing when injected into a prompt.
    """
    if not body.strip():
        return []
    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        return [(doc_title, body.strip())]
    passages: list[tuple[str, str]] = []
    # Preamble before the first "## " heading (usually the intro).
    preamble = body[: matches[0].start()].strip()
    if preamble:
        passages.append((doc_title, preamble))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[m.start(): end].strip()
        if text:
            passages.append((m.group(1).strip(), text))
    return passages


def _knowledge_fingerprint(knowledge_dir: str) -> str:
    """Stable fingerprint of the knowledge directory contents.

    Used to decide whether a prebuilt index is still current. Cached briefly
    so a chat turn does not re-hash ~100 files.
    """
    kd = Path(knowledge_dir)
    try:
        st = kd.stat()
    except OSError:
        return "missing"
    key = str(kd.resolve())
    now = time.monotonic()
    cached = _FINGERPRINT_CACHE.get(key)
    if cached and (now - cached[0]) < _FINGERPRINT_TTL:
        return cached[1]
    h = hashlib.sha256()
    h.update(str(st.st_mtime_ns).encode())
    for p in sorted(kd.glob("*.md")):
        try:
            h.update(p.name.encode())
            h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode())
        except OSError:
            continue
    digest = h.hexdigest()
    _FINGERPRINT_CACHE[key] = (now, digest)
    return digest


def _j(value: Any) -> str: return json.dumps(value if value is not None else [], ensure_ascii=False)
def _norm(value: str) -> str: return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
def _tokens(value: str) -> list[str]: return re.findall(r"[a-z0-9_]+", value.lower())


def build_index(registry_path, knowledge_dir, db_path) -> dict:
    """Build the FTS5 index.

    `registry_path` is OPTIONAL (2026-10-23, P2a). When it exists, the
    product registry enriches the index with aliases/tags/scenarios. When it
    does not exist — the normal case in the deployed image, where the brand
    KNOWLEDGE/ directory is not shipped — the index is built from
    backend/knowledge/*.md alone, which IS in the image. That is the change
    that makes retrieval work in prod.

    Passages are indexed at SECTION granularity in the `passages` table so
    retrieval can return the exact section that answers a question instead of
    the head of a file.
    """
    global _LAST_DB
    registry = {}
    registry_present = False
    if registry_path:
        rp = Path(registry_path)
        if rp.exists():
            registry = _yaml_load(rp)
            registry_present = True
    version = str(registry.get("registry_version", "knowledge-only"))
    records = registry.get("products", []) or registry.get("items", []) or []
    if isinstance(records, dict): records = list(records.values())
    docs: list[tuple[str, str, str, dict[str, Any]]] = []
    kd = Path(knowledge_dir)
    if kd.exists():
        for p in sorted(kd.glob("*.md")):
            raw = p.read_text(encoding="utf-8", errors="replace"); meta, body = _front_matter(raw)
            docs.append((p.stem, p.name, body, meta))
    db = Path(db_path); db.parent.mkdir(parents=True, exist_ok=True)
    tmp = db.with_name(db.name + ".tmp")
    if tmp.exists(): tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE registry_items (item_id TEXT PRIMARY KEY, kind TEXT, name TEXT, status TEXT,
          summary TEXT, body TEXT, routes TEXT, aliases TEXT, tags TEXT, scenarios TEXT,
          supported_actions TEXT, available_in TEXT, visibility TEXT, source_refs TEXT, data TEXT);
        CREATE TABLE documents (document_id TEXT PRIMARY KEY, title TEXT, body TEXT, status TEXT, source_hash TEXT, meta TEXT);
        CREATE TABLE chunks (chunk_id INTEGER PRIMARY KEY, item_id TEXT, document_id TEXT, kind TEXT, text TEXT, source_ref TEXT);
        CREATE TABLE passages (passage_id INTEGER PRIMARY KEY, document_id TEXT, doc_title TEXT,
          section TEXT, ordinal INTEGER, text TEXT, source_ref TEXT);
        CREATE VIRTUAL TABLE fts_content USING fts5(item_id UNINDEXED, name, aliases, actions, tags, scenarios, summary, body,
          tokenize='unicode61 remove_diacritics 2');
        CREATE VIRTUAL TABLE fts_passages USING fts5(passage_id UNINDEXED, document_id UNINDEXED, doc_title, section, text,
          tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE registry_versions (registry_version TEXT, built_at TEXT, items INTEGER, chunks INTEGER);
        CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT);
        """)
        item_ids = set()
        for rec in records:
            if not isinstance(rec, dict) or not rec.get("id"): continue
            r = dict(rec); iid = str(r["id"]); item_ids.add(iid)
            status = str(r.get("status", "live")); name = str(r.get("name", iid))
            body = " ".join(str(r.get(k, "")) for k in ("description", "details", "capabilities", "response_pattern", "caveats"))
            aliases = _as_list(r.get("aliases")) + _as_list(r.get("user_phrasings"))
            actions = _as_list(r.get("supported_actions")) + _as_list(r.get("recommended_action_ids"))
            tags = _as_list(r.get("tags")); scenarios = _as_list(r.get("scenarios")) + _as_list(r.get("scenario_ids"))
            visibility = str(r.get("visibility", "private" if status == "private" else "public"))
            source = _as_list(r.get("source_docs")) + _as_list(r.get("source_refs"))
            con.execute("INSERT INTO registry_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (iid, str(r.get("kind", "feature")), name, status, str(r.get("summary", "")), body, _j(r.get("routes", r.get("route", []))), _j(aliases), _j(tags), _j(scenarios), _j(actions), _j(r.get("available_in", [])), visibility, _j(source), _j(r)))
            con.execute("INSERT INTO fts_content VALUES (?,?,?,?,?,?,?,?)", (iid, name, " ".join(aliases), " ".join(actions), " ".join(tags), " ".join(scenarios), str(r.get("summary", "")), body))
            con.execute("INSERT INTO chunks(item_id,document_id,kind,text,source_ref) VALUES (?,?,?,?,?)", (iid, iid, str(r.get("kind", "feature")), (str(r.get("summary", "")) + " " + body).strip(), (source[0] if source else iid)))
        passage_count = 0
        for docid, filename, body, meta in docs:
            dh = hashlib.sha256(body.encode()).hexdigest()
            doc_title = str(meta.get("title", filename))
            con.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", (docid, doc_title, body, str(meta.get("status", "published")), dh, _j(meta)))
            links = _as_list(meta.get("feature_ids")) + _as_list(meta.get("item_ids")) + _as_list(meta.get("scenario_ids"))
            links = links or [docid]
            for iid in links:
                if iid not in item_ids:
                    iid = docid
                    if not con.execute("SELECT 1 FROM registry_items WHERE item_id=?", (iid,)).fetchone():
                        con.execute("INSERT INTO registry_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (iid, "document", doc_title, "live", "", "", "[]", "[]", "[]", "[]", "[]", "[]", "public", _j([filename]), _j({"id": iid})))
                        con.execute("INSERT INTO fts_content VALUES (?,?,?,?,?,?,?,?)", (iid, doc_title, "", "", "", "", "", body))
                con.execute("INSERT INTO chunks(item_id,document_id,kind,text,source_ref) VALUES (?,?,?,?,?)", (iid, docid, "document", body, filename))
            # Section-level passages for precise retrieval.
            for ordinal, (section, text) in enumerate(_split_sections(body, doc_title)):
                cur = con.execute(
                    "INSERT INTO passages(document_id, doc_title, section, ordinal, text, source_ref) VALUES (?,?,?,?,?,?)",
                    (docid, doc_title, section, ordinal, text, filename),
                )
                passage_id = cur.lastrowid
                con.execute(
                    "INSERT INTO fts_passages VALUES (?,?,?,?,?)",
                    (passage_id, docid, doc_title, section, text),
                )
                passage_count += 1
        chunk_count = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        con.execute(
            "INSERT INTO registry_versions VALUES (?,?,?,?)",
            (version, datetime.now(timezone.utc).isoformat(), len(item_ids), chunk_count),
        )
        # Record the knowledge-directory fingerprint so ensure_index() can
        # tell a current index from a stale one.
        con.execute(
            "INSERT OR REPLACE INTO index_meta(key, value) VALUES (?,?)",
            ("knowledge_fingerprint", _knowledge_fingerprint(str(kd))),
        )
        con.execute(
            "INSERT OR REPLACE INTO index_meta(key, value) VALUES (?,?)",
            ("built_at", datetime.now(timezone.utc).isoformat()),
        )
        con.execute(
            "INSERT OR REPLACE INTO index_meta(key, value) VALUES (?,?)",
            ("registry_present", "1" if registry_present else "0"),
        )
        con.commit()
    finally: con.close()
    os.replace(tmp, db); _LAST_DB = str(db)
    return {
        "registry_version": version,
        "registry_present": registry_present,
        "documents": len(docs),
        "items": len(item_ids),
        "chunks": chunk_count,
        "passages": passage_count,
        "fingerprint": _knowledge_fingerprint(str(kd)),
        "ok": True,
    }


def _db_from_context(context):
    if isinstance(context, str): return context
    if isinstance(context, dict) and context.get("db_path"): return context["db_path"]
    return _LAST_DB or os.environ.get("TRUST_KNOWLEDGE_DB", "trust_knowledge.db")


# --------------------------------------------------------------------------- #
# Index lifecycle (2026-10-23, P2a)
# --------------------------------------------------------------------------- #

def default_db_path() -> str:
    """Resolve the index database path.

    Priority: TRUST_KNOWLEDGE_DB env var, then <backend>/data/trust_knowledge.db
    (the path that works both locally and in the /app image).
    """
    env = os.environ.get("TRUST_KNOWLEDGE_DB")
    if env:
        return env
    backend_root = Path(__file__).resolve().parents[1]
    return str(backend_root / "data" / "trust_knowledge.db")


def default_registry_path() -> str:
    """Resolve the optional product-registry YAML path (may not exist)."""
    env = os.environ.get("TRUST_KNOWLEDGE_REGISTRY")
    if env:
        return env
    backend_root = Path(__file__).resolve().parents[1]
    return str(backend_root / "KNOWLEDGE" / "trustoffice-registry.yaml")


def default_knowledge_dir() -> str:
    env = os.environ.get("TRUST_KNOWLEDGE_DIR")
    if env:
        return env
    backend_root = Path(__file__).resolve().parents[1]
    return str(backend_root / "knowledge")


def ensure_index(
    db_path: str | None = None,
    knowledge_dir: str | None = None,
    registry_path: str | None = None,
    *,
    rebuild: bool = False,
) -> dict:
    """Make sure a current FTS index exists at `db_path`.

    Decision (2026-10-23, P2a — the db-runtime fate):

    The index is built from backend/knowledge/*.md alone when the product
    registry YAML is absent, and it is REBUILT ON STARTUP (or on first use)
    from the knowledge files that ship in the image. The prebuilt DB in the
    repo is a build artifact that keeps local/dev fast and gives the image a
    usable index the instant the container boots, but it is never trusted as
    the source of truth in prod: `build_index()` is re-run when the knowledge
    directory fingerprint no longer matches the one recorded in the DB.

    Why rebuild rather than ship-static: the stale "41 templates" claim
    proved a shipped DB can silently disagree with the corpus it claims to
    index. A fingerprint check makes that class of drift impossible rather
    than merely unlikely.

    Returns a dict describing what happened (for logging / tests).
    """
    db_path = db_path or default_db_path()
    knowledge_dir = knowledge_dir or default_knowledge_dir()
    registry_path = registry_path if registry_path is not None else default_registry_path()
    db = Path(db_path)
    fingerprint = _knowledge_fingerprint(knowledge_dir)
    info = {
        "db_path": str(db),
        "knowledge_dir": knowledge_dir,
        "registry_path": registry_path,
        "registry_present": Path(registry_path).exists(),
        "fingerprint": fingerprint,
        "rebuilt": False,
        "reason": "",
    }
    needs_build = rebuild or not db.exists()
    if not needs_build:
        try:
            con = sqlite3.connect(str(db))
            try:
                row = con.execute(
                    "SELECT registry_version FROM registry_versions ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                has_passages = con.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='passages'"
                ).fetchone()[0]
                stored = con.execute(
                    "SELECT value FROM index_meta WHERE key='knowledge_fingerprint'"
                ).fetchone() if con.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='index_meta'"
                ).fetchone()[0] else None
            finally:
                con.close()
            if stored is None:
                # Index predates the fingerprint scheme (or was built elsewhere).
                # Rebuild once so the invariant is established.
                needs_build = True
                info["reason"] = "no-fingerprint"
            elif stored[0] != fingerprint:
                needs_build = True
                info["reason"] = "stale-fingerprint"
            elif not has_passages:
                needs_build = True
                info["reason"] = "missing-passages"
        except sqlite3.Error as e:
            needs_build = True
            info["reason"] = f"unreadable: {type(e).__name__}"
    if not needs_build:
        info["reason"] = "current"
        return info
    result = build_index(registry_path, knowledge_dir, str(db))
    info["rebuilt"] = True
    info["build"] = result
    if not info["reason"]:
        info["reason"] = "missing-db" if not db.exists() else "forced"
    return info


def _expand_terms(query: str) -> list[str]:
    """Query terms plus domain synonyms, de-duplicated, longest first."""
    terms = [t for t in _tokens(str(query)) if len(t) > 1]
    expanded: list[str] = []
    for t in terms:
        for cand in (t,) + _SYNONYMS.get(t, ()):
            if cand not in expanded:
                expanded.append(cand)
    # Longer terms first: FTS5 OR is order-independent for scoring, but this
    # keeps the MATCH expression readable and stable.
    expanded.sort(key=lambda x: (-len(x), x))
    return expanded


def retrieve_passages(
    query: str,
    context: dict | None = None,
    *,
    limit: int = 5,
    max_chars: int = 2400,
) -> dict:
    """Retrieve the top-matching KB PASSAGES for a query.

    Unlike `retrieve()` (which returns whole registry items, each keyed to a
    product catalogue entry), this returns SECTION-level passages with their
    document title, section heading, source file, and a relevance score. It is
    the retrieval primitive the Trust Assistant's doctrine leg uses.

    Falls back to the item-level FTS table when the index has no passages
    (e.g. an index built by an older build), so the function never returns
    nothing just because the DB is a different shape.
    """
    ctx = context if isinstance(context, dict) else {}
    db_path = _db_from_context(ctx)
    if not Path(db_path).exists():
        return {"results": [], "not_found": True, "reason": "no-index", "db_path": db_path}
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        try:
            version = con.execute(
                "SELECT registry_version FROM registry_versions ORDER BY rowid DESC LIMIT 1"
            ).fetchone()[0]
        except sqlite3.Error:
            version = "unknown"
        has_fts_passages = con.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='fts_passages'"
        ).fetchone()[0]
        if not has_fts_passages:
            return {"registry_version": version, "results": [], "not_found": True, "reason": "no-passage-index"}
        terms = _expand_terms(query)
        if not terms:
            return {"registry_version": version, "results": [], "not_found": True, "reason": "no-terms"}
        match = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
        # FTS5 caps the number of rows an OR-MATCH can return at 500 by
        # default; a broad query with many OR terms can hit that. Keep the
        # per-term selectivity high so the MATCH stays narrow.
        raw_terms = sorted({t for t in terms if len(t) > 2})
        # Boost terms are vocabulary the caller knows is relevant (e.g. the
        # doctrinal concept names for a matched question). They are NOT part
        # of the FTS MATCH: adding a broad term like "distribution" to the
        # MATCH pulls in every distribution passage and drowns the passage
        # the member actually asked for. They are used only in the re-rank,
        # where they lift a passage that really addresses the concept.
        boost_terms = set()
        raw_boost = ctx.get("boost_terms") or []
        if isinstance(raw_boost, str):
            raw_boost = [raw_boost]
        for t in raw_boost:
            boost_terms.update(x for x in _tokens(str(t)) if len(x) > 2)
        # Pull a generous candidate pool, then rank in Python. The FTS
        # MATCH itself is broad (OR over the query terms), so the SQL LIMIT
        # must be large enough that the re-rank has something to choose
        # from — otherwise the winner is decided by rowid order, not
        # relevance.
        rows = con.execute(
            """
            SELECT p.passage_id, p.document_id, p.doc_title, p.section, p.text,
                   p.source_ref, bm25(fts_passages, 0.0, 0.0, 3.0, 2.0, 1.0) AS rank
              FROM fts_passages f
              JOIN passages p ON p.passage_id = f.passage_id
             WHERE fts_passages MATCH ?
             ORDER BY rank
             LIMIT ?
            """,
            (match, 400),
        ).fetchall()
        # Hybrid re-rank: BM25 alone rewards a passage that repeats one term
        # many times, which is not the same as "answers the question". Add a
        # coverage term — how many DISTINCT query concepts the passage
        # actually addresses — and a title/section bonus so a passage whose
        # heading names the topic outranks one that merely mentions it.
        query_concepts = {t for t in _tokens(str(query)) if len(t) > 2}
        scored = []
        for r in rows:
            text = r["text"] or ""
            if not text.strip():
                continue
            body_tokens = set(_tokens(text))
            title_tokens = set(_tokens(r["doc_title"]))
            heading_tokens = title_tokens | set(_tokens(r["section"]))
            covered = query_concepts & (body_tokens | heading_tokens)
            coverage = len(covered) / max(1, len(query_concepts))
            bm25 = max(0.0, -float(r["rank"]))
            heading_hit = 1.0 if (query_concepts & heading_tokens) else 0.0
            # A document whose OWN TITLE names the concept is the canonical
            # source for it ("03-trustee-duties" for a duties question).
            # That is a stronger signal than a section heading, because the
            # file name is how the corpus is organized.
            title_hit = len(query_concepts & title_tokens)
            # Concept boost: the passage addresses the doctrinal concept the
            # caller's trigger matched. Counted in the BODY, so a passage
            # that genuinely covers the concept wins over one that merely
            # names it in a heading.
            boost_hit = len(boost_terms & (body_tokens | heading_tokens))
            score = (
                bm25 * (1.0 + 2.0 * coverage)
                + 3.0 * heading_hit
                + 4.0 * title_hit
                + 2.0 * boost_hit
            )
            scored.append((score, bm25, coverage, heading_hit, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        used = 0
        for score, bm25, coverage, heading_hit, r in scored:
            text = r["text"] or ""
            if not text.strip():
                continue
            # The slice budget is hard. A passage that does not fit is
            # TRUNCATED, not skipped: dropping the top-ranked passage
            # because it is long would hand the slot to a worse answer.
            if used + len(text) > max_chars:
                remaining = max_chars - used
                if remaining <= 200:
                    break
                text = text[:remaining].rstrip() + "…"
            results.append({
                "passage_id": r["passage_id"],
                "document_id": r["document_id"],
                "title": r["doc_title"],
                "section": r["section"],
                "text": text,
                "source_ref": r["source_ref"],
                "score": round(score, 4),
                "bm25": round(bm25, 4),
                "coverage": round(coverage, 4),
                "heading_hit": heading_hit,
            })
            used += len(text)
            if len(results) >= limit or used >= max_chars:
                break
        return {
            "registry_version": version,
            "results": results,
            "not_found": not bool(results),
            "terms": terms,
            "db_path": db_path,
        }
    finally:
        con.close()


def retrieve(query, context=None) -> dict:
    db_path = _db_from_context(context); con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        vr = con.execute("SELECT registry_version FROM registry_versions ORDER BY rowid DESC LIMIT 1").fetchone()
        version = vr[0] if vr else "unknown"
        ctx = context if isinstance(context, dict) else {}
        allowed_status = ctx.get("status", "live"); allowed = {allowed_status} if isinstance(allowed_status, str) else set(allowed_status)
        visibility = ctx.get("visibility", "public"); public = visibility != "private" and not ctx.get("internal", False)
        plan = ctx.get("plan")
        rows = []
        nq = _norm(str(query)); exact = []
        for r in con.execute("SELECT * FROM registry_items"):
            if r["status"] not in allowed: continue
            if public and r["visibility"] != "public": continue
            if plan and plan not in json.loads(r["available_in"] or "[]"): continue
            fields = [r["item_id"], r["name"]]
            for raw_field in (r["routes"], r["aliases"], r["supported_actions"], r["scenarios"]):
                try:
                    value = json.loads(raw_field or "[]")
                    fields.extend(value if isinstance(value, list) else [value])
                except (TypeError, ValueError):
                    fields.append(raw_field)
            if any(nq == _norm(str(x)) for x in fields): exact.append((r, 100.0))
        seen = set()
        for r, score in exact: seen.add(r["item_id"]); rows.append((r, score))
        terms = [t for t in _tokens(str(query)) if len(t) > 1]
        if terms:
            match = " OR ".join('"' + t.replace('"', '') + '"' for t in terms)
            for r in con.execute("SELECT i.*, bm25(fts_content, 8.0, 7.0, 7.0, 5.0, 5.0, 3.0, 1.0) AS rank FROM fts_content f JOIN registry_items i ON i.item_id=f.item_id WHERE fts_content MATCH ? ORDER BY rank LIMIT 32", (match,)):
                if r["item_id"] in seen or r["status"] not in allowed or (public and r["visibility"] != "public") or (plan and plan not in json.loads(r["available_in"] or "[]")): continue
                seen.add(r["item_id"]); rows.append((r, max(0.01, -float(r["rank"]))))
        rows.sort(key=lambda x: x[1], reverse=True); results = []
        for r, score in rows[:8]:
            routes = json.loads(r["routes"] or "[]"); refs = json.loads(r["source_refs"] or "[]")
            body = (r["summary"] + " " + r["body"]).strip(); snippet = re.sub(r"\s+", " ", body)[:280]
            results.append({"item_id":r["item_id"],"kind":r["kind"],"status":r["status"],"score":round(score, 4),"title":r["name"],"snippet":snippet,"route":routes[0] if routes else None,"supported_actions":json.loads(r["supported_actions"] or "[]"),"source_refs":refs})
        return {"registry_version": version, "results": results, "warnings": [], "not_found": not bool(results)}
    finally: con.close()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 1 or argv[0] not in ("build", "search"):
        print("usage: python -m backend.services.trust_knowledge build <registry> <knowledge_dir> <db> | search <db> <query>", file=sys.stderr); return 2
    if argv[0] == "build":
        if len(argv) != 4: return 2
        print(json.dumps(build_index(argv[1], argv[2], argv[3])))
    else:
        if len(argv) != 3: return 2
        print(json.dumps(retrieve(argv[2], {"db_path": argv[1]})))
    return 0


if __name__ == "__main__": raise SystemExit(main())

__all__ = [
    "build_index",
    "retrieve",
    "retrieve_passages",
    "ensure_index",
    "default_db_path",
    "default_knowledge_dir",
    "default_registry_path",
]
