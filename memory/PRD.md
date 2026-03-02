# TrustOffice - Trust Governance Workspace

## Original Problem Statement
Build TrustOffice - a trust governance workspace for individual/family trustees. Core jobs: Record trustee minutes and decisions, track distributions and expenses, maintain activity timeline per trust/entity, surface governance health status.

## Architecture

### Tech Stack
- **Frontend**: React 18, Tailwind CSS, Shadcn/UI
- **Backend**: FastAPI, Python 3.10+
- **Database**: MongoDB (with indexes)
- **Auth**: JWT + Google OAuth, Password Reset
- **Payments**: Stripe (LIVE MODE - $79/mo, $790/yr)
- **Email**: Postmark (12 templates)
- **Background Jobs**: APScheduler

### Backend Architecture (Refactored Mar 2, 2026)
The backend now has a modular structure for better maintainability:
```
/app/backend/
├── server.py           # Main FastAPI app with all endpoints (7538 lines)
├── database.py         # MongoDB connection singleton
├── models.py           # All Pydantic models and enums (~700 lines)
├── dependencies.py     # Shared auth, helpers, and middleware functions
├── routers/            # Domain-specific router modules (for gradual migration)
│   ├── auth.py         # Auth endpoints (ready for migration)
│   ├── trusts.py       # Trust CRUD (ready for migration)
│   ├── entities.py     # Entity management (ready for migration)
│   ├── tasks.py        # Governance tasks (ready for migration)
│   ├── units.py        # Trust certificate units (ready for migration)
│   └── [others]        # Placeholder stubs for future migration
├── email_service.py    # Postmark email integration
├── email_templates.py  # Email template content
└── background_tasks.py # APScheduler background jobs
```

### Design System (AnchorPoint)
- Light: Navy #010079, Gold #D5AD36
- Dark: Gold on slate backgrounds
- 0px border-radius, Cormorant Garamond/DM Sans/JetBrains Mono fonts

## Completed Features

### Latest Updates (Mar 2, 2026) - FRONTEND READ-ONLY MODE INTEGRATION ✅

1. **ReadOnlyBanner Component** (`/frontend/src/components/ReadOnlyBanner.js`)
   - Amber/warning color scheme banner at top of pages
   - Shows "Your trial has expired" or "Subscription inactive" message
   - "Subscribe Now" button links to `/settings?tab=subscription`
   - Only appears when `isReadOnly` is true

2. **SubscriptionGate Updated** (`/frontend/src/components/SubscriptionGate.js`)
   - No longer shows paywall - instead shows content with ReadOnlyBanner
   - Users can VIEW all data in read-only mode
   - Write operations blocked by backend (403 response)

3. **AuthContext Updates** (`/frontend/src/context/AuthContext.js`)
   - New `isReadOnly` state from `/api/subscription/state`
   - `loadSubscriptionState()` function fetches normalized state
   - Event listeners for `subscription-expired` and `subscription-readonly`

4. **LoginPage Updated** (`/frontend/src/pages/LoginPage.js`)
   - Now calls `loadSubscriptionState()` after login
   - Ensures read-only state is set before navigating to dashboard

5. **API Utility Updated** (`/frontend/src/utils/api.js`)
   - Dispatches `subscription-readonly` event on 403 with X-Subscription-Status header
   - Doesn't consume response body (fixes JSON parse error)

6. **Custom Hook** (`/frontend/src/hooks/useReadOnlyAwareSubmit.js`)
   - `useReadOnlyAwareSubmit` - Form submission with read-only awareness
   - `useReadOnlyCheck` - Simple hook to check read-only status
   - Shows toast with "Subscribe" action on blocked operations

### Previous Updates (Mar 2, 2026) - SUBSCRIPTION STATE MANAGEMENT ✅

1. **Unified Subscription State Helper**
   - New `get_subscription_state(user_id)` function returns normalized `SubscriptionState` object
   - Returns: plan_type, status, trial_start_date, trial_end_date, trial_days_remaining
   - Computed booleans: is_trial, is_active, is_read_only
   - Single source of truth for subscription status across all modules

2. **New Endpoint: GET /api/subscription/state**
   - Returns complete SubscriptionState with all computed fields
   - Frontend can use this for consistent subscription UI

