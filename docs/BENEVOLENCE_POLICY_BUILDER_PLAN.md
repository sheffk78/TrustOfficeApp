# Written Benevolence Policy Builder — Implementation Plan

**Feature:** Create, store, version, and manage a written benevolence policy that defines eligibility criteria, charitable class, approval processes, allowable types of assistance, per-recipient limits, and documentation requirements. Individual benevolence records link to the active policy version.

**Date:** August 14, 2026
**Codebase:** `Kit/life/brands/TrustOffice/projects/TrustOfficeApp/`

---

## 1. Database Model Additions

### 1a. New Pydantic Models — `backend/models.py`

Add after the existing `BenevolenceRecordResponse` block (after L961):

```python
# ==================== BENEVOLENCE POLICY MODELS ====================

class AssistanceTypeConfig(BaseModel):
    """One allowable type of assistance within a policy"""
    purpose: BenevolencePurpose          # reuses existing enum (L151-160)
    label: str                            # display name, e.g. "Medical Expenses"
    is_allowed: bool = True               # True = covered, False = explicitly excluded
    per_recipient_limit: Optional[float] = None   # e.g. 500.00 (None = no limit)
    per_recipient_period: Optional[str] = None     # "annual" | "lifetime" | "per_request"
    notes: str = ""

class CommitteeMember(BaseModel):
    name: str
    role: str = "member"                   # "chair" | "secretary" | "member"
    email: Optional[str] = None

class EligibilityCriterion(BaseModel):
    criterion: str                         # e.g. "Must reside within 50 miles"
    is_required: bool = True               # hard requirement vs. preference

class DocumentationRequirement(BaseModel):
    item: str                              # e.g. "Receipt for medical bill"
    is_required: bool = True

class BenevolencePolicyCreate(BaseModel):
    trust_id: str
    version_label: str = "1.0"             # user-facing version, e.g. "1.0", "1.1", "2.0"
    charitable_class: str                  # IRS-required: who can receive (e.g. "indigent persons in X county")
    charitable_class_description: str = "" # broader description
    eligibility_criteria: List[EligibilityCriterion] = []
    assistance_types: List[AssistanceTypeConfig] = []   # covered + excluded types
    per_recipient_annual_limit: Optional[float] = None  # global cap across all types
    approval_process: str = ""             # free-text description of approval workflow
    approval_threshold: Optional[float] = None  # amounts below this = single approver; above = committee
    committee_members: List[CommitteeMember] = []
    documentation_requirements: List[DocumentationRequirement] = []
    designated_gift_prohibition: str = "No earmarked contributions for specific individuals will be accepted."
    employee_benevolence_note: str = ""    # IRC §102 / §139 taxability note
    board_approval_date: Optional[str] = None     # ISO date string
    board_approval_reference: Optional[str] = None  # minutes_id link to approving minutes
    effective_date: str                    # ISO date — when this version takes effect
    supersedes_version_id: Optional[str] = None   # policy_version_id of prior version
    notes: str = ""

class BenevolencePolicyUpdate(BaseModel):
    """Used for editing a DRAFT version only — published versions are immutable"""
    version_label: Optional[str] = None
    charitable_class: Optional[str] = None
    charitable_class_description: Optional[str] = None
    eligibility_criteria: Optional[List[EligibilityCriterion]] = None
    assistance_types: Optional[List[AssistanceTypeConfig]] = None
    per_recipient_annual_limit: Optional[float] = None
    approval_process: Optional[str] = None
    approval_threshold: Optional[float] = None
    committee_members: Optional[List[CommitteeMember]] = None
    documentation_requirements: Optional[List[DocumentationRequirement]] = None
    designated_gift_prohibition: Optional[str] = None
    employee_benevolence_note: Optional[str] = None
    board_approval_date: Optional[str] = None
    board_approval_reference: Optional[str] = None
    effective_date: Optional[str] = None
    notes: Optional[str] = None

class BenevolencePolicyResponse(BaseModel):
    policy_id: str                         # unique ID for the policy (one per trust)
    trust_id: str
    user_id: str
    current_version_id: str                # policy_version_id of the active version
    current_version_label: str
    current_version_status: str            # "draft" | "published" | "superseded"
    created_at: str
    updated_at: Optional[str] = None

class BenevolencePolicyVersionResponse(BaseModel):
    policy_version_id: str
    policy_id: str
    trust_id: str
    user_id: str
    version_label: str
    version_number: int                    # auto-incremented (1, 2, 3...)
    status: str                            # "draft" | "published" | "superseded"
    charitable_class: str
    charitable_class_description: str
    eligibility_criteria: List[dict]       # stored as list of dicts (EligibilityCriterion)
    assistance_types: List[dict]           # stored as list of dicts (AssistanceTypeConfig)
    per_recipient_annual_limit: Optional[float]
    approval_process: str
    approval_threshold: Optional[float]
    committee_members: List[dict]
    documentation_requirements: List[dict]
    designated_gift_prohibition: str
    employee_benevolence_note: str
    board_approval_date: Optional[str]
    board_approval_reference: Optional[str]
    effective_date: str
    supersedes_version_id: Optional[str]
    notes: str
    published_at: Optional[str] = None     # timestamp when status → "published"
    created_at: str
    updated_at: Optional[str] = None
    created_by: str                        # user_id of creator
```

