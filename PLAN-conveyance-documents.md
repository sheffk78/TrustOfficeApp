# Plan: Conveyance Documents (Bill of Sale, Assignment of Property)

**Date:** July 6, 2026  
**Status:** Ready for implementation  
**Decision:** Extend existing Minutes system — no new page, no new router, no new nav item

---

## Background

Jeff wants TrustOffice to help customers move assets (vehicles, artwork, antiques, jewelry) into their trust with proper paperwork — specifically "bill of sale" and similar transfer documents. Three review agents were spawned to assess whether this should be a new feature or consolidated into existing functionality.

**Review consensus (all 3 agents, unanimous):** Do NOT build a new feature. The Minutes template system already does 90% of this — it generates pre-filled legal PDFs from trust data, has 24 template types including `acceptance_of_property`, auto-links to Schedule A, and stores in the Vault. Adding bill of sale / assignment as new Minutes template types is the right approach.

**Jeff's directive:** "We want to consolidate as much as we can and not just add more features and make trustoffice so confusing."

**Important note on the review agents:** The agents searched a different path (`Kit/life/brands/TrustOffice/projects/TrustOfficeApp/`) and did NOT find the Trust Admin Kit generator. The kit generator DOES exist — it was built this session, is committed to git (commit `06fe980`), and is deployed at `api.trustoffice.app`. The files are at `~/Projects/TrustOfficeApp/backend/routers/trust_admin_kits.py` and `~/Projects/TrustOfficeApp/frontend/src/pages/TrustAdminKitsPage.js`. The agents' core recommendation (extend Minutes, don't add a new page) is still correct, but their claim that the kit generator doesn't exist is wrong — they just searched the wrong path.

---

## What We're Building

Three new Minutes template types that produce conveyance instruments (the actual legal document, not just a resolution about the transfer):

1. **Bill of Sale** — transfers tangible personal property (vehicles, equipment, furnishings) from grantor to trust
2. **Assignment of Personal Property** — transfers artwork, antiques, jewelry, collectibles to the trust
3. **General Assignment** — catch-all for intangible assets (notes receivable, IP, business interests, digital assets)

### Why Minutes templates, not a new feature

| Existing capability | What it does | Already handles? |
|---|---|---|
| Minutes templates | Generate pre-filled legal PDFs from trust data, 24 existing types, Schedule A auto-link, Vault storage, watermark/footer | ✅ 90% of what we need |
| `acceptance_of_property` template | Records trustee resolution accepting property into trust, auto-adds to Schedule A | ✅ The resolution side |
| Schedule A | Asset registry, tracks conveyance date, value, `minutes_ref` linking back to conveying minutes | ✅ The registry side |
| Trust Admin Kit generator | Instruction packets for external parties (DMV, banks, county recorder) | ✅ Instructions, but NOT the document itself |

**What's missing:** The actual conveyance instrument — a document the grantor signs to transfer ownership. The `acceptance_of_property` template records the trust's *acceptance* of property, but not the *grantor's conveyance*. Bill of Sale and Assignment fill that gap. They're the companion documents to the acceptance resolution.

### How it differs from the Kit generator

The Trust Admin Kit generator produces **instruction packets** — "go to the DMV with these forms, here's the fee schedule, here's where to go." The conveyance document templates produce the **actual legal document** itself — a bill of sale the grantor signs, an assignment of personal property with notary block. These are different things. Kits tell you what to do; documents are what you sign.

**The flow for a customer would be:**
1. Generate a Bill of Sale (Minutes template) → grantor signs → notarized → trust accepts via `acceptance_of_property` resolution → asset auto-added to Schedule A
2. Generate a Vehicle Retitling Kit → take the signed bill of sale + kit instructions to DMV → retitle vehicle in trust's name

They work together — they don't overlap.

---

## Implementation

### Architecture: Extend existing Minutes system

No new router. No new page. No new nav item. Three changes across existing files:

```
backend/models.py                         → 3 enum values
backend/routers/template_registry.py      → 3 template definitions (~60 lines)
backend/routers/minutes.py                → 3 content generators (~120 lines) + 3 dispatch branches + 3 Schedule A auto-link blocks
frontend/src/pages/MinutesTemplateFormPage.js → 3 template titles + 3 form sections + 3 data builders
```

### Step 1: Backend — Add template types to enum

**File:** `backend/models.py`  
**Location:** `MinutesTemplateType` enum, after line 133 (`conflict_of_interest`)  
**Add:**
```python
# Conveyance documents
bill_of_sale = "bill_of_sale"
assignment_of_personal_property = "assignment_of_personal_property"
general_assignment = "general_assignment"
```

