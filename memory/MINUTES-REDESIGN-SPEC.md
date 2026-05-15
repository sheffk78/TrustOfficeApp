# Minutes Redesign — Implementation Spec

**Date:** May 15, 2026  
**Status:** Approved  
**Scope:** Consolidate 7 minutes pages → 3, unify data model, add multi-section minutes + retroactive safeguards + autosave

---

## 1. Architecture Overview

### Before (7 pages, 2 collections, 2 AI endpoints)
```
MinutesPage (list) → MinutesTemplatesPage → MinutesTemplateFormPage (→ minutes_templates)
MinutesPage (list) → NewMinutesPage (→ minutes_records)
MinutesPage (list) → GuidedMinutesPage (→ minutes_records, source="guided_wizard")
MinutesDetailPage
RetroactiveMinutesPage (hidden, no review)
AI: /ai/minutes-draft + /guided-minutes/draft
```

### After (3 pages, 1 collection, 1 AI endpoint)
```
MinutesPage (list) → NEW: /minutes/new (unified 3-step wizard) → MinutesDetailPage
MinutesNewPage replaces: NewMinutesPage, GuidedMinutesPage, MinutesTemplatesPage, MinutesTemplateFormPage, RetroactiveMinutesPage
AI: /api/minutes/draft (unified)
Data: minutes_records (unified, with template_type field)
```

---

## 2. Data Model Changes

### Unified `minutes_records` Schema

```python
# New fields added to existing minutes_records
{
    "minutes_id": "minutes_xxx",           # existing
    "trust_id": "...",                      # existing
    "user_id": "...",                       # existing
    "minutes_type": "annual",              # existing MinutesType (kept for backward compat)
    "template_type": "annual_review",      # NEW: MinutesTemplateType value
    "meeting_date": "2026-05-15",          # existing
    "participants_text": "...",             # existing
    "other_attendees_text": "...",          # existing
    "decisions_text": "...",                # existing — full minutes body
    "sections": [],                         # NEW: list of section objects for multi-section minutes
    "template_data": {},                    # NEW: structured form fields (from template forms)
    "source": "ai_generated|template|manual", # existing, expanded
    "status": "draft|finalized",            # NEW: draft state for autosave
    "is_retroactive": false,                # NEW
    "retroactive_reason": null,             # NEW: why wasn't this recorded?
    "retroactive_trustees_aware": null,     # NEW: Y/N
    "retroactive_type": null,              # NEW: ratification|documentation
    "manually_edited": false,              # NEW: flag if user edited AI-generated text
    "created_at": "...",                    # existing
    "updated_at": "...",                    # existing
}
```

### Section Object (for multi-section minutes)
```python
{
    "section_id": "sec_xxx",
    "template_type": "distribution_to_beneficiaries",
    "title": "Distribution to Beneficiaries",
    "template_data": { ... },  # section-specific fields
    "generated_text": "...",    # AI or template-generated text for this section
}
```

### Model Changes in models.py

**Keep:**
- `MinutesType` enum (backward compat, maps to `minutes_type` field)
- `MinutesTemplateType` enum (NOW used in `minutes_records` too)
- `MinutesCreate`, `MinutesResponse` (expanded)
- `GuidedMinutesContext` (keep as-is for trust context loading)
- `RecordFromMinutes` (keep for money↔minutes linking)

**New/Modified:**
- Expand `MinutesCreate` to include `template_type`, `sections`, `template_data`, `status`, retroactive fields
- Expand `MinutesResponse` to include all new fields
- New `MinutesDraftCreate` model — unified AI draft request (merges GuidedMinutesDraftRequest + /ai/minutes-draft)
- New `MinutesSection` model for section objects
- Kill `GuidedMinutesType` (unified into MinutesTemplateType)
- Keep `GuidedMinutesDraftRequest` temporarily for backward compat but mark deprecated

---

## 3. Backend Endpoint Changes

### New Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/minutes/draft` | **Unified AI draft** — accepts template_type + bullet points OR structured fields, returns generated minutes text |
| POST | `/minutes/autosave` | Save/update a draft minutes record (status=draft) |
| GET | `/minutes/drafts` | List draft minutes for current trust |

### Modified Endpoints

| Method | Path | Change |
|--------|------|-------|
| POST | `/minutes` | Accept expanded fields (template_type, sections, template_data, status, retroactive fields) |
| GET | `/minutes` | Include `status` filter, return template_type + sections |
| GET | `/minutes/{id}` | Return all new fields |
| PUT | `/minutes/{id}` | Allow updating sections, template_data, retroactive fields |
| GET | `/template-options` | Add `fields` array per template — defines what form fields each template needs |

### Deprecated (kept with redirect logic, 6 months)

