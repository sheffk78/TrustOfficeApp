# TrustOffice Design Consistency Audit
**Date:** 2026-08-25
**Scope:** All app sections — 27 page files + 5 shared layout components
**Design system:** "The Royal Ledger" (Navy #010079, Gold #D5AD36, 0px radius, serif headings, mono data)
**Method:** 5 parallel code-reading agents + manual source verification

---

## Executive Summary

The core pages (Dashboard, Distributions, Minutes, Compensation, Expenses, Investments, Beneficiaries, Structures, Governance, Settings, Billing) are **largely consistent** — they use `page-title`, `page-subtitle`, `page-header`, `page-container`, `PageHelpButton`, and `btn-primary`/`btn-gold` design-system classes.

The inconsistency you're seeing comes from **9 outlier pages** that were built differently — missing the standard header pattern, missing help buttons, using raw HTML buttons, or importing off-palette colors. These are the pages that look like "a different designer made them."

---

## The Design Standard (what pages SHOULD look like)

The canonical pattern, verified from `App.css` + `index.css`:

```
page-container    → padding 32px, max-width 1400px
page-header       → margin-bottom 32px, flex row (title left, help button right)
page-title        → Cormorant Garamond serif, 2.5rem, 600 weight, navy
page-subtitle     → JetBrains Mono, 10px, uppercase, 3px tracking, navy 60%
card-trust        → white bg, 1px navy/20 border, p-6, 0px radius, corner-marks
btn-primary       → navy bg, white text, uppercase, 0px radius, h-10 px-6
btn-gold          → gold bg, navy text, bold uppercase, 0px radius
btn-secondary     → transparent, navy border, hover fill, uppercase, 0px radius
PageHelpButton    → 8x8 round, navy border, popover with items + "Ask TA" link
Tabs (TabsList)   → mb-6, icon + label, "flex items-center gap-2"
```

**Pages that follow this pattern correctly (17 of 27):**
DashboardPage, TrustAssistantPage, ScheduleAPage, DistributionsPage, CompensationPage, ExpensesPage, InvestmentsPage, BenevolencePage (Log), TransactionLedgerPage, StructuresPage, BeneficiariesPage, MessagingPage, CommunicationsPage, EntityDetailPage, MinutesPage, AuditTrailPage, AuthorityPage, GovernancePage, RiskDashboardPage, StateCompliancePage, SettingsPage, BillingPage

---

## 🔴 PRIORITY 1 — Pages with NO standard header (looks like a different designer)

### 1. BenevolencePolicyPage.js (`/benevolence?tab=policy`)
**The worst offender.** This page was built completely outside the design system.
- ❌ Uses `<h1 className="text-2xl font-bold text-gray-900">` — no `page-title` class, **gray-900 instead of navy**
- ❌ No `page-header` flex row, no `page-subtitle`
- ❌ No `page-container` wrapper
- ❌ No `<PageHelpButton>` — zero help on this page
- ❌ Uses `rounded-lg` and `rounded-full` (violates 0px radius rule)
- ❌ Buttons use bare `<Button>` without `btn-primary`/`btn-secondary` classes
- ❌ Uses `shadow-sm` (design system says no shadows except floating)
- **Impact:** User clicks "Policy" tab in Benevolence → completely different visual language

### 2. TrustCalendarPage.js (`/calendar`)
- ❌ No `page-title`, `page-subtitle`, or `page-header` — has `page-container` but no title
- ❌ No `<PageHelpButton>` — the only Governance section page without help
- ✅ Uses `btn-primary` for buttons, `card-trust` for cards
- **Impact:** User goes from Minutes (has title "Minutes & Decisions" + help) to Calendar (no title, no help) — feels broken

### 3. OnboardingPage.js (`/onboarding`)
- ❌ No `page-title`, `page-header`, `page-container`, `PageHelpButton`, `card-trust`
- ❌ Completely custom layout — first-run experience, somewhat understandable, but jarring
- ⚠️ Uses `rounded-full` for loading spinner (acceptable for spinners)
- **Impact:** First impression of the app doesn't match the rest

### 4. CoursePage.js (`/course`) — from Agent 4
- ❌ Dark navy hero band (`bg-navy text-white px-6 py-8`) — no other page uses this
- ❌ No `page-title`/`page-subtitle`, no `PageHelpButton`
- ❌ `rounded-lg` icon tiles (0px radius violation)
- ❌ `border-slate-200` instead of navy-based borders
- ❌ Loader2 spinner vs CSS spinner used elsewhere
- **Impact:** Learn section looks like a different product

### 5. KnowledgeBasePage.js (`/knowledge`) — from Agent 4
- ❌ Uses icon-in-rounded-tile motif (`rounded-lg`) not seen anywhere else
- ❌ No `page-title`/`page-subtitle` classes, no `PageHelpButton`
- ❌ Off-palette pastel category colors (blue/purple/pink/cyan)
- **Impact:** Browse Articles looks nothing like the rest of the app

### 6. KnowledgeAdmin.js (`/knowledge/admin`) — from Agent 4
- ❌ `rounded-lg` icon tile, no `page-title` class, no `PageHelpButton`
- ❌ Off-palette pastel colors (duplicated from KnowledgeArticleDetail)
- ❌ Form modal save button without `btn-primary` class
- **Impact:** Manage Articles is admin-only but still breaks the visual language

### 7. KnowledgeArticleDetail.js (`/knowledge/:id`) — from Agent 4
- ❌ No standard header, no `PageHelpButton`
- ❌ Off-palette pastel category colors
- ❌ `rounded` on related-article rows
- **Impact:** Article detail page doesn't match the app

### 8. PrintableBinderPage.js (`/vault?tab=binder`) — from Agent 4
- ❌ Uses raw `<h1 className="text-2xl md:text-3xl font-bold text-navy">` instead of `page-title`
- ❌ `PageHelpButton` placed below the title (unique — all other pages put it beside)
- ⚠️ Subtitle is freeform paragraph, not `page-subtitle` class

### 9. NotFoundPage.js (`/*`)
- ❌ `<h1 className="text-4xl font-bold text-navy">404</h1>` — raw, no design system classes
- ✅ Acceptable for a 404, but could still use the page container

---

## 🟡 PRIORITY 2 — Pages with partial inconsistencies

### Button placement deviations
| Page | Issue | Detail |
|------|-------|--------|
| TrustAdminKitsPage.js | Buttons mid-flow, not top-right | Primary actions scattered in cards (line 443) |
| SuccessorPacketPage.js | Raw `<button>` instead of `<Button>` | `bg-navy hover:bg-navy/90` and `bg-gold hover:bg-gold/80` hand-rolled (lines 230-243) |
| CoursePage.js | CTA at page bottom | All other pages put primary action in header-right |
| BenevolencePolicyPage.js | Bare `<Button>` without design classes | Lines 177-189 |

### Border radius violations (0px rule)
| Page | Lines | What |
|------|------|------|
| ScheduleAPage.js | 758, 762, 766 | `rounded-full` on status badges |
| StructuresPage.js | 161, 166, 198 | `rounded-lg`, `rounded-md`, `rounded-full` on view-mode toggle |
| MessagingPage.js | 306, 311, 374, 418, 476 | `rounded-lg`, `rounded-full` on message bubbles, avatar, container |
| MinutesPage.js | 273 | `rounded-full` on badge |
| AuthorityPage.js | 256, 261 | `rounded-full` on role icon and badge |
| LoginPage.js | 227, 236 | `rounded-lg` on session notice and WingPoint welcome |
| CoursePage.js | 190 | `rounded` on upgrade box |
| KnowledgeBasePage.js | 171, 214 | `rounded-lg` icon tile and view toggle |
| BenevolencePolicyPage.js | 195, 211 | `rounded-lg` and `rounded-full` |
| PrintableBinderPage.js | 284 | `rounded` on related rows |
| KnowledgeAdmin.js | 405 | `rounded-lg` icon tile |

**Note:** `rounded-full` on avatars and spinner elements is a common exception — the real violations are `rounded-lg` on cards/containers/tiles.

### Off-palette colors
| Page | Lines | What |
|------|------|------|
| BenevolencePolicyPage.js | L170 | `text-gray-900` instead of navy |
| CoursePage.js | 133, 147, 222-223 | `border-slate-200` instead of navy-based borders |
| KnowledgeArticleDetail.js | 37-48 | Pastel category colors (blue/purple/pink/cyan) |
| KnowledgeAdmin.js | 81-92 | Same pastel palette duplicated |

### Loading state inconsistency
- `Loader2` icon spinner: CoursePage, BenevolencePolicyPage
- CSS border spinner: KnowledgeArticleDetail, OnboardingPage, DashboardPage
- Skeleton blocks: ExportDashboard, BeneficiaryReportPage
- **Recommendation:** Standardize on one approach (CSS border spinner for simple, skeleton for data-heavy)

### Destructive action confirmation
- AlertDialog: KnowledgeAdmin (line 654)
- `window.confirm`: BeneficiaryReportPage (line 108)
- **Recommendation:** Always use AlertDialog for destructive actions

---

## 🟢 PRIORITY 3 — Minor / acceptable differences

### Tabbed wrappers (all consistent ✅)
InvestmentsTabbed, BenevolenceTabbed, HealthComplianceTabbed, DocumentsTabbed — all use identical `TabsList mb-6` + `TabsTrigger "flex items-center gap-2"` pattern. No issues.

### Auth pages (acceptable deviation)
LoginPage and SignUpPage use `card-trust` with `corner-mark` and `btn-primary` — they don't use `page-title` but auth pages are intentionally different (full-screen, centered). The `rounded-lg` on session notices in LoginPage is a minor violation.

### Badge `rounded-full` (minor)
ScheduleAPage, MinutesPage, AuthorityPage use `rounded-full` on small status badges. While technically violating 0px radius, this is a common pattern for pills/badges. Could standardize to sharp rectangles for full compliance, but low impact.

### Corner marks inconsistency
`corner-mark` (gold L-shapes) appears on: ScheduleAPage, DistributionsPage, CompensationPage, InvestmentsPage, GovernancePage, SettingsPage, BillingPage, LoginPage, SignUpPage. Missing from many other pages that use `card-trust`. Should be applied consistently to all `card-trust` containers or removed from all.

---

## Fix Priority Order

1. **BenevolencePolicyPage** — complete rebuild to design system (no `page-title`, wrong colors, no help, radius violations)
2. **TrustCalendarPage** — add `page-header`/`page-title`/`page-subtitle`/`PageHelpButton`
3. **CoursePage** — replace dark hero with standard header, remove `rounded-lg`, add help button
4. **KnowledgeBasePage + KnowledgeAdmin + KnowledgeArticleDetail** — add `page-title`/`page-subtitle`, remove pastel colors, add help buttons, fix `rounded-lg`
5. **PrintableBinderPage** — switch to `page-title` class, reposition help button to header row
6. **SuccessorPacketPage** — replace raw `<button>` with `<Button className="btn-primary/btn-gold">`
7. **TrustAdminKitsPage** — add `PageHelpButton`, move primary button to header-right
8. **OnboardingPage** — add `page-container` and basic design-system alignment
9. **NotFoundPage** — minor, add `page-container` wrapper

---

*Audit was read-only. No files were modified.*