### Step 2: Backend — Add template definitions to registry

**File:** `backend/routers/template_registry.py`  
**Location:** After `real_estate_lease` entry (line 267), still under `property_assets` category  
**Add three entries** following the `acceptance_of_property` pattern:

```python
"bill_of_sale": {
    "display_name": "Bill of Sale (Vehicle/Equipment)",
    "description": "Generate a bill of sale transferring tangible personal property to the trust",
    "icon": "file-text",
    "category": "property_assets",
    "fields": [
        {"name": "grantor_name", "label": "Grantor/Seller Name", "type": "text", "required": True},
        {"name": "property_description", "label": "Property Description", "type": "textarea", "required": True},
        {"name": "property_identifier", "label": "Identifier (VIN, Serial #, etc.)", "type": "text", "required": False},
        {"name": "property_location", "label": "Property Location", "type": "text", "required": False},
        {"name": "property_value", "label": "Sale Price / Approximate Value", "type": "currency", "required": False},
        {"name": "conveyance_date", "label": "Date of Sale/Transfer", "type": "date", "required": True},
        {"name": "add_to_schedule_a", "label": "Auto-add to Schedule A", "type": "boolean", "required": False},
        {"name": "schedule_a_category", "label": "Schedule A Category", "type": "select", "required": False,
         "options": ["personal_property", "real_property", "other_property"]},
    ],
    "ai_prompt_template": (
        "Generate a bill of sale for transfer of tangible personal property to {trust_name}. "
        "Grantor: {grantor_name}. Property: {property_description}. Identifier: {property_identifier}. "
        "Value: {property_value}. Date: {conveyance_date}. Trustee: {trustee_name}. EIN: {ein}. "
        "Include conveyance language, consideration statement, 'as-is' clause, and notary acknowledgment block "
        "for {state_code}. Output formal bill of sale document text."
    ),
},
```

Repeat for `assignment_of_personal_property` (artwork/jewelry/collectibles — fields: grantor, description, appraised_value, appraiser_name, conveyance_date, add_to_schedule_a, schedule_a_category) and `general_assignment` (intangible assets — fields: grantor, asset_description, asset_type, conveyance_date, add_to_schedule_a, schedule_a_category).

### Step 3: Backend — Add content generator functions

**File:** `backend/routers/minutes.py`  
**Location:** After `generate_property_acceptance_content()` (line 1736)  
**Pattern:** Follow the exact same structure as `generate_property_acceptance_content()`

```python
def generate_bill_of_sale_content(data: dict) -> str:
    """Generate bill of sale content for tangible personal property transfer."""
    grantor = data.get("grantor_name", "[Grantor]")
    trust_name = data.get("trust_name", "[Trust Name]")
    trustee = data.get("trustee_name", "[Trustee]")
    description = data.get("property_description", "[Description]")
    identifier = data.get("property_identifier", "N/A")
    value = data.get("property_value")
    conveyance_date = data.get("conveyance_date", "[Date]")
    
    value_text = f"${value:,.2f}" if value else "$1.00 (One Dollar) and other good and valuable consideration"
    
    content = f"""BILL OF SALE

WHEREAS, {grantor} ("Grantor") is the lawful owner of the following described personal property:

    Description: {description}
    Identifier: {identifier}
    
NOW, THEREFORE, for and in consideration of {value_text}, the receipt and sufficiency of which is hereby acknowledged, Grantor does hereby BARGAIN, SELL, GRANT, ASSIGN, TRANSFER, and CONVEY unto {trust_name} ("Trust"), the following described personal property:

    {description}
    Identifier: {identifier}

TO HAVE AND TO HOLD said property unto the Trust, its successors and assigns, forever.

Grantor warrants that Grantor is the lawful owner of said property, that the same is free from all encumbrances and liens, and that Grantor has full right and authority to convey the same.

This Bill of Sale is executed in conjunction with the trust's acceptance resolution dated {conveyance_date}.

AS-IS: Said property is conveyed "as-is" and "where-is" without any warranty, express or implied, except as expressly stated herein.

GRANTOR:

___________________________________________
{grantor}, Grantor

Date: {conveyance_date}

TRUSTEE ACKNOWLEDGMENT OF RECEIPT:

___________________________________________
{trustee}, Trustee of {trust_name}

Date: {conveyance_date}

NOTARY ACKNOWLEDGMENT:

State of _________________
County of _________________

On this _____ day of ____________, 20___, before me personally appeared {grantor}, known to me to be the person whose name is subscribed to the foregoing instrument, and acknowledged that he/she executed the same for the purposes therein contained.

___________________________________________
Notary Public
My Commission Expires: _________________

"""
    return content
```

