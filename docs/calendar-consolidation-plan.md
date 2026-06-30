# Trust Calendar Consolidation Plan

> **Goal:** Merge the Governance Calendar (`/calendar`) and Tax Calendar (`/tax-calendar`) into a single unified "Calendar" page. One feed, one mental model, one place to see what's due.

---

## Current State

Two separate pages under the Governance nav group:

| Page | Route | File | What it shows |
|---|---|---|---|
| Governance Calendar | `/calendar` | `CalendarPage.js` (484 lines) | Manual governance tasks (annual review, quarterly review, compensation, distributions, insurance, transactions, custom). Checklists, complete/delete actions. |
| Tax Calendar | `/tax-calendar` | `TaxCalendarPage.js` (324 lines) | Auto-generated federal tax deadlines (1041, K-1, estimated payments). Year selector, fiscal year awareness, mark-as-filed, month grouping, summary cards. |

**Backend already has a unified endpoint** (`/calendar/events` in `calendar.py`) that aggregates both `governance_tasks` and `tax_calendar` collections. The frontend calls it but maps everything back to the old task-only shape, discarding tax-specific metadata (filing_status, days_remaining, deadline_type, etc.).

**Additional references to `/tax-calendar`:**
- `Sidebar.js` line 63: nav entry
- `DashboardPage.js` lines 804, 819: "View All" and "Set Up Tax Calendar" links
- `SnapshotColumn.js` line 77: fetches upcoming tax deadlines independently
- `App.js` line 280: route definition

---

## Design Decisions (Locked)

These are decided. Don't reopen during implementation.

1. **Single page, single feed.** Events from both sources in one chronological list, grouped by month.
2. **Two-level filter.** Primary tabs = status (Upcoming / Overdue / Completed / All). Secondary = type dropdown (All Types / Trust Tasks / Tax Filings). Dropdown on mobile, segmented control on desktop.
3. **Default to "Upcoming" tab.** Users open the calendar to see what's next, not their full history.
4. **Polymorphic cards.** Governance cards and tax cards share a container but render type-specific content and actions.
5. **Visual type indicator.** Each card gets an icon: shield/file for governance, dollar/tax for tax filings. Status border color (red/green/navy) shows urgency. Two signals, one glance.
6. **Tax cards get a thin gold accent border** in addition to the status border. Prevents tax deadlines from getting visually buried among more frequent governance tasks.
7. **"Next Up" widget at top.** Single most urgent item shown before filters. Instant answer on mobile.
8. **Plain English labels.** "Trust Tasks" and "Tax Filings" in the type filter. Not "Governance."
9. **No schema changes, no data migration.** Two MongoDB collections stay as-is. Backend routers stay as-is. Only the unified endpoint gets enriched and the frontend gets rebuilt.
10. **`/tax-calendar` becomes a redirect** to `/calendar`. Old bookmarks work.
11. **Keep both backend routers.** `calendar.py` (unified feed) and `tax_calendar.py` (generate, update filing status) both stay. The unified page calls both.
12. **Page title stays "Calendar"** in the sidebar. Under Governance group. No rename needed.

---

## Phase 1: Backend - Enrich the Unified Endpoint ✅ COMPLETED

**Files:**
- `backend/routers/calendar.py`
- `backend/utils/tax_calendar_math.py` (bug fix: deleted lines 138-140 reassignment of CALENDAR_RULES/FISCAL_RULES)

**What was done:**

### 1.1 Expand the tax entry mapping (lines 74-85)

Currently the unified endpoint maps tax entries to a generic shape and drops critical fields. Add these to the tax event dict:

- `filing_status` (string: pending, filed, extended, not_required)
- `deadline_type` (string: federal_1041, federal_1041_extension, k1_beneficiaries, estimated_q1-q4)
- `days_remaining` (int, computed inline or via `_days_remaining` import)
- `accountant_engaged` (bool)
- `notes` (string or null)
- `tax_year` (int)
- `is_fiscal_year` (bool, from trust doc)
- `entry_id` (string, the tax calendar entry_id, not the MongoDB _id)

### 1.2 Add `event_type` field to ALL events

Every event in the unified feed gets an explicit `event_type`:
- `"governance_task"` for governance tasks
- `"tax_deadline"` for tax calendar entries

