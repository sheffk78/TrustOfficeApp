# TrustOffice Design System — "Royal Ledger"

> The canonical visual structure for every page in the TrustOffice web app.
> All new pages and all fixes must conform to this document.

---

## 1. Design Tokens

### Color Palette

| Token | Value | Usage |
|---|---|---|
| **Navy** (primary) | `#010079` (`var(--navy)`) | Headings, primary buttons, sidebar, active states, borders |
| **Gold** (secondary/accent) | `#D5AD36` (`var(--gold)`) | Accents, hover states, active indicators, help button links |
| **Background** | `#F9FAFB` (`var(--subtle-bg)`) | Main content area background |
| **Paper** | `#F5F5F7` (`var(--paper)`) | Alternate section backgrounds |
| **Card** | `#FFFFFF` | Card backgrounds |
| **Border** | `navy/20` opacity | Card borders, input borders |
| **Muted foreground** | `slate-500` / `navy/60` | Subtitles, secondary text |

**Rules:**
- Navy is the only heading color. Never use `text-gray-900`, `text-slate-900`, or raw black for headings.
- Gold is for accents and interactive highlights only — never for body text or large fill areas.
- Status colors (emerald, amber, red, blue) are allowed **only** in badges and status indicators, never as page-level styling.
- No pastel category colors (blue/purple/pink backgrounds). If categories need visual distinction, use navy/gold tint variations or icon differences.

### Typography

| Element | Font | Size | Weight |
|---|---|---|---|
| Page title | Cormorant Garamond (serif) | 2.5rem (desktop), 1.75rem (mobile) | 600 |
| Page subtitle | JetBrains Mono (mono) | 10px, uppercase, 3px tracking | 400 |
| Card titles | Cormorant Garamond (serif) | 1.25–1.5rem | 600 |
| Body text | DM Sans (sans) | 14px–16px | 400 |
| Data values / labels | JetBrains Mono (mono) | 10px–14px, uppercase tracking | 500 |
| Button text | DM Sans (sans) | 12px, uppercase, wider tracking | 500 |

**Rules:**
- Headings (`h1`–`h6`) always use Cormorant Garamond via `font-serif` or the `.page-title` class.
- Data, metrics, and labels use JetBrains Mono via `font-mono`.
- Body text uses DM Sans (the default body font — no class needed).

### Border Radius

**0px everywhere.** This is the defining visual signature of the brand.

The CSS already enforces this globally:
```css
* { border-radius: 0 !important; }
.rounded, .rounded-sm, .rounded-md, .rounded-lg, .rounded-xl, .rounded-2xl, .rounded-3xl {
  border-radius: 0 !important;
}
```

**Allowed exceptions** (these may use `rounded-full`):
- Avatars / profile images
- Status dots / indicator dots
- Progress bars (pill shape)
- Toggle switches
- Small icon badges (the gold dot in PageHelpButton list items)
- Badges (`badge-trust`, `badge-success`, etc.) — these are sharp by default; only use `rounded-full` if the badge is a status pill

**Never allowed:**
- `rounded-lg`, `rounded-md`, `rounded-xl` on cards, containers, tiles, inputs, or buttons
- If you see `rounded-lg` in a page's JSX, it's a violation — remove it. The global CSS already nullifies it visually, but leaving it in the source creates confusion and signals the page was built outside the system.

---

## 2. Page Structure — The Canonical Pattern

Every page in the app follows this structure. This is what makes 17 pages feel like one designer.

### Layout wrapper

```jsx
<div className="main-content dot-grid mobile-layout-offset">
  <div className="page-container">
    {/* Page header */}
    {/* Page content */}
  </div>
</div>
```

- `main-content` — provides the left sidebar offset (256px) and the subtle background
- `dot-grid` — adds the faint dot pattern background (optional but standard)
- `mobile-layout-offset` — handles mobile padding
- `page-container` — 32px padding, max-width 1400px

### Page header (the signature element)

```jsx
<div className="page-header flex items-center justify-between">
  <div>
    <h1 className="page-title">Page Name</h1>
    <p className="page-subtitle">One-line description of what the user does here</p>
  </div>
  <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
    <PageHelpButton
      items={[
        { text: 'What this page does — bullet 1' },
        { text: 'What this page does — bullet 2' },
        { text: 'What this page does — bullet 3' },
      ]}
      taPrompt="Walk me through [page name]"
    />
    {/* Action buttons (Button component, right-aligned) */}
  </div>
</div>
```

