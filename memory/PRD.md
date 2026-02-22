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

### Design System (AnchorPoint)
- Primary: Navy #010079
- Accent: Gold #D5AD36
- Fonts: Cormorant Garamond (headings), DM Sans (body), JetBrains Mono (data/labels)
- 0px border-radius everywhere

## What's Been Implemented (Feb 22, 2026)

### Session Persistence ✅
- Fixed race condition - users stay logged in on page refresh

### Dashboard Enhancements ✅
- Governance Insights Panel with actionable recommendations
- 5-Criteria Health Score Display with checkmarks
- Onboarding Checklist (auto-updating, dismissible)

### Distribution Approval Workflow ✅
- Approval Modal with solvency + recusal confirmations

### PDF Generation for Minutes ✅
- ReportLab PDF with professional formatting
- Preview modal with Download button

### Historical Health Score Chart ✅
- 30-day trend chart with SVG rendering
- Daily score snapshots

### Postmark Email Integration ✅ NEW
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
- User registration → Welcome email
- Create minutes → Minutes notification
- Create distribution → Distribution notification
- Approve distribution → Approval confirmation

**API Endpoints:**
- `GET /api/email/status` - Check configuration
- `POST /api/email/test` - Send test email
- `POST /api/email/send-task-reminders` - Trigger task reminders

**Note:** Postmark sandbox mode restricts sending to domains matching from address until account approval.

### Backend APIs (48 endpoints, 100% tested)
- Auth, Trusts, Entities, Relationships, Tasks, Minutes, Distributions, Compensation, Health, Onboarding, Subscription, Email

### Frontend Pages (All implemented)
- Login/Signup, Onboarding, Dashboard, Calendar, Minutes (PDF), Distributions (approval), Compensation, Entities, Entity Detail, Structure, Governance Health (chart), Settings, Billing

## Test Credentials
- Email: test@trustoffice.com
- Password: testpassword123

## Prioritized Backlog

### P0-P1 - ✅ COMPLETE
- Session persistence, all pages, health score, Stripe, PDF generation, historical chart, email integration

### P2 (Medium Priority)
- [ ] Automated cron job for daily task reminders
- [ ] Background task status updates
- [ ] Audit log with detailed history
- [ ] Export data to CSV

### P3 (Nice to Have)
- [ ] Dark mode toggle
- [ ] Multi-trustee collaboration
- [ ] Mobile-optimized views
- [ ] AI-assisted minutes drafting

## Next Tasks
1. Set up cron job for automated daily task reminders
2. Background job for auto-updating task statuses
3. Audit log for tracking all changes
