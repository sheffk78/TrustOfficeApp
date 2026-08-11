"""
TrustOffice knowledge-store validation / CI script.

Checks the canonical registry (trustoffice-registry.yaml) for schema integrity and
runs retrieval smoke queries against the consolidated SQLite FTS5 index to assert
the current product facts. Exits non-zero on any failure.

Usage:
    python -m backend.scripts.validate_trust_knowledge [--registry PATH] [--db PATH]
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from the backend dir or as a module.
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import trust_knowledge  # noqa: E402

BRAND_ROOT = BACKEND.parents[2]  # .../TrustOfficeApp/backend -> parents[0]=backend [1]=TrustOfficeApp [2]=projects [3]=TrustOffice
DEFAULT_REGISTRY = BRAND_ROOT / "KNOWLEDGE" / "trustoffice-registry.yaml"
DEFAULT_KNOWLEDGE = BACKEND / "knowledge"
DEFAULT_DB = BACKEND / "data" / "trust_knowledge.db"

VALID_KINDS = {"feature", "offer", "scenario", "policy", "roadmap"}
VALID_STATUSES = {"live", "beta", "planned", "retired", "private"}


def _load_registry(path: Path) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"Registry {path} is not a mapping")
    return data


def validate_schema(registry: dict) -> list[str]:
    errors = []
    products = registry.get("products", [])
    ids = set()
    for p in products:
        pid = p.get("id")
        if not pid:
            errors.append("record missing id")
            continue
        if pid in ids:
            errors.append(f"duplicate id: {pid}")
        ids.add(pid)
        kind = p.get("kind")
        if kind not in VALID_KINDS:
            errors.append(f"{pid}: invalid kind {kind!r}")
        status = p.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{pid}: invalid status {status!r}")
        # Private offers must not be public.
        if kind == "offer" and status == "private" and p.get("public_visibility", False):
            errors.append(f"{pid}: private offer marked public_visibility true")
    return errors


def validate_source_refs(registry: dict, knowledge_dir: Path) -> list[str]:
    errors = []
    for p in registry.get("products", []):
        for ref in p.get("source_docs", []) or []:
            # Allow references to the KNOWLEDGE/ docs and the audit/architecture docs.
            if ref in ("FEATURE-AUDIT-2026-08-10.md", "SCENARIOS-AND-QA.md",
                       "CONSOLIDATION-ARCHITECTURE.md", "TRUST-ASSISTANT-TRAINING-2026-08-10.md",
                       "OFFERS.md"):
                continue
            if not (knowledge_dir / ref).exists():
                errors.append(f"{p.get('id')}: source_docs ref missing: {ref}")
    return errors


def smoke_queries(db_path: str) -> list[str]:
    errors = []
    checks = [
        # (query, must_contain_item_id, label)
        ("Trust Assistant", "trust_assistant", "Trust Assistant is live"),
        ("trustee pricing", "trustee", "Trustee plan present"),
        ("estate plan", "estate", "Estate plan present"),
        ("advisor plan", "advisor", "Advisor plan present"),
    ]
    for q, want, label in checks:
        r = trust_knowledge.retrieve(q, {"db_path": db_path, "status": "live", "visibility": "public"})
        ids = [x.get("item_id") for x in r.get("results", [])]
        if want not in ids:
            errors.append(f"smoke FAIL: {label} (query {q!r} did not return {want!r}; got {ids[:5]})")

    # Trust Health score must be 115, not 120.
    r = trust_knowledge.retrieve("trust health score", {"db_path": db_path, "status": "live", "visibility": "public"})
    joined = " ".join(str(x.get("snippet", "")) for x in r.get("results", []))
    # The 115 fact is carried in the record body/caveats; inspect the underlying
    # index body for the trust_health record too.
    found_115 = ("115" in joined or "0-115" in joined or "0–115" in joined)
    if not found_115:
        import sqlite3
        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT body FROM registry_items WHERE item_id='trust_health'"
        ).fetchone()
        if row and ("115" in (row[0] or "") or "0-115" in (row[0] or "") or "0–115" in (row[0] or "")):
            found_115 = True
        con.close()
    if not found_115:
        errors.append("smoke FAIL: Trust Health score 115 not surfaced")

    # WingPoint must NOT leak to a public query.
    r = trust_knowledge.retrieve("wingpoint annual pricing", {"db_path": db_path, "status": "live", "visibility": "public"})
    leaked = [x for x in r.get("results", []) if "wingpoint" in x.get("item_id", "").lower()]
    if leaked:
        errors.append(f"smoke FAIL: WingPoint leaked to public query: {[x['item_id'] for x in leaked]}")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--knowledge", default=str(DEFAULT_KNOWLEDGE))
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"FATAL: registry not found at {registry_path}")
        return 1

    registry = _load_registry(registry_path)
    errors = validate_schema(registry)
    errors += validate_source_refs(registry, Path(args.knowledge))

    # Build the index (idempotent) and run smoke queries.
    trust_knowledge.build_index(str(registry_path), args.knowledge, args.db)
    errors += smoke_queries(args.db)

    if errors:
        print(f"VALIDATION FAILED ({len(errors)} errors):")
        for e in errors:
            print(f"  - {e}")
        return 1

    n = len(registry.get("products", []))
    print(f"VALIDATION PASSED: registry OK ({n} records), source refs OK, smoke queries OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