**Anatomy:**
1. **`page-header`** — container with `flex items-center justify-between`, 32px bottom margin
2. **Left side** — `page-title` (h1, serif, navy) + `page-subtitle` (mono, uppercase, navy/60)
3. **Right side** — `PageHelpButton` + action buttons, wrapped in `flex flex-wrap gap-3`
4. **`PageHelpButton`** — present on EVERY content page. The help icon in the top-right corner is part of the trust the user builds with the system. Missing = broken.

**Rules:**
- The title is always an `<h1>` with class `page-title`. Never a raw `<h1>` with inline classes.
- The subtitle is always a `<p>` with class `page-subtitle`. Never a `<p>` with inline classes.
- `PageHelpButton` goes in the right-side button cluster, NOT below the title.
- Action buttons use the `<Button>` component (from `@/components/ui/button`), never raw `<button>` elements.

### When a page has no action buttons

Still include `PageHelpButton` on the right:
```jsx
<div className="page-header flex items-center justify-between">
  <div>
    <h1 className="page-title">Page Name</h1>
    <p className="page-subtitle">Description</p>
  </div>
  <PageHelpButton items={[...]} taPrompt="..." />
</div>
```

---

## 3. Component System

### Buttons

Use the `<Button>` component from `@/components/ui/button`. **Never use raw `<button>` elements** for page-level actions.

| Variant | When to use | Visual |
|---|---|---|
| `default` (no variant prop) | Primary action on the page | Navy bg, white text, gold on hover |
| `outline` | Secondary actions | Navy border, transparent bg, navy text |
| `ghost` | Tertiary / icon-only actions | Transparent, subtle hover bg |
| `destructive` | Delete / remove actions | Red bg, white text |

For the legacy CSS button classes (still valid, defined in `index.css`):
- `.btn-primary` — navy bg, white text, mono, uppercase
- `.btn-gold` — gold bg, navy text, mono, uppercase
- `.btn-secondary` — navy outline, transparent bg

**Rules:**
- One primary action per page section. Secondary actions use `outline` or `ghost`.
- Buttons in the page header are right-aligned in the button cluster.
- Buttons in card footers are right-aligned.
- Never scatter action buttons mid-content — place them in the header or card footer.

### Cards

```jsx
<div className="card-trust">
  {/* Card content */}
</div>
```

- `card-trust` — white bg, `border border-primary/20`, 24px padding, `overflow-hidden`
- No `rounded-lg`, no `shadow-sm` as card classes (the global CSS handles shadow via hover on `.card-trust`)
- For cards that need visible overflow (badges, etc.): `card-trust overflow-visible`

### Tables

```jsx
<table className="trust-table">
```

- Headers: navy bg, mono font, uppercase, gold underline on hover
- Cells: mono font, subtle borders
- Already styled in `index.css` — just use the class

### Badges

```jsx
<span className="badge-trust">Label</span>
<span className="badge-trust badge-success">Approved</span>
<span className="badge-trust badge-warning">Review</span>
<span className="badge-trust badge-error">Declined</span>
```

- Sharp corners (0px radius)
- Mono font, uppercase, tiny text
- Border + transparent bg, color-coded by status

### Inputs

```jsx
<input className="input-trust" />
```

- Sharp corners, navy border at 30% opacity, gold focus ring
- Mono font for data inputs

### Tabs

Use Radix `Tabs` / `TabsList` / `TabsTrigger` / `TabsContent` from `@/components/ui/tabs`.
- Tab triggers are styled by the design system
- Active tab gets gold underline (handled in CSS for mobile)
- Never hand-roll tab buttons with custom styling

---

## 4. Layout & Spacing

| Element | Spec |
|---|---|
| Page container padding | 32px desktop, 16px mobile |
| Page header bottom margin | 32px |
| Card padding | 24px (16px mobile) |
| Card grid gap | 24px |
| Section spacing | 32px between major sections |
| Button gap | 12px (`gap-3`) |
| Max content width | 1400px |

---

## 5. Intentional Exceptions

Some pages have legitimate reasons to differ. These are **intentional** deviations, not bugs:

| Page | Deviation | Why it's OK |
|---|---|---|
| **OnboardingPage** | Custom layout, no sidebar | First-run experience — user hasn't entered the app shell yet |
| **NotFoundPage** | Minimal, no header | 404 error state — should be sparse and redirect quickly |
| **Print/export pages** | Print-optimized layout | Formatted for physical printing, not screen navigation |
| **Auth pages** (Login, SignUp, ForgotPassword) | Centered, no sidebar | Pre-auth — outside the app shell |

