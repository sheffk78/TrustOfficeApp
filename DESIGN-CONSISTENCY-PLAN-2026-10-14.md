# TrustOffice UI Consistency Program — Page-by-Page
**Date:** 2026-10-14 · **Owner:** Kit · **Status:** Plan ready — awaiting Jeff go
**Supersedes:** `DESIGN-CONSISTENCY-AUDIT-2026-08-25.md` (that audit fixed 9 outliers; drift has regrown in new places since)

---

## What today's code scan found (77 page files, 2026-10-14)

The core standard is real and widely followed — **52 files** now carry `page-title` + `page-container` (the Aug audit's Priority-1 offenders were fixed). But new drift has grown:

| Drift class | Count | Where it clusters |
|---|---|---|
| Pages missing the standard header (`page-title` + `page-container` + help button) | ~15 real pages | AffiliatePage, ContactPage, PricingPage, MinutesDetailPage, MinutesTemplatesPage, TrustPartyManager, SuccessorAccessPage, TrustCalendarPage |
| In-app pages with **no PageHelpButton** | 19 files | incl. CreateMinutesPage, OrgConsolePage, TrustAccessPage, all 4 tabbed wrappers |
| `rounded-lg/xl/full/md` violations (0px-radius rule) | 114 hits | PricingPage (22), PerformanceDashboard (10), MinutesDetailPage (4) |
| Off-palette gray/slate/pastel classes | 405 hits | **PrintableBinderPage alone = 216** (embedded doc markup), SuccessorAccessPage (34) |
| Raw `<button>` elements instead of `Button` + `btn-*` | 80 hits | PricingPage (8), CreateMinutesPage (4), StatsPage (4) |
| Two competing tab styles | 15 pages `flex items-center gap-2` vs 1 page navy-active-bg | BeneficiariesPage is the outlier |
| Spinner split | 26 files `Loader2` vs 52 files CSS `animate-spin` | both alive |
| `window.confirm` (should be AlertDialog) | 10 files | |
| Corner-marks applied inconsistently | 37 files have them, many `card-trust` pages don't | |

Plus one structural fact: **50 hand-rolled `page-header` divs** instead of a shared `<PageHeader>` component — so every future page copies markup by hand and drift is guaranteed to regrow. That's the root cause. Fixes are not enough; the repetitive part becomes a component and a machine gate.

---

## The method (how the page-by-page walk works)

### Ground rule
No redesign. Every page already has the right look designed in `design_guidelines.json` ("Royal Ledger"). This program aligns each page to that standard — same colors, same type, same spacing — and removes freelancing.

### Step 0 — Lock the standard into the repo (½ session)
1. Write `frontend/UI-STANDARD.md`: the canonical 12-point spec (below), with one screenshot per rule showing correct usage. The single file every future page is built from.
2. Extract shared components so pages stop hand-copying markup:
   - `<PageHeader title subtitle actions />` (title + subtitle + help button + action slot, used by ≥50 files)
   - `<Spinner />` (kills the Loader2 vs animate-spin split)
   - Extend `scripts/ui-consistency-scan.py` (this scan, already written) into the **ratchet gate**: per-page consistency score committed to the repo; CI/pre-deploy fails if any page's score drops or a new violation appears.
3. Set the two style decisions (my calls, reversed by Jeff if wanted):
   - **Corner-marks: apply to every `card-trust`** — it's the signature motif; currently random.
   - **Status badges: square, mono text** (Royal Ledger "no softness"). `rounded-full` stays only on avatars/spinners.

### Step 1 — Baseline captures (read-only, no deploy needed)
Playwright script via headless browser (agent profile, browser-session-gate, close-tabs on finish): log in as the seeded test user, visit **every routed page**, save desktop (1440px) + mobile (390px) screenshots. ~45 in-app routes + public pages. These are the "before" photos and the audit evidence.

### Step 2 — The page-by-page walk, in 7 waves (the core)
Pages are audited **individually**, grouped into waves by page type so similar fixes land together. Each wave: parallel audit subagents (code-reading only, one page at a time against the checklist) → fixes applied page-by-page → re-screenshot → score updated in the ratchet ledger → wave ships. Waves ship independently, so value lands continuously and every wave is a safe deploy point.

| Wave | Pages | What gets fixed |
|---|---|---|
| 1 — Work surfaces | Dashboard, TrustCalendar, Minutes family (list, detail, create, templates), Schedule A, Trust Assistant | headers, tabs, spinners, raw buttons |
| 2 — Money | Distributions, Transaction Ledger, Compensation, Expenses, Investments, Benevolence (all tabs) | header/help parity, tab unification, confirms |
| 3 — Structure & parties | Structures, EntityDetail, Beneficiaries, Authority, Governance + subroutes, TrustPartyManager | full header build for TrustPartyManager, radius, palette |
| 4 — Records & compliance | Audit Trail, State Compliance, Vault (incl. PrintableBinder), Admin Kits, Successor Packet, Exports, Reports | **PrintableBinder 216-hit palette purge**, successor access 34-hit |
| 5 — Platform & learning | Knowledge (base/admin/article), Course, OrgConsole, TrustAccess, Clients, Health dashboards | help buttons, off-palette pastels |
| 6 — Comms & settings | Messaging, Communications, NotificationCenter, Settings, Billing | message-bubble radius w/ checklist exception, standard header |
| 7 — Public & shell | Login/SignUp/Forgot/Reset/AcceptInvite, Onboarding, Pricing, Affiliate, Contact, PostCheckout, NotFound | public pages get the same Royal Ledger discipline (auth screens keep the intentional centered layout, but same type/palette/buttons) |

### The 12-point per-page checklist (what every page is measured on)
1. `page-container` wrapper (p-8, max-w 1400)
2. `page-header` flex row — title left, primary action right
3. `page-title` (Cormorant 2.5rem/600) + `page-subtitle` (mono 10px uppercase)
4. `PageHelpButton` top-right, wired to the page's real help topic
5. Tabs = `TabsList mb-6` + trigger `flex items-center gap-2`, no per-page active-bg overrides
6. Buttons only via `Button` + `btn-primary/gold/secondary`; zero raw `<button>` in page code
7. 0px radius on cards/containers/tiles/inputs (exceptions: avatars, spinners, badges)
8. Palette: navy/gold/slate-muted only; mono font for every number, date, dollar
9. Loading: skeleton for data-heavy, shared CSS Spinner for simple; no ad-hoc spinners
10. Destructive actions: AlertDialog, never `window.confirm`
11. Empty states: `card-trust` + serif heading + one clear action
12. Mobile: reachable via bottom nav, no overlap with nav, forms scroll clean; focus-visible + aria-labels on nav/icon buttons

### Step 3 — Verification (multi-perspective, per AGENTS.md)
- **Jeff review packet (standing directive 2026-10-14, msg 1559987891785044152):** every change batch ends with a visual packet before it counts as done — numbered BEFORE/AFTER PNGs (desktop + mobile 390px), copied to `~/Documents/Deliverables/` (Finder-revealed) with a copy in `qa-reports/`, attached in Discord, plus click-through URLs while the dev server is up. No wave closes without Jeff able to see the pages.
- **Dev:** ratchet gate green, `craco test` suites pass, no console errors on page load
- **Human/desktop:** screenshot review of every page after its wave — before/after pairs
- **Mobile:** 390px captures per page; tap-path check of primary actions
- **Accessibility:** axe-style pass on nav, dialogs, focus states per wave
- **Deploy:** batches at wave ends through the full Railway gate (`railway-deploy` skill → preflight → `status == SUCCESS` → live probe)

---

## Deliberation-gate check
Significant, multi-session change — the plan itself went through structure-first reasoning (root cause: unshared markup + no machine gate, not "pages look different" symptoms). Before fixing Wave 1, a red-team subagent gets the plan and the 3 worst pages to attack for missed drift classes or wrong standard; its findings amend the checklist before any code changes.

## Guardrails
- No new colors, no logo/mark work (brand-identity hard block), no pricing/product changes
- Every wave is independently deployable and reversible (git per wave)
- Drift can't silently regrow: the ratchet gate trips on any new violation

## Effort
~3–4 focused working sessions across the 7 waves (audit waves are subagent-parallel and fast; the PrintableBinder purge and the `<PageHeader>` migration across 50 files are the two big lifts). Gate scripts + standard doc: first session.