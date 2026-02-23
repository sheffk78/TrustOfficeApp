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

### Billing & Subscription
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

### CSV Data Export
**Export Endpoints:**
- `GET /api/export/minutes` - Export all minutes records
- `GET /api/export/distributions` - Export all distribution records
- `GET /api/export/compensation` - Export all compensation payments
- `GET /api/export/tasks` - Export all governance tasks

### Subscription Gating (Feb 23, 2026) - NEW
**Backend Middleware:**
- SubscriptionMiddleware checks trial status on all protected routes
- Returns 402 Payment Required for expired trials
- Exempt paths: `/api/auth/*`, `/api/subscription/*`, `/api/categories`

**Frontend Paywall:**
- `SubscriptionGate` component wraps protected routes
- Shows "Your Trial Has Ended" message with feature list
- "Subscribe Now" CTA button navigates to billing page
- Settings and Billing pages remain accessible for expired users

**User Experience:**
- Active users see normal app content
- Expired users see paywall on all pages except Settings/Billing
- Clear messaging about data safety ("Your data is safe")

## Test Credentials
- Active User: test@example.com / testpassword123
- Expired User: expired@test.com / testpass123

## API Endpoints Summary

### Subscription Gating
- Protected routes return 402 for expired trials
- Exempt paths: auth, subscription, categories

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
- [x] **Subscription gating (trial expiration enforcement)**

### P2 (Medium Priority)
- [ ] Audit Log UI - view history of changes
- [ ] Email notifications for subscription events (canceled, renewed)
- [ ] Stripe webhook for subscription lifecycle events

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
- Expired trials are blocked from app features but can access settings/billing