### 1b. New MongoDB Collections

| Collection | Purpose | Key Fields |
|---|---|---|
| `benevolence_policies` | One document per trust (the policy container) | `policy_id`, `trust_id`, `user_id`, `current_version_id`, `created_at`, `updated_at` |
| `benevolence_policy_versions` | One document per version (immutable once published) | `policy_version_id`, `policy_id`, `trust_id`, `user_id`, `version_number`, `version_label`, `status`, all policy content fields, `published_at`, `supersedes_version_id` |

### 1c. Field Addition to Existing `BenevolenceRecordCreate` / `BenevolenceRecordResponse`

Add one optional field to link records to the active policy version:

```python
# In BenevolenceRecordCreate (L920) — add:
policy_version_id: Optional[str] = None    # links to active policy version at time of creation

# In BenevolenceRecordResponse (L946) — add:
policy_version_id: Optional[str] = None
```

### 1d. Field Addition to `BenevolenceRecordUpdate` (L934)

```python
policy_version_id: Optional[str] = None
```

### 1e. No Changes to Trust Model

The trust model already has `benevolence_enabled` (L320) and `benevolence_mission` (L290). No additional trust fields are needed — the policy is a separate entity linked by `trust_id`.

---

## 2. Backend API Endpoints

### New Router: `backend/routers/benevolence_policy.py`

All endpoints follow the existing patterns in `benevolence.py`: `get_current_user` for reads, `require_write_access` for writes, `db.trusts.find_one()` ownership check, `uuid.uuid4().hex[:12]` for IDs.