| Method | Path | Replacement |
|--------|------|-------------|
| POST | `/ai/minutes-draft` | `/minutes/draft` |
| POST | `/guided-minutes/draft` | `/minutes/draft` |
| POST | `/guided-minutes/save` | `/minutes` with expanded fields |
| POST | `/guided-minutes/save-with-records` | `/minutes` + separate record creation |
| GET | `/guided-minutes/context` | `/minutes/context` (new, simpler) |
| POST | `/minutes-templates` | `/minutes` with template_type |
| GET | `/minutes-templates` | `/minutes` with filter |
| GET | `/minutes-templates/{id}` | `/minutes/{id}` |
| PUT | `/minutes-templates/{id}` | `/minutes/{id}` |

### Template Registry Enhancement

The `/template-options` endpoint returns `fields` array per template. This drives the dynamic form in Step 2.

```json
{
  "type": "distribution_to_beneficiaries",
  "name": "Distribution to Beneficiaries",
  "description": "Document a distribution of trust proceeds to beneficiaries",
  "icon": "dollar-sign",
  "category": "distributions",
  "fields": [
    {"name": "distribution_total", "label": "Total Amount", "type": "currency", "required": true},
    {"name": "distribution_recipient", "label": "Recipient", "type": "text", "required": true},
    {"name": "distribution_date", "label": "Distribution Date", "type": "date", "required": true},
    {"name": "distribution_characterization", "label": "Characterization", "type": "select", "options": ["income", "principal", "both"], "required": true},
    {"name": "distribution_purpose", "label": "Purpose/Notes", "type": "textarea", "required": false}
  ]
}
```

---

## 4. Frontend Changes

### New Page: MinutesNewPage (`/minutes/new`)

**3-step wizard with multi-section support.**

#### Step 1: What kind of minutes?

**Two paths:**

**A) Quick Minutes (AI-Assisted)**
- Card: "Annual Review" — Year-end financial and governance review
- Card: "Quarterly Review" — Routine quarterly trustee meeting
- Card: "General Meeting" — For any other meeting

These 3 start with bullet-point entry (Step 2 has "Draft with AI" as primary action).

**B) Specific Action (Template-Driven)**
Category groups, collapsible:
- **Trustee Changes** — Appoint Trustee, Successor Trustee, Resignation
- **Property & Assets** — Purchase Real Estate, Accept Property, Dispose Asset, Business Interest, Lease
- **Financial** — Bank Account, Investment Policy, Loan, Insurance
- **Distributions** — Distribution to Beneficiaries, HEMS, Beneficiary Loan
- **Legal & Governance** — Trust Amendment, Conflict of Interest, Emergency Ratification, Power of Attorney
- **Admin** — Change of Situs, Fiscal Year Election, Tax Filing
- **Beneficiaries** — Designation, Request Denial  
- **Benevolence** — Approval (conditional on trust.benevolence_enabled)

**First Meeting** card appears at TOP with "Start Here" badge, but ONLY if the trust has zero minutes records.

**After picking a type**, user can click "Add Another Section" to add a second template section to the same minutes document. This solves the "one meeting, multiple actions" problem.

#### Step 2: Fill in the details

**Common fields (always shown):**
- Meeting date (date picker)
- Trustees present (checkboxes from trust data, editable)
- Other attendees (comma-separated text)
- Meeting location (text input, NOT auto-populated — too often wrong)

**Template-specific fields:**
- Rendered dynamically from `template.fields` array returned by `/template-options`
- Each template type defines its own fields, types, required/optional
- For "Quick Minutes" types: no template-specific fields, just bullet-point areas

**AI Drafting area (for Quick Minutes):**
- "Agenda Items" — bullet list input
- "Key Decisions" — bullet list input
- "Additional Notes" — freeform textarea
- **"Draft with AI" button** — calls `POST /minutes/draft`
  - Behavior: **replaces** any existing generated text (explicit, not append)
  - Undo button visible after draft (reverts to previous version)
  - Loading skeleton during generation
  - Disclaimer: "AI-generated — review carefully before saving"

**For template-driven types:**
- Template fields rendered as form inputs
- "Preview Section" button generates the WHEREAS/RESOLVED text from form fields
- Text is editable but edits flagged with `manually_edited: true`
- If user modifies generated text, show: "You've edited the generated text. Changes to form fields won't automatically update your edits."

**Multi-section:**
- Each section is a collapsible card with its own template fields
- "Add Section" button opens the template picker (Step 1 categories) in a dropdown
- Sections render in document order, each contributing its generated text to the full minutes

