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

### Backend Architecture (Refactored Dec 30, 2025)
The backend now has a modular structure for better maintainability:
```
/app/backend/
├── server.py           # Main FastAPI app (1128 lines, down from 7538 - 85% reduction)
├── database.py         # MongoDB connection singleton
├── models.py           # All Pydantic models and enums (777 lines)
├── dependencies.py     # Shared auth, helpers, feature gating, health score (751 lines)
├── routers/            # Domain-specific router modules (14 migrated)
│   ├── auth.py          # Auth, register, login, profile, OAuth (356 lines)
│   ├── preferences.py   # Notification + user preferences (133 lines)
│   ├── distributions.py # Distribution endpoints
│   ├── governance.py    # Governance health/history/insights
│   ├── minutes.py       # Minutes CRUD + templates + PDF
│   ├── schedule_a.py    # Schedule A assets CRUD + PDF
│   ├── compensation.py  # Compensation plans + payments
│   ├── subscriptions.py # Stripe payments + webhooks
│   ├── benevolence.py   # Benevolence CRUD + PDF
│   ├── exports.py       # CSV exports (premium feature)
│   ├── trust_units.py   # Trust units certificates + transfers
│   ├── trusts.py        # Trust CRUD
│   ├── entities.py      # Entity + relationship management
│   └── tasks.py         # Governance tasks
├── email_service.py    # Postmark email integration
├── email_templates.py  # Email template content
└── background_tasks.py # APScheduler background jobs
```

**Migration Statistics (Dec 30, 2025):**
- Original server.py: 7538 lines
- Final server.py: 1128 lines
- **Total reduction: 85% (6410 lines moved)**
- 14 routers created with clear domain separation
- All enums/models centralized in models.py
- All helper functions centralized in dependencies.py

### Design System (AnchorPoint)
- Light: Navy #010079, Gold #D5AD36
- Dark: Gold on slate backgrounds
- 0px border-radius, Cormorant Garamond/DM Sans/JetBrains Mono fonts

## Completed Features



### Latest Updates (Mar 2, 2026) - 10 MORE MINUTES TEMPLATES (BATCH 2) ✅

**Session Summary:** Implemented 10 additional minutes templates, bringing the total to 31 templates.

**New Templates Added (Batch 2):**

| Category | Templates |
|----------|-----------|
| **Legal/Amendment** | Trust Amendment, Power of Attorney Authorization, Trust Termination/Dissolution |
| **Asset Management** | Real Estate Purchase, Business Interest Acquisition, Real Estate Lease |
| **Tax & Compliance** | Fiscal Year Election, Tax Filing Authorization |
| **Special Situations** | Emergency Action Ratification, Conflict of Interest Disclosure |

**Files Updated:**
- `/app/backend/models.py` - Added 10 new MinutesTemplateType enum values
- `/app/backend/routers/minutes.py` - Added 10 content generators and template options
- `/app/frontend/src/pages/MinutesTemplateFormPage.js` - Added 10 form states and form sections

**Testing:** 100% pass rate (iteration_61) - 12 backend tests + all 10 frontend forms verified

**Total Templates Now Available:** 31


### Previous Updates (Mar 2, 2026) - COMBINED BENEFICIARIES + UNITS PAGE ✅

**Session Summary:** Merged the separate "Units" and "Beneficiaries" pages into a single "Beneficiaries" page with tabs, and fixed Trust Units validation issues.

**Page Combination:**
- Created new `/app/frontend/src/pages/BeneficiariesPage.js` with 3 tabs:
  - **Overview Tab**: Ownership pie chart, summary cards (Total Authorized, Issued, Remaining, Beneficiaries count), Certificate Holders list with expandable details
  - **Certificates Tab**: Full certificate management (issue, edit, transfer, revoke), status filter, PDF generation
  - **Transfers Tab**: Transfer history with audit trail
- Updated routes to redirect `/trust/units` and `/trust/beneficiaries` to `/beneficiaries`
- Updated sidebar to show single "Beneficiaries" link

**Trust Units Fixes:**
1. **Demo data cleaned up** - Now shows 4 realistic certificates totaling exactly 100 units:
   - John Smith: 40 units (40%)
   - Jane Smith: 30 units (30%)
   - Smith Family Trust: 20 units (20%)
   - Robert Smith Jr.: 10 units (10%)
2. **Decimal input fixed** - Changed `step="0.0001"` to `step="any"` so users can enter any number without forced decimals
3. **Validation feedback added** - Shows warning when trying to issue more units than available

**Files Changed:**
- `/app/frontend/src/pages/BeneficiariesPage.js` - NEW combined page
- `/app/frontend/src/App.js` - Updated routes with redirects
- `/app/frontend/src/components/Sidebar.js` - Single Beneficiaries link
- `/app/frontend/src/pages/TrustUnitsPage.js` - Fixed decimal step values
- Database: Updated demo user subscription to `forever_free`, cleaned up certificate data

**Testing:** 100% pass rate (iteration_60) - 11 frontend features verified


### Previous Updates (Mar 2, 2026) - GUIDED MINUTES PARTICIPANT FIX + COMPENSATION TRUSTEE SELECTOR ✅

**Session Summary:** Fixed two user-reported UX issues:
1. Guided Minutes now separates trustees from other attendees
2. Compensation page now has trustee selector for payments

**Issue 1 Fixed - Guided Minutes Participant Titles:**
- **Problem:** All participants were titled as "Trustees" in the final PDF, even guests/advisors/beneficiaries
- **Solution:** 
  - Split participants into "TRUSTEES PRESENT" and "OTHER ATTENDEES (OPTIONAL)" sections
  - Added dropdown to select participant type when adding manually
  - PDF now shows "TRUSTEES PRESENT" section (with Trustee titles) and "ALSO PRESENT" section (no title)
  
