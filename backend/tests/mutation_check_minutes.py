"""Mutation harness: prove each regression test actually catches its bug.

For each mutation we revert one specific fix, run the suite, and assert the
expected test(s) fail. Restores the original file afterwards.
"""
import os
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
BASE = BACKEND.parent  # repo root
TESTS = "tests/test_minutes_prefill_and_link.py"


def run_suite():
    r = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "-p", "no:cacheprovider"],
        cwd=str(BACKEND), capture_output=True, text=True, env=os.environ.copy(),
    )
    out = r.stdout + r.stderr
    failed = {l.split("::")[-1].split("[")[0] for l in out.splitlines() if l.startswith("FAILED")}
    tail = [l for l in out.splitlines() if " passed" in l or " failed" in l]
    return failed, (tail[-1] if tail else out[-400:])


MUTATIONS = [
    (
        "M1 silent downgrade to general",
        "backend/minutes_type_normalizer.py",
        "    if alias and alias in valid:",
        "    if True:\n        alias = alias or \"general\"",
        {"test_normalizer_maps_quarterly_review_to_quarterly",
         "test_normalizer_unresolvable_returns_none_not_general",
         "test_exec_minutes_records_quarterly_not_general",
         "test_exec_minutes_unresolvable_type_falls_back_with_caveat"},
    ),
    (
        "M2 review_link back to the 404 /edit route",
        "backend/routers/chat.py",
        '"review_link": f"/minutes/{result.minutes_id}",',
        '"review_link": f"/minutes/{result.minutes_id}/edit",',
        {"test_review_link_points_at_a_real_frontend_route"},
    ),
    (
        "M3 prefill disabled (empty-shell draft)",
        "backend/routers/chat.py",
        '    out.update({\n        "prefilled": True,',
        '    out.update({\n        "prefilled": False,',
        {"test_exec_minutes_prefills_sections_from_trust_data"},
    ),
    (
        "M4 success message drops the link",
        "backend/approval_handler.py",
        '    if review_link:\n        text += f" Open it: {review_link}"',
        '    if False:\n        text += f" Open it: {review_link}"',
        {"test_success_message_includes_review_link",
         "test_approval_reply_text_carries_the_link"},
    ),
    (
        "M5 participants not defaulted to trustees on record",
        "backend/routers/chat.py",
        '    resolved_participants = participants_text or ""\n    if not resolved_participants:\n        resolved_participants = ", ".join(trustee_names)',
        '    resolved_participants = participants_text or ""',
        {"test_exec_minutes_participants_default_to_trustees_on_record"},
    ),
]


def main():
    baseline_failed, baseline_tail = run_suite()
    print(f"BASELINE: {baseline_tail}  failed={sorted(baseline_failed)}")
    if baseline_failed:
        print("!! baseline is not green — aborting mutation run")
        return 2

    all_ok = True
    for label, relpath, old, new, expect_fail in MUTATIONS:
        f = BASE / relpath
        orig = f.read_text()
        if old not in orig:
            print(f"!! {label}: pattern not found in {relpath} — SKIPPED")
            all_ok = False
            continue
        f.write_text(orig.replace(old, new, 1))
        try:
            failed, tail = run_suite()
        finally:
            f.write_text(orig)
        caught = expect_fail & failed
        ok = bool(caught)
        all_ok = all_ok and ok
        status = "CAUGHT" if ok else "NOT CAUGHT"
        print(f"\n{status}: {label}")
        print(f"   result: {tail}")
        print(f"   expected failures caught: {sorted(caught)}")
        if not ok:
            print(f"   MISSED: {sorted(expect_fail - failed)}")

    # restore check
    base_failed, base_tail = run_suite()
    print(f"\nRESTORED BASELINE: {base_tail}")
    if base_failed:
        all_ok = False

    print("\nRESULT:", "ALL MUTATIONS CAUGHT" if all_ok else "SOME MUTATIONS NOT CAUGHT")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