**Retroactive mode:**
- Toggle at top of Step 2: "These minutes are for a past event"
- When ON, shows 3 required fields:
  1. "Why weren't these minutes recorded at the time?" (textarea, required)
  2. "Were all acting trustees aware of this action?" (Y/N, required)
  3. "Is this a ratification of prior action, or documentation of an unrecorded meeting?" (select, required)
- Meeting date field allows past dates
- Yellow "Retroactive" banner displayed on form and in saved record
- Creation date and meeting date shown distinctly in saved record

**Autosave:**
- Every 30 seconds, if form has changed, call `POST /minutes/autosave`
- Autosave saves with `status: "draft"` — doesn't appear in main list
- Drafts section on MinutesPage shows resumable drafts
- First autosave creates the record; subsequent ones update it
- `minutes_id` stored in component state after first autosave

#### Step 3: Review & Save

**Structured review (not just document preview):**
- Checklist of key items: ✅ 2 trustees present, ✅ Meeting date: May 15, ✅ Distribution: $10,000 to Jane Doe
- Full rendered minutes text (editable, but with "edit the form fields instead" nudge)
- If any sections have AI-generated text, show: "⚠️ AI-generated content — review carefully"
- If retroactive, show amber banner: "Retroactive minutes — created [today] for meeting on [date]"

**Save button:**
- Changes `status` from "draft" to "finalized"
- If linked records exist (compensation/distribution), creates them
- On success: redirect to `/minutes` with success toast

**"Save as Draft" button:**
- Keeps `status: "draft"`, returns to MinutesPage (draft section)

---

### Modified Pages

**MinutesPage (`/minutes`)**  
- Add "Drafts" section at top (collapsed, shows count) — only if user has draft records
- Add `template_type` to each record's display (badge/label)
- Filter enhancements: template_type filter, status filter (draft/finalized)
- Single "New Minutes" button → `/minutes/new`
- Remove "Guided Minutes" button

**MinutesDetailPage (`/minutes/:id`)**  
- Show `template_type` badge
- Show retroactive banner if `is_retroactive`
- Show creation date + meeting date distinctly for retroactive
- Show sections as collapsible cards
- Show "AI Generated" badge if `source === "ai_generated"`
- Show "Draft" badge if `status === "draft"`

---

## 5. Frontend Route Changes

### Routes to Add/Modify

```javascript
// Modified
<Route path="/minutes/new" element={<MinutesNewPage />} />  // New unified wizard

// Remove (after migration period)
<Route path="/minutes/templates" />     // → redirect to /minutes/new
<Route path="/minutes/template/:templateType" />  // → redirect to /minutes/new?type=X
<Route path="/guided-minutes" />       // → redirect to /minutes/new
<Route path="/retroactive-minutes" />   // → redirect to /minutes/new?retroactive=1
```

### Component Architecture (avoid the 3051-line monster)

```
MinutesNewPage/
├── Step1TemplatePicker.js       // Template selection grid
├── Step2FormBuilder.js           // Dynamic form from template fields
├── SectionCard.js                // Individual section card (reusable)
├── QuickMinutesForm.js           // Bullet-point + AI input for simple types
├── TemplateFieldsForm.js         // Dynamic fields from template definition
├── RetroactiveSubform.js         // Retroactive questions
├── Step3ReviewAndSave.js         // Structured review + save
├── AiDraftPanel.js              // AI draft generation + undo
├── useMinutesAutosave.js        // Autosave hook
└── useMinutesDraft.js           // Draft state management hook
```

---

## 6. Migration Plan

### Phase 1: Deploy new backend + frontend (non-breaking)
- Add new fields to `minutes_records` (MongoDB schemaless — just start writing them)
- New endpoints added alongside old ones
- New MinutesNewPage deployed alongside old routes
- Old routes get redirect banners ("This page has moved → /minutes/new")

### Phase 2: Data Migration Script
```python
# migrate_template_records.py
# For each record in minutes_templates:
#   1. Read the record
#   2. Map fields: template_type → template_type, template_data → template_data, 
#      generated_doc → decisions_text, add source="template"
#   3. Insert into minutes_records with new schema
#   4. Log the old → new ID mapping
#   5. Mark old record as migrated (add flag, don't delete)
# Batch size: 100, resumable from last processed ID
# Verifiable: count(minutes_templates) == count(migrated)
```

### Phase 3: Cutover
- Remove old routes from App.js
- Add React Router redirects for old URLs
- Remove old page imports (keep files for 30 days, then archive)

---

## 7. AI Endpoint Merger

### New `/minutes/draft` — Unified

