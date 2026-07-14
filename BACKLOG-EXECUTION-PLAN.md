# TrustOffice Backlog Execution Plan
## Deep Testing Features #4 (Money) + #5 (Structure)

**Total items:** 31 (15 Money + 16 Structure)
**Generated:** 2026-07-13

---

## Execution Strategy

Four batches, ordered by priority then effort. Batches 1-2 can overlap (different files). Batch 3 touches shared backend. Batch 4 is cross-feature integration work.

**Batch sizing for parallel delegation:**
- Batch 1: 13 items, all Low/Low, no interdependencies. 3-4 parallel agents.
- Batch 2: 6 items, Medium priority, CRUD completions. 2-3 parallel agents (file-isolated).
- Batch 3: 3 items, backend pagination + data integrity. Sequential (shared backend files).
- Batch 4: 9 items, cross-feature integration. 2 parallel agents per section (Money integrations vs Structure integrations), but Calendar/TrustAssistant/PrintableBinder appear in both, so those need coordination.

---

## Batch 1: Quick Frontend Fixes (Low/Low)
**Strategy:** 3-4 parallel agents, each takes a file cluster. No file overlaps.

### Agent 1A: Money Quick Fixes (6 items)
| Item | File | Fix |
|------|------|-----|
| Money-D | CompensationPage.js | Header should say "All Years" or filter payment history to current year. Check what `paymentHistory` fetch returns vs what header displays. |
| Money-G | TransactionLedgerPage.js | Add empty state CTA when no entities exist. Pattern: card-trust with icon + "Add your first entity" button linking to /structures. |
| Money-H | InvestmentsPage.js | Wrap deleteInvestment in confirm dialog. Use existing dialog pattern from other pages. |
| Money-I | DistributionsPage.js | Send filterStatus to backend as query param instead of client-side filtering. Check distributions.py list endpoint for status param support. |
| Money-K | AuditTrailPage.js | Fix BenevolenceLogPage `?highlight=` deep link. Check how highlight param is consumed, likely URL param not read on mount. |
| Money-L | DashboardPage.js | Add deep-links from dashboard to Money section pages (/transactions, /distributions, /compensation, /investments, /benevolence). |

### Agent 1B: Structure Quick Fixes (7 items)
| Item | File | Fix |
|------|------|-----|
| Structure-B | CommunicationsPage.js | Wrap formatDate in try/catch. Return "Invalid date" fallback on bad input. |
| Structure-C | CommunicationsPage.js | Add parties input field to the communication form. Backend already accepts it. |
| Structure-F | BeneficiariesPage.js (or dashboard) | Remove most-recent-trust fallback when no trust_id. Show "Select a trust" instead. |
| Structure-G | ScheduleAPage.js | Add date format validation on date_conveyed field. Reject non-date input with toast. |
| Structure-H | entities.py | Validate formation_date format on create_entity. Add Pydantic validator or date parsing check. |
| Structure-J | DashboardPage.js | Add quick link to /structures page in dashboard. |
| Structure-P | StructuralMap component | Fix Partnership border color typo. Check border color class string. |

### Agent 1C: Shared File Coordination
Money-L and Structure-J both touch DashboardPage.js. Assign both to the same agent to avoid merge conflicts. That agent handles all DashboardPage.js changes in one pass.

**Agent 1C = Dashboard fixes only:**
- Money-L: Deep-links to Money section pages
- Structure-J: Quick link to /structures

**Dependency note:** Money-L and Structure-J must be done by the same agent or sequentially.

---

## Batch 2: CRUD Completions (Medium Priority)
**Strategy:** 3 parallel agents, each owns a page or page cluster. No file overlaps.

