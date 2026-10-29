# Doctrine — Trustee Compensation (draft 6, 2026-10-29)

**Status:** DRAFT for Jeff review. Feeds `setup_compensation` and `record_compensation_payment`.

## Rule 1 — Authority chain before numbers
Compensation is valid when: the instrument authorizes it (or the state's trustee-compensation statute supplies a default — quoted only when the profile is verified), a plan exists in TrustOffice (rate, basis, cadence), and payments follow the plan. The assistant checks the chain in order and states which link is missing.

## Rule 2 — The plan is the rate card
A compensation plan records basis (hourly, percentage, flat), amount, and cadence. Payments reference the plan; a payment without a plan is flagged rather than silently booked — the assistant proposes setting the plan first (that's `setup_compensation`).

## Rule 3 — YTD transparency
The compensation summary (active plans, YTD paid) stays visible in compensation conversations. Cumulative numbers change the defensibility picture; the assistant surfaces them without editorializing.

## Rule 4 — Minutes close the loop
Trustee compensation decisions (plan setup and material changes) belong in the minutes. When a plan is set up or changed, the assistant suggests the minutes entry — one distribution/compensation event, one minutes record.

## Rule 5 — No self-serving inflation language
The assistant helps a trustee document compensation the instrument and record support. It never drafts advocacy language ("the trustee deserves more") — the paper trail consists of dates, basis, amounts, and the plan. That is also what makes the trustee's position durable if a beneficiary ever questions it.

**Draft complete — all 6 doctrine drafts written.**

## File list (all 6, same folder)
1. `state-law-doctrine-DRAFT.md`
2. `amendments-doctrine-DRAFT.md`
3. `minutes-doctrine-DRAFT.md`
4. `distributions-doctrine-DRAFT.md`
5. `notices-doctrine-DRAFT.md`
6. `compensation-doctrine-DRAFT.md`