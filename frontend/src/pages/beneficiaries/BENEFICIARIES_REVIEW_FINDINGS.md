# TrustOffice Beneficiaries — Frontend Deeper Review Findings

**Reviewer:** Hermes Subagent  
**Scope:** `frontend/src/pages/beneficiaries/*`, `BeneficiariesPage.js`, `hooks.js`, `Modals.jsx`, tab components, `constants.js`  
**Date:** 2026-08-11  
**Severity:** Blocking / Major / Minor  
**Status:** Report only — no code changes made

---

## 1. BLOCKING — Missing `Link` import causes runtime crash on Overview tab  
**File:** `OverviewTab.jsx:1` (missing import), crash at `~80`  
**Detail:** `OverviewTab.jsx` uses `<Link>` (react-router-dom) inside the expanded beneficiary row ("Draft Minutes" button) but never imports it. Expanding any holder row throws `ReferenceError: Link is not defined` and white-screens the page.  
**User impact:** Real — any user who clicks the expand chevron on Overview tab crashes the app.  
**Fix:** Add `import { Link } from 'react-router-dom';` at the top of `OverviewTab.jsx`.

---

## 2. BLOCKING — Settings save calls stale/undefined reload callbacks (stale closure via ref)  
**File:** `hooks.js:306-360`, `BeneficiariesPage.js:41-58`  
**Detail:** `useSettings` receives `loadCertificatesDataRef` and `loadOverviewDataRef` as refs. Inside `handleSaveSettings` (line 341-342) it calls `loadCertificatesDataRef.current()` and `loadOverviewDataRef.current()`. However, `loadCertificatesDataRef.current` is assigned **after** the hook is initialized (line 57 in `BeneficiariesPage.js`). On the first render cycle, `ref.current` is `null`, so `handleSaveSettings` silently skips reloading data. Worse, if the user opens Settings before any other interaction, the refs may still be null and the UI stays stale after a successful settings update.  
**User impact:** Real — after increasing authorized units, the summary cards and pie chart don't refresh, so the user sees old numbers until they manually refresh the page.  
**Fix:** Remove the ref indirection and pass the callbacks directly into `handleSaveSettings` via a stable wrapper, or ensure the ref is populated before the modal can be opened.

---

## 3. MAJOR — Transfer sends `holder_name` strings instead of `certificate_id` to backend, causing wrong-cert selection when names collide  
**File:** `hooks.js:238-247` (frontend payload), `backend/routers/trust_units.py:598-604` (backend lookup)  
**Detail:** The frontend `TransferModal` lets the user pick source and destination certificates by `certificate_id`. But `handleTransfer` posts `from_holder: fromCert.holder_name` and `to_holder: toCert.holder_name` (strings). The backend then does `find_one({"holder_name": transfer.from_holder, "status": "active"})`. If a holder has multiple active certificates (e.g., re-issued, split, or trust-to-trust), the backend picks the **first** match by name, which may be a different certificate than the one the user selected in the UI.  
**User impact:** Real — a user could accidentally transfer units from/to the wrong certificate when a holder has multiple active certs.  
**Fix:** Change the API contract to accept `from_certificate_id` / `to_certificate_id` (or at minimum `certificate_id` for the source), and update the backend transfer endpoint to use them.

---

## 4. MAJOR — Transfer modal allows transferring to the same certificate (no self-transfer guard)  
**File:** `Modals.jsx:265-271` (dropdown filter), `hooks.js:221-261` (`handleTransfer`)  
**Detail:** The `To` dropdown filters out the currently selected `From` certificate (`c.certificate_id !== transferForm.from_certificate_id`), but this is UI-only. `handleTransfer` does not validate `from_certificate_id !== to_certificate_id`. A user could programmatically submit or race-condition-submit a self-transfer. The backend doesn't check either.  
**User impact:** Theoretical via normal UI, but possible via rapid UI interactions or programmatic triggers.  
**Fix:** Add an explicit guard in `handleTransfer`: `if (fromCert.certificate_id === toCert.certificate_id) { toast.error('Cannot transfer to the same certificate'); return; }`.

---

## 5. MAJOR — Transfer modal doesn't validate sender has enough units before API call  
**File:** `hooks.js:221-261`  
**Detail:** `handleTransfer` trusts the backend for unit validation but does not pre-validate that `fromCert.units >= transferForm.units`. The user can type more units than the sender holds and only learns after the backend 400.  
**User impact:** Real — poor UX, wasted click, no immediate inline feedback.  
**Fix:** Pre-validate: `if (units > fromCert.units) { toast.error(...); return; }` before calling `fetchWithAuth`.

---

## 6. MAJOR — "Fully allocated" banner absent on People & Overview tabs; Add Beneficiary button stays active with no pre-flight warning  
**File:** `PeopleTab.jsx:12-52`, `OverviewTab.jsx:140-222`, `CertificatesTab.jsx:142-156`  
**Detail:** The fully-allocated banner (`remaining_units === 0`) only renders in `CertificatesTab`. The `PeopleTab` and `OverviewTab` still show the "Add Beneficiary" button. When a user clicks it and enters a percentage, `handleAddPerson` (hooks.js:502) rejects with a toast only **after** submit. There's no pre-modal guidance.  
**User impact:** Real — users on People/Overview tabs get no warning that no units remain, open the modal, fill it out, click Add, then get an error. Feels broken.  
**Fix:** Conditionally disable/hide the "Add Beneficiary" button (or show a contextual banner) on People/Overview when `remaining_units === 0`, and add an inline "Increase authorized units" action there too.