**Issue 2 Fixed - Compensation Trustee Selection:**
- **Problem:** When recording payments, users couldn't specify which trustee received the payment
- **Solution:**
  - Added "RECIPIENT TRUSTEE" dropdown in Record Payment modal
  - Dropdown populated with known trustees from trust context
  - Payments display trustee name badges in the payment list
  - Renamed "Trustee-Specific Plans" to "Per-Trustee Compensation Caps" for clarity

**Files Updated:**
- `/app/frontend/src/pages/GuidedMinutesPage.js` - Separate trustees/attendees UI
- `/app/frontend/src/pages/CompensationPage.js` - Added trustee selector
- `/app/backend/routers/guided_minutes.py` - Added other_attendees_text field
- `/app/backend/routers/minutes.py` - PDF shows "ALSO PRESENT" section
- `/app/backend/routers/compensation.py` - Store trustee_name with payments
- `/app/backend/models.py` - Updated Pydantic models

**Testing:** 100% pass rate (iteration_59) - 9 backend tests + all frontend features verified


### Previous Updates (Mar 2, 2026) - ENHANCED PDF FORMATTING FOR LEGAL DOCUMENTS ✅

**Session Summary:** Completely rewrote the PDF generation function to preserve formatting and create professional legal-style documents.

**Problem Fixed:**
- Previously, all paragraphs merged into one large block of text
- Line breaks and paragraph structure were lost
- WHEREAS/RESOLVED clauses not properly formatted
- Document didn't look like a professional legal document

**Solution Implemented:**
- Complete rewrite of `generate_minutes_pdf()` function in `/app/backend/routers/minutes.py`
- New `_parse_legal_document_text()` helper function that intelligently parses legal document content
- Uses Times font family for professional legal appearance
- Proper paragraph separation and spacing

**New PDF Features:**
1. **Document Header**: Decorative borders, centered trust name, subtitle
2. **Meeting Details Table**: Clean layout with bold labels
3. **TRUSTEES PRESENT Section**: Bullet-pointed list of participants
4. **Formatted Body Content**:
   - WHEREAS clauses: Bold keyword, proper indentation
   - RESOLVED clauses: Bold keyword, proper indentation
   - NOW THEREFORE: Bold lead-in
   - Bullet points: Indented with bullets
   - Nested bullets: Double-indented with circles
   - Section headers: Bold, navy color
   - Key-value pairs: Bold labels
5. **Certification Section**: Legal certification language
6. **Signature Blocks**: Multiple signature lines for trustees
7. **Footer**: Confidentiality notice, generation timestamp

**Files Updated:**
- `/app/backend/routers/minutes.py` - Completely rewrote PDF generation (lines 116-350)

**Testing:** PDF verified with 4-page output, proper section formatting, preserved line breaks and bullet points.


### Previous Updates (Mar 2, 2026) - 10 NEW MINUTES TEMPLATES ✅

**Session Summary:** Tested and fixed 10 new minutes templates to expand the template library for common governance tasks.

**New Templates Added:**
1. **Investment Policy Approval** - Adopt/amend/review investment policy with risk tolerance, asset allocation, restrictions
2. **Loan Authorization** - Authorize loans to/from trust with amount, interest rate, term, purpose, collateral
3. **Insurance Authorization** - Obtain/renew/modify insurance coverage for trust assets
4. **Annual Review Meeting** - Annual review with fiscal year summary, accomplishments, priorities, governance review
5. **Quarterly Review Meeting** - Quarterly financial review with balances, discussion items, action items
6. **Trustee Compensation Approval** - Approve trustee fee arrangements with amount, basis, duties
7. **Trustee Resignation/Removal** - Document trustee departure (resignation/removal/death/incapacity)
8. **Beneficiary Request Denial** - Document and justify denial of beneficiary requests
9. **HEMS Distribution** - Health/Education/Maintenance/Support distributions with standard compliance
10. **Loan to Beneficiary** - Intra-family loans with AFR interest, term, repayment terms

**Bug Fixed:**
- Added all 10 new template types to `MinutesTemplateType` enum in `/app/backend/models.py`
- Without this fix, POST /api/minutes-templates returned 422 validation errors for new templates

**Files Updated:**
- `/app/backend/models.py` - Added 10 new enum values to MinutesTemplateType
- `/app/backend/routers/minutes.py` - Content generator functions (already implemented)
- `/app/frontend/src/pages/MinutesTemplateFormPage.js` - Form state and fields (already implemented)
- `/app/frontend/src/pages/MinutesTemplatesPage.js` - Template cards (already implemented)

**Testing:** 100% pass rate - 12/12 backend tests + all frontend features verified (iteration_58)


### Latest Updates (Mar 2, 2026) - MINUTES ↔ MONEY INTEGRATION ✅

**Session Summary:** Built bi-directional integration between Guided Minutes and Compensation/Distributions/Benevolence modules for proper governance workflows.

**Feature Overview:**
Two governance flows implemented:
1. **Minutes → Money**: Create tracking records directly from approved minutes
2. **Money → Minutes**: Link existing money records to minutes or create new minutes retroactively

**Flow 1: Minutes → Money (Guided Minutes Step 3)**
- Toggle switches: "Create tracking records from this approved decision"
  - Compensation records
  - Distribution records
  - Benevolence records
- Compact form to add records: Amount, Recipient, Date, Description, Purpose
- On save: Creates minutes first, then linked records with `minutes_record_id`
- Step 4 shows summary of created records

**Flow 2: Money → Minutes (Money pages)**
- New "Minutes" column in Distributions table
- Dropdown menu on each unlinked record:
  - "Link to existing minutes" → Opens AttachMinutesDialog
  - "Document in minutes (retroactive)" → Navigates to Guided Minutes with prefill
- Same actions added to Compensation payments and Benevolence records
- Shows "Linked" indicator when minutes_record_id is set