| Method | Path | Request Model | Response | Notes |
|---|---|---|---|---|
| `POST` | `/benevolence/policies` | `BenevolencePolicyCreate` | `BenevolencePolicyVersionResponse` | Creates policy (if not exists) + first draft version. Returns the version. |
| `GET` | `/benevolence/policies/{trust_id}` | — | `BenevolencePolicyResponse` | Gets policy metadata with `current_version_id` |
| `GET` | `/benevolence/policies/{trust_id}/versions` | — | `List[BenevolencePolicyVersionResponse]` | Lists all versions (draft + published + superseded), sorted by `version_number` desc |
| `GET` | `/benevolence/policies/{trust_id}/active` | — | `BenevolencePolicyVersionResponse` | Gets the currently published version (status="published"). Returns 404 if none published. |
| `GET` | `/benevolence/policies/versions/{policy_version_id}` | — | `BenevolencePolicyVersionResponse` | Gets a single version by ID |
| `PUT` | `/benevolence/policies/versions/{policy_version_id}` | `BenevolencePolicyUpdate` | `BenevolencePolicyVersionResponse` | Edits a DRAFT version only. 400 if status != "draft". |
| `POST` | `/benevolence/policies/versions/{policy_version_id}/publish` | `dict` (optional `board_approval_date`, `board_approval_reference`) | `BenevolencePolicyVersionResponse` | Publishes a draft: sets status="published", sets `published_at`, supersedes prior active version (sets prior to "superseded"), updates `benevolence_policies.current_version_id`. |
| `POST` | `/benevolence/policies/{trust_id}/amend` | `BenevolencePolicyCreate` (partial) | `BenevolencePolicyVersionResponse` | Creates a new DRAFT version copying the current published version as a starting point. Auto-increments `version_number`, sets `supersedes_version_id` to current. |
| `DELETE` | `/benevolence/policies/versions/{policy_version_id}` | — | `{"message": "..."}` | Deletes a DRAFT version only. 400 if status != "draft". |
| `GET` | `/benevolence/policies/{trust_id}/export/pdf` | — | `Response` (PDF) | Generates styled PDF of the active (or specified) policy version using ReportLab + `pdf_utils.py` helpers. |

### Endpoint Detail: `POST /benevolence/policies` (Create first policy + draft version)

```python
@router.post("/benevolence/policies", response_model=BenevolencePolicyVersionResponse)
async def create_benevolence_policy(policy: BenevolencePolicyCreate, user: dict = Depends(require_write_access)):
    # 1. Verify trust exists + benevolence_enabled
    trust = await db.trusts.find_one({"trust_id": policy.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(404, "Trust not found.")
    if not trust.get("benevolence_enabled"):
        raise HTTPException(400, "Benevolence mode is not enabled for this trust.")

    # 2. Check no existing policy
    existing = await db.benevolence_policies.find_one({"trust_id": policy.trust_id, "user_id": user["user_id"]})
    if existing:
        raise HTTPException(409, "A benevolence policy already exists for this trust. Use amend to create a new version.")

    # 3. Create policy + first version
    policy_id = f"benpol_{uuid.uuid4().hex[:12]}"
    version_id = f"benpolv_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    policy_doc = {
        "policy_id": policy_id,
        "trust_id": policy.trust_id,
        "user_id": user["user_id"],
        "current_version_id": version_id,
        "current_version_label": policy.version_label,
        "current_version_status": "draft",
        "created_at": now,
        "updated_at": None,
    }
    version_doc = {
        "policy_version_id": version_id,
        "policy_id": policy_id,
        "trust_id": policy.trust_id,
        "user_id": user["user_id"],
        "version_number": 1,
        "version_label": policy.version_label,
        "status": "draft",
        # ... all fields from BenevolencePolicyCreate ...
        "published_at": None,
        "supersedes_version_id": None,
        "created_at": now,
        "updated_at": None,
        "created_by": user["user_id"],
    }

    await db.benevolence_policies.insert_one(policy_doc)
    await db.benevolence_policy_versions.insert_one(version_doc)
    return BenevolencePolicyVersionResponse(**{k: v for k, v in version_doc.items() if k != "_id"})
```

### Endpoint Detail: `POST /benevolence/policies/versions/{policy_version_id}/publish`

