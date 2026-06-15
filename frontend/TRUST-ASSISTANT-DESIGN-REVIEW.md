# Trust Assistant — Design Alignment Review

**Date:** June 13, 2026
**Reviewer:** Kit (GPT-5.5 analysis)
**Scope:** Visual design comparison between Trust Assistant page/components and established pages (Dashboard, Governance/Trust Health, Calendar)

---

## 1. Layout Architecture

### Page Container

| Pattern | Dashboard / Governance / Calendar | Trust Assistant |
|---|---|---|
| Outer wrapper | `main-layout` (flex, min-h-100vh) | `trust-assistant-layout` (flex, flex:1, min-h-0, overflow:hidden) |
| Main wrapper | `main-content dot-grid` (ml-256px, flex:1, subtle-bg, dot-grid bg) | `main-content` (same — inherited) ✅ |
| Content wrapper | `page-container` (padding:32px, max-width:1400px) | ❌ **NONE** — content directly inside `main-content` |
| Inner layout | Natural document flow (cards stack vertically) | `trust-assistant-layout` (flex row: SnapshotColumn + ChatPanel) |

**Issue:** The Trust Assistant page has no `page-container` wrapper. The content starts directly inside `main-content`. This means the page lacks the 32px padding and 1400px max-width boundary that every other page uses.

### Page Header

✅ **Consistent.** The Trust Assistant page correctly uses:
```jsx
<div className="page-header">
  <h1 className="page-title">Trust Assistant</h1>
  <p className="page-subtitle">{selectedTrust?.name}</p>
</div>
```

This matches Dashboard (`page-title` / `page-subtitle`) and Governance (`page-title` / `page-subtitle`).

---

## 2. Spacing & Padding

| Element | Established Pattern | Trust Assistant | Gap |
|---|---|---|---|
| Page edge padding | 32px (`page-container`) | ❌ No wrapper → flush to edges | **CRITICAL** |
| Between header and content | 32px (`page-header margin-bottom: 32px`) | ✅ Header is in `page-header` | OK |
| Card internal padding | 24px via `card-trust` | Uses `p-4` (SnapshotColumn), `p-6` (ChatPanel messages) | Slight drift |
| Content max-width | 1400px (`page-container`) | Chat messages: `max-w-3xl mx-auto` (768px) | Intentional — chat is narrower |
| Inner layout gap | Grid gap-6 | Space between SnapshotColumn and ChatPanel via flex row | Different approach |

---

## 3. Card & Container Styling

### SnapshotColumn vs Dashboard/Governance Cards

Dashboard and Governance use `card-trust class="corner-mark"` — a shared component class with navy border, consistent padding, gold corner marks on important cards.

SnapshotColumn:
- ❌ Does NOT use `card-trust` anywhere
- Uses raw `border border-navy/10 bg-white` or `bg-navy/5` with explicit `p-4`
- Sections are separated by `border-b border-navy/10`
- No `corner-mark` on any section

**Impact:** The SnapshotColumn looks visually distinct from the rest of the app — more like a sidebar panel than app content.

### ChatPanel

- Messages area: `bg-transparent` with `max-w-3xl mx-auto` — no card structure
- Message bubbles use `.message-bubble-user` (navy/5 bg) and `.message-bubble-ai` (subtle-bg) — these are custom classes not present elsewhere in the app
- Action cards use `.action-card` (composes `card-trust`) ✅ — but this isn't being applied in the JSX directly; it's a CSS class

---

## 4. Brand Token Violations in SnapshotColumn

The SnapshotColumn introduces brand-violating color tokens that don't exist on Dashboard or other branded pages:

| Line | Code | Should Be |
|---|---|---|
| 106 | `text-emerald-600 dark:text-emerald-400` (scoreColor >= 80) | `text-gold` |
| 108 | `text-red-500 dark:text-red-400` (scoreColor < 60) | `text-rust` (Critical state) |
| 112 | `bg-emerald-500` (score bar ≥ 80) | `bg-gold` |
| 113 | `bg-amber-500` (score bar ≥ 60) | `bg-gold/60` |
| 114 | `bg-red-500` (score bar < 60) | `bg-rust` |
| 188 | `text-emerald-500` (CheckCircle2 icon) | `text-gold` |
| 193 | `text-red-400` (XCircle icon) | `text-rust` |
| 197 | `text-emerald-600 dark:text-emerald-400` (points) | `text-gold` |
| 213 | `text-amber-500` (Lightbulb icon) | `text-gold` |
| 255 | `text-red-500 font-bold` (overdue), `text-amber-500` (≤14 days) | `text-rust` / `text-gold/80` |