**Backend New Endpoints:**
- `GET /api/guided-minutes/search` - Search minutes for attachment dialog
- `POST /api/guided-minutes/save-with-records` - Save minutes + create linked records
- `PATCH /api/distributions/{id}/attach-minutes` - Attach existing minutes to distribution
- `PATCH /api/compensation-payments/{id}/attach-minutes` - Attach existing minutes to compensation
- `PATCH /api/benevolence/{id}/attach-minutes` - Attach existing minutes to benevolence

**New Models:**
- `RecordFromMinutes` - Single money record to create from minutes
- `GuidedMinutesSaveWithRecordsRequest` - Save minutes with linked records
- `GuidedMinutesSaveWithRecordsResponse` - Response with created record counts
- `AttachMinutesRequest` - Attach existing minutes to money record
- `MinutesSearchResult` - Search result for minutes

**Files Created/Updated:**
- `/app/frontend/src/components/AttachMinutesDialog.js` (NEW)
- `/app/frontend/src/pages/GuidedMinutesPage.js` (Step 3 record toggles)
- `/app/frontend/src/pages/DistributionsPage.js` (Minutes column and dropdown)
- `/app/frontend/src/pages/CompensationPage.js` (Minutes actions)
- `/app/frontend/src/pages/BenevolencePage.js` (Minutes actions)
- `/app/backend/routers/guided_minutes.py` (search, save-with-records endpoints)
- `/app/backend/routers/distributions.py` (attach-minutes endpoint)
- `/app/backend/routers/compensation.py` (attach-minutes endpoint)
- `/app/backend/routers/benevolence.py` (attach-minutes endpoint)
- `/app/backend/models.py` (New integration models)

**Testing:** 100% pass rate - 14/14 backend tests + all frontend features verified (iteration_57)


### Previous Updates (Mar 2, 2026) - GUIDED MINUTES WIZARD ✅

**Session Summary:** Built a new AI-assisted "Guided Minutes" section with a 4-step wizard flow for creating meeting minutes.

**Feature Overview:**
- New navigation item under "Governance" with a gold "BETA" badge
- 4-step wizard that walks users through creating minutes like an interview
- AI generates formal WHEREAS/RESOLVED style minutes from simple bullet points
- Integrates with existing minutes_records collection

**Backend Implementation:**
- **New Router:** `/app/backend/routers/guided_minutes.py`
- **New Models:** `GuidedMinutesContext`, `GuidedMinutesDraftRequest`, `GuidedMinutesDraftResponse`, `GuidedMinutesSaveRequest`
- **Endpoints:**
  - `GET /api/guided-minutes/context` - Returns trust info (name, jurisdiction, trustees, beneficiary standard)
  - `POST /api/guided-minutes/draft` - Generates AI draft using Claude Sonnet
  - `POST /api/guided-minutes/save` - Saves as minutes_records entry

**Frontend Implementation:**
- **New Page:** `/app/frontend/src/pages/GuidedMinutesPage.js`
- **Route:** `/guided-minutes` (subscription-protected)
- **Sidebar:** "Guided Minutes" with gold "BETA" badge under Governance

**Wizard Steps:**
1. **Meeting Type & Date**: Select Annual/Quarterly/General, pick date, select participants from known trustees or add custom
2. **Topics & Decisions**: Enter bullet points for agenda items and key decisions (AI drafts formal language)
3. **Review Draft**: View/edit AI-generated WHEREAS/RESOLVED minutes with cautions displayed
4. **Save**: Confirmation screen with "View All Minutes" and "Create Another" buttons

**Key Features:**
- Auto-pulls trust context (trustees, jurisdiction, beneficiary standard)
- Simple bullet point input - AI handles formal language
- Editable draft with regenerate option
- Clear AI disclaimer and caution notices
- Mobile-responsive stepper design

**Files Created/Updated:**
- `/app/backend/routers/guided_minutes.py` (NEW)
- `/app/backend/models.py` (Added guided minutes models)
- `/app/backend/server.py` (Router registration)
- `/app/frontend/src/pages/GuidedMinutesPage.js` (NEW)
- `/app/frontend/src/App.js` (Route added)
- `/app/frontend/src/components/Sidebar.js` (Navigation updated)
- `/app/frontend/src/pages/MinutesPage.js` (Link to guided minutes)

**Testing:** 100% pass rate - 19/19 frontend features + 10/10 backend tests (iteration_56)


### Previous Updates (Mar 2, 2026) - PDF PREVIEW FIX ✅

**Session Summary:** Fixed PDF preview showing "PDF preview not supported in this browser" by creating a robust reusable PDFPreviewModal component.

**Problem Fixed:**
- Old implementation used `data:` URLs which are blocked by many browsers' security policies
- No proper fallback when browser cannot render PDF inline
- Mobile users had no clear way to view PDFs

**Solution Implemented:**
- Created new reusable `PDFPreviewModal` component at `/app/frontend/src/components/PDFPreviewModal.js`
- Uses Blob URLs instead of `data:` URLs for better browser compatibility
- 3-second timeout detection to identify when iframe fails to load
- Mobile device detection for immediate fallback
- Clear "Preview Unavailable" message with actionable buttons

**UI Structure:**
1. **Header**: Title + "Open in Tab" + "Download" + Close (X) buttons
2. **Content Area**: 
   - PDF iframe (when browser supports it)
   - OR Fallback: Document icon + "Preview Unavailable" message + "Open in New Tab" + "Download PDF" buttons

**Key Features:**
- Blob URL approach: Better browser support than `data:` URLs
- Timeout detection: 3-second timeout triggers fallback if iframe doesn't load
- Mobile detection: Shows fallback immediately on mobile devices
- Graceful cleanup: Revokes Blob URLs when modal closes

**Files Updated:**
- `/app/frontend/src/components/PDFPreviewModal.js` (NEW)
- `/app/frontend/src/pages/MinutesPage.js` (uses PDFPreviewModal)
- `/app/frontend/src/pages/TrustUnitsPage.js` (uses PDFPreviewModal)