---

## 7. MAJOR — `loading` state only tracks certificate load, not overview load; tabs show "No data" prematurely  
**File:** `hooks.js:17,31-48` (only `loadCertificatesData` touches `loading`), `OverviewTab.jsx:132`, `PeopleTab.jsx:42`  
**Detail:** `useBeneficiariesData` sets `loading=true` inside `loadCertificatesData`, but `loadOverviewData` never touches it. If the overview endpoint is slower than certificates, `OverviewTab` and `PeopleTab` render the "No data available" / "No beneficiaries yet" empty states while data is still in flight.  
**User impact:** Real — flickering empty states on slower connections; looks like data is missing.  
**Fix:** Make `loading` reflect **both** fetches, or add a separate `overviewLoading` state.

---

## 8. MAJOR — `canSelectTrustHolder` predicate is broken (always true)  
**File:** `constants.js:139-140`  
**Detail:** `canSelectTrustHolder` calls `isTrustHolder({ holder_type: 'trust' })` with a hardcoded object, so it always returns `true` regardless of `trusts` length or `selectedTrust`. It's currently unused in the UI, but if imported later it will silently mislead logic.  
**User impact:** Theoretical (dead code), but exported and dangerous.  
**Fix:** Change to `isTrustHolder(form) && hasMultipleTrustsAvailable(trusts, selectedTrust)`.

---

## 9. MAJOR — `loadOverviewData` swallows all errors silently (no user feedback)  
**File:** `hooks.js:19-28`  
**Detail:** If `/beneficiaries/dashboard` returns non-OK or throws, `loadOverviewData` logs to console and does nothing. The user sees empty tabs with no explanation.  
**User impact:** Real — on backend errors or network issues, the user thinks there is simply no data.  
**Fix:** Show a toast via `showError` and/or set an `overviewError` state that the tabs can render.

---

## 10. MAJOR — Revoke & Class-delete handlers silently ignore non-OK responses  
**File:** `hooks.js:278-294` (`handleRevoke`), `hooks.js:433-445` (`handleDeleteClassBeneficiary`)  
**Detail:** Both functions check `if (response.ok)` and do nothing in an `else` branch. If the backend returns 400/403/404, the modal stays open, no toast fires, and the user has no feedback.  
**User impact:** Real — user clicks Revoke/Remove, backend rejects it, UI gives zero feedback, modal stays open. User is stuck.  
**Fix:** Add `else { const errBody = await response.json().catch(() => ({})); showError(...); }` to both handlers.

---

## 11. MINOR — Settings modal accepts zero / negative / non-numeric authorized units  
**File:** `Modals.jsx:362-368`, `hooks.js:329-350`  
**Detail:** `parseInt(e.target.value) || 0` turns "abc" into `0` and doesn't prevent `0` or negative values. The backend rejects reduction below active units (good), but the frontend lets the user submit `0` or `-5` before the backend round-trip.  
**User impact:** Minor — backend catches it, but poor UX.  
**Fix:** Add frontend validation: `total_authorized_units` must be > 0 and >= `summary.total_issued_units`.

---

## 12. MINOR — Issue/edit certificate date inconsistency (`issue_date` format)  
**File:** `hooks.js:86-96` (`handleOpenCertificateModal`), `hooks.js:107-117` (`openEditModal`)  
**Detail:** When opening the edit modal via `handleOpenCertificateModal` (line 94), `issue_date` is set with `.split('T')[0]`. When opening via `openEditModal` (line 115), it uses the raw `certificate.issue_date` (possibly ISO with `T`). The `<input type="date">` may misbehave with an ISO datetime string.  
**User impact:** Real — the date input may appear blank or wrong when editing from Overview tab vs Certificates tab.  
**Fix:** Standardize both paths to `.split('T')[0]`.

---

## 13. MINOR — Mobile tab list can overflow awkwardly; 5-tab horizontal list has no scroll  
**File:** `BeneficiariesPage.js:127-148`  
**Detail:** `TabsList` has `flex flex-wrap gap-1` which causes wrapping on narrow screens. The 5 tabs (People, Overview, Ownership Shares, Transfer History, Class Beneficiaries) wrap to 2-3 lines, eating vertical space and looking cramped. No `overflow-x-auto` or scroll snap is provided.  
**User impact:** Real — on iPhone SE / small Android devices the tab bar wraps and pushes content down.  
**Fix:** Consider `overflow-x-auto whitespace-nowrap` on `TabsList` with scroll snap, or collapse to an icon-only mode below `sm`.

---

