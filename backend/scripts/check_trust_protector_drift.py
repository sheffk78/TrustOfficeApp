#!/usr/bin/env python3
"""
Verify that the frontend TRUST_PROTECTOR_POWERS constant and the backend
email label map both agree with the canonical backend/data/trust_protector_powers.json.

Run as a CI / pre-push guard:

    python backend/scripts/check_trust_protector_drift.py

Exits 0 (no drift) or 1 (drift found). If drift is found, regenerate the frontend
constant and fix the backend label map so they match the JSON.
"""
import json
import pathlib
import re
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent  # backend/
JSON_PATH = BACKEND_DIR / "data" / "trust_protector_powers.json"
FRONTEND_FILE = BACKEND_DIR.parent / "frontend" / "src" / "pages" / "trustProtectorPowers.js"
SUCCESSOR_ROUTER = BACKEND_DIR / "routers" / "successor.py"


def load_json_powers() -> dict:
    data = json.loads(JSON_PATH.read_text())
    return {p["value"]: {"label": p["label"], "description": p["description"]} for p in data["powers"]}


def load_frontend_powers() -> dict:
    src = FRONTEND_FILE.read_text()
    block = re.search(r"export const TRUST_PROTECTOR_POWERS = \[(.*?)\];", src, re.S)
    if not block:
        return {}
    # Parse each { value: "...", label: "...", description: "..." } entry.
    result = {}
    for m in re.finditer(
        r"value:\s*\"([^\"]+)\",\s*label:\s*\"([^\"]+)\",\s*description:\s*\"((?:[^\"\\]|\\.)*)\"",
        block.group(1),
    ):
        result[m.group(1)] = {"label": m.group(2), "description": m.group(3)}
    return result


def load_backend_map() -> dict:
    src = SUCCESSOR_ROUTER.read_text()
    # The backend now loads labels from the JSON at runtime; the inline fallback
    # map must stay in sync so drift check covers it.
    block = re.search(r"_TRUST_PROTECTOR_POWER_LABELS_FALLBACK = \{(.*?)\}", src, re.S)
    if not block:
        return {}
    result = {}
    for m in re.finditer(r"\"([^\"]+)\":\s*\"([^\"]+)\"", block.group(1)):
        result[m.group(1)] = m.group(2)
    return result


def main():
    errors = []

    json_powers = load_json_powers()
    front_powers = load_frontend_powers()
    backend_map = load_backend_map()

    if not front_powers:
        errors.append("frontend constant not found — regenerate with generate_trust_protector_powers.py")
    else:
        json_keys = set(json_powers)
        front_keys = set(front_powers)
        for k in sorted(json_keys - front_keys):
            errors.append(f"frontend missing power: {k}")
        for k in sorted(front_keys - json_keys):
            errors.append(f"frontend has power not in JSON: {k}")
        for k in json_keys & front_keys:
            if json_powers[k] != front_powers[k]:
                errors.append(f"frontend label/description mismatch for: {k}")

    if backend_map is None:
        errors.append("backend label map not found in successor.py")
    else:
        for k in sorted(json_keys - set(backend_map)):
            errors.append(f"backend label map missing power: {k}")
        for k in json_keys & set(backend_map):
            if backend_map[k] != json_powers[k]["label"]:
                errors.append(f"backend label mismatch for: {k} ({backend_map[k]!r} != {json_powers[k]['label']!r})")

    if errors:
        print("DRIFT DETECTED:")
        for e in errors:
            print(f"  - {e}")
        print("Fix: edit backend/data/trust_protector_powers.json, then run")
        print("  python backend/scripts/generate_trust_protector_powers.py")
        print("and update the _TRUST_PROTECTOR_POWER_LABELS_FALLBACK map in backend/routers/successor.py.")
        return 1

    print(f"OK: {len(json_powers)} powers in sync across JSON, frontend, and backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