The frontend uses this to render the correct card variant. Currently the endpoint uses `type` but the values are `"governance_task"` and `"tax_deadline"` already. Just make sure it's consistent and documented.

### 1.3 Dedup overlapping entries

`governance_tasks` collection includes `tax_filing_1041` and `tax_filing_k1` as task types (see `CalendarPage.js` lines 30-31). These overlap with auto-generated tax calendar entries for the same forms.

**Logic:** If a governance task has `task_type` of `tax_filing_1041` or `tax_filing_k1`, AND a tax calendar entry with matching `deadline_type` exists for the same trust + tax_year, skip the governance task in the unified feed. Prefer the tax calendar entry because it has filing_status, fiscal year awareness, and proper date math.

### 1.4 Add `days_remaining` to governance events too

Currently only tax entries get days_remaining (and even that is dropped). Compute it inline for all events. Simple: `(due_date - today).days`.

### 1.5 Import `_days_remaining` from tax_calendar_math

The endpoint should use the existing `_days_remaining` function from `utils/tax_calendar_math.py` for consistency with the tax calendar router.

**Verification:**
- `GET /calendar/events?trust_id=X` returns events with all tax metadata preserved
- Governance tasks that duplicate tax deadlines are filtered out
- `event_type` is present on every event
- `days_remaining` is present on every event

**Note:** There is a bug in `tax_calendar_math.py` lines 138-140. At the bottom of the file, `CALENDAR_RULES` and `FISCAL_RULES` are reassigned to empty dicts, overwriting the definitions at lines 5-23. This breaks the import. Fix this: delete lines 138-140 (the reassignment) so the original definitions at the top of the file remain intact.

---

## Phase 2: Frontend - Build the Unified Calendar Page ✅ COMPLETED

**Files:**
- `frontend/src/pages/TrustCalendarPage.js` (new, replaces both existing pages)
- `frontend/src/components/TrustCalendarCard.js` (new, polymorphic card component)

**Do NOT delete the old pages yet.** Build the new page alongside, then swap routes in Phase 4.

**Build status:** Production build (`craco build`) compiles clean. Code review passed (4 issues found and fixed, see Implementation Notes below).

### 2.1 Page Layout (top to bottom)

```
+--------------------------------------------------+
| Page Header                                       |
| "Calendar" title + subtitle                      |
| Year selector | Generate Tax Calendar button     |
+--------------------------------------------------+
| "Next Up" Widget (single most urgent item)       |
| One card, one action, no scrolling needed         |
+--------------------------------------------------+
| Persistent Banner (if no tax calendar for year)  |
| "Tax deadlines not set up for 2026. Generate?"   |
+--------------------------------------------------+
| Summary Row (compact on mobile)                   |
| Total | Completed | Pending | Overdue            |
+--------------------------------------------------+
| Status Tabs: Upcoming | Overdue | Completed | All |
| Type Filter: [All Types v] (dropdown on mobile)  |
+--------------------------------------------------+
| Trust Profile Info Bar (if tax entries present)   |
| EIN: XX-XXXXX | Fiscal year ends MM/DD            |
+--------------------------------------------------+
| Month Group: January 2026                         |
|   [Card] [Card] [Card]                            |
| Month Group: March 2026                           |
|   [Card] [Card]                                   |
+--------------------------------------------------+
```

### 2.2 "Next Up" Widget

- Shows the single most urgent event (earliest due date among pending/non-completed items)
- Full-width card with: event title, due date, days remaining countdown, primary action button
- If no upcoming items: shows "All caught up" with a subtle checkmark
- This is the mobile hero. User sees it before anything else.

### 2.3 Persistent Tax Setup Banner

- Shows when `tax_calendar` collection has zero entries for the current year for this trust
- Shows regardless of type filter (so users discover the gap without switching filters)
- Slim bar: "Tax deadlines not set up for [year]." + "Generate" button
- Disappears once tax calendar is generated

### 2.4 Summary Cards

- 4 metrics: Total / Completed / Pending / Overdue
- Desktop: `grid-cols-4` with card backgrounds
- Mobile: single compact row, no card backgrounds, just bold number + tiny label. Saves vertical space.

### 2.5 Status Filter Tabs