3. **Dashboard Integration**
   - GET /api/dashboard now includes `subscription` field with:
     - plan_type, status, is_trial, is_active, is_read_only, trial_days_remaining
   - Frontend can show subscription status in dashboard

4. **Read-Only Mode for Expired Subscriptions**
   - SubscriptionMiddleware updated to allow read-only access:
     - **GET requests**: Always allowed (users can view all their data)
     - **POST/PUT/PATCH/DELETE**: Return 403 with clear error message
   - Error response includes: detail, subscription_status, is_read_only, trial_days_remaining
   - Write operations blocked consistently across: minutes, distributions, compensation, tasks, entities, Schedule A, trust units

5. **Code Architecture**
   - `dependencies.py`: SubscriptionState model, get_subscription_state(), require_write_access()
   - `models.py`: SubscriptionState, DashboardSubscriptionState models
   - `server.py`: SubscriptionMiddleware with read-only mode logic

### Previous Updates (Mar 2, 2026) - BENEVOLENCE MODE FOR DISTRIBUTIONS ✅

1. **Data Model Extensions**
   - Added `is_benevolence` boolean field on distribution_records (default false)
   - Added optional benevolence fields:
     - `benevolence_recipient_name` (required when is_benevolence=true)
     - `benevolence_need_description` (required when is_benevolence=true)
     - `benevolence_notes` (optional)

2. **API Endpoints**
   - `POST /api/distributions` - validates benevolence fields when is_benevolence=true
   - `PATCH /api/distributions/{id}` - new endpoint for updating distributions including benevolence fields
   - `GET /api/benevolence-log` - returns:
     - All distributions where is_benevolence=true
     - Monthly aggregates (YYYY-MM format, amount, count)
     - Yearly aggregates (year, amount, count)
     - Total all-time amount and count
     - Incomplete documentation count

3. **Governance Health Integration**
   - Distribution Documentation criterion now considers benevolence quality
   - **Full points (20)**: All distributions logged AND all benevolence distributions have:
     - recipient_name and need_description
     - approval (approved_at) or minutes reference
   - **Partial points (10-19)**: Some benevolence distributions missing documentation
   - Criterion description shows: "X/Y benevolence distributions need documentation"

### Previous Updates (Mar 2, 2026) - P2 FEATURES COMPLETE ✅

1. **Dashboard Trust Selection Parameter**
   - `GET /api/dashboard` now accepts optional `trust_id` query param
   - Validates trust ownership - returns 404 if trust doesn't exist or belongs to another user
   - Defaults to most recently created trust if not specified

2. **Beneficiary Dashboard** (`/trust/beneficiaries`)
   - New endpoint: `GET /api/beneficiaries/dashboard`
   - Returns: trust_name, total_authorized_units, total_issued_units, remaining_units, beneficiaries array, recent_transfers
   - Beneficiaries aggregated by holder with total units, percentage, certificate count
   - Sorted by total_units descending
   
3. **Beneficiary Dashboard Frontend**
   - Summary cards: Total Authorized, Issued, Remaining, Beneficiaries count
   - **Ownership Distribution pie chart** with color-coded legend
   - **Certificate Holders list** - expandable rows showing certificate details
   - **Recent Transfers section** with transfer history
   - Navigation link in sidebar under "Structures" group
   - "Manage Units" button links to `/trust/units`

### Previous Updates (Mar 2, 2026) - LOGIN FLOW FIX ✅

1. **Fixed trusts not loading after login**
   - Added `loadTrusts()` call after successful authentication in LoginPage.js
   - Trust selector now populates immediately after login (no page refresh needed)

### Previous Updates (Mar 2, 2026) - DASHBOARD UI REFACTORING ✅

1. **Unified Dashboard API Integration**
   - DashboardPage.js now calls single `GET /api/dashboard` instead of 3 separate API calls
   - All data flows through `dashboard` state from unified response
   - Removed redundant `getInsights()` function - now uses `governance_insights` from API

2. **Enhanced "What's Next" Card**
   - Displays governance insights from `/api/dashboard` response
   - Each insight shows: title, description, +points badge, action button
   - Color-coded by type: error (red), warning (yellow), info (blue)
   - Action buttons navigate to correct routes (action_path)
   - Shows total potential points gain in header

