"""
Drift gate: backend/knowledge/16-minutes-types-and-templates.md must stay in
lockstep with routers/template_registry.TEMPLATE_REGISTRY.

Why this exists (2026-10-23): the knowledge file claimed "41 minutes template
types" and enumerated 37, while the registry had 43. Six real templates were
missing from the file, four of its category headings did not match the rows
underneath them, and the live assistant told members "Here are all 41 minutes
template types" — a false product fact, sourced from a stale KB slice that the
Trust Practice Core has to compete with for the same question.

The KB file is injected into the chat prompt, so its claims are member-facing.
This test makes drift a build failure instead of a live surprise.

Guards, in order:
  1. The "N minutes template types" count equals len(TEMPLATE_REGISTRY).
  2. The catalog table lists every registry slug, and no slug that isn't one.
  3. Every category heading's count matches the rows beneath it.
  4. The mapping table covers every registry slug.
  5. No registry display_name contradicts the file's name for the same slug.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

KB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "knowledge", "16-minutes-types-and-templates.md"
)


def _load_kb() -> str:
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _registry() -> dict:
    from routers.template_registry import TEMPLATE_REGISTRY
    return TEMPLATE_REGISTRY


class TestMinutesKnowledgeMatchesRegistry:
    def test_kb_file_exists(self):
        assert os.path.isfile(KB_PATH), f"missing knowledge file: {KB_PATH}"

    def test_stated_count_matches_registry(self):
        kb = _load_kb()
        registry = _registry()
        m = re.search(r"supports (\d+) minutes template types", kb)
        assert m, "knowledge file no longer states a template count — update the test"
        assert int(m.group(1)) == len(registry), (
            f"knowledge file says {m.group(1)} template types, "
            f"registry has {len(registry)}"
        )

    def test_heading_count_matches_registry(self):
        kb = _load_kb()
        registry = _registry()
        m = re.search(r"^## All (\d+) Template Types$", kb, re.M)
        assert m, "knowledge file no longer has an '## All N Template Types' heading"
        assert int(m.group(1)) == len(registry), (
            f"heading says {m.group(1)}, registry has {len(registry)}"
        )

    def test_catalog_lists_every_registry_template(self):
        kb = _load_kb()
        registry = _registry()
        listed = set(re.findall(r"^\| `([a-z_]+)`", kb, re.M))
        missing = sorted(set(registry) - listed)
        extra = sorted(listed - set(registry))
        assert not missing, f"templates missing from the knowledge file: {missing}"
        assert not extra, f"knowledge file lists non-existent templates: {extra}"

    def test_category_headings_match_their_rows(self):
        kb = _load_kb()
        for m in re.finditer(r"^### (.+?) \((\d+) templates?\)$", kb, re.M):
            category, stated = m.group(1), int(m.group(2))
            start = m.end()
            nxt = kb.find("\n### ", start)
            section = kb[start: nxt if nxt > 0 else len(kb)]
            rows = len(re.findall(r"^\| `([a-z_]+)`", section, re.M))
            assert stated == rows, (
                f"category '{category}' says {stated} templates but has {rows} rows"
            )

    def test_mapping_table_covers_every_template(self):
        kb = _load_kb()
        registry = _registry()
        mapping = set(re.findall(r"\|\s*`([a-z_]+)`\s*\|\s*$", kb, re.M))
        missing = sorted(set(registry) - mapping)
        assert not missing, f"templates missing from the request-mapping table: {missing}"

    def test_names_agree_with_registry(self):
        kb = _load_kb()
        registry = _registry()
        for slug, definition in registry.items():
            display = definition.get("display_name")
            if not display:
                continue
            row = re.search(rf"^\| `{re.escape(slug)}` \| ([^|]+) \|", kb, re.M)
            assert row, f"{slug} is not in the knowledge catalog"
            name = row.group(1).strip()
            assert name == display, (
                f"{slug}: knowledge file says {name!r}, "
                f"registry says {display!r}"
            )
