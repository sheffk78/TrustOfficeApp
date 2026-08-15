#!/usr/bin/env python3
"""
Deepsec-Findings Bridge — routes Deepsec scan candidates through the
OpenRouter rotation proxy with DeepSeek V4 Flash for investigation.

Why: Deepsec's agents (Codex, Pi, Claude) are hardcoded to their
respective provider SDKs. None support DeepSeek via OpenRouter.
This script reads the scan results, sends batches to the proxy, and
writes findings in Deepsec's report format.
"""

import json, os, sys, time, re, textwrap
from pathlib import Path
from collections import defaultdict

PROXY_URL = "http://127.0.0.1:11510/v1/chat/completions"
# Load first available OpenRouter key
KEYS_FILE = Path.home() / ".hermes" / "secrets" / "openrouter-keys.txt"

def load_key():
    if KEYS_FILE.exists():
        with open(KEYS_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("sk-or-v1-"):
                    return line
    return None

API_KEY = load_key()
if not API_KEY:
    print("ERROR: No OpenRouter key found", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path("/Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/TrustOfficeApp")
DATA_DIR = Path("/Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/TrustOfficeApp/.deepsec/data/TrustOfficeApp")

import requests

def investigate_file(filepath: str, candidates: list) -> dict:
    """Send a file + its candidates to DeepSeek V4 Flash for investigation."""
    full_path = PROJECT_ROOT / filepath
    if not full_path.exists():
        return {"file": filepath, "error": "file not found", "findings": []}
    
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return {"file": filepath, "error": str(e), "findings": []}
    
    # Build the prompt
    candidate_summaries = "\n".join(
        f"- Line {c['lineNumbers']}: [{c['vulnSlug']}] {c['matchedPattern'][:80]}"
        for c in candidates
    )
    
    prompt = textwrap.dedent(f"""\
    You are a security researcher reviewing Python FastAPI code for vulnerabilities.
    
    File: {filepath}
    
    Regex scan flagged these candidates:
    {candidate_summaries}
    
    Instructions:
    1. Review the actual code below
    2. For each candidate, determine if it's a TRUE POSITIVE (real vulnerability) or FALSE POSITIVE (safe by design)
    3. For true positives: describe the vulnerability, severity (critical/high/medium/low), and suggested fix
    4. Return ONLY a JSON array. Each element: {{
        "vulnSlug": "...",
        "title": "brief title",
        "severity": "critical|high|medium|low",
        "description": "what's wrong and why",
        "lineNumbers": [N],
        "recommendation": "how to fix",
        "confidence": "high|medium|low",
        "verdict": "true_positive|false_positive"
    }}
    5. If no true positives: return []
    
    === CODE ===
    {content[:12000]}
    === END CODE ===
    """)
    
    try:
        resp = requests.post(
            PROXY_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek/deepseek-v4-flash",
                "messages": [
                    {"role": "system", "content": "You are a security code reviewer. Output ONLY valid JSON arrays. No markdown, no prose."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 4000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        
        # Extract JSON from response
        # DeepSeek sometimes wraps in markdown
        json_match = re.search(r'\[.*\]', raw, re.DOTALL)
        if json_match:
            findings = json.loads(json_match.group())
        else:
            findings = []
        
        return {"file": filepath, "findings": findings, "raw_tokens": data.get("usage", {})}
    except Exception as e:
        return {"file": filepath, "error": str(e), "findings": []}


def run_investigation(limit: int = 50):
    """Read scan results and investigate prioritized files."""
    # Read scan file records
    files_dir = DATA_DIR / "files"
    if not files_dir.exists():
        print(f"No files dir at {files_dir}. Run 'deepsec scan' first.")
        return
    
    records = []
    for fp in sorted(files_dir.rglob("*.json")):
        with open(fp) as f:
            rec = json.load(f)
        # Skip venv, node_modules, tests
        path = rec.get("filePath", "")
        if not path:
            continue
        if any(x in path for x in ["venv", "node_modules", "__pycache__", "/tests/", "/test_"]):
            continue
        # Only backend Python files for now
        if not path.startswith("backend/") or not path.endswith(".py"):
            continue
        # Prioritize routers
        is_router = "routers/" in path
        candidate_count = len(rec.get("candidates", []))
        if candidate_count == 0:
            continue
        records.append({
            "path": path,
            "candidates": rec.get("candidates", []),
            "is_router": is_router,
            "count": candidate_count,
        })
    
    # Sort: routers first, then by candidate count desc
    records.sort(key=lambda r: (-r["is_router"], -r["count"]))
    
    to_investigate = records[:limit]
    print(f"Investigating {len(to_investigate)} files ({sum(r['count'] for r in to_investigate)} candidates)")
    
    results = []
    for i, rec in enumerate(to_investigate, 1):
        print(f"  [{i}/{len(to_investigate)}] {rec['path']} ({rec['count']} candidates)")
        result = investigate_file(rec["path"], rec["candidates"])
        true_positives = [f for f in result.get("findings", []) if f.get("verdict") == "true_positive"]
        print(f"       -> {len(true_positives)} true positives, {len(result.get('findings',[]))-len(true_positives)} false positives")
        results.append(result)
        time.sleep(1)  # rate limit buffer
    
    # Write report
    report_dir = DATA_DIR / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"deepsec-findings-{int(time.time())}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    
    # Summary
    total_findings = sum(len(r.get("findings", [])) for r in results)
    total_tp = sum(len([f for f in r.get("findings", []) if f.get("verdict") == "true_positive"]) for r in results)
    total_fp = total_findings - total_tp
    
    print(f"\n=== Summary ===")
    print(f"Files investigated: {len(results)}")
    print(f"Total findings: {total_findings}")
    print(f"True positives: {total_tp}")
    print(f"False positives: {total_fp}")
    print(f"Report saved: {report_path}")
    
    return results


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run_investigation(limit)
