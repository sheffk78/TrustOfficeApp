# TrustOffice Features Guide — Product Knowledge Base

This document maps every feature, page, and action available in the TrustOffice web app. The Trust Assistant uses this to answer "how do I..." and "where do I..." questions, and to route user requests to the correct action.

## Navigation Structure

TrustOffice has a sidebar with these sections:

### Hero Items (top)
1. **Dashboard** (`/dashboard`) — Home screen showing trust overview, health score, recent activity, governance insights, and onboarding checklist
2. **Trust Assistant** (`/trust-assistant`) — AI chat interface for trust administration help (current page)

### Governance
- **Calendar** (`/calendar`) — Governance task calendar. Create, view, and manage tasks. Tasks track reviews, filings, and deadlines.
- **Minutes** (`/minutes`) — Trust meeting minutes. View, create, draft, and manage minutes records. Each minutes sets meeting dates, participants, decisions, and attachments.
- **Tax Calendar** (`/tax-calendar`) — IRS and state tax filing deadlines auto-calculated from trust formation date and state. Shows filing types, due dates, and overdue status.

### Money
- **Distributions** (`/distributions`) — Record and track distributions to beneficiaries. Create records with HEMS purpose classification, amounts, and dates. Send beneficiary notices.
- **Compensation** (`/compensation`) — Trustee compensation plans and payment records. Create plans, log payments, track YTD totals.
- **Investments** (`/investments`) — Log and track trust investments. Add investment accounts, track performance, view summary.
- **Benevolence** (`/benevolence`, conditional) — Record charitable/benevolence distributions. Only visible when the trust has benevolence enabled.

### Structure
- **Structures** (`/structures`) — Trust entity hierarchy. Create subsidiary entities (LLCs, sub-trusts), manage entity relationships, view organizational structure.
- **Schedule A** (`/schedule-a`) — Trust asset inventory. Add, edit, dispose of assets. Categories: real property, financial accounts, tangible property, business interests, intellectual property, other. Export full PDF.
- **Beneficiaries** (`/beneficiaries`) — Manage beneficiaries and trust unit certificates. Add beneficiaries with contact info, create unit certificates, record transfers.
- **Communications** (`/communications`) — Log beneficiary communications. Record interactions with beneficiaries for audit trail.
- **Vault** (`/vault`) — Document storage. Upload files (PDF, images), link from Google Drive/Dropbox, categorize documents, search, download.

### Compliance
- **Risk Dashboard** (`/risk`) — Risk assessment dashboard. Shows alerts, risk scores, pending reviews, and compliance status across multiple dimensions.
- **State Compliance** (`/state-compliance`) — State-specific trust compliance requirements. Shows relevant state laws, filing requirements, and compliance status by state.
- **Authority** (`/authority`) — Trustee authority tracking. Documents what powers and authorities the trustee has under the trust instrument.
- **Audit Trail** (`/audit-trail`) — Action log. Shows all changes made in the trust — who did what and when. Read-only audit view.
- **Binder Tools** (`/binder`) — Generate printable audit defense binders. Cover sheets, minutes summaries, asset lists.

### Standalone Links
- **Trust Health** (`/governance`) — 7-criteria defensibility score. Shows score chart, criteria breakdown (Quarterly Minutes, Task Compliance, Compensation, Distributions, Annual Review, Transaction Classification, Separation Alerts), scoring guide, and hidden insights management.
- **Settings** (`/settings`) — Trust profile settings. Edit trust name, formation date, EIN, jurisdiction, state code, notification preferences.

### Admin (visible only to admin users)
- **Admin Dashboard** (`/admin`) — User management, customer list, impersonation, revenue metrics, stats dashboard access grants.

### Mobile Navigation
On mobile (≤1024px), a bottom navigation bar replaces the sidebar with 6 items: Home, Minutes, Money (submenu), Assistant, Trust Health, Settings.

## Key Features by Domain

### Trust Health & Score
- 7-criteria defensibility scoring system
- Health score from 0-100 with color-coded ranges (green 80+, amber 60-79, red <60)
- Historical score chart (30-day trend)
- Criteria breakdown with per-criterion points and max scores
- Actionable governance insights with dismiss/restore functionality
- AI-generated suggestions for improvement
- Onboarding checklist (8 steps): Formation Date, EIN, Trust Document, EIN Letter, Beneficiaries, Bank Account, First Meeting, Tax Calendar

