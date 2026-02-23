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
- **Theme**: Light/Dark mode with localStorage persistence

### Design System (AnchorPoint)
- **Light Mode**: Primary Navy #010079, Gold accent #D5AD36
- **Dark Mode**: Gold accent on slate backgrounds (#0f172a, #1e293b)
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

### Dark Mode (Feb 23, 2026) - NEW
**Implementation:**
- `ThemeProvider` context manages theme state
- `ThemeToggle` component in sidebar
- Tailwind class-based dark mode (`dark:` utilities)
- CSS variables for color tokens
- localStorage persistence (`trustoffice-theme`)

**Features:**
- Toggle between light and dark themes
- System preference detection (if no manual preference)
- Persists across sessions
- Full styling coverage: sidebar, cards, buttons, tables, inputs

### Email Integration (Postmark) - 11 Templates
- Governance: welcome, task_reminder, task_overdue, minutes_created, distribution_created, distribution_approved
- Subscription: subscription_activated, subscription_canceled, subscription_renewed, payment_failed, subscription_upgraded

### Background Jobs (APScheduler) 
- Hourly task status updates
- Daily reminders at 9 AM UTC
- Daily health score snapshots at midnight UTC

### Billing & Subscription (Stripe)
- Checkout sessions for Monthly ($79) and Annual ($790) plans
- Customer portal for payment management
- Cancel/reactivate/upgrade with email notifications
- Webhook handling for lifecycle events

### CSV Data Export
- Minutes, Distributions, Compensation, Tasks exports

### Subscription Gating
- Backend middleware blocks expired trials (402 response)
- Frontend paywall for expired users
- Settings/Billing remain accessible

## Test Credentials
- Active User: test@example.com / testpassword123
- Expired User: expired@test.com / testpass123

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
- [x] Subscription gating
- [x] Stripe webhook with email notifications
- [x] **Dark mode toggle**

### P2 (Medium Priority)
- [ ] Audit Log UI - view history of changes
- [ ] Receipt/invoice download from billing page

### P3 (Nice to Have)
- [ ] Multi-trustee collaboration
- [ ] Mobile-optimized views
- [ ] AI-assisted minutes drafting

## Notes
- Postmark is in sandbox mode (can only send to verified sender domain)
- Stripe is in test mode (use test card 4242424242424242)
- Background jobs run automatically on server startup
- Dark mode toggle is in the sidebar below user profile