**These 10 violations** make the SnapshotColumn look like a different app — it uses green/amber/red success/warning/error colors instead of TrustOffice's gold/navy/rust palette.

DashboardPage uses **`bg-success/5 border-success/30`** etc. (CSS custom properties, resolved to brand-appropriate colors), while GovernancePage uses **`text-success bg-success`** (same CSS variable system).

---

## 5. Typography Drift

| Element | Established | Trust Assistant | OK? |
|---|---|---|---|
| Page title | `page-title` (Cormorant Garamond serif, 2.5rem) | Same ✅ | OK |
| Section headers | `font-serif text-lg text-navy` (Dashboard, Governance) | `font-mono text-[10px] uppercase tracking-widest text-muted-foreground` (SnapshotColumn) | **Different** — SnapshotColumn uses mono all-caps labels, not serif section titles |
| Score display | Governance: `score-circle` with large serif number | SnapshotColumn: `font-serif text-4xl font-bold` | Slightly different sizing but acceptable |
| Labels | `label-trust` (mono, uppercase, tracking) | Inline `font-mono text-[10px] uppercase tracking-widest` | Equivalent but not using the class |
| Body text | `text-sm text-muted-foreground` | `font-mono text-[11px]` | **Different** — SnapshotColumn uses smaller mono body text vs standard sans-serif body |

The SnapshotColumn uses **all-mono typography** for everything (labels, body text, even suggestions), while the rest of the app uses:
- Serif for titles (`font-serif`)
- Standard sans-serif for body text
- Mono only for labels (`label-trust`) and data

---

## 6. Chat Panel Height Issue

**Root cause:** The chat panel uses `h-full` in a flex chain:
```
trust-assistant-layout (flex:1, min-height:0, overflow:hidden)
  → flex-1 flex flex-col min-h-0 (ChatPanel wrapper)
    → chat-panel flex flex-col h-full
      → chat-messages flex-1 overflow-y-auto p-6
      → quick-chips
      → chat-input-bar (border-t, padding:16px)
```

The `h-full` chain causes the chat panel to fill the entire remaining viewport height. On a 1080p screen (~800px content height after sidebar/header):
- ~680px goes to messages area (flex-1)
- ~40px goes to quick chips
- ~60px goes to input bar

The user has to scroll through potentially hundreds of pixels of message history to reach the input bar at the bottom. If 5+ messages are in the conversation, the first message is ~300px above the fold.

**Comparison:** No other page in the app has this pattern because no other page has a scrollable main content area with a fixed input bar at the bottom.

---

## 7. Empty States

- SnapshotColumn has fallback text ("Loading...", "No score available", "No upcoming deadlines") but **no designed empty state** — no illustration, no friendly message
- The ChatPanel has a greeting message on first load ✅
- **Dashboard** has proper empty states (no-trust page with illustration + CTAs, onboarding checklist)
- **Calendar** has loading skeleton but no designed empty state for no-tasks

---

## 8. Alignment with Chat Input

The chat input field:
- Uses `font-mono text-sm border-0 bg-transparent` — doesn't use `input-trust` class
- Has no focus ring (`focus:outline-none focus:ring-0`)
- Send button is a raw `<button>` with `p-2 bg-navy text-white` — not using `btn-primary` or `btn-gold`

---

## Summary of Gaps