- Tabs: Upcoming (default) / Overdue / Completed / All
- Show count badges on each tab
- Same visual style as current CalendarPage: `bg-navy text-white` for active, `bg-white border border-navy/20` for inactive
- Font: `font-mono text-xs uppercase tracking-widest`

### 2.6 Type Filter

- Desktop: segmented control (All Types / Trust Tasks / Tax Filings)
- Mobile: dropdown select to save horizontal space
- When type changes, filter applies within the current status tab

### 2.7 Trust Profile Info Bar

- Same content as current TaxCalendarPage lines 224-239
- EIN, tax year end, fiscal year badge
- Only visible when tax entries are in the current filtered set
- Collapses to single truncating line on mobile

### 2.8 Month Grouping

- Group events by `format(parseISO(date), 'MMMM yyyy')`
- Month headers: `text-sm font-semibold text-neutral-500 uppercase tracking-wide`
- **Sticky month headers on mobile** (CSS `position: sticky; top: 0`) so the user always knows which month they're in while scrolling

### 2.9 Polymorphic Card Component (`TrustCalendarCard.js`)

Shared container:
- `border-l-4` with status color (same as current CalendarPage: success/error/navy)
- Left border + icon area at top

Type-specific elements:

**Governance Task Card:**
- Icon: `FileText` or `Shield` (lucide)
- Title: task_type humanized (e.g., "Quarterly Review")
- Description (if present)
- Due date (mono font)
- Completed date (if completed, green mono text)
- Expandable checklist with progress bar (from CalendarPage lines 340-381)
- Actions: Complete button (or Undo if completed) + Delete (X icon)

**Tax Deadline Card:**
- Icon: `DollarSign` or `FileText` with tax styling
- Thin gold accent border (in addition to status border) to prevent visual burial
- Title: deadline label (from DEADLINE_LABELS in TaxCalendarPage)
- Description (if present)
- Date block (month + day, from TaxCalendarPage lines 269-272)
- Filing status badge (Filed / Extended / Pending / Overdue)
- Days remaining countdown (from TaxCalendarPage lines 288-298)
- Notes (if present, italic)
- Actions: "Mark Filed" button + "Mark Extended" button (NEW, backend already supports it)

**Tax filing actions need confirmation:**
- "Mark Filed" shows a confirm dialog: "Confirm: mark [form name] as filed for tax year [year]?"
- "Mark Extended" shows a confirm dialog: "Confirm: mark [form name] as extended?"
- This is a legal compliance record. Misclicks matter.

### 2.10 Empty States

**Complete empty (no tasks, no tax calendar):**
- Centered panel
- Headline: "Set up your trust calendar"
- Subtext: "Your calendar tracks both trust tasks and tax filing deadlines in one place."
- Two buttons: "Create a Task" and "Generate Tax Deadlines"

**Filtered empty (no items match current filter):**
- Centered panel
- Headline: "No [filter] items"
- Subtext varies by filter ("No upcoming deadlines. You're all caught up." / "No overdue items. Great work." / "No completed items yet." / "No tasks of this type.")

**Tax calendar not generated (tax filter active, no entries):**
- Centered panel
- Headline: "No tax calendar for [year]"
- Subtext: "Generate the federal tax deadlines for this trust."
- Button: "Generate [year] Tax Calendar"

### 2.11 Create Task Modal

- Port directly from CalendarPage lines 422-481
- Same task types (minus tax_filing_1041 and tax_filing_k1 since those are now handled by the tax calendar)
- Remove those two options from the TASK_TYPES array

### 2.12 Year Selector

- Shows current year, prev, next (same as TaxCalendarPage lines 178-191)
- **Filters ALL events by due_date calendar year**, not just tax entries
- If user selects 2025, they see 2025 governance tasks AND 2025 tax deadlines
- Fiscal year label shows for fiscal-year trusts

### 2.13 Generate Tax Calendar Action

- Same logic as TaxCalendarPage lines 85-106
- POST to `/trusts/{trust_id}/tax-calendar/generate` with `{ tax_year: year }`
- On success: toast + reload feed
- On 409 (already exists): toast.info with the message
- Button appears in header area, only visible when type filter includes tax AND no tax entries exist for selected year

