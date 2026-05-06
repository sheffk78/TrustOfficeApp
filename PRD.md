# TrustOffice Product Improvement — Phase 1

**Scope:** Execute the highest-leverage improvements that close the gap between what the Trustee 101 course teaches and what the product delivers.

---

## 1. Defensibility Score Rename (High Impact, Low Effort)

The "Governance Health Score" → "Defensibility Score" migration has been specced since 2026-05-03 in GOVERNANCE-HEALTH-DIFF-BUNDLE.md. Execute now.

### Changes:
- Frontend label changes across 8 component files
- GovernancePage.js: page title + scoring guide
- DashboardPage.js: score card label
- Sidebar.js: nav label ('Defensibility Score', keep Shield icon)
- MobileBottomNav.js: nav label ('Score', keep Shield icon)
- OnboardingPage.js: feature card + checklist + tooltip
- PricingPage.js: feature list
- UpgradeModal.js: feature list
- SubscriptionGate.js: feature list
- BenevolenceLogPage.js: inline tip

### NOT changing:
- Backend internal identifiers (governance.py, models.py field names, API routes)
- Database column names

---

## 2. Tax Deadlines Dashboard (P0 Gap — Highest Anxious Pain Point)

Trustees lose track of 1041 deadlines, K-1 distribution requirements, and state fiduciary taxes. This is the #1 complaint in Reddit threads and the #1 topic in Trustee 101 Lesson 6.

### MVP Scope:
- Add `ein`, `tax_year_end_month`, `tax_year_end_day`, `is_fiscal_year`, `state_of_administration` columns to `trusts` table (PostgreSQL)
- New `tax_calendar` table: per-trust per-tax-year deadline tracking
- New `tax_deadline_templates` seed table: federal deadlines (1041 Apr 15, extension Sept 15, K-1 Mar 15, estimated Q1-Q4 dates)
- API: GET/POST `/api/trusts/{id}/tax-calendar`, GET `/api/tax-calendar/upcoming`
- Frontend: New "Tax Calendar" page (`/tax-calendar`) with:
  - Upcoming deadlines list with countdown badges
  - Mark filed / mark extended actions
  - Trust profile section with EIN + tax year end + state fields
  - Quick-add tax calendar for current year from trust profile
- Dashboard widget: next 3 upcoming tax deadlines

### Out of scope for MVP:
- State-specific tax deadlines (just federal 1041/K-1/estimated for now)
- Fiscal year offset calculation (just calendar year for now)
- Multi-state trusts
- AI chat for tax guidance

---

## 3. State Compliance Badge (P0 Gap — Quick Win)

Show state-specific compliance requirements on the trust profile. This validates the Trustee 101 lessons on UTC adoption and notice requirements.

### MVP Scope:
- New `state_compliance_profiles` seed table: basic info per state (state_code, state_name, utc_adopted, notice_required boolean, accounting_frequency)
- Trust profile shows state badge with quick-compliance summary
- State selector with compliance preview during trust setup

---

## Execution Order

1. Apply defensibility score rename (fast, safe)
2. Add tax fields to trusts table + tax_calendar tables + seed data
3. Build tax calendar API
4. Build tax calendar page + dashboard widget
5. Build state compliance seed data + trust profile integration

---

## Testing Criteria

After every feature:
- Backend API tests: 100% pass rate on new endpoints
- Frontend: Verified working in browser (routes, forms, data display)
- Integration: New features connect cleanly to existing trust model, task system, dashboard

## Design Standards

- TrustOffice palette: Navy (#010079), Gold (#D5AD36), Paper (#F5F5F7)
- Fonts: Georgia (headlines), Inter (body), JetBrains Mono (data)
- No gradients, no glassmorphism
- Clean, intentional alignment
- Reuse existing card patterns, badge patterns, and page structures