### Governance Calendar & Tasks
- Create tasks with type (annual review, quarterly review, compensation review, distribution review, insurance compliance, transaction review, tax filing 1041, tax filing K-1, custom)
- Track task completion with checklist items
- Filter tasks by status (all, pending, completed, overdue)
- Due date tracking with overdue detection
- Priority levels (normal, high, critical)

### Meeting Minutes
- Create minutes via templates (general meeting, initial trustee meeting, acceptance of property, bank account authorization, distribution to beneficiaries, appointment of additional trustee, resignation of trustee)
- AI-powered draft assistant on Create Minutes page
- Form fields: meeting date, participants, decisions/agenda items, attachments
- Save with linked records (distributions, compensation, entity changes)
- Autosave draft support
- PDF export of completed minutes
- Minutes templates management (create, edit, delete custom templates)

### Trust Assets (Schedule A)
- Asset categories: real_property, financial_accounts, tangible_property, business_interests, intellectual_property, other
- Track: description, value, date acquired, ownership percentage, notes
- Asset disposal with date and reason
- Export full Schedule A PDF
- Summary view with counts and total value

### Distributions
- Create with: beneficiary name, amount, HEMS purpose classification, date, source account
- Purpose categories: health, education, maintenance, support, medical_expenses, education_expenses, housing, emergency, other
- Records track status (pending, approved, sent)
- Send beneficiary notice via email (idempotent — prevents double-send)
- Attach minutes to distributions
- Delete and edit existing distributions

### Beneficiaries & Trust Units
- Add beneficiaries: name, email, phone, notes
- Update beneficiary info (email, phone, notes) — edits existing record, does not create duplicate
- Trust unit certificates: create with unit count, class, beneficiary allocation, vesting schedule, transfer restrictions
- Trust unit transfers: record transfers between beneficiaries with approval tracking
- Beneficiary dashboard showing counts, unit totals, and allocation overview

### Vault (Document Storage)
- Upload documents (file upload or URL link from Google Drive/Dropbox)
- Categories: trust_document, court_filing, tax_return, correspondence, financial_statement, legal, insurance, property, beneficiary_doc, other
- Download documents
- Edit document metadata (title, category, notes)
- Delete documents
- Document summary with category counts

### Communications
- Log beneficiary communications: type (email, phone, meeting, letter, other), subject, notes, participants
- Edit and delete communication records
- Summary per trust

### Trust Entities
- Create subsidiary entities (LLCs, trusts, partnerships, corporations, other)
- Entity relationships: parent-child hierarchy, ownership percentages
- Edit entity name, type, EIN, notes
- Delete entities

### Compensation
- Create compensation plans: trustee name, role, amount, frequency (monthly, quarterly, annually, per_meeting), effective dates
- Log compensation payments: plan reference, amount, date, notes
- YTD compensation totals
- Attach payments to minutes
- Delete plans and payments

### Investments
- Log trust investments: name, type, institution, account number, value, date
- Update investment value and notes
- Investment summary with total portfolio value

### Tax Calendar
- Auto-generated from trust formation date and state code
- Common filing types: Form 1041, Form 1041-ES, K-1, state returns
- Upcoming deadlines view (next 30/60/90 days)
- Overdue detection with day counting
- Calendar entries can be edited

### Transactions
- Log trust transactions: type (income, expense, transfer), amount, date, category, description
- Categorize: rental_income, interest, dividends, capital_gains, business_income, other_income, legal_fees, accounting_fees, trustee_fees, insurance, property_taxes, maintenance, utilities, distributions, investments, other_expense
- Import transactions in bulk (CSV)
- Bulk classification with AI suggestions
- Separation dashboard — flags personal/trust commingling
- Transaction summary with income/expense breakdown

### Risk Dashboard
- Risk alerts and scores across categories
- Alert resolution workflow
- Risk history tracking
- Auto-scan generates new alerts

### State Compliance
- State-specific trust law profiles
- Per-trust compliance status
- Filing requirements by state
- Track which states the trust has obligations in

### Authority Tracking
- Document trustee powers and authorities
- Track limits and restrictions