```python
@router.post("/benevolence/policies/versions/{policy_version_id}/publish", response_model=BenevolencePolicyVersionResponse)
async def publish_policy_version(policy_version_id: str, request: dict, user: dict = Depends(require_write_access)):
    version = await db.benevolence_policy_versions.find_one(
        {"policy_version_id": policy_version_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not version:
        raise HTTPException(404, "Policy version not found.")
    if version["status"] != "draft":
        raise HTTPException(400, "Only draft versions can be published.")

    now = datetime.now(timezone.utc).isoformat()
    policy_id = version["policy_id"]

    # Supersede the currently published version (if any)
    current_published = await db.benevolence_policy_versions.find_one(
        {"policy_id": policy_id, "status": "published"}, {"_id": 0}
    )
    if current_published:
        await db.benevolence_policy_versions.update_one(
            {"policy_version_id": current_published["policy_version_id"]},
            {"$set": {"status": "superseded", "updated_at": now}}
        )

    # Publish the draft
    update_fields = {
        "status": "published",
        "published_at": now,
        "updated_at": now,
    }
    if request.get("board_approval_date"):
        update_fields["board_approval_date"] = request["board_approval_date"]
    if request.get("board_approval_reference"):
        update_fields["board_approval_reference"] = request["board_approval_reference"]

    await db.benevolence_policy_versions.update_one(
        {"policy_version_id": policy_version_id},
        {"$set": update_fields}
    )

    # Update policy container
    await db.benevolence_policies.update_one(
        {"policy_id": policy_id},
        {"$set": {
            "current_version_id": policy_version_id,
            "current_version_label": version["version_label"],
            "current_version_status": "published",
            "updated_at": now,
        }}
    )

    # Log audit event
    await log_audit_event(user["user_id"], "benevolence_policy_published", "benevolence_policy", policy_id, {
        "version_id": policy_version_id,
        "version_label": version["version_label"],
    })

    updated = await db.benevolence_policy_versions.find_one({"policy_version_id": policy_version_id}, {"_id": 0})
    return BenevolencePolicyVersionResponse(**updated)
```

### Registration in `backend/server.py`

Add after line 62 (`from routers.benevolence import router as benevolence_router`):

```python
from routers.benevolence_policy import router as benevolence_policy_router
```

And in the `include_router` section:

```python
app.include_router(benevolence_policy_router)
```

### Modification to existing `POST /benevolence` (in `benevolence.py` L25-56)

Add auto-linking to active policy version when creating a record:

```python
# After line 34 (benevolence_enabled check), before record creation:
# Auto-attach active policy version if not explicitly provided
if not record.policy_version_id:
    active_policy = await db.benevolence_policies.find_one(
        {"trust_id": record.trust_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if active_policy and active_policy.get("current_version_status") == "published":
        record_doc["policy_version_id"] = active_policy["current_version_id"]
    else:
        record_doc["policy_version_id"] = None
else:
    record_doc["policy_version_id"] = record.policy_version_id
```

### Feature Gating — `backend/dependencies.py`

`BENEVOLENCE_MODE` (L388) is already premium-gated. The policy builder is a sub-feature of benevolence mode — no new feature flag is needed. All policy endpoints check `trust.get("benevolence_enabled")` just like the existing benevolence router.

---

## 3. Frontend Pages/Components

### 3a. New Page: `frontend/src/pages/BenevolencePolicyPage.js`

**Route:** `/benevolence/policy` (added in `App.js`)
**Sidebar:** Add a sub-nav link under the existing Benevolence item, or a "Policy" tab within the BenevolencePage.

**Key UI Elements:**
- **Policy Status Banner** — shows whether a policy exists, current version label, status (draft/published), effective date
- **Active Policy View** (when published version exists):
  - Charitable class display
  - Eligibility criteria list (checkmark items)
  - Allowable assistance types table (type, allowed/excluded, per-recipient limit, period)
  - Global annual limit
  - Approval process description + committee members
  - Documentation requirements checklist
  - Designated gift prohibition text
  - Employee benevolence tax note
  - Board approval date + linked minutes
  - "Download PDF" button
  - "Amend Policy" button (creates new draft from current)
- **Draft Editor** (when draft exists or after "Amend"):
  - Multi-section form with the same fields, editable
  - Section 1: Charitable Class & Eligibility
  - Section 2: Assistance Types (add/remove rows, toggle allowed/excluded, set limits)
  - Section 3: Approval Process & Committee
  - Section 4: Documentation Requirements
  - Section 5: Board Approval & Effective Date
  - "Save Draft" + "Publish" buttons
  - IRS compliance checklist sidebar (non-blocking warnings)