### Agent 2A: Transaction Ledger + Investments (3 items)
| Item | File | Fix |
|------|------|-----|
| Money-A | TransactionLedgerPage.js | Add inline edit for individual transactions. Needs: edit button per row, edit dialog with fields, PUT/PATCH call to transactions endpoint. Backend update endpoint already exists. |
| Money-E | InvestmentsPage.js | Build edit/update flow. Backend PATCH endpoint exists at /trusts/{id}/investments/{inv_id}. Add edit button, edit dialog with fields, PATCH call. |
| Money-H | InvestmentsPage.js | (Carried from Batch 1 if not done) Confirm dialog on delete. |

### Agent 2B: Benevolence (2 items)
| Item | File | Fix |
|------|------|-----|
| Money-B | BenevolencePage.js | Add delete and edit for benevolence records. Check backend for DELETE/PATCH endpoints. If missing, add to benevolence backend. Add UI: edit button, delete button with confirm, edit dialog. |
| Money-F | BenevolencePage.js | Harden duplicate data merging. Replace amount+date+name match with a stable unique key (record ID or hash). Prevents false dedup merges. |

### Agent 2C: Distributions + Beneficiaries + Schedule A (3 items)
| Item | File | Fix |
|------|------|-----|
| Money-C | DistributionsPage.js | Add delete functionality. Check backend for DELETE endpoint. Add delete button with confirm dialog. May need backend DELETE route. |
| Structure-A | BeneficiariesPage.js | Fix transfer dropdown to use beneficiary ID instead of holder_name as value. Prevents collision when two beneficiaries share a name. |
| Structure-D | ScheduleAPage.js | Fix handleEdit to preserve minutes_ref when editing an asset. Currently drops the field on edit save. |

---

## Batch 3: Backend Infrastructure (Medium/Medium)
**Strategy:** Sequential. All touch backend list endpoints or shared backend patterns.

| Item | Files | Fix |
|------|-------|-----|
| Money-J | distributions.py, compensation.py | Add pagination to list endpoints. Replace to_list(1000) with skip/limit params. Add total count to response. Update frontend to handle paginated response. |
| Structure-E | entities.py, schedule_a.py, beneficiaries.py, communications.py | Add pagination across all Structure list endpoints. Same pattern: skip/limit params, total count, frontend updates. |
| Money-F | BenevolencePage.js (backend) | If not resolved in Batch 2, harden dedup logic in backend. |

**Order:** Money-J first (establishes the pagination pattern), then Structure-E applies same pattern to 4 endpoints.

**Frontend impact:** Every page consuming these endpoints needs to handle the new paginated response shape. Batch 3 agent should update all consuming frontend pages in the same pass.

---

## Batch 4: Cross-Feature Integration (Low Priority / High Effort)
**Strategy:** 2 parallel tracks. Money integrations and Structure integrations run concurrently, but shared target pages (Calendar, TrustAssistant, PrintableBinder) need coordination.

### Track 4A: Money Section Integrations (3 items)
| Item | Target | Fix |
|------|--------|-----|
| Money-M | Calendar | Auto-populate Money events: distribution dates, compensation payment dates, investment records. Need backend calendar endpoint to query Money section data. |
| Money-N | TrustAssistantPage / chat_service.py | Add Money section API access to Trust Assistant context. Inject distributions, compensation, investments, transactions data into chat context. |
| Money-O | PrintableBinder / Vault | Add Money section data to printable binder. Include transaction ledger, distribution history, compensation summary, investment portfolio. |

### Track 4B: Structure Section Integrations (5 items)
| Item | Target | Fix |
|------|--------|-----|
| Structure-I | StructuralMap component | Make nodes clickable, navigate to entity detail page on click. |
| Structure-K | PrintableBinder | Add Structure data: entity org chart, beneficiary list, Schedule A assets, relationship map. |
| Structure-L | RiskDashboardPage | Add Structure API integration: entity count, beneficiary count, Schedule A total value. Surface as risk factors. |
| Structure-M | Calendar | Add Structure events: entity formation dates, beneficiary review dates, Schedule A conveyance dates. |
| Structure-N | TrustAssistantPage / chat_service.py | Add Structure section data to Trust Assistant context: entities, beneficiaries, Schedule A summary. |
| Structure-O | MobileBottomNav.js | Add Structure section pages to mobile nav: /structures, /beneficiaries, /schedule-a, /communications. |