```python
class MinutesDraftRequest(BaseModel):
    """Unified AI minutes draft request"""
    trust_id: str
    template_type: Optional[str] = None  # MinutesTemplateType value
    minutes_type: Optional[str] = None   # MinutesType for backward compat
    meeting_date: str
    participants: List[str] = []
    other_attendees: List[str] = []
    
    # Quick minutes mode (bullets)
    agenda_items: List[str] = []
    key_decisions: List[str] = []
    additional_context: Optional[str] = None
    
    # Template mode (structured fields)
    template_data: Optional[dict] = None
    
    # Retroactive
    is_retroactive: bool = False
    retroactive_reason: Optional[str] = None
    
    # Section mode (for multi-section)
    section_context: Optional[str] = None  # "This is section 2 of 3 in the meeting minutes"
```

The AI prompt construction logic:
1. If `template_type` provided → use template-specific prompt template (from `generate_template_document`)
2. If `agenda_items`/`key_decisions` provided → use bullet-to-formal prompt (from guided minutes)
3. If both → combine: template structure + bullet context
4. Always include trust context (jurisdiction, trustee names, trust name)

---

## 8. Category/Template Mapping (29 templates → 8 display categories)

| Display Category | Template Types |
|---|---|
| **First Meeting** | initial_trustee_meeting (shown only if trust has 0 minutes) |
| **Quick Minutes** | annual_review, quarterly_review, general_meeting |
| **Trustee Changes** | appointment_additional_trustee, appointment_successor_trustee, trustee_resignation, trustee_compensation |
| **Property & Assets** | real_estate_purchase, acceptance_of_property, disposition_of_asset, business_interest_acquisition, real_estate_lease |
| **Financial** | bank_account_authorization, investment_policy, loan_authorization, insurance_authorization |
| **Distributions** | distribution_to_beneficiaries, hems_distribution, beneficiary_loan |
| **Legal & Governance** | trust_amendment, conflict_of_interest, emergency_ratification, power_of_attorney, trust_termination, change_of_situs |
| **Admin** | fiscal_year_election, tax_filing_authorization, designation_of_beneficiaries, beneficiary_request_denial |
| **Benevolence** | benevolence_approval (conditional) |

Note: `blank` template removed — "General Meeting" serves the same purpose. Users who need truly blank can just type in the free-form area.

---

## 9. Key Guards (from Review Feedback)

1. **AI overwrite is EXPLICIT** — "Draft with AI" replaces generated text. Undo button available. No silent overwrites.
2. **AI disclaimer is VISIBLE** — "AI-generated — review carefully before saving" shown in Step 2 and Step 3.
3. **Retroactive has 3 REQUIRED fields** — not just a toggle. Creation vs. meeting date stored distinctly.
4. **Autosave every 30s** — draft records don't clog main list.
5. **Structured review** — Step 3 shows checklist summary, not just wall of text.
6. **Source of truth is FORM FIELDS** — structured data drives linked records. If user edits generated text, `manually_edited: true` flag set, and edits to form fields prompt "This will regenerate the minutes text. Continue?"
7. **Old routes get redirects** — not 404s.
8. **Template field definitions from backend** — not hardcoded in 3051-line React component.
9. **Multi-section** — one meeting = one document, multiple action sections.
10. **`blank` template removed** — "General Meeting" + free-form is the same thing.

---

## 10. Files Changed

### Backend
- `models.py` — Add new models, expand MinutesCreate/MinutesResponse, add MinutesDraftRequest
- `routers/minutes.py` — Add /minutes/draft, /minutes/autosave, /minutes/drafts, /minutes/context; expand template-options with fields; expand CRUD endpoints
- `routers/guided_minutes.py` — Mark endpoints deprecated, redirect to new endpoints
- `routers/ai.py` — Mark /ai/minutes-draft deprecated
- `template_registry.py` (NEW) — Template field definitions, category mappings, prompt templates

### Frontend
- `pages/MinutesNewPage.js` (NEW) — Unified 3-step wizard
- `pages/MinutesNewPage/Step1TemplatePicker.js` (NEW)
- `pages/MinutesNewPage/Step2FormBuilder.js` (NEW)
- `pages/MinutesNewPage/Step2FormBuilder/QuickMinutesForm.js` (NEW)
- `pages/MinutesNewPage/Step2FormBuilder/TemplateFieldsForm.js` (NEW)
- `pages/MinutesNewPage/Step2FormBuilder/SectionCard.js` (NEW)
- `pages/MinutesNewPage/Step2FormBuilder/RetroactiveSubform.js` (NEW)
- `pages/MinutesNewPage/Step3ReviewAndSave.js` (NEW)
- `pages/MinutesNewPage/AiDraftPanel.js` (NEW)
- `pages/MinutesPage.js` — Add drafts section, single "New Minutes" button, template_type badges
- `pages/MinutesDetailPage.js` — Add retroactive banner, section cards, source badges
- `App.js` — Update routes, add redirects

### Migration
- `scripts/migrate_minutes_templates.py` (NEW)