- **Version History** tab/section:
  - Table of all versions (version number, label, status, effective date, published date)
  - Click to view any historical version (read-only)
  - "Download PDF" per version

**Components breakdown:**
- `BenevolencePolicyPage.js` — main page, tab management (View / Edit Draft / Version History)
- `frontend/src/pages/benevolence-policy/PolicyViewTab.js` — read-only display of a published version
- `frontend/src/pages/benevolence-policy/PolicyDraftEditor.js` — multi-section form
- `frontend/src/pages/benevolence-policy/AssistanceTypesEditor.js` — dynamic row editor for assistance types
- `frontend/src/pages/benevolence-policy/CommitteeMembersEditor.js` — dynamic row editor for committee
- `frontend/src/pages/benevolence-policy/VersionHistoryTab.js` — version list + viewer
- `frontend/src/pages/benevolence-policy/ComplianceChecklist.js` — IRS requirements sidebar
- `frontend/src/pages/benevolence-policy/constants.js` — PURPOSE_OPTIONS reuse, PERIOD_OPTIONS, STATUS_LABELS

### 3b. Route Registration — `frontend/src/App.js`

Add import (near L29):
```javascript
import BenevolencePolicyPage from "@/pages/BenevolencePolicyPage";
```

Add route (after L293):
```javascript
<Route path="/benevolence/policy" element={
  <SubscriptionProtectedRoute>
    <BenevolencePolicyPage />
  </SubscriptionProtectedRoute>
} />
```

### 3c. Sidebar / Navigation — `frontend/src/components/Sidebar.js`

Option A (preferred): Add a secondary link under the Benevolence nav item:
```javascript
{ path: '/benevolence/policy', icon: FileText, label: 'Policy', parentPath: '/benevolence', requiresBenevolence: true }
```

Option B: Add a "Policy" tab within the existing `BenevolencePage.js` that navigates to `/benevolence/policy`.

### 3d. Integration into existing `BenevolencePage.js`

Add a "Policy" button/link in the page header (near the existing "Download" and "Add Record" buttons) that navigates to `/benevolence/policy`. Also, in each benevolence record card/row, display the linked policy version label as a small badge (e.g., "Policy v1.2"). If no policy exists, show a prompt: "Create a written benevolence policy to strengthen IRS compliance →".

---

## 4. Integration Points

### 4a. Existing Benevolence Module (`backend/routers/benevolence.py`)
- **Record creation** (L25-56): Auto-attach `policy_version_id` to new records (see Section 2 modification above)
- **Record response** (L946-961): `BenevolenceRecordResponse` gains `policy_version_id` field
- **PDF export** (L268-555): Add a "Policy Reference" section to the PDF showing the active policy version label, charitable class, and per-recipient limits
- **Summary endpoint** (L183-263): Add `active_policy_version` to summary response for frontend display

### 4b. Distributions Module (`backend/routers/distributions.py`)
- Distributions with `is_benevolence=True` (L850-852) should also link to `policy_version_id` — add optional field to `DistributionCreate`/`DistributionResponse`
- When a benevolence distribution is created, validate against policy limits (warning, not block):
  - Check `per_recipient_annual_limit` — if amount + YTD total for this recipient exceeds limit, return a warning in the response
  - Check `assistance_types` — if the distribution's purpose is marked `is_allowed=False`, return a warning

### 4c. Risk Dashboard (`backend/services/risk_gathering.py`)
Add a new risk section after the benevolence vault check (around L158):

