"""
Knowledge-store audience-tier validation (WingPoint isolation).

Walks every backend/knowledge/**/*.md and asserts the audience-tiering
contract that chat_service._load_knowledge_base() and the retrieval gates
rely on:

  1. Front-matter, when present, parses through the same light parser the
     loader uses (no ambiguity that could silently change audience routing).
  2. Files with no front-matter default to the "universal" audience — same
     behavior as the loader.
  3. Any file under backend/knowledge/wingpoint/ MUST declare `audiences`
     explicitly in its front-matter. A WP-tier file that forgets its
     declaration would silently drop into the universal partition and leak
     WingPoint-only doctrine to every member.

Exit 1 on any violation; silent success (exit 0) otherwise. Wired into
backend/tests/test_wingpoint_knowledge_isolation.py so pytest enforces it.

Usage:
    python3 backend/scripts/validate_knowledge.py [root]
"""
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def validate(root: str = "") -> list:
    """Return a list of violation strings ([] = the tree is valid)."""
    knowledge_root = root or os.path.join(BACKEND, "knowledge")
    if not os.path.isdir(knowledge_root):
        return [f"knowledge root missing: {knowledge_root}"]

    violations = []
    wingpoint_dir = os.path.join(knowledge_root, "wingpoint")

    for dirpath, _dirnames, filenames in os.walk(knowledge_root):
        for fname in sorted(filenames):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(dirpath, fname)
            rel = os.path.relpath(path, knowledge_root)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as e:
                violations.append(f"{rel}: unreadable ({e})")
                continue

            # Same front-matter parser the loader uses.
            try:
                from chat_service import _parse_front_matter
                meta, _body = _parse_front_matter(text)
            except Exception as e:
                violations.append(f"{rel}: front-matter parser raised ({e})")
                continue

            in_wingpoint_dir = os.path.commonpath(
                [os.path.abspath(dirpath), os.path.abspath(wingpoint_dir)]
            ) == os.path.abspath(wingpoint_dir) if os.path.exists(wingpoint_dir) else (
                rel.startswith("wingpoint" + os.sep) or rel == "wingpoint"
            )
            if in_wingpoint_dir:
                # HARD RULE: WP-directory files must declare audiences.
                if not meta.get("audiences"):
                    violations.append(
                        f"{rel}: file under knowledge/wingpoint/ does not "
                        "declare `audiences` in front-matter — it would "
                        "silently default to the universal partition"
                    )
                    continue
                audiences = meta.get("audiences")
                if isinstance(audiences, str):
                    audiences = [audiences]
                if not any(
                    str(a).strip().lower() == "wingpoint" for a in audiences
                ):
                    violations.append(
                        f"{rel}: declares audiences={meta.get('audiences')!r} "
                        "but does not include 'wingpoint' while living under "
                        "knowledge/wingpoint/"
                    )

    return violations


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else ""
    violations = validate(root)
    if violations:
        print("KNOWLEDGE AUDIENCE-TIER VALIDATION FAILED:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("Knowledge audience-tier validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())