## 14. MINOR — `OverviewTab.jsx` references `overviewData.unit_label` which may not exist at top level  
**File:** `OverviewTab.jsx:64`  
**Detail:** Line 64 uses `{overviewData.unit_label}s` (e.g., "Units"). The `/beneficiaries/dashboard` endpoint returns `unit_label` under `settings` in the certificates/summary data, not necessarily at the top level of the dashboard response. If absent, it renders "undefineds".  
**User impact:** Real if the backend shape drifts; currently may show wrong label.  
**Fix:** Derive label from `summary?.settings?.unit_label || 'Unit'` and pass it down, or verify backend always returns it at top level.

---

## 15. MINOR — Class Beneficiaries percentage input accepts >100 and negative values  
**File:** `Modals.jsx:476-485` (`AddClassBeneficiaryModal`)  
**Detail:** The percentage `<input>` has `min="0" max="100"` but no JavaScript validation. `handleAddClassBeneficiary` (hooks.js:415) does `parseFloat(...) || 0` with no range check. Backend may or may not reject >100.  
**User impact:** Theoretical — depends on backend validation.  
**Fix:** Add `if (pct < 0 || pct > 100)` guard before POST.

---

## 16. MINOR — `DeleteClassModal` calls `handleDeleteClassBeneficiary` synchronously then immediately `setDeleteConfirmClass(null)` even on failure  
**File:** `Modals.jsx:421`  
**Detail:** The confirm button fires `handleDeleteClassBeneficiary(...); setDeleteConfirmClass(null);` sequentially. If the async delete fails, the modal is already closed and the error toast appears with no context.  
**User impact:** Minor — error shown after modal closed, less clear what failed.  
**Fix:** Move `setDeleteConfirmClass(null)` into the success branch of `handleDeleteClassBeneficiary`, or return a promise from the handler and await it.

---

## 17. MINOR — `isFullyAllocated` uses strict `=== 0` which breaks with floating-point  
**File:** `constants.js:142-143`  
**Detail:** `isFullyAllocated` does `summary.remaining_units === 0`. If `remaining_units` is `0.0001` due to floating-point math (fractional units), the predicate is false even though no meaningful units remain.  
**User impact:** Theoretical — unlikely with current data shapes, but brittle.  
**Fix:** Use `summary.remaining_units <= 0.0001` or `Math.abs(summary.remaining_units) < 1e-9`.

---

## Summary Table

| # | Severity | File:Line | Issue | Real User-Facing? |
|---|----------|-----------|-------|-------------------|
| 1 | **BLOCKING** | `OverviewTab.jsx:1` / `~80` | Missing `Link` import → crash on expand | ✅ Yes |
| 2 | **BLOCKING** | `hooks.js:341-342` | Settings save uses stale ref callbacks | ✅ Yes |
| 3 | **MAJOR** | `hooks.js:238-247` | Transfer sends name strings, not cert IDs | ✅ Yes |
| 4 | **MAJOR** | `hooks.js:221-261` | No self-transfer guard | ⚠️ Theoretical |
| 5 | **MAJOR** | `hooks.js:221-261` | No pre-validation of sender's unit balance | ✅ Yes |
| 6 | **MAJOR** | `PeopleTab.jsx`, `OverviewTab.jsx` | Fully-allocated banner missing; Add btn active | ✅ Yes |
| 7 | **MAJOR** | `hooks.js:17,31-48` | `loading` only tracks certs, not overview | ✅ Yes |
| 8 | **MAJOR** | `constants.js:139-140` | `canSelectTrustHolder` always true | ⚠️ Dead code |
| 9 | **MAJOR** | `hooks.js:19-28` | `loadOverviewData` swallows errors silently | ✅ Yes |
| 10 | **MAJOR** | `hooks.js:278-294`, `433-445` | Revoke/delete ignore non-OK responses | ✅ Yes |
| 11 | **MINOR** | `Modals.jsx:362-368` | Settings accepts 0 / negative units | ✅ Yes |
| 12 | **MINOR** | `hooks.js:86-117` | Inconsistent `issue_date` format on edit | ✅ Yes |
| 13 | **MINOR** | `BeneficiariesPage.js:127-148` | Tab list wraps poorly on mobile | ✅ Yes |
| 14 | **MINOR** | `OverviewTab.jsx:64` | `overviewData.unit_label` may be undefined | ✅ Yes |
| 15 | **MINOR** | `Modals.jsx:476-485` | Class % accepts >100, no JS guard | ⚠️ Theoretical |
| 16 | **MINOR** | `Modals.jsx:421` | Delete modal closes before async completes | ✅ Yes |
| 17 | **MINOR** | `constants.js:142-143` | Strict `=== 0` with floats | ⚠️ Theoretical |

---

**Recommended next steps (in priority order):**
1. Fix the missing `Link` import in `OverviewTab.jsx` (#1) — one-liner, unblocks users.
2. Fix settings-save stale-ref issue (#2) — pass callbacks directly or use a promise-based reload.
3. Add transfer pre-validation (#4, #5) and consider switching the API to `certificate_id`-based transfers (#3) — requires backend + frontend coordination.
4. Surface the fully-allocated state on People/Overview tabs (#6) — add conditional banner/disable button.
5. Fix silent error swallowing in `loadOverviewData`, revoke, and class-delete (#9, #10) — improves user trust.