```python
# === BENEVOLENCE POLICY RISK ===
if is_benevolence:
    policy = await db.benevolence_policies.find_one(
        {"trust_id": trust_id, "user_id": trust.get("user_id")}, {"_id": 0}
    )
    if not policy:
        risks.append({
            "type": "no_benevolence_policy",
            "severity": "high",
            "title": "No written benevolence policy on file",
            "detail": "IRS requires a written policy defining eligibility criteria, charitable class, and approval processes for benevolence programs.",
            "action": "Create a written benevolence policy",
            "module": "benevolence",
            "deeplink": "/benevolence/policy",
        })
    elif policy.get("current_version_status") == "draft":
        risks.append({
            "type": "policy_not_published",
            "severity": "medium",
            "title": "Benevolence policy draft not yet published",
            "detail": f"Policy version {policy.get('current_version_label')} is in draft status. Publish it after board approval.",
            "action": "Review and publish the policy draft",
            "module": "benevolence",
            "deeplink": "/benevolence/policy",
        })
    else:
        # Check for records without policy version link
        unlinked_count = await db.benevolence_records.count_documents({
            "trust_id": trust_id,
            "policy_version_id": {"$in": [None, ""]},
        })
        if unlinked_count > 0:
            risks.append({
                "type": "records_without_policy",
                "severity": "low",
                "title": f"{unlinked_count} benevolence record(s) not linked to a policy version",
                "detail": "Records created before the policy was established are not linked to a specific policy version.",
                "action": "Review historical records for policy compliance",
                "module": "benevolence",
                "deeplink": "/benevolence",
            })
```

### 4d. Audit Trail (`backend/utils/audit.py`)
Use the existing `log_audit_event()` function (L17-44) for all policy actions:

| Action | Entity Type | Details |
|---|---|---|
| `benevolence_policy_created` | `benevolence_policy` | `{policy_id, version_id, version_label}` |
| `benevolence_policy_draft_saved` | `benevolence_policy` | `{policy_id, version_id, fields_changed}` |
| `benevolence_policy_published` | `benevolence_policy` | `{policy_id, version_id, version_label, board_approval_date}` |
| `benevolence_policy_amended` | `benevolence_policy` | `{policy_id, new_version_id, supersedes_version_id}` |
| `benevolence_policy_draft_deleted` | `benevolence_policy` | `{policy_id, deleted_version_id}` |

These events will automatically appear in the existing `AuditTrailPage.js` since it reads from `db.audit_logs`.

### 4e. AI Assistant (`backend/chat_service.py`)
Add policy-awareness to the trust assistant context. In `_build_trust_type_guidance` or the context builder (around L1302-1348), when `benevolence_enabled` is True:

```python
# Inject active policy summary into assistant context
policy = await db.benevolence_policies.find_one({"trust_id": trust_id}, {"_id": 0})
if policy and policy.get("current_version_status") == "published":
    version = await db.benevolence_policy_versions.find_one(
        {"policy_version_id": policy["current_version_id"]}, {"_id": 0}
    )
    if version:
        context_lines.append(f"Benevolence Policy: Version {version['version_label']}, effective {version['effective_date']}")
        context_lines.append(f"Charitable Class: {version['charitable_class']}")
        context_lines.append(f"Annual Limit: ${version.get('per_recipient_annual_limit', 'No limit')}")
```

This lets the AI assistant answer questions like "What's our per-recipient limit?" by referencing the actual policy.

### 4f. Knowledge Base
Add a new knowledge file: `backend/knowledge/18-benevolence-policy-requirements.md` covering IRS requirements for written benevolence policies (charitable class, eligibility, approval process, documentation, designated gift prohibition, IRC §102/§139). Reference it in `_TRUST_TYPE_FILE_MAP` or add a separate benevolence-specific lookup in `chat_service.py`.

---

## 5. PDF Policy Document Generation

### New Service: `backend/services/benevolence_policy_pdf.py`

Follow the exact pattern from `beneficiary_report_service.py` and the existing `benevolence.py` PDF export (L268-555).

