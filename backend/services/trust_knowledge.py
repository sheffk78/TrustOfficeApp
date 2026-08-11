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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LAST_DB: str | None = None


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


def _j(value: Any) -> str: return json.dumps(value if value is not None else [], ensure_ascii=False)
def _norm(value: str) -> str: return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
def _tokens(value: str) -> list[str]: return re.findall(r"[a-z0-9_]+", value.lower())


def build_index(registry_path, knowledge_dir, db_path) -> dict:
    global _LAST_DB
    registry = _yaml_load(Path(registry_path))
    version = str(registry.get("registry_version", "unknown"))
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
        CREATE VIRTUAL TABLE fts_content USING fts5(item_id UNINDEXED, name, aliases, actions, tags, scenarios, summary, body,
          tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE registry_versions (registry_version TEXT, built_at TEXT, items INTEGER, chunks INTEGER);
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
        for docid, filename, body, meta in docs:
            dh = hashlib.sha256(body.encode()).hexdigest()
            con.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", (docid, str(meta.get("title", filename)), body, str(meta.get("status", "published")), dh, _j(meta)))
            links = _as_list(meta.get("feature_ids")) + _as_list(meta.get("item_ids")) + _as_list(meta.get("scenario_ids"))
            links = links or [docid]
            for iid in links:
                if iid not in item_ids:
                    iid = docid
                    if not con.execute("SELECT 1 FROM registry_items WHERE item_id=?", (iid,)).fetchone():
                        con.execute("INSERT INTO registry_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (iid, "document", str(meta.get("title", filename)), "live", "", "", "[]", "[]", "[]", "[]", "[]", "[]", "public", _j([filename]), _j({"id":iid})))
                        con.execute("INSERT INTO fts_content VALUES (?,?,?,?,?,?,?,?)", (iid, str(meta.get("title", filename)), "", "", "", "", "", body))
                con.execute("INSERT INTO chunks(item_id,document_id,kind,text,source_ref) VALUES (?,?,?,?,?)", (iid, docid, "document", body, filename))
        chunk_count = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        con.execute("INSERT INTO registry_versions VALUES (?,?,?,?)", (version, datetime.now(timezone.utc).isoformat(), len(item_ids), chunk_count))
        con.commit()
    finally: con.close()
    os.replace(tmp, db); _LAST_DB = str(db)
    return {"registry_version": version, "items": len(item_ids), "chunks": chunk_count, "ok": True}


def _db_from_context(context):
    if isinstance(context, str): return context
    if isinstance(context, dict) and context.get("db_path"): return context["db_path"]
    return _LAST_DB or os.environ.get("TRUST_KNOWLEDGE_DB", "trust_knowledge.db")


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

__all__ = ["build_index", "retrieve"]
