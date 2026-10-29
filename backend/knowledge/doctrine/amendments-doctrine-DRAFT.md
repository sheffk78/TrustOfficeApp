# Doctrine — Trust Amendments (draft 2, 2026-10-29)

**Status:** DRAFT for Jeff review. Feeds the `check_amendment_preconditions` intent (shipped this session) and future amendment document flows.

## Rule 1 — Preconditions before any drafting conversation
The assistant runs the deterministic precondition block FIRST: instrument on file, amendment clause extracted (any key mentioning "amend" in the analysis), distribution standard for rights assessment, trustees identified, revocability status. A missing precondition is surfaced as what to upload, not as a blocker to conversation.

## Rule 2 — Revocable vs irrevocable is the load-bearing distinction
- **Revocable:** the grantor generally amends by instrument. The assistant still points at the instrument's amendment mechanics (signing, witnesses, notary) because mechanics live in the instrument, not the state.
- **Irrevocable:** amendment power flows ONLY from the instrument's amendment clause, plus narrow statutory escape hatches (decanting under the state's statute if verified, consent agreements with beneficiaries, court petitions). The assistant names the statutory escape hatches only when the state profile is verified.

## Rule 3 — The assistant explains, never executes law
The assistant can draft a checklist, list the clause language found in the member's document, and prepare the member for attorney review. It never purports to produce the executed amendment itself and never calls that review complete. Closing line on every amendment conversation: document review is not legal advice; the executed amendment merits attorney review in this state.

## Rule 4 — Amendment of beneficiary rights
When an amendment would touch beneficiary rights (standards, classes, terminations), the precondition review flags the distribution standard and current beneficiaries so the member sees the blast radius before drafting. The assistant does not opine on whether affected beneficiaries' consent is required unless the instrument itself says so.

## Rule 5 — Amendments in the document record
An executed amendment belongs in the Vault (category `amendment`) and should trigger a fresh document analysis — the precondition block reads the newest complete analysis. The assistant reminds the member of this loop when it notices an amendment-shaped upload or a stale analysis after amendment talk.

**Draft complete — remaining 4 doctrine files to follow this session.**