Repeat for `generate_assignment_of_personal_property_content()` (artwork/jewelry language — "Assignment and Conveyance of Personal Property") and `generate_general_assignment_content()` (intangible assets — "General Assignment of Assets").

### Step 4: Backend — Add dispatch branches

**File:** `backend/routers/minutes.py`  
**Location:** In the template dispatch block, after `conflict_of_interest` branch (line 1059)  
**Add:**
```python
elif template_type == "bill_of_sale":
    doc += generate_bill_of_sale_content(template_data)
elif template_type == "assignment_of_personal_property":
    doc += generate_assignment_of_personal_property_content(template_data)
elif template_type == "general_assignment":
    doc += generate_general_assignment_content(template_data)
```

### Step 5: Backend — Extend Schedule A auto-link

**File:** `backend/routers/minutes.py`  
**Location:** Lines 3663-3685, the `acceptance_of_property` Schedule A auto-insert block  
**Change:** Extend the condition to include the three new template types:

```python
# Current (line 3664):
if template.template_type.value == "acceptance_of_property" and template.template_data.get("add_to_schedule_a"):

# Change to:
CONVEYANCE_TEMPLATES = {"acceptance_of_property", "bill_of_sale", "assignment_of_personal_property", "general_assignment"}
if template.template_type.value in CONVEYANCE_TEMPLATES and template.template_data.get("add_to_schedule_a"):
```

The rest of the Schedule A insert block (lines 3665-3685) already reads from `template_data` fields that match our new templates — `property_description`, `property_identifier`, `property_location`, `property_value`, `conveyance_date`, `schedule_a_category`. No changes needed to the insert logic.

### Step 6: Frontend — Add template titles

**File:** `frontend/src/pages/MinutesTemplateFormPage.js`  
**Location:** `TEMPLATE_TITLES` object, after line 75  
**Add:**
```javascript
'bill_of_sale': 'Bill of Sale',
'assignment_of_personal_property': 'Assignment of Personal Property',
'general_assignment': 'General Assignment',
```

### Step 7: Frontend — Add form sections

**File:** `frontend/src/pages/MinutesTemplateFormPage.js`  
**Pattern:** Copy the `acceptance_of_property` form section (lines 1449-1537). The fields are identical — grantor_name, property_description, property_identifier, property_location, property_value, conveyance_date, add_to_schedule_a, schedule_a_category.

The simplest approach: **reuse the `acceptance_of_property` form section for all three new templates** by extending the condition:

```javascript
// Current (line 1449):
{templateType === 'acceptance_of_property' && (

// Change to:
{(templateType === 'acceptance_of_property' || templateType === 'bill_of_sale' || templateType === 'assignment_of_personal_property' || templateType === 'general_assignment') && (
```

**For `assignment_of_personal_property`** — add an optional `appraiser_name` field to the form. This can be a conditional field that only shows when `templateType === 'assignment_of_personal_property'`:

```jsx
{templateType === 'assignment_of_personal_property' && (
  <div className="md:col-span-2">
    <Label className="label-trust">Appraiser Name (if appraised)</Label>
    <Input
      value={propertyData.appraiser_name || ''}
      onChange={(e) => setPropertyData({ ...propertyData, appraiser_name: e.target.value })}
      className="mt-1 input-trust"
      placeholder="e.g., Sotheby's Appraisal Services"
    />
  </div>
)}
```

### Step 8: Frontend — Add data builders

**File:** `frontend/src/pages/MinutesTemplateFormPage.js`  
**Location:** The `buildTemplateData()` switch, after `case 'acceptance_of_property'` (line 716)  
**Add:**
```javascript
case 'bill_of_sale':
case 'assignment_of_personal_property':
case 'general_assignment':
  return {
    ...baseData,
    grantor_name: propertyData.grantor_name,
    property_description: propertyData.property_description,
    property_value: parseFloat(propertyData.property_value) || null,
    property_identifier: propertyData.property_identifier,
    property_location: propertyData.property_location,
    conveyance_date: propertyData.conveyance_date,
    appraiser_name: propertyData.appraiser_name || null,
    add_to_schedule_a: propertyData.add_to_schedule_a,
    schedule_a_category: propertyData.schedule_a_category
  };
```

### Step 9 (Optional but recommended): Backend — Create shared PDF utilities module

**File:** `backend/pdf_utils.py` (NEW)  
**Purpose:** Extract the ReportLab boilerplate that's duplicated across 5 routers into one shared module.

This is a consolidation win independent of the conveyance documents, but do it first so the new content generators can use it. Extract from `audit_defense.py` (which already has factored helpers):