**Structure:**
```python
from pdf_utils import NAVY, GRAY, LIGHT_GRAY, separator_line, create_doc_template, build_styles, info_table, data_table, signature_block

async def generate_policy_pdf(version: dict, trust: dict, show_watermark: bool) -> bytes:
    doc, buffer = create_doc_template()
    styles = build_styles()
    story = []

    # Title: "BENEVOLENCE POLICY"
    # Subtitle: trust name, version label, effective date
    # Section 1: Charitable Class & Purpose
    # Section 2: Eligibility Criteria (table)
    # Section 3: Allowable Types of Assistance (table: type, allowed/excluded, limit, period)
    # Section 4: Per-Recipient Limits (summary)
    # Section 5: Approval Process & Committee
    # Section 6: Documentation Requirements (checklist)
    # Section 7: Designated Gift Prohibition
    # Section 8: Employee Benevolence Tax Note (§102/§139)
    # Section 9: Board Approval (date, reference, signature block)
    # Footer: generated date, watermark if applicable

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
```

**Endpoint** (in `benevolence_policy.py`):
```python
@router.get("/benevolence/policies/{trust_id}/export/pdf")
async def export_policy_pdf(trust_id: str, version_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    # Get trust, verify ownership + benevolence_enabled
    # Get policy version (specified or active)
    # Generate PDF via service
    # Return Response with application/pdf
```

Reuse `create_doc_template()`, `build_styles()`, `info_table()`, `data_table()`, `separator_line()`, and `signature_block()` from `pdf_utils.py` — all already shared across the codebase.

---

## 6. Implementation Order (Dependencies)

| Phase | Component | Depends On | Effort |
|---|---|---|---|
| **1** | Pydantic models in `models.py` (Section 1a-1d) | Nothing | **Small** |
| **2** | Backend router `benevolence_policy.py` — CRUD + versioning + publish (Section 2) | Phase 1 | **Medium** |
| **3** | Register router in `server.py` + modify `benevolence.py` record creation for auto-linking (Section 2) | Phase 2 | **Small** |
| **4** | PDF generation service `benevolence_policy_pdf.py` + export endpoint (Section 5) | Phase 2 | **Medium** |
| **5** | Risk dashboard integration in `risk_gathering.py` (Section 4c) | Phase 2 | **Small** |
| **6** | Audit trail integration — `log_audit_event` calls in policy router (Section 4d) | Phase 2 | **Small** |
| **7** | Frontend `BenevolencePolicyPage.js` + sub-components (Section 3a) | Phase 3 (API must be live) | **Large** |
| **8** | Route registration in `App.js` + Sidebar nav (Section 3b-3c) | Phase 7 | **Small** |
| **9** | Integration into existing `BenevolencePage.js` — policy badge + link (Section 3d) | Phase 7 | **Small** |
| **10** | Distributions integration — policy_version_id on benevolence distributions + limit validation (Section 4b) | Phase 3 | **Medium** |
| **11** | AI assistant context injection (Section 4e) | Phase 2 | **Small** |
| **12** | Knowledge file `18-benevolence-policy-requirements.md` (Section 4f) | Nothing | **Small** |
| **13** | Backend tests `test_benevolence_policy.py` (Section 7 below) | Phase 3 | **Medium** |
| **14** | Frontend test `BenevolencePolicyPage.test.js` | Phase 8 | **Medium** |

### Critical Path
```
Phase 1 → Phase 2 → Phase 3 → Phase 7 → Phase 8
```
Phases 4-6, 10-14 can proceed in parallel once Phase 3 is complete.

---

## 7. Testing

### Backend: `backend/tests/test_benevolence_policy.py`

Follow the pattern from `test_benevolence.py`. Key test cases:
- Create policy → first draft version created
- Edit draft → fields updated
- Publish draft → status changes, prior version superseded, policy container updated
- Amend published policy → new draft created with incremented version_number, supersedes_version_id set
- Delete draft → removed; Delete published → 400 error
- Create benevolence record → auto-linked to active policy version
- Export PDF → returns application/pdf
- Risk dashboard → "no policy" finding when none exists
- Audit trail → events logged for create/publish/amend/delete

