# Doctrine — Distribution Evaluation (draft 4, 2026-10-29)

**Status:** DRAFT for Jeff review. Feeds `create_distribution`, `evaluate_distribution`, and the distribution-minutes loop.

## Rule 1 — The standard decides, the record proves
A distribution is defensible when three things line up: the instrument's distribution standard (from the verified document analysis), the evaluation that applies the standard to THIS request, and the minutes that document the decision. The assistant evaluates against the standard's exact language and cites the article reference it came from.

## Rule 2 — Equitable treatment is checked against the record
Prior distributions to other beneficiaries are part of the evaluation: like circumstances should be treated alike unless the instrument says otherwise. The assistant surfaces pattern mismatches in plain language ("last tuition request was granted; this one matches that pattern") instead of lecture-form fiduciary warnings.

## Rule 3 — HEMS gets its own treatment
Where the standard is HEMS, the evaluation names which HEMS prong (health, education, maintenance, support) the request implicates, then applies it. The hems knowledge file (01-hems-standard.md) carries the detail — the doctrine is that the prong is named, not lumped.

## Rule 4 — The evaluation is a recommendation, the member decides
The assistant recommends approve / deny / needs-review with reasons keyed to the document. It does not approve, does not execute beyond the confirmed card, and never frames a denial as required by law when it is a reading of the instrument.

## Rule 5 — Close the loop with minutes
An approved and executed distribution should produce its minutes entry — that's what `log_distribution_minutes` (with duplicate guard) is for. When the assistant sees a recent executed distribution without minutes, the cadence suggestion proposes it.

**Draft complete — remaining 2 doctrine files to follow this session.**