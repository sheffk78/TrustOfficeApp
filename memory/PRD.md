# TrustOffice - Trust Governance Workspace

## Original Problem Statement
Build TrustOffice - a trust governance workspace for individual/family trustees. Core jobs: Record trustee minutes and decisions, track distributions and expenses, maintain activity timeline per trust/entity, surface governance health status. Web-first (desktop optimized) with responsive mobile support. React + FastAPI + MongoDB stack.

## User Choices
- Both JWT and Google Social Login authentication
- 5-Criteria Governance Health Score (quarterly minutes, task compliance, compensation alignment, distribution docs, annual review)
- Entity management for Trusts, Holding LLCs, Operating LLCs with EGP fields
- Compensation tracking with annual plans and YTD monitoring
- Stripe subscription integration ($79/month or $790/year)
- Default categories for distributions/expenses
- Demo data included

## Architecture

### Tech Stack
- **Frontend**: React 18, Tailwind CSS, Shadcn/UI components
- **Backend**: FastAPI, Python 3.10+
- **Database**: MongoDB
- **Auth**: JWT + Emergent-managed Google OAuth
- **Payments**: Stripe (test mode)

### Design System (AnchorPoint)
- Primary: Navy #010079
- Accent: Gold #D5AD36
- Fonts: Cormorant Garamond (headings), DM Sans (body), JetBrains Mono (data/labels)
- 0px border-radius everywhere
- Status colors: Success #059669, Warning #D97706, Error #DC2626

### Data Model
| Collection | Purpose |
|------------|---------|
| users | User accounts with auth |
| user_sessions | OAuth session tokens |
| trusts | Trust workspace definitions |
| user_onboarding | Auto-updating checklist state |
| entities | Trusts, LLCs with EGP fields |
| entity_relationships | Hierarchy mapping (owns, controls) |
| governance_tasks | Calendar tasks with due dates |
| minutes_records | Meeting minutes with PDF |
| distribution_records | Distributions with approval workflow |
| compensation_plans | Annual approved amounts |
| compensation_payments | Individual payments with YTD tracking |
| health_score_snapshots | Historical score tracking |
| subscriptions | Stripe subscription state |
| payment_transactions | Payment history |

### Key Files
- `/app/backend/server.py` - All API endpoints
- `/app/frontend/src/App.js` - Main router with protected routes
- `/app/frontend/src/context/AuthContext.js` - Auth state management
- `/app/frontend/src/components/Sidebar.js` - Navigation with trust selector

## What's Been Implemented (Feb 22, 2026)

### Session Persistence Fix ✅
- Fixed race condition where users were logged out on page refresh
- AuthContext now synchronously checks localStorage before rendering
- ProtectedRoute waits for auth check to complete before redirecting

### Backend APIs (26 endpoints, 100% working)
- **Auth**: /register, /login, /google, /callback, /session, /me, /logout
- **Trusts**: CRUD + demo seeding
- **Entities**: CRUD with EGP fields, PATCH for updates
- **Entity Relationships**: CRUD for hierarchy
- **Governance Tasks**: CRUD + complete/uncomplete actions
- **Minutes**: CRUD with PDF storage
- **Distributions**: CRUD with approval workflow
- **Compensation Plans**: CRUD
- **Compensation Payments**: CRUD + YTD calculation
- **Governance Health**: 5-criteria score calculation
- **Onboarding**: Auto-updating checklist state
- **Subscription**: Trial creation, Stripe checkout, webhook handling

### Frontend Pages (All implemented)
- **Login/Signup**: Email/password + Google OAuth
- **Onboarding**: Trust creation wizard
- **Dashboard**: Governance score, quick actions, timeline
- **Calendar** ✅ NEW: Task management with filters
- **Minutes**: List + wizard for recording
- **Distributions**: Table with add modal
- **Compensation** ✅ NEW: Plans + payments with YTD
- **Entities** ✅ NEW: Grid view with entity cards
- **Entity Detail** ✅ NEW: Full EGP editor
- **Structure** ✅ NEW: Hierarchy visualization
- **Governance Health**: 5-criteria score breakdown
- **Settings**: Profile + trust management
- **Billing** ✅ NEW: Stripe subscription management

### Stripe Integration ✅
- 14-day free trial for new users
- Monthly plan: $79/month (price_1T3Ot92AK0Mb8Foa8ZXlTLuY)
- Annual plan: $790/year (price_1T3OtZ2AK0Mb8FoaTCchoxEI)
- Checkout redirect, webhook handling, subscription status tracking

## Test Credentials
- Email: test@trustoffice.com
- Password: testpassword123
- Demo data: Use "Use Demo Data" button on empty dashboard

## Prioritized Backlog

### P0 (Critical) - ✅ COMPLETE
- Session persistence fix
- All new pages (Calendar, Entities, Structure, Compensation)
- 5-criteria governance health score
- Stripe subscription integration

### P1 (High Priority)
- [ ] Distribution approval workflow modal (solvency + recusal checks)
- [ ] PDF generation for minutes
- [ ] Email notifications for task reminders
- [ ] Onboarding checklist auto-update display

### P2 (Medium Priority)
- [ ] Entity detail page improvements (more EGP fields)
- [ ] Historical health score chart
- [ ] Background cron for task status updates
- [ ] Audit log

### P3 (Nice to Have)
- [ ] Dark mode toggle
- [ ] Multi-trustee collaboration
- [ ] Mobile-optimized views
- [ ] AI-assisted minutes drafting

## Next Tasks
1. Add distribution approval modal with solvency/recusal checkboxes
2. Display onboarding checklist on dashboard (entities_confirmed, calendar_set, etc.)
3. Add PDF preview/download for minutes
4. Implement email reminders for overdue tasks