**Environment Note:** The Emergent preview environment blocks Blob URLs in iframes due to CSP. The fallback correctly handles this. In production deployments without these restrictions, PDFs render inline.

**Testing:** 100% pass rate - 10/10 frontend features verified (iteration_55)



### Previous Updates (Mar 2, 2026) - STRUCTURES PAGE COMBINATION ✅

**Session Summary:** Combined 'Entities' and 'Hierarchy' pages into a single unified 'Structures' page with tabs.

**Problem Fixed:**
- Navigation had separate "Entities" and "Hierarchy" links (cluttered sidebar)
- Users had to switch between two pages to manage related data
- Inconsistent navigation patterns for trust structure management

**Solution Implemented:**
- Created new `StructuresPage.js` with two tabs: "Entities" and "Hierarchy"
- Tab state syncs with URL via `?tab=entities` or `?tab=hierarchy`
- Old routes `/entities` and `/structure` redirect to new unified page
- Sidebar updated with single "Structures" link
- Old files `EntitiesPage.js` and `StructurePage.js` deleted

**UI Structure:**
1. **Header**: "Structures" + subtitle "[Trust Name] • Entities & Relationships"
2. **Tabs**: "Entities" (default) | "Hierarchy"
3. **Entities Tab**: Grid of entity cards + "New Entity" button
4. **Hierarchy Tab**: Hierarchy Tree + Relationships table + "Add Relationship" button

**Key Routes:**
- `/structures` - Unified structures page (default: entities tab)
- `/structures?tab=entities` - Entities tab
- `/structures?tab=hierarchy` - Hierarchy tab
- `/entities/:entityId` - Entity detail page (unchanged)
- `/entities` - Redirects to `/structures?tab=entities`
- `/structure` - Redirects to `/structures?tab=hierarchy`

**Testing:** 100% pass rate - 12/12 frontend features verified (iteration_54)


### Previous Updates (Mar 2, 2026) - BENEVOLENCE PAGE SIMPLIFIED ✅

**Session Summary:** Simplified Benevolence section from confusing 2-tab system to single unified log with filters.

**Problem Fixed:**
- "Grants" tab pulled from `benevolence_records` collection
- "History" tab pulled from `distribution_records` where `is_benevolence=true`
- Users saw records in Grants but nothing in History (different data sources!)

**Solution Implemented:**
- Single unified "Benevolence Log" page (no tabs)
- Merges data from both endpoints (`/api/benevolence` + `/api/benevolence-log`)
- Deduplicates by amount+date+recipient name
- Filters replace tabs: Date range, Search recipient, Purpose/Category

**UI Structure:**
1. **Header**: "Benevolence Log" + "Record Grant" button
2. **Summary Strip**: This Month, This Year, All Time, Total Grants (4 cards)
3. **Filters Bar**: Search input, Date dropdown (6 options), Category dropdown
4. **Records List**: Each record shows recipient name, Documented/Pending badge, date, category, description, amount

**Date Filter Options:**
- All History (default)
- Last 30 Days
- This Month
- Last Month
- This Year
- Last Year

**Empty States:**
- No records exist → "No Benevolence Records Yet" + "Record First Grant" button
- No records match filters → "No Records Match Filters" + "Clear All Filters" button

**Filter Indicator:**
- Shows "Showing X of Y records • [filter descriptions]" when filters active
- "Clear" button appears to reset all filters

**Testing:** 100% pass rate - 12/12 frontend features verified (iteration_53)

### Previous Updates (Mar 2, 2026) - COMPENSATION MODULE REFACTORED ✅

**Session Summary:** Refactored Compensation module to use "one primary plan per trust per year" model with clearer UX.

**Problem Addressed:**
- Previous implementation allowed unlimited plans without clear hierarchy
- Confusing UX for normal use case (single trust-wide compensation envelope)
- YTD calculations didn't clearly indicate which plan they referenced

**New Data Model:**
- `compensation_plans` collection now has: `is_primary` (boolean), `year` (int)
- One primary plan per trust per year (auto-determined if not specified)
- Additional trustee-specific plans allowed when `trustee_name` is provided

**Backend Changes (`/app/backend/routers/compensation.py`):**
- `get_primary_plan_for_year(trust_id, user_id, year)` - finds primary plan with fallbacks
- `POST /compensation-plans` - auto-sets `is_primary` based on context, demotes existing primary if needed
- `PUT /compensation-plans/{plan_id}` - supports updating `is_primary`, `year`
- `GET /compensation-plans/primary` - NEW: returns primary plan for specified year
- `GET /compensation-ytd` - returns `year`, `ytd_total`, `annual_approved`, `exceeds_plan`, `remaining`, `percent_used`, `primary_plan` object

**Frontend Changes (`/app/frontend/src/pages/CompensationPage.js`):**
- **YTD Progress Card**: Shows year, total, envelope, remaining with progress bar, "Within Plan" / "Exceeds Plan" badge
- **Primary Plan Card**: Shows annual amount, effective date, edit button, helper text: "This is the total annual compensation envelope for this trust. Individual payments are tracked against this amount."
- **Advanced Section**: Collapsible "TRUSTEE-SPECIFIC PLANS (ADVANCED)" with badge showing count, helper text: "Optional: Set separate compensation caps for individual trustees or roles."
- **Payment Modal**: Warning when payment would exceed plan: "This payment will exceed the annual plan" with calculation breakdown
- **Plan Modal**: Different titles/descriptions for primary vs trustee-specific plans

**UX Improvements:**
- Default interaction is to edit the single primary plan
- "Add Trustee-Specific Plan" button only in Advanced section
- Trustee-specific plans require `trustee_name` field
- Clear separation between trust-wide envelope and individual caps

**Testing:** 100% pass rate - 14/14 backend tests, all UI elements verified (iteration_52)