### Coordination Points
Three target files are touched by both tracks:
1. **Calendar** (Money-M + Structure-M): One agent should handle both, or sequential with clear interface.
2. **TrustAssistant / chat_service.py** (Money-N + Structure-N): Same, one agent for both.
3. **PrintableBinder** (Money-O + Structure-K): Same, one agent for both.

**Recommended:** Assign Calendar, TrustAssistant, and PrintableBinder each to a single agent that handles both Money and Structure integration for that target.

### Batch 4 Refined Assignment:
- **Agent 4-1:** Calendar (Money-M + Structure-M)
- **Agent 4-2:** TrustAssistant/chat_service (Money-N + Structure-N)
- **Agent 4-3:** PrintableBinder (Money-O + Structure-K)
- **Agent 4-4:** RiskDashboard (Structure-L only)
- **Agent 4-5:** StructuralMap (Structure-I only)
- **Agent 4-6:** MobileBottomNav (Structure-O only)

6 agents, all file-isolated, fully parallel.

---

## Dependency Graph

```
Batch 1 (parallel, no deps)
  |
  v
Batch 2 (parallel, no deps on Batch 1 except Money-H if deferred)
  |
  v
Batch 3 (sequential, depends on Batch 2 CRUD endpoints existing)
  |
  v
Batch 4 (parallel, benefits from Batch 3 pagination for data loading)
```

**Hard dependencies:**
- Batch 3 pagination MUST complete before Batch 4 integration work (otherwise integration code uses unpaginated endpoints)
- Structure-D (minutes_ref fix) should complete before Structure-K (PrintableBinder Structure data) to ensure clean data
- Money-B (benevolence edit/delete) should complete before Money-O (PrintableBinder Money data)

**Soft dependencies:**
- Money-H (delete confirm) can be done in Batch 1 or Batch 2, doesn't block anything
- Money-F (dedup hardening) can be done in Batch 2 or Batch 3, only blocks nothing

---

## Effort Summary

| Batch | Items | Est. Effort | Parallel Agents | Est. Wall Time |
|-------|-------|-------------|-----------------|----------------|
| 1 | 13 | All Low/Low | 3 | 1-2 hours |
| 2 | 6 | Medium/Medium | 3 | 3-4 hours |
| 3 | 3 | Medium/Medium | 1 (sequential) | 2-3 hours |
| 4 | 9 | Low/High | 6 | 4-6 hours |
| **Total** | **31** | | | **10-15 hours** |

---

## Verification Checklist

After each batch:
1. Build succeeds (npm run build)
2. Railway auto-deploy confirms live
3. Spot-check affected pages load without console errors
4. Verify read-only guard still blocks new write endpoints
5. Verify user_id filter present in any new backend queries

After all batches:
1. Full regression: navigate every page in the app
2. Check audit trail captures new CRUD operations
3. Verify mobile nav includes all new routes
4. Confirm brand tokens used in all new UI (no raw Tailwind colors)
5. Run through the original deep-testing log checklist to confirm no regressions

---

## Risk Notes

- **Batch 3 pagination** changes API response shape. Every consuming frontend page must be updated in the same pass. Risk of breaking pages if partially deployed.
- **Batch 4 integration** adds significant data to Calendar, TrustAssistant, and PrintableBinder. Need to verify these pages handle the additional data without performance degradation.
- **Structure-A** (beneficiary transfer dropdown) changes the value field from holder_name to ID. Any existing transfer records using holder_name need migration or backward compatibility.
- **Money-B** (benevolence delete/edit) may need new backend endpoints if they don't exist. Check before starting.
- **Money-C** (distributions delete) same, may need new backend DELETE endpoint.