```python
# backend/pdf_utils.py
# Shared ReportLab utilities — extracted from audit_defense.py, schedule_a.py, minutes.py

import io, base64
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

# Brand colors (currently duplicated in 5 routers)
NAVY = colors.HexColor('#010079')
GOLD = colors.HexColor('#d5ad36')
GRAY = colors.HexColor('#666666')
LIGHT_GRAY = colors.HexColor('#f0f0f0')

def build_styles(font_family='Helvetica'): ...
def separator_line(width=6.5*inch, thickness=1, color=NAVY): ...
def info_table(rows, label_width=1.5*inch, value_width=4.5*inch): ...
def data_table(header, rows, col_widths=None): ...
def signature_block(signatories, styles=None): ...
def notary_block(state='', county='', styles=None): ...  # NEW — no existing implementation
def watermark_footer(trust_name, doc_type, hide_watermark, styles=None): ...
def create_doc_template(margins=None): ...
def pdf_response(buffer, filename): ...
```

**After creating `pdf_utils.py`**, refactor `audit_defense.py` to import from it (validate the module works), then use it in the new content generators. Refactoring the other 4 routers (`schedule_a.py`, `minutes.py`, `benevolence.py`, `units.py`) to use `pdf_utils.py` can be done later — it's a nice-to-have, not a blocker.

**Note:** The minutes content generators currently produce plain text (not ReportLab flowables) — the PDF is built by `generate_minutes_pdf()` which wraps the text content. The `pdf_utils.py` module is for when we eventually want to generate standalone PDFs (bill of sale as its own PDF, not just minutes text). For now, the conveyance documents integrate into the minutes PDF flow and don't need `pdf_utils.py` to function. Build `pdf_utils.py` as a forward-looking consolidation step, not a prerequisite.

---

## What This Delivers

**For the customer (Gale or any trustee):**
1. Go to Minutes → Create New → see "Bill of Sale" alongside existing templates
2. Fill in grantor name, property description (e.g., "2018 Ford F-150, VIN XYZ"), value, date
3. Check "Auto-add to Schedule A" → select category
4. Generate → get a minutes document with the bill of sale text, signature block, notary block
5. Download PDF → grantor signs → notarize → done
6. Asset appears in Schedule A automatically, linked back to these minutes

**For the product:**
- Zero new nav items
- Zero new pages
- Zero new routers
- Three new entries in the existing template picker (which already has 24 templates)
- Full Schedule A integration inherited for free
- Full PDF generation inherited for free
- Full Vault storage inherited for free

**Consolidation wins:**
- `pdf_utils.py` eliminates ~100 lines of ReportLab duplication per router across 5 existing routers (optional but recommended)
- No feature bloat — the capability lives exactly where users would expect it

---

## Verification

1. **Backend syntax:** `python3 -c "import ast; ast.parse(open('backend/routers/minutes.py').read())"`
2. **Frontend build:** `cd frontend && npx craco build` → exit 0
3. **Template registry:** `curl https://api.trustoffice.app/api/minutes/templates` → verify new types appear
4. **End-to-end test:** Create minutes with `bill_of_sale` template type via API → verify PDF contains bill of sale text + notary block → verify Schedule A item created with `minutes_ref` linking back
5. **Existing tests:** `pytest backend/tests/test_minutes_router.py` → all pass (no regressions to existing templates)

---

## Files Touched

| File | Change | Lines |
|---|---|---|
| `backend/models.py` | Add 3 enum values | ~3 |
| `backend/routers/template_registry.py` | Add 3 template definitions | ~60 |
| `backend/routers/minutes.py` | Add 3 content generators + 3 dispatch branches + extend Schedule A condition | ~130 |
| `frontend/src/pages/MinutesTemplateFormPage.js` | Add 3 titles + extend form condition + add data builder cases | ~25 |
| `backend/pdf_utils.py` (optional) | New shared PDF utilities module | ~120 |

**Total: ~220 lines of new code, ~120 lines of consolidation refactoring. Zero new pages. Zero new nav items.**

---

## What This Plan Does NOT Do

- Does NOT create a new "Documents" page or nav item (consolidation directive)
- Does NOT create a new backend router (extends `minutes.py`)
- Does NOT duplicate the kit generator (kits = instructions, conveyance docs = the document itself — different things)
- Does NOT refactor all 5 existing PDF routers to use `pdf_utils.py` (only `audit_defense.py` as validation; rest is deferred)
- Does NOT add notary blocks to existing templates (only the new conveyance templates have them — existing templates don't need notary blocks since they're internal trust resolutions, not external-facing transfer instruments)