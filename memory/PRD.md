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

### Email Integration (Postmark) - 11 Templates
**Governance Emails:**
- `welcome` - Onboarding for new users
- `task_reminder` - Upcoming task reminders
- `task_overdue` - Overdue task alerts
- `minutes_created` - New minutes notification
- `distribution_created` - New distribution logged
- `distribution_approved` - Distribution approval confirmation

**Subscription Emails (NEW):**
- `subscription_activated` - Welcome to Pro!
- `subscription_canceled` - Cancellation confirmation with access date
- `subscription_renewed` - Payment successful/renewal
- `payment_failed` - Payment failure alert with retry info
- `subscription_upgraded` - Plan upgrade confirmation

### Background Jobs (APScheduler) 
- Hourly task status updates
- Daily reminders at 9 AM UTC
- Daily health score snapshots at midnight UTC
- Manual trigger endpoints for testing

### Billing & Subscription
**Stripe Integration:**
- Checkout session creation for Monthly ($79) and Annual ($790) plans
- Customer portal for payment method management
- Subscription cancellation (with email notification)
- Plan upgrade monthly to annual (with email notification)

**Billing Page Features:**
- Current plan status with clear badges (Trial, Active, Canceling, Expired)
- Trial end date prominently displayed
- Days remaining countdown
- Next billing date for active subscriptions
- Cancel/Reactivate subscription controls
- Upgrade to Annual button (saves $158)
- FAQ section

### CSV Data Export
- Minutes, Distributions, Compensation, Tasks exports
- Filter by trust_id

### Subscription Gating
- Backend middleware blocks expired trials (402 response)
- Frontend paywall for expired users
- Settings/Billing remain accessible

### Stripe Webhook Integration (Feb 23, 2026) - ENHANCED
**Events Handled:**
- `checkout.session.completed` - Activates subscription, sends welcome email
- `customer.subscription.updated` - Detects plan changes and cancellation scheduling
- `customer.subscription.deleted` - Marks subscription as canceled
- `invoice.paid` - Handles renewals, sends renewal confirmation
- `invoice.payment_failed` - Updates status to past_due, sends payment alert

**Email Triggers:**
- New subscription -> `subscription_activated`
- Cancellation scheduled -> `subscription_canceled`
- Plan upgrade -> `subscription_upgraded`
- Renewal success -> `subscription_renewed`
- Payment failure -> `payment_failed`

## Test Credentials
- Active User: test@example.com / testpassword123
- Expired User: expired@test.com / testpass123

## API Endpoints Summary

### Stripe Webhook
- `POST /api/stripe/webhook` - Handles subscription lifecycle events

### Subscription
- `GET /api/subscription` - Get subscription status
- `POST /api/subscription/create-checkout` - Start Stripe checkout
- `POST /api/subscription/create-portal` - Open Stripe portal
- `POST /api/subscription/cancel` - Cancel at period end (triggers email)
- `POST /api/subscription/reactivate` - Undo cancellation
- `POST /api/subscription/upgrade` - Monthly to annual (triggers email)

### Email
- `GET /api/email/status` - View email config and 11 templates
- `POST /api/email/test` - Send test email

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
- [x] Email integration (Postmark) - 11 templates
- [x] Background jobs (APScheduler)
- [x] Stripe subscription management
- [x] CSV data export
- [x] Subscription gating (trial expiration enforcement)
- [x] **Stripe webhook improvements with email notifications**

### P2 (Medium Priority)
- [ ] Audit Log UI - view history of changes
- [ ] Receipt/invoice download from billing page

### P3 (Nice to Have)
- [ ] Dark mode toggle
- [ ] Multi-trustee collaboration
- [ ] Mobile-optimized views
- [ ] AI-assisted minutes drafting

## Notes
- Postmark is in sandbox mode (can only send to verified sender domain)
- Stripe is in test mode (use test card 4242424242424242)
- Background jobs run automatically on server startup
- Webhook requires valid Stripe signature for event processing