3. **Preserved Visual Components**
   - Health score circle with 5-criteria progress bars
   - Quick Actions grid (6 actions)
   - Stats section with total_decisions, pending_reviews
   - Recent Activity timeline with status badges
   - Onboarding checklist (when not dismissed)

### Previous Updates (Mar 2, 2026) - TRUST CERTIFICATE UNITS FEATURE ✅

1. **Trust Certificate Units - Complete Backend & Frontend**
   - Full certificate management system for tracking trust ownership/beneficial interest
   - **Backend API Endpoints**:
     - `GET /api/trust-units/summary?trust_id={id}` - Returns settings, certificates, aggregates
     - `PATCH /api/trust-units/settings?trust_id={id}` - Update unit settings
     - `POST /api/trust-units/certificates` - Issue new certificate
     - `PATCH /api/trust-units/certificates/{id}` - Update certificate
     - `GET /api/trust-units/certificates/{id}/pdf` - Generate certificate PDF
     - `POST /api/trust-units/transfers` - Transfer units between holders
     - `GET /api/trust-units/transfers` - List all transfers
     - `POST /api/trust-units/bootstrap-from-minutes/{minutes_id}` - Bootstrap certificates from beneficiary designation minutes (admin operation)
   - `GET /api/dashboard` - Unified dashboard aggregating health_score, onboarding_state, recent_activity, stats, governance_insights
   - **Database Collections**:
     - `trust_units_settings`: total_authorized_units, unit_label, allow_fractional
     - `trust_unit_certificates`: certificate_id, holder_name, units, percentage, certificate_number (CU-XXX), status
     - `trust_unit_transfers`: transfer records with from/to holders
   - **Frontend Page** (`/trust/units`):
     - Settings card at top with editable fields and Save button
     - Read-only summary: Total Issued, Remaining, Active Certificates
     - Certificates table with columns: Certificate #, Holder, Units, Percentage, Status, Issue Date, Actions
     - Filter dropdown: Active Only / All Certificates
     - Issue Units button above table
     - Row actions: Print (PDF preview), Edit, Reissue, Cancel
     - Transfer dialog for moving units between holders
     - PDF preview modal with Download button
     - Navigation link in sidebar under "Structures" group

2. **Certificate PDF Generation**:
   - Professional legal-style PDF with serif headings, mono labels
   - Contains: Trust name, jurisdiction, certificate number, holder name/ID
   - Shows: Units, percentage, issue date, status
   - Includes: Trustee signature blocks (2 sets)
   - Watermark based on subscription status

3. **Validation Rules**:
   - Units cannot exceed total_authorized_units
   - Cannot reduce total_authorized_units below currently issued
   - Sequential certificate numbering (CU-001, CU-002, etc.)
   - Fractional units only allowed when setting enabled
   - Transfer validates source holder has sufficient units

### Previous Updates (Feb 25, 2026) - SCHEDULE A ENHANCEMENTS ✅

