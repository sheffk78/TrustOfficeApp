# TrustOffice - Trust Governance Workspace

## Original Problem Statement
Build TrustOffice - a trust governance workspace for individual/family trustees. Core jobs: Record trustee minutes and decisions, track distributions and expenses, maintain activity timeline per trust/entity, surface governance health status. Web-first (desktop optimized) with responsive mobile support. React + FastAPI + MongoDB stack.

## Architecture

### Tech Stack
- **Frontend**: React 18, Tailwind CSS, Shadcn/UI components
- **Backend**: FastAPI, Python 3.10+
- **Database**: MongoDB
- **Auth**: JWT + Emergent-managed Google OAuth
- **Payments**: Stripe (test mode)
- **PDF Generation**: ReportLab
- **Email**: Postmark (transactional emails)
- **Background Jobs**: APScheduler (cron-like scheduling)

### Design System (AnchorPoint)
- Primary: Navy #010079
- Accent: Gold #D5AD36
- Fonts: Cormorant Garamond (headings), DM Sans (body), JetBrains Mono (data/labels)
- 0px border-radius everywhere

## What's Been Implemented

### Core Features
- **Authentication**: JWT + Google OAuth with session persistence
- **Dashboard**: Governance Insights panel, 5-criteria health score, onboarding checklist
- **Minutes**: Record meeting minutes with PDF generation and download
- **Distributions**: Log and track with approval workflow (solvency/recusal checks)
- **Compensation**: Track payments with plan alignment monitoring
- **Entities**: Manage trusts, LLCs, and entity relationships
- **Governance Calendar**: Task tracking with due dates and status
- **Health Score History**: 30-day trend chart with daily snapshots

### Email Integration (Postmark)
- Welcome emails on registration
- Task reminder and overdue notifications
- Minutes/Distribution creation alerts
- Distribution approval confirmations

### Background Jobs (APScheduler) 
- Hourly task status updates
- Daily reminders at 9 AM UTC
- Daily health score snapshots at midnight UTC
- Manual trigger endpoints for testing

### Billing & Subscription (Feb 22, 2026) - NEW
**Stripe Integration:**
- Checkout session creation for Monthly ($79) and Annual ($790) plans
- Customer portal for payment method management
- Subscription cancellation (at period end with reactivation option)
- Plan upgrade (monthly to annual with proration)

**Billing Page Features:**
- Current plan status with clear badges (Trial, Active, Canceling, Expired)
- Trial end date prominently displayed
- Days remaining countdown
- Next billing date for active subscriptions
- Cancel/Reactivate subscription controls
- Upgrade to Annual button (saves $158)
- Manage Payment Method (Stripe portal)
- FAQ section

### CSV Data Export (Feb 22, 2026) - NEW
**Export Endpoints:**
- `GET /api/export/minutes` - Export all minutes records
- `GET /api/export/distributions` - Export all distribution records
- `GET /api/export/compensation` - Export all compensation payments
- `GET /api/export/tasks` - Export all governance tasks

**Features:**
- Filter by trust_id for specific trust exports
- Properly formatted CSV with headers
- Download with timestamped filename
- Available from Settings page

## Test Credentials
- Email: test@example.com
- Password: testpassword123

## API Endpoints Summary

### Export
- `GET /api/export/minutes` - CSV export
- `GET /api/export/distributions` - CSV export
- `GET /api/export/compensation` - CSV export
- `GET /api/export/tasks` - CSV export

### Subscription
- `GET /api/subscription` - Get subscription status
- `POST /api/subscription/create-checkout` - Start Stripe checkout
- `GET /api/subscription/verify-payment` - Verify checkout session
- `POST /api/subscription/create-portal` - Open Stripe portal
- `POST /api/subscription/cancel` - Cancel at period end
- `POST /api/subscription/reactivate` - Undo cancellation
- `POST /api/subscription/upgrade` - Monthly to annual

### Background Jobs
- `GET /api/background-jobs/status` - View scheduled jobs
- `POST /api/background-jobs/run/task-status-update` - Manual trigger
- `POST /api/background-jobs/run/daily-reminders` - Manual trigger
- `POST /api/background-jobs/run/health-snapshots` - Manual trigger

## Prioritized Backlog

### Completed
- [x] Core authentication (JWT + Google OAuth)
- [x] Dashboard with governance insights
- [x] Minutes management with PDF generation
- [x] Distribution approval workflow
- [x] Compensation tracking
- [x] Entity management
- [x] Governance calendar and tasks
- [x] Health score with historical chart
- [x] Email integration (Postmark)
- [x] Background jobs (APScheduler)
- [x] Stripe subscription management
- [x] CSV data export

### P2 (Medium Priority)
- [ ] Audit Log UI - view history of changes
- [ ] Gate app features based on subscription status
- [ ] Email notifications for subscription events

### P3 (Nice to Have)
- [ ] Dark mode toggle
- [ ] Multi-trustee collaboration
- [ ] Mobile-optimized views
- [ ] AI-assisted minutes drafting
- [ ] Additional entity types (more LLCs)

## Notes
- Postmark is in sandbox mode (can only send to verified sender domain)
- Stripe is in test mode (use test card 4242424242424242)
- Background jobs run automatically on server startup