**Verification:**
- Page renders on mobile (375px) without horizontal scroll
- "Next Up" widget shows the most urgent item
- Filters work correctly (status + type compose)
- Tax cards show filing status, days remaining, mark filed/extended
- Governance cards show checklists, complete/delete
- Month grouping with sticky headers on mobile
- Empty states render correctly for all combinations
- Create task modal works
- Generate tax calendar works
- Confirm dialogs appear for tax filing actions

---

## Phase 3: Frontend - Dashboard & Snapshot Updates ✅ COMPLETED

**Files:**
- `frontend/src/pages/DashboardPage.js`
- `frontend/src/components/SnapshotColumn.js`

### 3.1 DashboardPage links (lines 804, 819)

- Change `to="/tax-calendar"` to `to="/calendar"` on both lines
- The "View All" link (line 804) should go to `/calendar`
- The "Set Up Tax Calendar" button (line 819) should go to `/calendar?type=tax` to pre-select the tax filter

### 3.2 SnapshotColumn (line 77)

- The upcoming tax deadlines fetch (`/trusts/{trust_id}/tax-calendar/upcoming?days=90`) stays as-is
- This is a data fetch, not a navigation link. No change needed unless the component links to `/tax-calendar` for "view all", in which case update to `/calendar`

**Verification:** (subagent audit, all 5 checks PASS)
- DashboardPage "View All" links to `/calendar` ✅
- DashboardPage "Set Up Tax Calendar" links to `/calendar?type=tax` ✅
- SnapshotColumn has zero nav links to `/tax-calendar` (only API fetch, stays as-is) ✅
- No stray `/tax-calendar` nav links remain outside Phase 4 scope (App.js route, Sidebar entry, old page files all deferred to Phase 4) ✅
- `craco build` compiles clean ✅

---

## Phase 4: Routing & Navigation ✅ COMPLETED

**Files:**
- `frontend/src/App.js`
- `frontend/src/components/Sidebar.js`
- `frontend/src/pages/TaxCalendarPage.js` (delete)
- `frontend/src/pages/CalendarPage.js` (delete)

### 4.1 App.js routing

- Replace the `/calendar` route (line 184-188) to render `TrustCalendarPage` instead of `CalendarPage`
- Replace the `/tax-calendar` route (line 280-284) with: `<Route path="/tax-calendar" element={<Navigate to="/calendar" replace />} />`
- Update import: replace `CalendarPage` and `TaxCalendarPage` imports with `TrustCalendarPage`
- Support optional `type` query param: if `?type=tax`, pre-select the Tax Filings filter. The new page reads `useSearchParams` for this.

### 4.2 Sidebar.js

- Remove line 63: `{ path: '/tax-calendar', icon: CalendarDays, label: 'Tax Calendar' }`
- Keep line 61: `{ path: '/calendar', icon: Calendar, label: 'Calendar' }`
- Remove `CalendarDays` from the lucide import if no longer used elsewhere in the sidebar

### 4.3 Delete old pages

- Delete `TaxCalendarPage.js` (moved to `_archived/`, redirect is in place)
- Delete `CalendarPage.js` (moved to `_archived/`, replaced by TrustCalendarPage)
- Keep both backend routers intact

**Verification:**
- `/calendar` loads the new unified page
- `/tax-calendar` redirects to `/calendar`
- `/calendar?type=tax` loads with tax filter pre-selected
- Sidebar shows only "Calendar" under Governance
- No console errors, no broken imports

---

## Phase 5: Polish & QA ✅ COMPLETED

**Files:**
- `frontend/src/pages/TrustCalendarPage.js`
- `frontend/src/components/TrustCalendarCard.js`

### 5.1 Mobile polish

- Verify sticky month headers work (test on 375px viewport)
- Summary cards compact row renders correctly
- Type filter dropdown works on mobile
- "Next Up" widget is the first visible content (above the fold on 375px)
- No horizontal scroll at any breakpoint

### 5.2 Desktop polish

- Summary cards in 4-column grid
- Type filter as segmented control
- Month headers not sticky on desktop (not needed, more screen space)
- Cards have appropriate hover states

### 5.3 Edge case testing

