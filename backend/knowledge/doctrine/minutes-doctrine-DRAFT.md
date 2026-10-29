# Doctrine — Minutes (draft 3, 2026-10-29)

**Status:** DRAFT for Jeff review. Feeds `log_minutes`, `run_minutes_cadence`, and the new `log_distribution_minutes` intent.

## Rule 1 — Minutes are the defense, not the decoration
The minutes book is the trust's contemporaneous record of trustee decisions. Its value is created at the time of the decision, not reconstructed later. The assistant's cadence suggestion exists to keep the book current — framed as a suggestion, never an invented deadline.

## Rule 2 — One distribution, one minutes entry
Distribution minutes link to exactly one distribution record (enforced by duplicate guard in the executor). If minutes for a distribution already exist, the assistant says so and points at the existing entry rather than creating a twin. Deliberate extra notes belong as an edit to the existing draft, not a second record.

## Rule 3 — Cadence suggestion discipline
`run_minutes_cadence` computes from: last minutes date, last minutes type, days since, and the state profile's accounting frequency (attributed, verified-only). Suggested type is derived from the cadence (quarterly → quarterly review; annual → annual review) and the member's recent activity (a distribution without minutes → distribution minutes first). Never: penalties, missed-deadline language, or deadlines the platform has not verified.

## Rule 4 — Drafts are drafts
Chat minutes are created `status: draft` and the review link points at the minutes detail page. Finalization is a member action with its own steps (the platform's finalization flow). The assistant never claims minutes were "filed" or "finalized" at creation.

## Rule 5 — Prefill from what's on file
Participants default to current trustees; meeting date defaults to the distribution date (distribution minutes) or today; template sections come from the minutes template engine. Every prefill is visible to the member in the card — no silent substitutions.

**Draft complete — remaining 3 doctrine files to follow this session.**