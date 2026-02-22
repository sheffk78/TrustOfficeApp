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

### Session Persistence
- Fixed race condition - users stay logged in on page refresh

### Dashboard Enhancements
- Governance Insights Panel with actionable recommendations
- 5-Criteria Health Score Display with checkmarks
- Onboarding Checklist (auto-updating, dismissible)

### Distribution Approval Workflow
- Approval Modal with solvency + recusal confirmations

### PDF Generation for Minutes
- ReportLab PDF with professional formatting
- Preview modal with Download button

### Historical Health Score Chart
- 30-day trend chart with SVG rendering
- Daily score snapshots

### Postmark Email Integration
**Configuration:**
- From: no-reply@contact.trustoffice.app
- Server Token: Configured in .env

**6 Email Templates (centralized in `email_templates.py`):**
1. `welcome` - Sent on new user registration
2. `task_reminder` - Upcoming governance task reminders
3. `task_overdue` - Overdue task alerts (red styling)
4. `minutes_created` - When new minutes are logged
5. `distribution_created` - When new distribution is logged
6. `distribution_approved` - When distribution is approved

**Automatic Email Triggers:**
- User registration -> Welcome email
- Create minutes -> Minutes notification
- Create distribution -> Distribution notification
- Approve distribution -> Approval confirmation

**Note:** Postmark sandbox mode restricts sending to domains matching from address until account approval.

### Background Jobs (APScheduler) - NEW (Feb 22, 2026)
**Scheduled Jobs:**
1. `task_status_update` - Runs hourly, updates task statuses (upcoming/overdue)
2. `daily_reminders` - Runs at 9 AM UTC, sends email reminders for upcoming/overdue tasks
3. `daily_health_snapshots` - Runs at 00:05 UTC, creates health score snapshots for all trusts

**API Endpoints:**
- `GET /api/background-jobs/status` - View scheduled jobs and their next run times
- `POST /api/background-jobs/run/task-status-update` - Manually trigger task status update
- `POST /api/background-jobs/run/daily-reminders` - Manually trigger daily reminders
- `POST /api/background-jobs/run/health-snapshots` - Manually trigger health snapshots

**Implementation:**
- APScheduler integrated with FastAPI lifecycle (startup/shutdown events)
- Background runner starts automatically with the server
- All manual trigger endpoints require authentication
- Audit logging for task status changes

### Backend APIs (50+ endpoints, 100% tested)
- Auth, Trusts, Entities, Relationships, Tasks, Minutes, Distributions, Compensation, Health, Onboarding, Subscription, Email, Background Jobs

### Frontend Pages (All implemented)
- Login/Signup, Onboarding, Dashboard, Calendar, Minutes (PDF), Distributions (approval), Compensation, Entities, Entity Detail, Structure, Governance Health (chart), Settings, Billing

## Test Credentials
- Email: test@example.com
- Password: testpassword123

## Prioritized Backlog

### P0-P1 - COMPLETE
- Session persistence, all pages, health score, Stripe, PDF generation, historical chart, email integration

### P2 - COMPLETE (Feb 22, 2026)
- [x] Automated cron job for daily task reminders (APScheduler)
- [x] Background task status updates (hourly)
- [x] Daily health score snapshots
- [ ] Audit log UI for viewing change history
- [ ] Export data to CSV

### P3 (Nice to Have)
- [ ] Dark mode toggle
- [ ] Multi-trustee collaboration
- [ ] Mobile-optimized views
- [ ] AI-assisted minutes drafting

## Next Tasks
1. Implement Audit Log UI - display history of changes from audit_logs collection
2. Export data to CSV functionality
3. Lift Postmark sandbox limitation (user action required)
4. Gate app features based on Stripe subscription status