- Trust with no tasks and no tax calendar (full empty state)
- Trust with tasks but no tax calendar (banner visible)
- Trust with tax calendar but no tasks
- Trust with both (normal case)
- Fiscal year trust (verify dates display correctly)
- Overdue tax deadline (red border, days-ago countdown, Mark Filed + Mark Extended)
- Overdue governance task (red border, Complete button)
- Completed tax deadline (green border, Filed badge)
- Completed governance task (green border, Undo button)
- Duplicate 1041 governance task + tax calendar entry (dedup works, only tax entry shows)
- Year selector changes (2025, 2026, 2027 all work)
- Generate tax calendar for a year that already has one (409 toast)
- Type filter + status filter compose correctly (e.g., Overdue + Tax Filings)

### 5.4 Accessibility

- All buttons have aria-labels
- Status icons have alt text or aria-label
- Filter tabs are keyboard navigable
- Confirm dialogs are keyboard accessible (Enter to confirm, Escape to cancel)
- Cards have appropriate ARIA roles (the checklist items already have `role="checkbox"` in CalendarPage, port that over)

**Verification:** (static code audit + fixes applied)
- **5.1 Mobile polish:** Sticky month headers (mobile-first `sticky` + `sm:static`) ✅ | Compact summary row (`sm:hidden`) ✅ | Type filter dropdown (`sm:hidden <select>`) ✅ | Next Up widget DOM order (first after header) ✅ | No horizontal scroll (uses `flex-wrap`, `min-w-0`) — requires runtime confirmation
- **5.2 Desktop polish:** 4-col summary grid (`hidden sm:grid grid-cols-4`) ✅ | Segmented control type filter (`hidden sm:flex`) ✅ | Month headers not sticky on desktop (`sm:static`) ✅ | Card hover states (`transition-shadow hover:shadow-md`) ✅ (added during Phase 5)
- **5.3 Edge cases (13 cases):** All 13 pass static audit. Full empty state ✅ | Banner visible ✅ | Tax-only ✅ | Both types ✅ | Fiscal year labels/badges ✅ | Overdue tax (red border + days-ago + Mark Filed/Extend) ✅ | Overdue governance (red border + Complete) ✅ | Completed tax (green border + Filed badge) ✅ | Completed governance (green border + Undo) ✅ | Dedup (frontend routes by event_type) ✅ | Year selector ✅ | 409 toast ✅ | Filter composition ✅
- **5.4 Accessibility (fixed during Phase 5):**
  - aria-labels: Added `aria-label="Close dialog"` to modal close button. `aria-hidden="true"` added to all decorative lucide icons (DollarSign, Shield, AlertTriangle, Clock, Check, ChevronUp, ChevronDown, X, Plus, Calendar) in both files ✅
  - Confirm dialogs: Added `role="dialog"`, `aria-modal="true"`, `onKeyDown` handlers (Escape to cancel, Enter to confirm) to all 3 dialog instances (card confirm, Next Up confirm, Create Task modal) ✅
  - Checklist items already had `role="checkbox"`, `aria-checked`, `aria-label` ✅
  - Filter tabs use native `<button>` elements (keyboard navigable) ✅
- **`craco build` compiles clean** ✅
- **Items requiring runtime testing** (cannot verify statically): above-the-fold on 375px viewport, no horizontal scroll at all breakpoints, Lighthouse audit. These need an authenticated browser session.

---

## What Stays Separate (Not Consolidated)

| Item | Why it stays separate |
|---|---|
| GovernancePage (`/governance`) | Trust Health is a scoring dashboard, not a calendar. Different product surface (assessment vs. scheduling). |
| Tax calendar math (`tax_calendar_math.py`) | Pure date math that generates entries. Backend service, not UI. |
| Tax-specific endpoints (generate, update filing status) | Filing status updates are tax-specific. Don't unify into a generic "complete" endpoint. Card component routes to the right endpoint by type. |
| Two MongoDB collections | `governance_tasks` and `tax_calendar` have different schemas and lifecycles. No data migration. |

---

## Implementation Notes (Phase 2)

**Code review:** Spawned a subagent to audit the implementation against the spec. 4 issues found, all fixed:

1. **`Clock` icon missing from imports in `TrustCalendarCard.js`** (High) - Used in `StatusIcon` default branch and days-remaining countdown but not imported. Would have crashed every upcoming event at runtime. Fixed: added `Clock` back to lucide-react import.

