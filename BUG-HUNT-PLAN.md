# TrustOffice Bug Hunt Plan

**Created:** July 16, 2026
**Status:** Ready to execute
**Context:** Four bugs found today through manual testing (TabsContent nesting, collapsed drafts, wrong CONTINUE route, "Trustee" phantom entry). This plan is a proactive sweep to find the rest.

---

## Execution Model

Four agents in parallel, each owning one workstream. Results consolidate into a single bug report with severity ratings. All criticals get fixed immediately.

**App URL:** https://app.trustoffice.app
**API URL:** https://api.trustoffice.app
**Source:** /Users/socializerender/.openclaw/workspace/Kit/life/brands/TrustOffice/projects/TrustOfficeApp/
**Frontend:** frontend/src/
**Backend:** backend/routers/

**Test account:** waylon@circlebara.com (Aldrich) — two trusts (Magen, Gleaning), both ecclesiastical, TX
**Admin API key:** /Users/socializerender/.openclaw/workspace/secrets/trustoffice-admin-api.key

**Deploy model:** git push to main → Railway auto-deploys. Verify with `curl -s https://app.trustoffice.app/ | grep -o 'main\.[a-f0-9]*\.js' | head -1`

---

## Workstream 1: User Flow Walkthrough (Browser-Based)

**Agent goal:** Log into Aldrich's account and walk every user flow end-to-end using browser tools. Snapshot each page. Flag anything broken.

### Flows to test:

**Dashboard**
- [ ] Page loads with content (not blank)
- [ ] Onboarding steps render and are clickable
- [ ] Each onboarding step button navigates to the right page
- [ ] Trust selector dropdown works (switch between Magen and Gleaning)
- [ ] All dashboard cards/buttons have functional targets

**Minutes**
- [ ] Minutes list page loads
- [ ] Drafts section is visible and auto-expanded
- [ ] Click CONTINUE on a draft → opens the draft detail page (NOT template picker)
- [ ] Minutes detail page shows structured content (LegalTextRenderer, not raw text)
- [ ] Edit Draft button works → textarea opens with content
- [ ] Save Changes persists
- [ ] View PDF generates and shows PDF
- [ ] Finalize Minutes button works → confirmation dialog → finalize succeeds
- [ ] Finalized minutes show green "Finalized" badge
- [ ] Create Minutes → template picker loads → select a template → form renders
- [ ] Back button returns to minutes list