1. **Enhanced "Accept Property into Trust" Template**
   - Added structured asset data collection: category, description, identifier (VIN/account#), location, value, date conveyed
   - "Add to Schedule A" checkbox auto-creates asset entry with `minutes_ref` linking to the authorizing minutes
   - Asset category selection dropdown appears when checkbox is enabled

2. **New "Dispose / Sell Asset" Minutes Template**
   - Select existing active Schedule A assets from dropdown
   - Record disposition details: reason (sale/transfer/donation/destruction), date, value, recipient, notes
   - "Mark as disposed in Schedule A" checkbox updates asset status without deleting
   - Generates proper legal WHEREAS/RESOLVED content for asset disposition

3. **Schedule A Status & Historical Assets**
   - Added `status` field (active/disposed) to Schedule A items
   - "Show disposed assets" toggle to view historical records
   - Status column with Active (green) / Disposed (orange) badges
   - Minutes reference shows which minutes entry added or disposed each asset
   - Disposed assets retain full history with `disposition_minutes_ref`, `disposition_date`, `disposition_notes`

4. **Backward Compatibility**
   - Legacy assets without status field are treated as "active"
   - Query logic handles both explicit status and missing status fields

### Previous Updates (Feb 25, 2026) - P0 BUG FIXES & P1 FEATURE ✅

1. **GA4 Analytics Integration - COMPLETE (NEW)**
   - Measurement ID: G-MT6FBPRE60
   - Added GA4 script to `public/index.html` (loads on all pages)
   - Created `useGA4PageTracking` hook in App.js for SPA route change tracking
   - Created `utils/analytics.js` utility with helper functions for custom events
   - Ready for subscription event tracking (subscription_started, subscription_upgraded, etc.)

2. **P0 Bug Fix: Save Minutes**
   - Issue: Saving generated minutes from templates was failing
   - Root Cause: PUT endpoint used plain `dict` instead of Pydantic model
   - Fix: Added `MinutesTemplateUpdate` Pydantic model with optional fields for `generated_document`, `status`, `template_data`
   - API: `PUT /api/minutes-templates/{minutes_id}`
   - Verified: Successfully creates, generates preview, saves, and navigates to /minutes

2. **P0 Bug Fix: Distribution Clock Icon**
   - Issue: Clicking clock icon on approved distributions caused error
   - Root Cause: Frontend was using PUT with query param, needed JSON body
   - Fix: Created new `PATCH /api/distributions/{id}/status` endpoint with `DistributionStatusUpdate` Pydantic model
   - Frontend: Updated `handleUpdateStatus` to use PATCH with JSON body `{status: 'review'}`
   - Verified: Clock icon now correctly sets approved distributions back to review

3. **P1 Feature: Auto-populate Minutes Form with Entity Data**
   - Implementation: `loadTrustEntityData()` in `MinutesTemplateFormPage.js`
   - Auto-populates: Trust Indenture Date (from `formation_date`), Trustees Present (from `trustee_names`)
   - Article References: Passes `article_ref_distribution`, `article_ref_compensation`, etc. to backend
   - Backend: Content generation functions use article references in WHEREAS clauses

4. **P2 Bug Fix: Compensation API**
   - Issue: GET /api/compensation-plans returned 500 error due to schema mismatch
   - Fix: Updated `CompensationPlanResponse` model to support both old (`annual_approved_amount`) and new (`annual_fee`, `trustee_name`) field schemas
   - Added field fallback logic in health score calculation and payment endpoints

### Previous Updates (Feb 24, 2026) - COMPLETE ✅

1. **Notification Preferences - COMPLETE (NEW)**
   - Settings page section with toggle switches for email notifications
   - Categories: Document Notifications (minutes, distributions), Task Reminders, Account & Subscription
   - 7 toggleable options: Minutes Created, Distribution Created, Distribution Approved, Task Reminders, Overdue Task Alerts, Subscription Updates, Weekly Digest
   - Real-time save on toggle (PUT to backend)
   - APIs: `GET /api/notifications/preferences`, `PUT /api/notifications/preferences`
   - DB Collection: `notification_preferences` with user_id and boolean flags

2. **Benevolence Report PDF Export - COMPLETE (NEW)**
   - Styled PDF report similar to Schedule A export
   - Contents: Trust info, tax status, summary statistics (total grants, amount, beneficiaries, categories)
   - Grants grouped by purpose category (Medical, Housing, Education, etc.)
   - Tables with date, beneficiary, description, amount columns
   - Optional year filter (`?year=2026`)
   - API: `GET /api/benevolence/export/{trust_id}/pdf`
   - Export button on Benevolence page

3. **Benevolence Mode - COMPLETE**
   - Optional feature for 501/508-type charitable trusts
   - **Settings Toggle**: Enable/disable per trust with tax status dropdown (501(c)(3), 508 Church/Religious Org, Private Foundation)
   - **Benevolence Log Page** (`/benevolence`):
     - Summary cards: Total Grants, Total Amount, This Year, Categories
     - Record Grant dialog with full form (beneficiary, type, purpose category, amount, etc.)
     - Data table with search/filter (by purpose, status)
     - CRUD operations for benevolence records
     - **Export Report button** for PDF download
   - **Conditional Navigation**: "Benevolence" sidebar link only visible when enabled for active trust
   - **Minutes Template Integration**: "Benevolence Assistance Approval" template in gallery with specialized form
   - APIs: `POST/GET/PUT/DELETE /api/benevolence`, `GET /api/benevolence/summary/{trust_id}`
   - DB Collection: `benevolence_records` with fields: record_id, trust_id, beneficiary_name, beneficiary_type, purpose, purpose_description, amount, date, approved_by, approval_method, status, notes

4. **Minutes Templates System - 10 Templates Total**
   - Blank, General Meeting, Distribution to Beneficiaries
   - Accept Property into Trust (auto-adds to Schedule A)
   - Appoint Additional/Successor Trustee
   - Designate Beneficiaries (units of beneficial interest)
   - Open Bank Account (signature authority, threshold options)
   - Change Trust Situs (jurisdiction change)
   - **NEW:** Benevolence Assistance Approval (auto-adds to Benevolence Log)
   - Dynamic forms with pre-filled WHEREAS/RESOLVED boilerplate from WingPoint templates
   - Editable preview with audit trail, PDF export
   - APIs: `/api/minutes-templates`, `/api/template-options?trust_id={trust_id}`

3. **Dashboard Quick Actions Panel**
   - 6 one-click actions: Record Distribution, Add Asset to Trust, Open Bank Account, Appoint Trustee, View Schedule A, General Meeting
   - "All Templates →" link to full template library
   - Color-coded icons per action type

3. **Schedule A (Trust Corpus Tracking)**
   - 8 asset categories: Real Property, Personal Property, Financial Accounts, Business Interests, Digital Assets, IP, Notes Receivable, Other
   - Full CRUD with summary totals by category
   - Integration: Property acceptance template auto-adds to Schedule A
   - **PDF Export** - Styled document with:
     - Header (SCHEDULE A - Initial Corpus of the Trust)
     - Trust name, date prepared, total assets, total value
     - Asset tables grouped by category with subtotals
     - Navy/white color scheme, professional styling
     - Grand total at bottom
   - APIs: `/api/schedule-a`, `/api/schedule-a/summary/{trust_id}`, `/api/schedule-a/export/{trust_id}/pdf`

4. **Bug Fixes**
   - Login page logo contrast (white on blue)
   - Login "body stream already read" error
   - Trust selector updates on new trust creation
   - "Made with Emergent" watermark removed
   - Added /login route for React Router
   - Fixed TrustResponse model for legacy data

### P0 - Critical (Feb 23, 2026) - COMPLETE
1. **Password Reset Flow**
   - `POST /api/auth/forgot-password` - Creates token, sends email
   - `GET /api/auth/verify-reset-token` - Validates token
   - `POST /api/auth/reset-password` - Changes password, invalidates sessions
   - Frontend pages: ForgotPasswordPage, ResetPasswordPage
   - Login page "Forgot password?" link

2. **Database Indexes** - Created on server startup
   - users: email (unique), user_id (unique)
   - subscriptions: user_id (unique), stripe_customer_id
   - trusts: user_id, trust_id (unique)
   - entities: (trust_id, user_id), entity_id (unique)
   - governance_tasks: (trust_id, user_id), (user_id, due_date), task_id (unique)
   - minutes_records: (trust_id, user_id), (user_id, meeting_date), minutes_id (unique)
   - distribution_records: (trust_id, user_id), (user_id, date), distribution_id (unique)
   - health_score_snapshots: (trust_id, calculated_at), snapshot_id (unique)
   - password_resets: token (unique), user_id (unique)
   - user_sessions: session_token (unique), user_id
   - audit_logs: (user_id, timestamp), audit_id (unique)

3. **Legacy Collection Cleanup**
   - Removed: `minutes`, `distributions` (old schema)
   - Active: `minutes_records`, `distribution_records` (proper schema)

### Core Features - COMPLETE
- Authentication (JWT + Google OAuth + Password Reset)
- Trust & Entity Management
- Minutes with PDF generation
- Distributions with approval workflow
- Compensation tracking
- Governance Health (5-criteria scoring)
- Historical health chart
- Calendar & tasks
- Dark mode toggle

### Integrations - COMPLETE
- **Stripe** (LIVE): Checkout, portal, cancel/reactivate/upgrade, webhooks
  - Monthly: $79/mo (price_1T4RVI2lZzmsSFmdoWliQfMu)
  - Annual: $790/yr (price_1T4RWl2lZzmsSFmdvQAnlrOY)
  - Webhook endpoint: /api/stripe/webhook
- **Postmark**: 12 email templates (including password_reset)
- **APScheduler**: Daily reminders, task updates, health snapshots

### Subscription - COMPLETE
- 14-day trial with gating
- Monthly ($79) and Annual ($790) plans
- Paywall for expired trials

## Email Templates (12)
1. welcome
2. password_reset (NEW)
3. task_reminder
4. task_overdue
5. minutes_created
6. distribution_created
7. distribution_approved
8. subscription_activated
9. subscription_canceled
10. subscription_renewed
11. payment_failed
12. subscription_upgraded

## Test Credentials
- demo@trustoffice.com / demopassword (main demo account with 2 trusts)
- test@example.com / testpassword123
- testuser@test.com / testpassword123 (created for P1 testing)

## Prioritized Backlog

### P0 (Technical Debt) - COMPLETE (Mar 2, 2026)
- [x] Backend modular structure - Created database.py, models.py, dependencies.py
- [x] Created routers/ directory with domain-specific router modules
- [x] Completed routers: auth.py, trusts.py, entities.py, tasks.py, units.py
- [x] Frontend read-only mode integration with ReadOnlyBanner
- [x] Unified subscription state management (get_subscription_state helper)
- [x] **Distributions router migrated** - 405 lines removed from server.py, now in routers/distributions.py (433 lines)
- [x] Migration guide created at /app/backend/MIGRATION_GUIDE.md

### P1 (High Priority) - COMPLETE (Mar 2, 2026)
- [x] Migrate distributions router (with require_write_access for subscription gating) - 433 lines
- [x] Migrate governance router (health score, dashboard, onboarding, activity) - 598 lines
- [x] Migrate minutes router (basic CRUD, PDF, templates with 11 types) - 1243 lines
- [x] Removed ~2000 lines total from server.py

**Server.py Reduction:** 7618 → 5611 lines (~26% reduction)

### P2 (Medium Priority) - IN PROGRESS
- [x] Implement hard feature gating for premium-only features
  - Created `Feature` class with core (trial) and premium (paid) features
  - `PLAN_FEATURES` dict maps plans to available features
  - `require_premium_feature()` dependency returns 402 for blocked features
  - CSV export endpoints gated: /api/export/minutes, distributions, compensation, tasks
  - New endpoint: GET /api/subscription/features returns feature flags
- [ ] Migrate remaining routers (schedule_a, compensation, subscriptions)
- [ ] Add Audit Log (backend + UI)
- [x] Profile editing (name change) - Edit button in Settings > Profile section
- [x] Search in minutes/distributions - Server-side search with debounced queries
- [x] Table horizontal scroll for mobile - overflow-x-auto on table containers
- [x] Benevolence Mode - Full feature for charitable trusts (toggle, log, template)
- [x] Notification preferences - Toggle switches in Settings page for email notification control
- [x] Benevolence Report PDF Export - Styled PDF similar to Schedule A
- [x] Auto-populate Minutes Form with Entity data (trust_indenture_date, trustees_present, article refs)

### P2 (Medium-term)
- [x] Fix Compensation API schema mismatch (Feb 25, 2026)
- [x] Trust Certificate Units UI (Mar 2, 2026)
- [x] Beneficiary Dashboard for unit allocations (Mar 2, 2026)
- [ ] Audit Log (backend + UI)
- [ ] Receipt/invoice download
- [ ] Feedback process

### P3 (Future)
- [ ] Multi-trustee collaboration
- [ ] AI-assisted minutes drafting
- [ ] Mobile app
- [ ] Date range filters for Minutes page
- [ ] More entity types (LLCs)
- [ ] Email retry queue for Postmark failures

## Notes
- Postmark: Sandbox mode (verified domain only)
- Stripe: LIVE MODE configured
- 14-day trial handled locally (no Stripe trial needed)
- Password reset tokens expire in 1 hour