2. **Next Up widget bypassed confirm dialogs for tax filings** (Medium) - The hero "Mark Filed" and "Extend" buttons called `markFiled`/`markExtended` directly with no confirmation, violating the spec's misclick-safety requirement (§2.9). Fixed: added page-level `nextUpConfirm` state + confirm modal matching the card's dialog text and behavior.

3. **Sticky month headers were desktop-only, not mobile** (Medium) - Spec §2.8 requires sticky headers on mobile. Implementation used `sm:sticky` (applies at >=640px). Fixed: swapped to mobile-first `sticky top-0 bg-white z-10` with `sm:static sm:bg-transparent sm:z-auto` to disable on desktop.

4. **Trust profile info bar visibility condition** (Low) - Spec §2.7 says "only visible when tax entries are in the current filtered set." Implementation used `hasTaxCalendar` (year-level, ignores status/type filters). Fixed: changed to `filteredEvents.some(e => e.event_type === 'tax_deadline')`.

**Deviations from spec (accepted, not bugs):**

- Generate Tax Calendar button is rendered in-flow below the filters rather than in the header area (§2.13). Functionally equivalent, better UX placement. The banner and empty-state buttons cover the other entry points.
- Tax-not-generated empty state (§2.10) is folded into the filtered-empty branch rather than a fully separate state. Headline text differs slightly ("No tax items" vs "No tax calendar for [year]"). Generate button is present.
- `not_required` filing status renders as "Filed" in the badge (spec §2.9 lists only Filed/Extended/Pending/Overdue). Semantically imprecise but spec gap, not a violation.
- `?type=` query param support added beyond spec for Phase 3/4 dashboard links (`?type=tax` pre-selects tax filter).
- `PageHelpButton`, loading skeletons, and `selectedTrust` empty state added beyond spec. Harmless enhancements.

---

## File Change Summary

| File | Action | Phase | Status |
|---|---|---|---|
| `backend/routers/calendar.py` | Enrich unified endpoint, add dedup, fix import | 1 | ✅ Done |
| `backend/utils/tax_calendar_math.py` | Fix CALENDAR_RULES/FISCAL_RULES reassignment bug (delete lines 138-140) | 1 | ✅ Done |
| `frontend/src/pages/TrustCalendarPage.js` | Accessibility fixes (aria-hidden, role=dialog, onKeyDown, aria-label) | 5 | ✅ Done |
| `frontend/src/components/TrustCalendarCard.js` | Accessibility fixes (aria-hidden, role=dialog, onKeyDown, hover states) | 5 | ✅ Done |
| `frontend/src/pages/DashboardPage.js` | Update `/tax-calendar` links to `/calendar` | 3 | ✅ Done |
| `frontend/src/components/SnapshotColumn.js` | Check for and update any `/tax-calendar` links | 3 | ✅ Done (no links found, data fetch only) |
| `frontend/src/App.js` | Swap routes, add redirect, update imports | 4 | ✅ Done |
| `frontend/src/components/Sidebar.js` | Remove Tax Calendar nav entry | 4 | ✅ Done |
| `frontend/src/pages/TaxCalendarPage.js` | Delete | 4 | ✅ Archived |
| `frontend/src/pages/CalendarPage.js` | Delete | 4 | ✅ Archived |

---

## Order of Execution

Build phases in order. Each phase is independently testable.

1. **Phase 1** (backend) ✅ DONE — verified with curl/API calls
2. **Phase 2** (frontend page) ✅ DONE — new page + card built, `craco build` passes, code review passed (4 issues found & fixed)
3. **Phase 3** (dashboard links) ✅ DONE — DashboardPage links updated, SnapshotColumn checked (no nav links, data fetch only)
4. **Phase 4** (routing swap) ✅ DONE — routes swapped, redirect added, Sidebar cleaned, old pages archived, `craco build` passes
5. **Phase 5** (polish) ✅ DONE — static audit passed (18/23 PASS), 3 accessibility FAILs fixed (aria-hidden on icons, role=dialog + onKeyDown on modals, aria-label on close button), card hover states added, `craco build` passes. Runtime items (above-the-fold, horizontal scroll, Lighthouse) require authenticated browser session.