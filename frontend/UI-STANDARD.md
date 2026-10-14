# TrustOffice UI Standard — "The Royal Ledger"

**One page, one look.** Every page in the app is built from the classes in this file. Nothing on this page is optional styling — it is the contract. The automated gate (`scripts/ui-consistency-scan.py`) fails any change that adds a violation.

- Full design token source: `design_guidelines.json` (project root)
- Philosophy: digitized legal document. Navy ink on white, gold only for high-value accents, monospace data, visible borders, **zero border radius**.

---

## The 12 rules (checked per page by the gate + review)

### 1. Container
Every page body renders inside `<div className="page-container">` (32px padding, max-width 1400px).

### 2. Header
Standard page header, title left / actions right:

```jsx
<PageHeader
  title="Distributions"
  subtitle="Record and manage trust distributions to beneficiaries"
  actions={<Button className="btn-gold">New Distribution</Button>}
/>
```

`PageHeader` (components/PageHeader.js) renders `page-header flex items-center justify-between` with `page-title` + `page-subtitle` on the left, an action slot on the right. Do not hand-roll this markup — it is the most-copied markup in the app and hand-copying is how drift started.

### 3. Title & subtitle
- `page-title` — Cormorant Garamond serif, 2.5rem/600, navy. Never raw `<h1 className="font-serif text-4xl/5xl/6xl">`.
- `page-subtitle` — JetBrains Mono 10px uppercase, tracking 3px, navy 60%.
- Marketing/public hero pages may keep a centered hero, but the h1 still uses serif + navy and caps at `text-4xl`.

### 4. Help
Every in-app page registers help via the invisible registrar (visible help lives in the global AssistantFab popover):

```jsx
<PageHelpButton
  items={[{ text: '…' }, { text: '…' }]}
  taPrompt="Walk me through the … page"
/>
```

It renders `null`; it only feeds PageHelpContext. No page ships without it (public marketing pages excepted only if it would misfire logged-out).

### 5. Tabs
Tabs use shadcn `Tabs`/`TabsList`/`TabsTrigger` with exactly `className="flex items-center gap-2"` on triggers and `mb-6` on the list. No per-page active-state background overrides (the one navy-active-bg page is scheduled for removal). Icon + label pattern.

### 6. Buttons
Buttons render through the shadcn `Button` with a design-system class — never a raw `<button>` for actions:

| Class | Use |
|---|---|
| `btn-primary` | standard nav/actions (navy bg, white text, uppercase, sharp) |
| `btn-gold` | the ONE high-value primary action per view |
| `btn-secondary` | cancel / back / inactive choices |

- **Exception:** a clickable selection **card** (template picker, plan card) may be a `<button>` — when it visually IS a card. Hand-rolled small action buttons styled as chrome are violations.
- Destructive actions: `AlertDialog`, never `window.confirm`.

### 7. Radius — everything sharp
`0px` radius everywhere. Allowed rounded exceptions: avatars, spinners, small status pills/badges. Everything else — cards, boxes, tiles, inputs, banners — square. `rounded-lg/md/xl/2xl` in page code = gate failure. `rounded-full` is legal only on the exception list.

### 8. Palette & data
- Navy `#010079` text/ink, gold `#D5AD36` accents/actions, white paper, slate muted. No gray-900, no slate borders, no pastels (blue/purple/pink/cyan).
- Every number, date, dollar amount, ID: `font-mono`.
- Shadows: none, except genuinely floating elements (dropdowns, floating ribbons).

### 9. Cards
`card-trust` (white bg, 1px navy/20 border, p-6, sharp) + **corner marks on every card-trust container** (the gold L-shape signature — applied uniformly, not randomly).

### 10. Badges & icon tiles
- Status badge: square (or pill per exception 7), `font-mono text-xs uppercase tracking-wider`, navy/gold/warning/success 10% bg + 20% border.
- Icon tiles: square `h-10 w-10` navy/5 or gold/10 fill. **No round icon discs** (rounded-full w-16 h-16 icon circles are a violation).

### 11. Loading
Shared `<Spinner />` (components/Spinner.js) for simple loads; skeleton blocks for data-heavy sections. No ad-hoc `Loader2` imports or bespoke spinners in pages.

### 12. Mobile & a11y
Reachable via `MobileBottomNav`; nothing overlaps it. Forms scroll clean at 390px. `aria-label` on icon-only buttons; `aria-hidden` on decorative icons; visible focus states.

---

## Exceptions register
| Page | Deviation | Status |
|---|---|---|
| Auth (Login/SignUp/Forgot/Reset/AcceptInvite) | centered full-screen layout, no page-container | intentional |
| Onboarding | custom wizard layout | tolerated, aligned at next touch |
| 404 | minimal | tolerated |
| Marketing hero bands (Pricing/Affiliate top) | centered hero | allowed; all other rules still apply |

## Gate & ratchet
`python3 scripts/ui-consistency-scan.py` — scans `frontend/src/pages/**` for violations, compares against `scripts/ui-consistency-baseline.json`. New violation (file gains hits) → non-zero exit → deploy gate fails. Fixes that lower counts are encouraged; update baseline in the same PR.

## Version history
- 2026-10-14: v1 written from DistributionsPage reference + design_guidelines.json. Corner-marks and square badges decisions by Kit (reversible by Jeff).