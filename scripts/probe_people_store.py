#!/usr/bin/env python3
"""Post-deploy probe: TrustOffice /api/service/people/{id} notes/tasks store.

READ-ONLY by default. Pass --write to exercise the write path (note -> task ->
task-status done -> re-read), which is what Jeff's card flow does end to end.

Usage (from the TrustOfficeApp repo root):

    # read-only shape check on a real lead id
    python3 scripts/probe_people_store.py --person-id lead_5a66201222c5

    # full flow incl. writes (only after the P4 store is deployed)
    python3 scripts/probe_people_store.py --person-id lead_5a66201222c5 --write

Exit 0 = contract holds. Exit 1 = a check failed (details on stdout).
The service key is read from ~/.hermes/secrets/trustoffice-leads-service.key
(skipping the header line); NEVER printed.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.trustoffice.app"
KEY_PATH = os.path.expanduser("~/.hermes/secrets/trustoffice-leads-service.key")
# Cloudflare (error 1010) bans the bare python-urllib signature; send the same
# UA the repo's curl-based probes use.
USER_AGENT = "curl/8.7.1"


def read_key(path=KEY_PATH):
    """Last non-empty line of the key file (line 1 is a descriptive header)."""
    with open(path, "r", encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]
    if not lines:
        raise SystemExit(f"no service key found in {path}")
    return lines[-1]


def call(base, path, key, method="GET", body=None, timeout=30) -> "tuple[int, dict]":
    """Return (status, parsed_body). parsed_body is a dict on success; when the
    payload isn't JSON (e.g. a Cloudflare HTML/edge error) it is {'raw': ...}."""
    data = None
    headers = {"X-Service-Key": key, "Accept": "application/json",
               "User-Agent": USER_AGENT}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)

    def _parse(raw):
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {"raw": raw.decode("utf-8", "replace")[:400]}
        return parsed if isinstance(parsed, dict) else {"raw": parsed}

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _parse(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--person-id", default="lead_5a66201222c5",
                    help="exact person id stored by the OS card (colon forms allowed)")
    ap.add_argument("--base", default=os.environ.get("TO_BASE", DEFAULT_BASE))
    ap.add_argument("--write", action="store_true",
                    help="exercise note/task/task-status writes (mutates the store)")
    ap.add_argument("--key-file", default=KEY_PATH)
    args = ap.parse_args()

    key = read_key(args.key_file)
    pid = args.person_id
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))

    # ---- 0. auth gate: no key must be 401 ----
    status, _ = call(args.base, f"/api/service/people/{pid}/notes", "")
    check("auth: missing key -> 401", status == 401, f"got {status}")

    # ---- 1. GET notes ----
    status, notes_body = call(args.base, f"/api/service/people/{pid}/notes", key)
    check("GET /notes -> 200", status == 200, f"got {status} {notes_body}")
    check("GET /notes shape {person_id, notes, as_of}",
          isinstance(notes_body.get("notes"), list) and notes_body.get("person_id") == pid)

    # ---- 2. GET tasks ----
    status, tasks_body = call(args.base, f"/api/service/people/{pid}/tasks", key)
    check("GET /tasks -> 200", status == 200, f"got {status} {tasks_body}")
    check("GET /tasks shape {person_id, tasks, as_of}",
          isinstance(tasks_body.get("tasks"), list))

    # ---- 3. GET detail carries notes + tasks (one read) ----
    status, detail = call(args.base, f"/api/service/people/{pid}/detail", key)
    check("GET /detail -> 200", status == 200, f"got {status}")
    check("GET /detail carries notes[] + tasks[]",
          isinstance(detail.get("notes"), list) and isinstance(detail.get("tasks"), list),
          f"keys={sorted(detail.keys())}")

    if args.write:
        # ---- 4. POST note ----
        status, note_body = call(args.base, f"/api/service/people/{pid}/note", key,
                                 method="POST", body={"text": "probe: note survives refresh"})
        note = (note_body or {}).get("note") or {}
        check("POST /note -> 200 success", status == 200 and note_body.get("success") is True,
              f"got {status} {note_body}")
        check("POST /note returns {id,text,at}",
              bool(note.get("id")) and bool(note.get("at")), str(note))

        # ---- 5. POST task ----
        status, task_body = call(args.base, f"/api/service/people/{pid}/task", key,
                                 method="POST", body={"title": "probe: task flips to done",
                                                      "status": "open"})
        task = (task_body or {}).get("task") or {}
        check("POST /task -> 200 success", status == 200 and task_body.get("success") is True,
              f"got {status} {task_body}")
        check("POST /task returns open row with id",
              task.get("status") == "open" and bool(task.get("id")), str(task))

        # ---- 6. flip task to done ----
        tid = task.get("id")
        status, flip = call(args.base, f"/api/service/people/{pid}/task-status", key,
                            method="POST", body={"task_id": tid, "status": "done"})
        check("POST /task-status -> done", status == 200 and (flip or {}).get("status") == "done",
              f"got {status} {flip}")

        # ---- 7. unknown task id -> 404 ----
        status, _ = call(args.base, f"/api/service/people/{pid}/task-status", key,
                         method="POST", body={"task_id": "pt_doesnotexist", "status": "done"})
        check("POST /task-status unknown id -> 404", status == 404, f"got {status}")

        # ---- 8. re-read: both survive (server-side persistence) ----
        _, notes_after = call(args.base, f"/api/service/people/{pid}/notes", key)
        _, tasks_after = call(args.base, f"/api/service/people/{pid}/tasks", key)
        note_ids = [n.get("id") for n in notes_after.get("notes", [])]
        task_rows = {t.get("id"): t.get("status") for t in tasks_after.get("tasks", [])}
        check("note survives re-read", note.get("id") in note_ids)
        check("task survives re-read as done", task_rows.get(tid) == "done", str(task_rows))

        # ---- 9. detail carries the same rows ----
        _, detail_after = call(args.base, f"/api/service/people/{pid}/detail", key)
        check("detail carries new note + task",
              note.get("id") in [n.get("id") for n in detail_after.get("notes", [])]
              and tid in [t.get("id") for t in detail_after.get("tasks", [])])

    failed = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed"
          + ("" if failed else "  -- contract holds"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