These pages are exempt from the page-header pattern. They are NOT exempt from the color palette, typography, or border-radius rules.

---

## 6. The 9 Outlier Pages — What's Broken

These pages were built outside the system and need to be brought into compliance:

### 🔴 Full breaks (no page-header, no PageHelpButton, off-palette)

| Page | Issues |
|---|---|
| **BenevolencePolicyPage** | `text-gray-900` heading (only page in app with gray text), no `page-title` class, no `page-subtitle`, no `PageHelpButton`, `rounded-lg` + `shadow-sm` on cards |
| **TrustCalendarPage** | No title, no subtitle, no `PageHelpButton` — user goes from Minutes (full header) to Calendar (empty) |
| **CoursePage** | Dark navy hero band not used elsewhere, `rounded-lg` tiles, `border-slate-200` borders, no `page-title` class, no `PageHelpButton`, raw `<button>` elements |
| **KnowledgeBasePage** | Pastel category colors, `rounded-lg` icon tiles, no `page-title` class, no `PageHelpButton`, raw `<button>` elements |
| **KnowledgeAdmin** | Same issues as KnowledgeBasePage |
| **KnowledgeArticleDetail** | Same issues as KnowledgeBasePage |

### 🟡 Partial breaks (has some system elements but misses others)

| Page | Issues |
|---|---|
| **PrintableBinderPage** | Has `page-title` + `page-subtitle` + `PageHelpButton` ✅, but uses raw `<button>` instead of `<Button>` component, `shadow-sm` on cards |
| **SuccessorPacketPage** | Has `page-title` + `page-subtitle` + `PageHelpButton` ✅, but uses `text-gray-900` for inner content, raw `<button>` elements |
| **TrustAdminKitsPage** | Has `page-title` + `page-subtitle` ✅, but no `PageHelpButton`, buttons scattered mid-flow instead of in header cluster |

### Cross-cutting violations

| Issue | Scope | Fix |
|---|---|---|
| `PageHelpButton` missing | 7 pages | Add to every content page's header |
| `rounded-lg`/`rounded-md` in JSX | ~11 pages | Remove from JSX (global CSS already nullifies, but source should be clean) |
| `text-gray-900` | 2 pages | Replace with `text-navy` or appropriate palette color |
| `border-slate-200` | 1 page (CoursePage) | Replace with `border-navy/20` or `border-primary/20` |
| Pastel category colors | 3 pages (Knowledge) | Replace with navy/gold tint variations |
| Raw `<button>` elements | 3 pages | Replace with `<Button>` component |
| `shadow-sm` on cards | 2 pages | Remove — card shadow is handled by `.card-trust` hover state |

---

## 7. Fix Priority

When fixing the 9 outlier pages, follow this order:

1. **Page header** — Add `page-header` with `page-title` + `page-subtitle` + `PageHelpButton`
2. **Color palette** — Replace `text-gray-900` → `text-navy`, `border-slate-200` → `border-navy/20`, pastels → navy/gold tints
3. **Buttons** — Replace raw `<button>` with `<Button>` component, move scattered buttons into header cluster
4. **Border radius** — Remove `rounded-lg`/`rounded-md` from JSX source
5. **Card styling** — Replace `shadow-sm` + custom borders with `card-trust` class
6. **Tab consistency** — If page has tabs, use Radix Tabs component, not hand-rolled buttons

---

## 8. Compliance Checklist (for fix agents)

Before marking a page as fixed, verify:

- [ ] Page has `<div className="page-header flex items-center justify-between">` 
- [ ] Title is `<h1 className="page-title">` (not raw `<h1>` with inline classes)
- [ ] Subtitle is `<p className="page-subtitle">` 
- [ ] `PageHelpButton` is present in the header button cluster
- [ ] All action buttons use `<Button>` component (no raw `<button>`)
- [ ] No `text-gray-900` — use `text-navy` for headings
- [ ] No `border-slate-200` — use `border-navy/20` or `border-primary/20`
- [ ] No pastel category colors — use navy/gold tints
- [ ] No `rounded-lg`/`rounded-md`/`rounded-xl` in JSX source
- [ ] No `shadow-sm` on cards — use `card-trust` class
- [ ] Page is wrapped in `page-container` inside `main-content`