### Previous Updates (Mar 2, 2026) - AI DRAFTING IMPROVEMENT ✅

**Session Summary:** Improved AI minutes drafting to enhance user's existing notes instead of ignoring them.

**Problem Fixed:**
- Previously, the AI ignored content written in the Details field
- Users expected AI to improve their draft, but it generated generic content instead

**Solution Implemented:**

1. **Frontend (`NewMinutesPage.js`):**
   - Now sends `formData.details` (user's draft) as `additional_context`
   - Labels it as "USER'S DRAFT TO IMPROVE AND EXPAND"
   - Button text changes dynamically:
     - "Draft with AI" when Details field is empty
     - "Improve with AI" when user has written content
   - Updated placeholder: "Write your notes here... AI will improve and formalize them"
   - Updated helper text explains the workflow clearly

2. **Backend (`ai_service.py`):**
   - Updated system prompt with explicit instructions to:
     - Keep the user's core content and decisions
     - Improve language to be more formal
     - Add WHEREAS/RESOLVED structure where appropriate
     - NOT replace user content with generic text
   - Generates context-aware cautions specific to user's content

**User Workflow Now:**
1. Write rough notes in Details field (e.g., "We met to review accounts. Discussed giving Emily money for college.")
2. Click "Improve with AI" button
3. AI transforms notes into formal minutes while preserving all key points
4. Review in modal, then click "Insert Draft" to populate form

**Testing:** Verified via curl and UI screenshots - AI now preserves and formalizes user content.

### Previous Updates (Mar 2, 2026) - UI/UX IMPROVEMENTS ✅

**Session Summary:** Fixed sidebar scrolling, combined Benevolence pages, updated Trust Units with 100-unit cap, redesigned PDF certificate, and improved demo data reset clarity.

**1. Sidebar Scrolling Fix:**
- Added `overflow-y-auto` to nav element in Sidebar.js (line 135)
- Users can now scroll to see all menu items when viewport is small

**2. Combined Benevolence Pages:**
- Merged "Benevolence" and "Benevolence Log" into single page with tabs
- Grants tab: Create/manage benevolence records
- History tab: View distribution log with summaries (This Month/Year/All Time)
- Removed "Benevolence Log" from sidebar navigation

**3. Trust Units 100-Unit Cap:**
- Default total authorized units set to 100 (was 1000)
- Demo data updated: Emily (25%), Michael (30%), James Jr (15%) = 70 units, 30 remaining
- UI displays "X units remaining" prominently
- Backend validation prevents exceeding 100% allocation

**4. Trust Units PDF Certificate (Landscape):**
- Redesigned as stock certificate style using canvas-based PDF generation
- Landscape orientation (11 x 8.5 inches)
- Decorative double border (Navy outer, Gold inner with corner ornaments)
- Beneficiary name centered and prominent
- 12-point gold star seal with "OFFICIAL SEAL" text
- Trust name watermark
- Signature lines for trustee

**5. Demo Data Reset Clarity:**
- Renamed "Delete All Data" to "Reset All Trust Data"
- Modal shows clear warning: "Warning: This action cannot be undone!"
- Explains all data types that will be deleted
- Notes that account and billing are preserved

**Files Updated:**
- `/app/frontend/src/components/Sidebar.js` - scrolling fix
- `/app/frontend/src/pages/BenevolencePage.js` - combined with tabs
- `/app/frontend/src/pages/TrustUnitsPage.js` - 100-unit default
- `/app/frontend/src/pages/SettingsPage.js` - Reset button text
- `/app/frontend/src/App.js` - removed BenevolenceLogPage route
- `/app/backend/routers/trust_units.py` - landscape PDF certificate
- `/app/backend/routers/demo.py` - updated demo unit values

**Testing:** 100% pass rate - 10/10 frontend tests verified (iteration_51)

### Previous Updates (Mar 2, 2026) - AI v1 INTEGRATION HARDENED FOR PRODUCTION ✅

**Session Summary:** Hardened AI integration for production with rate limiting, safe error handling, logging, UI guardrails, and fallback behavior.

**1. Robust Error Handling and Fallbacks:**
- Backend returns safe message: "AI assistant is currently unavailable. Please try again later."
- No internal details, stack traces, or API keys exposed in error responses
- Frontend Minutes page shows inline error near AI button (does not block manual drafting)
- Frontend Dashboard falls back to static governance_insights when AI fails

**2. Rate Limiting (Per User Per Hour):**
- Minutes drafting: Max 10 requests per hour
- Governance suggestions: Max 20 requests per hour
- 429 response with clear message when limit exceeded
- In-memory store with automatic cleanup of old entries

**3. Logging and Tracing:**
- Log format: `AI_CALL | user={user_id} | trust={trust_id} | endpoint={endpoint} | model={model} | input_chars={N}`
- Does NOT log raw AI response text (protects sensitive data)
- Logged for both minutes-draft and governance-suggestions endpoints

**4. UI Copy and Guardrails:**
- Minutes page disclaimer: "AI helps draft language; you remain responsible for accuracy and legal sufficiency."
- Dashboard disclaimer: "AI-generated suggestions. You decide which actions to take."
- Both use mono font as specified
- Draft with AI button disabled while request in progress

**5. Manual Testing Instructions (in code comments):**
- `ai.py` and `ai_service.py` contain testing instructions at the top

**Backend Files Updated:**
- `/app/backend/routers/ai.py` - Rate limiting, logging, error handling
- `/app/backend/ai_service.py` - Safe error messages, testing instructions

**Frontend Files Updated:**
- `/app/frontend/src/pages/NewMinutesPage.js` - Inline error state, disclaimer
- `/app/frontend/src/pages/DashboardPage.js` - Fallback to static insights, disclaimer

**Testing:** 100% pass rate - 12/12 pytest tests, all UI elements verified (iteration_50)

### Previous Updates (Mar 2, 2026) - DEMO DATA & FOREVER FREE ACCOUNT ✅

**Session Summary:** Enhanced demo data to showcase all features, added delete endpoint, and implemented forever free account for admin@wingpointtrusts.com.

**Demo Data Enhancements:**
- Comprehensive demo data now includes:
  - 2 Trusts with different configurations (benevolence enabled/disabled)
  - Multi-level entity hierarchy (Trust → Holding LLC → Operating LLCs)
  - Schedule A with **active AND disposed assets** (BMW X5 sold to CarMax)
  - Various minutes types: quarterly, annual, special, **disposition**, distribution, property acceptance
  - Distributions: approved and pending
  - Benevolence records: approved and pending
  - Compensation plans and payments
  - Trust unit certificates
  - Governance tasks: upcoming, overdue, completed

**New Demo Endpoints:**
- `GET /api/demo/status` - Returns data counts for user (trusts, minutes, assets, etc.)
- `POST /api/demo/seed` - Seeds comprehensive demo data (if no existing data)
- `DELETE /api/demo/data` - Deletes all user data (preserves account & subscription)

**Settings Page - Demo Data Management:**
- New section with data summary cards (Trusts, Minutes, Assets, Total Records)
- "Load Demo Data" button (disabled if user has data)
- "Delete All Data" button with confirmation dialog
- Refresh button to reload status

**Forever Free Account:**
- Email: `admin@wingpointtrusts.com`
- Automatically gets `forever_free` plan type with:
  - `status: active`, `is_read_only: false`
  - Access to ALL 8 premium features (PDF, CSV, multiple trusts, benevolence, beneficiary dashboard, trust units, governance history, advanced templates)
  - No trial expiration, no payment required ever
- Implemented via `FOREVER_FREE_EMAILS` set in `dependencies.py`

**Testing:** All 12 backend tests + all UI flows passed.

### Previous Updates (Mar 2, 2026) - DISPOSITION/SALE OF ASSET FLOW ✅

**Session Summary:** Implemented complete Disposition/Sale of Asset flow connecting Schedule A with Minutes.

**Backend Changes:**
- Added `POST /api/schedule-a/{item_id}/dispose` endpoint for direct disposition without minutes
- Validates already-disposed assets (400 error), non-existent assets (404)
- Supports all disposition types: sale, transfer, donation, destruction
- Status filtering: active (default), all (includes disposed)

**Schedule A UI Enhancements:**
1. **Status Badges:** Active (green) / Disposed (orange) for each asset
2. **Active/All Tabs:** Filter between active and all assets
3. **Summary Cards:** Now show "Active Assets" count and "Disposed" count
4. **Dispose Button:** Opens modal with:
   - Asset info display (description, category, value)
   - Disposition type dropdown (Sale/Transfer/Donation/Destruction)
   - Date, Value, Recipient, Notes fields
   - "Create minutes for this disposition" checkbox
5. **Disposition Minutes Link:** Click-through from Schedule A to disposition minutes

**Disposition Flow Paths:**
1. **Direct Dispose:** Uncheck "Create minutes" → "Mark as Disposed" → Immediate update
2. **With Minutes:** Keep checkbox checked → "Continue to Minutes" → Navigate to disposition template with pre-filled data via URL params

**Minutes Template Updates:**
- Added `disposition_of_asset` to TEMPLATE_TITLES
- URL params pre-fill: asset_id, description, date, reason, value, recipient, notes
- Existing disposition template generates WHEREAS/RESOLVED language

**Testing:** All 19 backend tests + all UI flows passed. Verified both dispose paths work correctly.

### Previous Updates (Mar 2, 2026) - SERVER.PY CLEANUP COMPLETE ✅

**Session Summary:** Completed final server.py modularization by migrating remaining endpoints.

**Migration Results:**
- `server.py` reduced from ~7600 lines → 305 lines (**96% reduction**)
- Created 19 modular router files in `/backend/routers/`
- Total router code: ~7576 lines (properly organized by domain)

**Newly Migrated Routers:**
1. **email.py** - Email status, test email, task reminders
2. **background_jobs.py** - Scheduler status, manual job triggers
3. **categories.py** - Enum values for forms (no auth required)
4. **beneficiaries.py** - Beneficiary dashboard (premium feature)
5. **demo.py** - Demo data seeding for new users

**Final Router Count: 19 routers**
```
auth.py, trusts.py, entities.py, tasks.py, trust_units.py,
minutes.py, schedule_a.py, distributions.py, benevolence.py,
compensation.py, governance.py, subscriptions.py, exports.py,
preferences.py, email.py, background_jobs.py, categories.py,
beneficiaries.py, demo.py
```

**server.py Now Contains Only:**
- FastAPI app configuration
- CORS middleware
- Subscription middleware (read-only enforcement)
- Router registration (19 routers)
- Database index creation
- Background task lifecycle

**Testing:** All 17 backend tests passed - verified all migrated endpoints working correctly.

### Previous Updates (Mar 2, 2026) - GA4 EVENTS & UPGRADE PROMPTS ✅

**Session Summary:** Implemented GA4 subscription funnel tracking and enhanced user prompts for trial/expired accounts.

**New GA4 Event Functions (in `/frontend/src/utils/analytics.js`):**
- `trackFeatureBlocked()` - When read-only user tries a blocked action
- `trackTrialBannerViewed()` - When trial banner displays (with days_remaining, location)
- `trackTrialBannerClicked()` - When user clicks Upgrade from banner
- `trackUpgradeModalShown()` - When upgrade modal appears
- `trackUpgradeModalClicked()` - When user clicks Subscribe from modal

**New Components:**
1. **TrialBanner** (`/frontend/src/components/TrialBanner.js`)
   - Shows "X days left in your trial" countdown
   - Color-coded urgency: Red (≤3 days), Amber (4-7 days), Blue (>7 days)
   - "Upgrade Now" button links to /settings?tab=subscription
   - Tracks GA4 events: trial_banner_viewed, trial_banner_clicked

2. **UpgradeModal** (`/frontend/src/components/UpgradeModal.js`)
   - Subscription Required dialog for read-only users
   - Shows feature list and pricing ($79/mo, $790/yr)
   - Triggered when blocked actions attempted

3. **UpgradeModalContext** (`/frontend/src/context/UpgradeModalContext.js`)
   - Global context provider for upgrade modal
   - `useUpgradeModal()` hook for triggering modal from any component
   - Automatically tracks GA4 feature_blocked events

**Page Updates:**
- DashboardPage, DistributionsPage, MinutesPage now include TrialBanner and ReadOnlyBanner
- Add Distribution button shows upgrade modal for read-only users
- Record Minutes button shows upgrade modal for read-only users

**Testing:** All 15 frontend tests passed verifying:
- TrialBanner displays correctly with days remaining
- GA4 events fire with correct parameters
- ReadOnlyBanner hidden for active trial users
- UpgradeModal not triggered for active trial users

### Previous Updates (Dec 30, 2025) - SUBSCRIPTION STATE VERIFICATION ✅

**Session Summary:** Verified and refined subscription/trial handling for consistent state across modules:

**Subscription State System (Already Implemented, Verified Working):**

1. **get_subscription_state(user_id)** - Normalized state object returns:
   - `plan_type`, `status`, `trial_start_date`, `trial_end_date`
   - `trial_days_remaining`
   - Booleans: `is_trial`, `is_active`, `is_read_only`
   - Stripe fields: `stripe_customer_id`, `stripe_subscription_id`, `current_period_end`, `cancel_at_period_end`

2. **Dashboard Integration:**
   - Fixed: Added `subscription` field to `DashboardResponse` model
   - GET /api/dashboard now returns `DashboardSubscriptionState` with key fields

3. **Read-Only Mode Enforcement:**
   - `require_write_access` dependency applied to ALL write endpoints
   - Returns consistent 403 error: "Your subscription is inactive. Please subscribe to create, update, or delete data."
   - Users can still view all data (minutes, distributions, compensation, entities, Schedule A, trust units, tasks, trusts)

4. **Verified require_write_access Applied To:**
   - minutes: POST, DELETE, templates
   - distributions: POST, PATCH, approve/unapprove, status, DELETE
   - compensation: POST plans/payments, DELETE
   - entities: POST, PATCH, DELETE + relationships
   - schedule_a: POST, PUT, DELETE
   - tasks: POST, complete, uncomplete, DELETE
   - trusts: POST, PUT, DELETE
   - trust_units: POST/PUT settings, certificates, transfers

**Testing:** All 33 tests passed verifying subscription state endpoints and write protection.

### Previous Updates (Dec 30, 2025) - MAJOR SERVER.PY CLEANUP ✅

1. **ReadOnlyBanner Component** (`/frontend/src/components/ReadOnlyBanner.js`)
   - Amber/warning color scheme banner at top of pages
   - Shows "Your trial has expired" or "Subscription inactive" message
   - "Subscribe Now" button links to `/settings?tab=subscription`
   - Only appears when `isReadOnly` is true

2. **SubscriptionGate Updated** (`/frontend/src/components/SubscriptionGate.js`)
   - No longer shows paywall - instead shows content with ReadOnlyBanner
   - Users can VIEW all data in read-only mode
   - Write operations blocked by backend (403 response)

3. **AuthContext Updates** (`/frontend/src/context/AuthContext.js`)
   - New `isReadOnly` state from `/api/subscription/state`
   - `loadSubscriptionState()` function fetches normalized state
   - Event listeners for `subscription-expired` and `subscription-readonly`

4. **LoginPage Updated** (`/frontend/src/pages/LoginPage.js`)
   - Now calls `loadSubscriptionState()` after login
   - Ensures read-only state is set before navigating to dashboard

5. **API Utility Updated** (`/frontend/src/utils/api.js`)
   - Dispatches `subscription-readonly` event on 403 with X-Subscription-Status header
   - Doesn't consume response body (fixes JSON parse error)

6. **Custom Hook** (`/frontend/src/hooks/useReadOnlyAwareSubmit.js`)
   - `useReadOnlyAwareSubmit` - Form submission with read-only awareness
   - `useReadOnlyCheck` - Simple hook to check read-only status
   - Shows toast with "Subscribe" action on blocked operations

### Previous Updates (Mar 2, 2026) - SUBSCRIPTION STATE MANAGEMENT ✅

1. **Unified Subscription State Helper**
   - New `get_subscription_state(user_id)` function returns normalized `SubscriptionState` object
   - Returns: plan_type, status, trial_start_date, trial_end_date, trial_days_remaining
   - Computed booleans: is_trial, is_active, is_read_only
   - Single source of truth for subscription status across all modules

2. **New Endpoint: GET /api/subscription/state**
   - Returns complete SubscriptionState with all computed fields
   - Frontend can use this for consistent subscription UI

3. **Dashboard Integration**
   - GET /api/dashboard now includes `subscription` field with:
     - plan_type, status, is_trial, is_active, is_read_only, trial_days_remaining
   - Frontend can show subscription status in dashboard

4. **Read-Only Mode for Expired Subscriptions**
   - SubscriptionMiddleware updated to allow read-only access:
     - **GET requests**: Always allowed (users can view all their data)
     - **POST/PUT/PATCH/DELETE**: Return 403 with clear error message
   - Error response includes: detail, subscription_status, is_read_only, trial_days_remaining
   - Write operations blocked consistently across: minutes, distributions, compensation, tasks, entities, Schedule A, trust units

5. **Code Architecture**
   - `dependencies.py`: SubscriptionState model, get_subscription_state(), require_write_access()
   - `models.py`: SubscriptionState, DashboardSubscriptionState models
   - `server.py`: SubscriptionMiddleware with read-only mode logic

### Previous Updates (Mar 2, 2026) - BENEVOLENCE MODE FOR DISTRIBUTIONS ✅

1. **Data Model Extensions**
   - Added `is_benevolence` boolean field on distribution_records (default false)
   - Added optional benevolence fields:
     - `benevolence_recipient_name` (required when is_benevolence=true)
     - `benevolence_need_description` (required when is_benevolence=true)
     - `benevolence_notes` (optional)

2. **API Endpoints**
   - `POST /api/distributions` - validates benevolence fields when is_benevolence=true
   - `PATCH /api/distributions/{id}` - new endpoint for updating distributions including benevolence fields
   - `GET /api/benevolence-log` - returns:
     - All distributions where is_benevolence=true
     - Monthly aggregates (YYYY-MM format, amount, count)
     - Yearly aggregates (year, amount, count)
     - Total all-time amount and count
     - Incomplete documentation count

3. **Governance Health Integration**
   - Distribution Documentation criterion now considers benevolence quality
   - **Full points (20)**: All distributions logged AND all benevolence distributions have:
     - recipient_name and need_description
     - approval (approved_at) or minutes reference
   - **Partial points (10-19)**: Some benevolence distributions missing documentation
   - Criterion description shows: "X/Y benevolence distributions need documentation"

### Previous Updates (Mar 2, 2026) - P2 FEATURES COMPLETE ✅

1. **Dashboard Trust Selection Parameter**
   - `GET /api/dashboard` now accepts optional `trust_id` query param
   - Validates trust ownership - returns 404 if trust doesn't exist or belongs to another user
   - Defaults to most recently created trust if not specified

2. **Beneficiary Dashboard** (`/trust/beneficiaries`)
   - New endpoint: `GET /api/beneficiaries/dashboard`
   - Returns: trust_name, total_authorized_units, total_issued_units, remaining_units, beneficiaries array, recent_transfers
   - Beneficiaries aggregated by holder with total units, percentage, certificate count
   - Sorted by total_units descending
   
3. **Beneficiary Dashboard Frontend**
   - Summary cards: Total Authorized, Issued, Remaining, Beneficiaries count
   - **Ownership Distribution pie chart** with color-coded legend
   - **Certificate Holders list** - expandable rows showing certificate details
   - **Recent Transfers section** with transfer history
   - Navigation link in sidebar under "Structures" group
   - "Manage Units" button links to `/trust/units`

### Previous Updates (Mar 2, 2026) - LOGIN FLOW FIX ✅

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

### P0 (Technical Debt) - COMPLETE (Mar 2, 2026)
- [x] Backend modular structure - Created database.py, models.py, dependencies.py
- [x] Created routers/ directory with domain-specific router modules
- [x] Completed routers: auth.py, trusts.py, entities.py, tasks.py, units.py
- [x] Frontend read-only mode integration with ReadOnlyBanner
- [x] Unified subscription state management (get_subscription_state helper)
- [x] **Distributions router migrated** - 405 lines removed from server.py, now in routers/distributions.py (433 lines)
- [x] Migration guide created at /app/backend/MIGRATION_GUIDE.md

### P1 (High Priority) - COMPLETE (Mar 2, 2026)
- [x] Migrate distributions router (with require_write_access for subscription gating) - 433 lines
- [x] Migrate governance router (health score, dashboard, onboarding, activity) - 598 lines
- [x] Migrate minutes router (basic CRUD, PDF, templates with 11 types) - 1243 lines
- [x] Removed ~2000 lines total from server.py

**Server.py Reduction:** 7618 → 5611 lines (~26% reduction)

### P2 (Medium Priority) - IN PROGRESS
- [x] Implement hard feature gating for premium-only features
  - Created `Feature` class with core (trial) and premium (paid) features
  - `PLAN_FEATURES` dict maps plans to available features
  - `require_premium_feature()` dependency returns 402 for blocked features
  - CSV export endpoints gated: /api/export/minutes, distributions, compensation, tasks
  - New endpoint: GET /api/subscription/features returns feature flags
- [ ] Migrate remaining routers (schedule_a, compensation, subscriptions)
- [ ] Add Audit Log (backend + UI)
- [x] Profile editing (name change) - Edit button in Settings > Profile section
- [x] Search in minutes/distributions - Server-side search with debounced queries
- [x] Table horizontal scroll for mobile - overflow-x-auto on table containers
- [x] Benevolence Mode - Full feature for charitable trusts (toggle, log, template)
- [x] Notification preferences - Toggle switches in Settings page for email notification control
- [x] Benevolence Report PDF Export - Styled PDF similar to Schedule A
- [x] Auto-populate Minutes Form with Entity data (trust_indenture_date, trustees_present, article refs)

### P2 (Medium-term)
- [x] Fix Compensation API schema mismatch (Feb 25, 2026)
- [x] Trust Certificate Units UI (Mar 2, 2026)
- [x] Beneficiary Dashboard for unit allocations (Mar 2, 2026)
- [ ] Audit Log (backend + UI)
- [ ] Receipt/invoice download
- [ ] Feedback process

### P3 (Future)
- [ ] Multi-trustee collaboration
- [x] AI-assisted minutes drafting ✅ (Mar 2, 2026) - Claude Sonnet generates WHEREAS/RESOLVED format
- [ ] Mobile app
- [ ] Date range filters for Minutes page
- [ ] More entity types (LLCs)
- [ ] Email retry queue for Postmark failures
- [ ] User-facing feedback submission system
- [x] Expand library of available minutes templates ✅ (Mar 2, 2026) - 10 new templates added (total: 20 templates)

## Notes
- Postmark: Sandbox mode (verified domain only)
- Stripe: LIVE MODE configured
- 14-day trial handled locally (no Stripe trial needed)
- Password reset tokens expire in 1 hour