### Audit Trail
- Read-only chronological activity log
- Shows action type, user, timestamp, entity affected
- Filterable by date range and action type

### Settings & Account
- Edit trust profile: name, type, formation date, EIN, jurisdiction, state code
- Notification preferences
- User preferences
- Subscription management (view, upgrade, cancel, reactivate)
- Billing history

## Subscription & Pricing

- Free for first trust with limited features
- $79/month per trust (monthly billing)
- Annual billing at a discount
- Features gated behind subscription: all write actions, advanced compliance, AI features, vault, audit trail
- Free user sees "All Features Included" banner with subscription promotion

## Common User Questions & Where to Send Them

| User asks | Section to recommend | Action path |
|-----------|---------------------|-------------|
| "Where do I see my health score?" | Trust Health page (`/governance`) | — |
| "How do I create meeting minutes?" | Minutes page (`/minutes`) → Create Minutes | `log_minutes` intent |
| "I need to add a new beneficiary" | Beneficiaries page (`/beneficiaries`) | `create_beneficiary` intent |
| "Change Jane's email" | Beneficiaries page | `update_beneficiary` intent |
| "Remove this beneficiary" | Beneficiaries page | `remove_beneficiary` intent |
| "Record a distribution" | Distributions page (`/distributions`) | `create_distribution` intent |
| "Cancel a distribution" | Distributions page | `cancel_distribution` intent |
| "I bought a new asset" | Schedule A (`/schedule-a`) | `add_asset` intent |
| "Upload a trust document" | Vault (`/vault`) | `upload_document` intent |
| "Set up trustee compensation" | Compensation page (`/compensation`) | `setup_compensation` intent |
| "What deadlines are coming?" | Calendar (`/calendar`) or Tax Calendar | `check_deadlines` intent |
| "Log a communication with a beneficiary" | Communications page | — (log communication) |
| "Find the trust document" | Vault | `review_document` intent |
| "Create a new entity (LLC)" | Structures | — (create entity) |
| "Record income/expense" | Transactions (if available) or Expenses page | `add_transaction` intent |
| "Dismiss this insight" | Dashboard → insight cards | `dismiss_alert` intent |
| "Schedule a quarterly review" | Calendar → Create Task | `schedule_task` intent |
| "Change my trust's EIN" | Settings → Trust Profile | `change_trust_settings` intent |

## Features That Don't Have AI Intents Yet (for honest routing)

If a user asks about these, suggest navigating to the page directly or acknowledge the feature exists:

- Creating/editing entities (structures)
- Editing the tax calendar
- Managing trust unit certificates
- Risk dashboard alerts
- State compliance settings
- Binder tools
- Investments
- Communications logging
- Subscription/billing changes
- Trust unit transfers
- Transaction import
- Bulk classification
- Minutes templates management
- User preferences
- Onboarding checklist

## Professional Escalation Guide

When a user's request touches legal, tax, or financial matters, recommend the appropriate professional:

### When to recommend a CPA/Tax Professional
- Form 1041 preparation or filing
- K-1 preparation
- Estimated tax payments (1041-ES)
- Trust tax planning
- Understanding tax implications of distributions (trust-level and beneficiary-level)
- State tax filing questions
- EIN application questions
- Deductibility of trust expenses

### When to recommend a Trust/Estates Attorney
- Trust instrument interpretation
- State-specific trust law questions
- Fiduciary duty questions involving legal risk
- Beneficiary disputes or disclaimers
- Trust modification or termination
- Trustee succession or removal
- Decanting or trust reformation
- Litigation risk assessment
- Questions about personal liability

### When to recommend a Financial Advisor
- Trust investment decisions
- Portfolio allocation
- Prudent Investor Act compliance
- Rebalancing trust assets
- Evaluating investment options
- Risk tolerance assessment for trust assets

### When to recommend both Attorney AND CPA
- Complex distributions (large amounts, multiple beneficiaries, tax-sensitive timing)
- Trust termination and asset distribution
- Trust decanting with tax implications
- Cross-state tax and legal compliance
- Any situation involving both legal authority questions AND tax consequences

### Default language (when the situation is ambiguous)
"This is an area where professional guidance is important. I'd recommend consulting with your [professional type] before moving forward. I'm an AI assistant, not a substitute for professional advice."