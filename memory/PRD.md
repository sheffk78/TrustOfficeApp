# TrustOffice - Trust Governance Workspace

## Original Problem Statement
Build TrustOffice - a trust governance workspace for individual/family trustees. Core jobs: Record trustee minutes and decisions, track distributions and expenses, maintain activity timeline per trust/entity, surface governance health status.

## Architecture

### Tech Stack
- **Frontend**: React 18, Tailwind CSS, Shadcn/UI
- **Backend**: FastAPI, Python 3.10+
- **Database**: MongoDB (with indexes)
- **Auth**: JWT + Google OAuth, Password Reset
- **Payments**: Stripe (test mode)
- **Email**: Postmark (12 templates)
- **Background Jobs**: APScheduler

### Design System (AnchorPoint)
- Light: Navy #010079, Gold #D5AD36
- Dark: Gold on slate backgrounds
- 0px border-radius, Cormorant Garamond/DM Sans/JetBrains Mono fonts

## Completed Features

### Latest Updates (Feb 24, 2026) - COMPLETE ✅

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
- **Stripe**: Checkout, portal, cancel/reactivate/upgrade, webhooks
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
- test@example.com / testpassword123
- testuser@test.com / testpassword123 (created for P1 testing)

## Prioritized Backlog

### P1 (Short-term) - COMPLETE (Feb 23-24, 2026)
- [x] Profile editing (name change) - Edit button in Settings > Profile section
- [x] Search in minutes/distributions - Server-side search with debounced queries
- [x] Table horizontal scroll for mobile - overflow-x-auto on table containers
- [x] Benevolence Mode - Full feature for charitable trusts (toggle, log, template)
- [ ] Notification preferences - TODO

### P2 (Medium-term)
- [ ] Audit Log (backend + UI)
- [ ] Receipt/invoice download
- [ ] Feedback process

### P3 (Future)
- [ ] Multi-trustee collaboration
- [ ] AI-assisted minutes drafting
- [ ] Mobile app

## Notes
- Postmark: Sandbox mode (verified domain only)
- Stripe: Test mode (card 4242424242424242)
- Password reset tokens expire in 1 hour