### Frontend: `frontend/src/pages/BenevolencePolicyPage.test.js`

Follow the pattern from `BenevolenceLogPage.test.js`. Key test cases:
- Renders policy view when published version exists
- Renders draft editor when draft exists
- "Amend" button creates new draft
- "Publish" button calls publish endpoint
- Version history tab shows all versions
- Compliance checklist shows warnings for missing fields

---

## 8. IRS Compliance Coverage

| IRS Requirement | Model Field | UI Location |
|---|---|---|
| Written policy defining eligibility criteria | `eligibility_criteria: List[EligibilityCriterion]` | Draft Editor §1 |
| Charitable class definition | `charitable_class` + `charitable_class_description` | Draft Editor §1 |
| Approval process documentation | `approval_process` + `approval_threshold` + `committee_members` | Draft Editor §3 |
| Types of needs covered/excluded | `assistance_types: List[AssistanceTypeConfig]` with `is_allowed` | Draft Editor §2 |
| Per-recipient limits | `per_recipient_annual_limit` (global) + `AssistanceTypeConfig.per_recipient_limit` (per-type) | Draft Editor §2 |
| Documentation requirements | `documentation_requirements: List[DocumentationRequirement]` | Draft Editor §4 |
| Committee structure (2-4 individuals) | `committee_members: List[CommitteeMember]` | Draft Editor §3 |
| Board approval | `board_approval_date` + `board_approval_reference` | Draft Editor §5 + Publish endpoint |
| Policy versioning (amendments) | `benevolence_policy_versions` collection + `version_number` + `supersedes_version_id` | Version History tab |
| Designated gift prohibition | `designated_gift_prohibition` (default text provided) | Draft Editor §7 |
| Employee benevolence = taxable (§102, §139) | `employee_benevolence_note` | Draft Editor §8 |

---

## 9. Effort Summary

| Component | Effort | Est. Hours |
|---|---|---|
| Pydantic models (1a-1d) | Small | 2-3h |
| Backend router + versioning logic | Medium | 6-8h |
| Router registration + benevolence.py modification | Small | 1-2h |
| PDF generation service + endpoint | Medium | 4-5h |
| Risk dashboard integration | Small | 1-2h |
| Audit trail integration | Small | 1h |
| Frontend BenevolencePolicyPage + 7 sub-components | Large | 12-16h |
| App.js + Sidebar registration | Small | 1h |
| BenevolencePage.js integration (badge + link) | Small | 1-2h |
| Distributions integration (policy_version_id + validation) | Medium | 3-4h |
| AI assistant context injection | Small | 1-2h |
| Knowledge file | Small | 1h |
| Backend tests | Medium | 3-4h |
| Frontend tests | Medium | 2-3h |
| **Total** | | **~40-55h** |

**Overall effort: Large** (approximately 1-2 sprints for a single developer)

---

## 10. Key Design Decisions

1. **Two-collection approach** (`benevolence_policies` + `benevolence_policy_versions`) — separates the policy container (one per trust) from immutable version documents, following the same pattern as governance history snapshots.

2. **Published versions are immutable** — once a version is published, it cannot be edited. Amendments create a new draft. This preserves the audit trail and ensures historical records always reference the exact policy that was in effect.

3. **Auto-linking on record creation** — new benevolence records automatically get the current published `policy_version_id`. Users can override, but the default ensures compliance linkage.

4. **No new feature flag** — the policy builder is part of the existing `BENEVOLENCE_MODE` premium gate. No changes to `dependencies.py` feature flags.

5. **Soft validation on distributions** — when a benevolence distribution exceeds policy limits, the API returns a warning (not an error). This avoids blocking legitimate decisions while flagging them for review.

6. **PDF uses shared `pdf_utils.py`** — all ReportLab boilerplate (styles, tables, signatures, watermarks) is already extracted into `pdf_utils.py`. The policy PDF service reuses these helpers directly.