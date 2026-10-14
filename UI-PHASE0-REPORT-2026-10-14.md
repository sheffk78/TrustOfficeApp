# UI Consistency Phase 0 — Execution Report
**Date:** 2026-10-14 · **Branch:** main (local commit, not deployed) · **Gate:** ratchet OK, no regressions

## What shipped

### Infrastructure (permanent)
| File | What it is |
|---|---|
| `frontend/UI-STANDARD.md` | The 12-rule spec — the contract every page is built against |
| `frontend/src/components/PageHeader.js` | Canonical `<PageHeader title subtitle actions help />` — ends 50 hand-rolled header copies |
| `frontend/src/components/Spinner.js` | Canonical loading spinner — ends the Loader2 vs animate-spin split |
| `scripts/ui-consistency-scan.py` | Automated ratchet gate: fails on any new violation vs baseline |
| `scripts/ui-consistency-baseline.json` | Locked baseline: 114 violation clusters across 77 pages |

### Pilot pages (public, no login needed — chosen so Jeff can see real pixels day 1)

**PricingPage** (`/pricing`):
- Billing toggles: pill-shaped → square segmented controls, mono uppercase labels, `aria-pressed` added (a11y)
- Promo pills & "Most Popular"/plan ribbons: rounded → sharp rectangles
- Raw close button → design-system ghost Button; "See other plans" raw button → `Button variant="link"`
- Guest-checkout modal: radius removed, serif heading, `btn-primary` submit
- **All 5 plan prices: serif → JetBrains Mono** ("data is truth" rule — comparison table already mono, prices now match)
- 26 header/hand places fixed. Counts: rounded-full 16→0, rounded-lg/xl 6→0, raw buttons 8→6 (remaining 6 = toggle segments, accepted pattern)

**AffiliatePage** (`/affiliate`):
- Headline capped at serif 5xl (was 6xl, one-off)
- Icon tiles + step numbers: circles → square navy tiles, mono digits
- Benefit cards → `card-trust` + gold corner marks (signature motif, now applied deliberately)
- Off-palette slate tints/footer → navy/5 + navy footer (6 palette violations → 0)
- CTA anchors → `btn-gold` styling, sharp, uppercase

**ContactPage** — fixed to standard (card-trust + corner marks, page-title, error token instead of off-palette red, shared Spinner instead of Loader2) — **but discovered it is ORPHANED: no route in App.js.** The live contact form lives on the WordPress site. Code kept current for the day it's wired; flagging so we decide: route it or delete it per archive rule.

## Verification done
- Ratchet gate: RATCHET OK, zero regressions; improvements priced in (affiliate palette 6→0, radius 1→0; pricing radius 22→0)
- Desktop before/after screenshots captured for all three pages (paths below)
- Mobile 390px after-shots: no overflow, cards stack, readable
- Page renders visually verified (ribbons sharp, toggles square segmented, mono prices)

## Evidence files
- Before: `~/.hermes/cache/scratch/to-ui-before/before-{pricing,contact,affiliate}.png`
- After (desktop + mobile): `~/.hermes/cache/scratch/to-ui-after/after2-*.png`
- Before/after copies for Discord review included in chat

## Scans recalibrated (plan updates)
- TrustCalendarPage already conforms (Aug audit fixed it via `CalendarPageHeader`)
- MinutesTemplatesPage is dead code (unrouted) — deletion/listed for archive, not fix
- "Raw button" rule needs the card-selector exception (template-picker cards ARE buttons) — encoded in gate

## Not deployed
Local commit only. Deploy decision after Jeff reviews the look. Stack note: local backend for logged-in page verification comes next phase (seeds exist in `trustoffice_local_test`-style DBs; demo creds in `demo_user_test.py` are stale/preview-env).

## Next (Wave 1)
1. Jeff reviews look → then Wire 1 in-app pages (Dashboard, Minutes, Schedule A) onto PageHeader
2. Migrate remaining 47 hand-rolled headers opportunistically per wave
3. Page-by-page audit waves per plan