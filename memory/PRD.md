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

### Design System (AnchorPoint)
- Light: Navy #010079, Gold #D5AD36
- Dark: Gold on slate backgrounds
- 0px border-radius, Cormorant Garamond/DM Sans/JetBrains Mono fonts

## Completed Features

### Latest Updates (Mar 2, 2026) - LOGIN FLOW FIX ✅

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

### P1 (Short-term) - COMPLETE (Feb 23-25, 2026)
- [x] Profile editing (name change) - Edit button in Settings > Profile section
- [x] Search in minutes/distributions - Server-side search with debounced queries
- [x] Table horizontal scroll for mobile - overflow-x-auto on table containers
- [x] Benevolence Mode - Full feature for charitable trusts (toggle, log, template)
- [x] Notification preferences - Toggle switches in Settings page for email notification control
- [x] Benevolence Report PDF Export - Styled PDF similar to Schedule A
- [x] Auto-populate Minutes Form with Entity data (trust_indenture_date, trustees_present, article refs)

### P2 (Medium-term)
- [x] Fix Compensation API schema mismatch (Feb 25, 2026)
- [ ] PDF Export for Trust Unit Certificates
- [ ] Beneficiary Dashboard for unit allocations
- [ ] Audit Log (backend + UI)
- [ ] Receipt/invoice download
- [ ] Feedback process

### P3 (Future)
- [ ] Multi-trustee collaboration
- [ ] AI-assisted minutes drafting
- [ ] Mobile app

## Notes
- Postmark: Sandbox mode (verified domain only)
- Stripe: LIVE MODE configured
- 14-day trial handled locally (no Stripe trial needed)
- Password reset tokens expire in 1 hour