**Settings**
- [ ] Account tab renders content (not blank)
- [ ] Profile tab renders content (not blank) — this was broken before the nesting fix
- [ ] People tab renders content with successor trustee form
- [ ] Compliance tab renders content
- [ ] Successor trustee form: fill all fields → save → verify data persists on reload
- [ ] Trust document upload works
- [ ] Each tab switch doesn't blank out content
- [ ] Hash routing (#successor-trustee) scrolls to the right section

**Vault**
- [ ] Vault page loads
- [ ] Documents list renders
- [ ] Upload a document → appears in list
- [ ] View a document → opens/renders
- [ ] Download a document → downloads successfully
- [ ] Delete a document → removed from list

**Successor Trustee Flow**
- [ ] Dashboard "Choose Successor Trustee" button → navigates to Settings People tab
- [ ] Form renders with all fields (name, email, phone, relationship, notes)
- [ ] Fill and save → data persists
- [ ] Successor Packet page loads (/successor-packet)
- [ ] Successor Packet renders as print-ready document

**Other Pages**
- [ ] Trust Assistant — chat interface loads, can send a message, response renders
- [ ] Trustee 101 — content loads
- [ ] Trust Health — scores/metrics render
- [ ] Every sidebar nav item loads a page with content

**Mobile**
- [ ] Bottom nav renders and every item works
- [ ] Pages don't have horizontal overflow on narrow screens

**Dark Mode**
- [ ] Toggle dark mode → all pages render correctly
- [ ] No invisible text (same-color text on same-color background)
- [ ] Cards and borders visible

**Bug criteria:** Page renders no content, buttons go nowhere, forms don't submit, data doesn't persist, anything broken or confusing.

---

## Workstream 2: Source Code Audit

**Agent goal:** Read the frontend source code and check for the specific bug classes found today plus common React/Radix issues. No browser needed — pure code reading.

### Checks:

**TabsContent Nesting (the bug we fixed)**
- [ ] In SettingsPage.js: verify all TabsContent components are siblings, not nested
- [ ] In any other page using Radix Tabs: same check
- [ ] Search for `<TabsContent` across all files — verify each has a matching `</TabsContent>` and none are nested inside another

**Route Targets**
- [ ] Every `navigate('/...')` call — does that route exist in App.js?
- [ ] Every `navigate` with query params (e.g., `?draft_id=`) — does the target page read those params?
- [ ] Every `Link to="/..."` — same check
- [ ] Any hardcoded paths that might be stale

**Default State Issues**
- [ ] Search for `useState(false)` on any toggle/accordion/dropdown that should default to `true` (like the drafts collapse bug)
- [ ] Any `useState(true)` that should be `false`
- [ ] Modals/dialogs that might open on page load unintentionally

**Comma-Split Display Bugs (the "Trustee" bug)**
- [ ] Search for `.split(',')` across all components — does the data being split ever contain commas that aren't delimiters?
- [ ] Participants fields, beneficiary fields, trustee fields — any that include role suffixes ("Trustee", "Admin") that would render as separate people
- [ ] Any `.split(',')` without `.filter(p => p.trim())` to handle empty strings

**Missing Imports / Dead Code**
- [ ] Components referenced in JSX but not imported
- [ ] Buttons/elements with no onClick handler
- [ ] Forms with no onSubmit or submit button
- [ ] Functions defined but never called
- [ ] API calls that don't handle error states

**API Call Consistency**
- [ ] Every `fetchWithAuth` call — does it handle non-OK responses?
- [ ] Any `fetchWithAuth` calls missing the auth header
- [ ] Endpoint paths match backend routes (cross-reference with backend/routers/)

**Files to audit:**
- frontend/src/pages/ (all page components)
- frontend/src/components/ (shared components)
- frontend/src/App.js (routing)
- frontend/src/context/ (auth context)

---

## Workstream 3: API Data Integrity

**Agent goal:** Hit the API directly and check data quality across all accounts. No browser needed.

### Checks:

**Per-user, per-trust:**
- [ ] Every trust has at least one minutes record (draft or finalized)
- [ ] Participants fields don't contain role suffixes (", Trustee", ", Admin")
- [ ] Beneficiary fields are clean (no placeholder text)
- [ ] Trustee fields are clean
- [ ] Onboarding completion state matches actual account contents (if onboarding says "minutes done", minutes exist)
- [ ] Vault documents exist and are non-empty
- [ ] No orphaned records (minutes for deleted trusts, vault docs for deleted trusts)

**Cross-account:**
- [ ] All 13 users — fetch each user's trusts, minutes, vault
- [ ] Any user with zero trusts — is that expected or a bug?
- [ ] Any trust with zero minutes — flag it
- [ ] Any trust with zero vault documents — flag it
- [ ] Check for any "Trustee" or "Unknown" or empty string in participant/beneficiary/trustee fields

**API endpoints to use:**
- Admin API: `GET /admin/users` (with X-Admin-API-Key header)
- For each user: login or use admin endpoints to fetch their trusts, minutes, vault
- Document any 404s, 500s, or unexpected responses

---

## Workstream 4: Edge Cases & Cross-Cutting

**Agent goal:** Test the things that only break in unusual states.

### Checks:

**Empty States**
- [ ] Brand new account with zero trusts — what does Dashboard show?
- [ ] Account with trusts but zero minutes — what does Minutes page show?
- [ ] Account with trusts but zero vault docs — what does Vault show?
- [ ] Trust with no beneficiary designated — what does Settings show?
- [ ] Trust with no successor trustee — does the form handle the empty state?

**Error States**
- [ ] What happens when API calls fail? (Can simulate by checking offline behavior or invalid session)
- [ ] Do pages show useful error messages or just blank screens?
- [ ] What happens if a minutes ID in the URL doesn't exist?
- [ ] What happens if a trust ID in the URL doesn't exist?
- [ ] Token expiry — does the app redirect to login gracefully?

**Cross-Trust Switching**
- [ ] Switch trusts while on Minutes page — does content update?
- [ ] Switch trusts while on Settings page — does content update?
- [ ] Switch trusts while on Vault page — does content update?
- [ ] Switch trusts while editing minutes — does it warn or save?

**Print/Export**
- [ ] Successor Packet print view — does it render correctly?
- [ ] Minutes PDF — does it include all content?
- [ ] Any other export/download functionality

---

## Bug Report Format

Each agent returns findings in this format:

```
### [Workstream Name]

#### 🔴 Critical (flow completely broken)
- **[Page/Flow]:** Description of bug
  - Expected: What should happen
  - Actual: What actually happens
  - Root cause: If identifiable from source
  - File: path:line if known

#### 🟡 Moderate (works but confusing or wrong data)
- Same format

#### 🔟 Polish (works but could be better)
- Same format
```

## Fix Protocol

1. **Criticals** — fix immediately, deploy, verify in browser
2. **Moderates** — fix if root cause is clear and fix is under 30 min, otherwise flag for backlog
3. **Polish** — add to backlog, batch fix later

Each fix follows: identify root cause → patch → build → commit → push → wait for deploy → verify in browser → update skill if pattern is reusable.

---

## Deployment Notes

- Frontend: `cd frontend && npm run build` then `git add . && git commit && git push origin main`
- Railway auto-deploys from main branch
- Verify deploy: `curl -s https://app.trustoffice.app/ | grep -o 'main\.[a-f0-9]*\.js' | head -1` (wait for new hash)
- Backend: currently no changes needed (all bugs today were frontend)
- Admin API key: `cat /Users/socializerender/.openclaw/workspace/secrets/trustoffice-admin-api.key`
- Test account password: `TempPass12345X` (may need reset — see admin API reset endpoint)

---

## Session Handoff

To pick this up in a new session:

1. Read this plan: `Kit/life/brands/TrustOffice/projects/TrustOfficeApp/BUG-HUNT-PLAN.md`
2. Load `trustoffice-webapp` and `trustoffice-product-health` skills
3. Spawn 4 agents in parallel using `delegate_task` — one per workstream
4. Pass each agent the relevant section of this plan as their goal
5. Consolidate results into a single bug report
6. Fix all criticals, deploy, verify
7. Update `SYSTEM/ACTIVE-TASK.md` with the bug hunt as the current task