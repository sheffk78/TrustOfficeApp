# TA Knowledge Golden Set — 40 Questions (2026-10-30, Phase A-2)

Deterministic knowledge-accuracy evaluation for the Trust Assistant retrieval surface.
Wired into the existing `ta_eval.py` rails (see `--mode knowledge`). No LLM scoring —
every assertion compares retrieval output against the corpus facts below.

## Scoring contract (per question)

Each golden question asserts up to three deterministic checks against
`services.trust_knowledge.retrieve_passages()`:

1. **`expected_sources` (top-N hit):** at least one passage in the top-2 comes from one
   of these corpus files. Calibrated against the current re-ranker, not aspirational —
   any-of lists cover legitimate overlap (e.g. `17-*.md` vs `24-utc-*.md`).
2. **`key_facts` (fact presence):** every phrase must appear verbatim (case-insensitive)
   in the union of the top-4 retrieved passages for the *granted* audience.
3. **`forbidden_for_no_grant` (audience isolation):** for questions marked with this
   flag, the no-grant (universal-only) caller must get ZERO wingpoint-tier sources —
   the fail-closed behavior we shipped in Phase A-1.

## Behavior asserts (council spec item 2)

- `education_not_advice`: WP inner-work/defend questions expect course/education docs
  as the source — never a product (12-15) or statute-quote doc as top source. The
  content-class boundary (Phase B #5) will render these as "EDUCATION — not law".
- `doctrine_for_doctrine_questions`: UTC-doctrine questions must surface the 24-utc-*
  file, not a marketing/outline file.

## Composition

- UTC doctrine: 8 (01/02/03/04/05/06/07/08)
- Notice register + state law: 3 (09, 06-general, Utah)
- Trustee 101: 4 (26/27/28/30)
- Product/how-to: 6 (05, 07, 08, 09, 12, 22, 23)
- Trust types: 4 (17-spendthrift, 17-special-needs, 17-revocable, 16-amendments)
- Tax: 2 (02-1041, 29-calendar)
- WP tax-101 (wingpoint tier): 5 (40, 43, 45, 50, 52)
- WP defend (wingpoint tier): 4 (59, 61, 63, 66)
- WP inner-work (wingpoint tier): 4 (70, 72, 76, 78)

## Maintenance rules

- Any `prompts/*.md` or retrieval-scoring change MUST run this set green before merge
  (council Phase A-2 gate). Run: `python scripts/ta_eval.py --mode knowledge`
- Failures are triaged as either (a) retrieval regression → fix scoring, or
  (b) calibration drift → update this file WITH the recalibration probe in the PR.
- Golden questions are never edited to make the code pass; code is fixed, or the
  golden is recalibrated with evidence.