| # | Issue | Severity | File |
|---|---|---|---|
| 1 | **No `page-container` wrapper** — content is flush to edges without 32px padding | **High** | TrustAssistantPage.js |
| 2 | **10 brand token violations** — emerald/amber/red instead of gold/navy/rust | **High** | SnapshotColumn.js |
| 3 | **`card-trust` not used** — SnapshotColumn sections use raw borders/backgrounds instead of shared card component | **Medium** | SnapshotColumn.js |
| 4 | **All-mono typography** in SnapshotColumn — body text in mono instead of sans-serif | **Medium** | SnapshotColumn.js |
| 5 | **Chat panel too tall** — fills viewport, forces scrolling to reach input bar | **High** | ChatPanel.js, index.css |
| 6 | **Section headers inconsistent** — mono all-caps labels instead of serif section titles | **Low** | SnapshotColumn.js |
| 7 | **Chat input not using `input-trust`** — missing branded input styling | **Low** | ChatPanel.js |
| 8 | **No designed empty states** in SnapshotColumn | **Low** | SnapshotColumn.js |

---

## Recommended Fix Plan

### Fix 1: Add `page-container` wrapper (High Priority)
Wrap the inner `trust-assistant-layout` div content in a proper `page-container`:

```jsx
// TrustAssistantPage.js — change from:
<main className="main-content">
  <div className="page-header">...</div>
  <div className="trust-assistant-layout">
    <SnapshotColumn ... />
    <div className="flex-1 flex flex-col min-h-0">
      <ChatPanel ... />
    </div>
  </div>
</main>

// To:
<main className="main-content dot-grid">
  <div className="page-container h-full">
    <div className="page-header">...</div>
    <div className="trust-assistant-layout">
      <SnapshotColumn ... />
      <div className="flex-1 flex flex-col min-h-0">
        <ChatPanel ... />
      </div>
    </div>
  </div>
</main>
```

Then adjust `trust-assistant-layout` to account for the padding:
```css
.trust-assistant-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  /* Height: calc(100% - page-header-height - 32px gap) */
  height: calc(100% - 96px); /* header ~64px + margin 32px */
}
```

### Fix 2: Fix brand tokens in SnapshotColumn (High Priority)
Replace all emerald/amber/red score colors with gold/navy/rust equivalents:
- `text-emerald-600` → `text-gold`
- `bg-emerald-500` → `bg-gold`
- `text-amber-500` → `text-gold/80` or `text-rust` for warnings
- `text-red-500` → `text-rust`
- `CheckCircle2 text-emerald-500` → `CheckCircle2 text-gold`
- `XCircle text-red-400` → `XCircle text-rust`

Also the `scoreColor` function should use the same CSS variable pattern as other pages (`text-success`, `text-warning`, `text-error`) or brand tokens directly.

### Fix 3: Constrain chat panel height (High Priority)
The chat panel should not fill the full viewport. Target a comfortable conversation height:

```css
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: calc(100vh - 300px); /* leave room for sidebar, header, padding */
}
```

Or restructure the layout so `trust-assistant-layout` has its height constrained by the page-container:
```css
.page-container.h-full {
  height: calc(100vh - 256px - 32px); /* sidebar + header + padding */
}
```

**The input bar should always be visible at the bottom of the conversation area** without requiring scroll to reach it. The messages area should scroll within its constrained height.

### Fix 4: Use `card-trust` in SnapshotColumn (Medium Priority)
Wrap each section in SnapshotColumn with `card-trust` (or a minimal card variant) to match the app's card pattern:
- Each bordered section → `card-trust` with `mb-4`
- Add `corner-mark` to the most important section (Defensibility Score)

### Fix 5: Fix typography in SnapshotColumn (Medium Priority)
- Change section headers from `font-mono text-[10px] uppercase tracking-widest` to match other pages: use `label-trust` class
- Keep body text as `text-sm` sans-serif (not mono) unless it's data/metrics

### Fix 6: Use branded input on chat bar (Low Priority)
- Add `input-trust` class styling to the chat input
- Switch send button to use `btn-primary` or `btn-gold` classes

---

## Verification

After fixes, verify:
1. Trust Assistant page has same outer padding as Dashboard (`page-container`)
2. No `text-emerald-*`, `text-amber-*`, `bg-emerald-*`, `bg-amber-*` remain in SnapshotColumn.js
3. Chat panel input bar is visible at all times without scrolling (the messages area scrolls within a constrained height)
4. Section headers use `label-trust` or equivalent branded styling
5. Body text uses sans-serif, not mono (except data labels)
6. `card-trust` is used for SnapshotColumn sections