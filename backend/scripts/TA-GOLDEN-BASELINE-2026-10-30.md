# TA Golden Eval — Baseline Report (2026-10-30)

**Command:** `env -u PYTHONPATH ../.venv/bin/python scripts/ta_eval.py --mode knowledge` (from `backend/`)
**Commit:** `cc37f33` — golden eval + state-family cap + Phase B plan persona
**Machine-readable results:** `/Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/TrustOfficeApp/backend/scripts/ta_golden_results.json`

## Headline

| Metric | Value |
|---|---|
| Golden questions | 40 (12 UTC doctrine, 3 state law, 4 Trustee-101, 6 product, 5 trust types, 4 tax, 10 WingPoint tier) |
| **Passed** | **22 / 40 = 55.0%** — this is the v1 baseline |
| Isolation (WP fail-closed, both surfaces) | **40 / 40 — zero leaks.** The 2026-10-30 audience gate holds on every question |
| Doctrine-triggered | 15 / 40 (regex trigger-gated, exactly as prod) |
| Education / intent-mode baseline (pre-existing) | 36% overall / 64% intent accuracy — stale scenario expectations, separate work item |

## What the eval measures (and why this is the member-real bar)

The two surfaces a member's chat turn actually assembles, both with production defaults:
1. **Prompt knowledge slice** — `chat_service._format_knowledge_context(user_message, intent="ask_knowledge", audiences=grant)` — the relevance-ranked 4,500-char slice.
2. **Retrieval block** — `trust_retrieval.fetch_doctrine(message, allowed_audiences=grant)` — trigger-gated, `limit=6, max_chars=3600`.

A question passes only when the expected source appears in the first two surfaced sources AND every verbatim key fact is present in the union text the LLM would see. No LLM judging, no network, no login — deterministic and CI-safe.

## Fixed during this build (verified by the eval itself)

**State-file flood (production bug, fixed in `_ranked_knowledge_slice`):** before the family cap, a generic doctrine question ("what must exist for a settlor to create a trust") surfaced 8× near-identical "Beneficiary Notice Requirements" boilerplate from the 50 state-compliance files, and the file that actually answers it (`24-utc-01`, s.402 checklist) never made the slice. Family cap = 1 passage per template family, waived when the member names a specific state (pinned topics keep their +2.0 bonus). Also applies to the 5 beneficiary-communication template copies.

**Two eval-harness bugs fixed in `build_trust_context`-adjacent rails:** audience string→char-list coercion (queries granted as `[list("wingpoint")]` char sets silently retrieved universal-only), and golden filenames vs slice stems.

## The 18 failures — honest findings, not eval bugs

Category A — **slice depth (9):** the answering section exists in the corpus but sits below the 4,500-char cut. utc-02 (Care section), utc-04, utc-05, utc-07, utc-08, t101-03, prod-04, type-01, wp-def-04. Root cause: passage scoring favors headings/message tokens but the winning file's deep section loses the budget to adjacent files. Fix direction (Phase B/C): doctrine-leg boost terms (`fetch_doctrine` vocabulary) applied in the ranked slicer, or a two-pass slice that reserves budget for the top file's second-best section.

Category B — **crowding by summary/product files (5):** utc-09 (12-features first), t101-02 + t101-04 (11-video-library lesson summaries outrank the 28/30 checklists), tax-02 (20-lifecycle + video lesson outrank the tax calendar), prod-06 (13-workflows — accepted as legit alt, still below expected pair). These are the same-content-different-file pattern; the corpus genuinely carries the answer in the canonical file, the ranker can't tell canonical from summary.

Category C — **WP course-meta questions (4):** wp-tax-04/05, wp-inw-03/04 — "what does the course cover / series" questions rank course CONTENT sections over the outline/research files, because the ranker matches body tokens and outline files are heading-heavy. The wrong-but-related WP files surfaced are still granted-tier (no isolation issue), just not the canonical outline.

Category D — **(0)** isolation or safety failures.

## Gates this eval now enforces

- Per council verdict: any `prompts/*.md` change must keep this suite green (no accuracy regression) before merge.
- Jeff's monthly re-eval directive: run this mode, diff against this baseline; new failures = regression, not noise.
- Isolation asserts ride with every question — any audience-gate regression shows as leak failures, not silent drift.

## Known limits (documented in GOLDEN-SET-NOTES.md)

- Retrieval is sensitive to corpus re-writes: key-fact phrases are verbatim by design — a section reworded under the same meaning will fail its golden. That is intentional: corpus edits get reviewed against goldens, not the other way round.
- Category A findings mean the eval is a floor, not a ceiling — expect the number to rise as slice-depth work lands, never silently fall.