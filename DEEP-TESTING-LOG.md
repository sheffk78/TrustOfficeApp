# TrustOffice Deep Testing Log

## Feature #1: Minutes Flow
**Date:** 2026-07-13  
**Agents:** 4 (Functional, UX/Visual, API/Data, Cross-Feature)  
**Pages tested:** MinutesPage, CreateMinutesPage, MinutesTemplateFormPage, MinutesDetailPage, MinutesTemplatesPage  
**Backend:** minutes.py (4175 lines), guided_minutes.py (482 lines)  

---

### Fixes Applied (15 items)

#### Frontend - MinutesDetailPage.js
1. **[FIXED] PDF error handler references undefined `error` variable** - Line 120. Would throw ReferenceError on non-OK API response. Replaced with `new Error('Failed to generate PDF')`.
2. **[FIXED] PDFPreviewModal reset uses wrong state shape** - Line 477. Reset `url: null` instead of `data: null`, causing stale PDF to persist. Fixed to clear `data` and `filename`.
3. **[FIXED] AI Generated badge uses raw purple colors** - Line 230. Replaced `bg-purple-100 text-purple-700` with brand tokens `bg-gold/10 text-gold`.
4. **[FIXED] Draft badge uses raw red colors** - Line 237. Replaced `bg-red-100 text-red-700` with `bg-warning/10 text-warning`.
5. **[FIXED] Finalized badge uses raw green colors** - Line 243. Replaced `bg-green-100 text-green-700` with `bg-success/10 text-success`.
6. **[FIXED] Section content uses font-mono** - Line 432. Meeting minutes body text in monospace. Changed to sans-serif.
7. **[FIXED] Full minutes content uses font-mono** - Line 463. Changed to sans-serif.
8. **[FIXED] Edit textarea uses font-mono** - Line 457. Changed to sans-serif for readability.
9. **[FIXED] Edit mode inputs missing input-trust class** - Lines 342, 352. Added `input-trust` for brand consistency.

#### Frontend - MinutesPage.js
10. **[FIXED] Infinite loading skeleton when no trust selected** - Loading state never cleared if no trust. Added early return with "Select a Trust" empty state + `setLoading(false)` in else branch.
11. **[FIXED] Drafts appear in both drafts section and main list** - loadMinutes fetched ALL minutes. Added `&status=finalized` filter to exclude drafts from main list.
12. **[FIXED] All PDF buttons spin when one is clicked** - Single `pdfLoading` boolean. Changed to `pdfLoadingId` per-entry tracking.
13. **[FIXED] Template type badges use raw blue colors** - Lines 276, 492. Replaced `bg-blue-100 text-blue-700` with `bg-gold/10 text-gold`.
14. **[FIXED] main-content missing dot-grid class** - Line 187. Added `dot-grid` for consistency with DashboardPage.

#### Frontend - Other Pages
15. **[FIXED] BenevolencePage.js: minutes dropdown never appears** - Line 693. Checked `record.source_type === 'benevolence'` but field is `record.source`. Minutes menu was invisible for all benevolence records.
16. **[FIXED] AuditTrailPage.js: minutes_updated event type never used** - Line 92. Both branches of ternary returned `'minutes_created'`. Changed non-retroactive to `'minutes_updated'`.
17. **[FIXED] DashboardPage.js: recent minutes activity not clickable** - Line 1233. Activity items were plain text. Added link to `/minutes/${activity.id}` for minutes-type activities.
18. **[FIXED] MinutesTemplatesPage.js: button missing btn-secondary class** - Line 104. Added `btn-secondary`.

#### Backend - minutes.py
19. **[FIXED] Autosave bypasses finalize protection (CRITICAL)** - Line 346. Autosave endpoint did not check if record was finalized. Could silently revert finalized minutes to draft and overwrite content. Added 403 check.
20. **[FIXED] Missing user_id filter in autosave read-back (IDOR)** - Line 371. `find_one` after update only filtered by `minutes_id`, not `user_id`. Added `user_id` to filter.
21. **[FIXED] Template PUT allows editing finalized records** - Line 4042. No status check before allowing content updates. Added 403 when status is "final" and generated_document is being modified.
22. **[FIXED] Template DELETE allows deleting finalized records** - Line 4077. No status check before deletion. Added find_one + 403 check for finalized records.
23. **[FIXED] Missing user_id in template update_one and find_one (IDOR)** - Lines 4057, 4068. Added `user_id` to both query filters.

---

### Fix-Later Backlog (21 items)

#### Architecture (P1)
1. **Split-collection architecture**: Template minutes stored in `minutes_templates` collection, never appear in minutes list or detail page. Either unify collections or add cross-collection queries. (minutes.py:132, 489, 3939)
2. **Draft save never called from frontend**: Backend has autosave endpoint, MinutesPage has draft "Continue" buttons, but MinutesTemplateFormPage never reads `draft_id` or calls autosave. Entire draft workflow is dead code.
3. **Layout inconsistency**: 4 of 5 Minutes pages use custom wrappers instead of `main-layout > main-content dot-grid > page-container`. Causes spacing differences.
4. **MinutesTemplatesPage is duplicate of CreateMinutesPage**: Legacy page showing flat template grid. Should be deprecated/redirected.

#### UX (P2)
5. **No inline form validation**: 3400-line template form has zero field-level validation. Only one toast error for evaluate_distribution. Users get no field-level feedback.
6. **No loading state in MinutesTemplateFormPage**: Form renders with empty fields while entity data loads, causing visible content shift.
7. **Cognitive overload on CreateMinutesPage**: 35 templates in 8 categories, no search/filter, all visible at once. Needs progressive disclosure or search.
8. **MinutesDetailPage empty state not designed**: "Minutes not found" is plain text, no icon or designed state.
9. **MinutesTemplateFormPage no-trust state not designed**: Plain text, no icon or CTA.
10. **MinutesTemplatesPage no-trust state not designed**: Plain text, no icon or CTA.

#### Cross-Feature (P2)
11. **No calendar-to-minutes connection**: Calendar has quarterly_review/annual_review task types but no link to creating minutes for those reviews.
12. **Printable binder has no actual minutes**: "Resolutions & Minutes" section is just a tab divider. Should include actual minutes content.
13. **Entity detail has no minutes section**: EntityDetailPage shows no minutes related to that entity.
14. **Audit trail events not clickable**: Minutes events in audit trail have no link to view the actual record.
15. **No automatic prompt to create authorizing minutes**: After creating a distribution/compensation/benevolence grant, user must manually find the minutes link in a dropdown.
16. **Trust Assistant prompts are generic**: "I need to document a meeting" doesn't carry trust context. Could reference trust name or recent activity.
17. **Legacy redirect routes in App.js**: `/guided-minutes` and `/retroactive-minutes` still have redirect entries. Should be removed if no inbound links.

#### API/Data (P2)
18. **No status enum validation**: `status` field accepts any string. Should be constrained to `draft` and `finalized`.
19. **Inconsistent "final" vs "finalized"**: Template collection uses "final", minutes_records uses "finalized". Cross-collection queries miss records.
20. **Template PDF missing XML escaping**: Some ReportLab Paragraph branches don't escape `&`, `<`, `>`. Can crash on user content with special chars.
21. **PUT /minutes/{id} uses raw json()**: No Pydantic model for update. No type checking, no OpenAPI docs for request body.

---

### What Was Verified Safe
- All 10 API endpoints return 401 (not 404) when unauthenticated
- Read-only users blocked from all write endpoints (require_write_access)
- Search parameter uses `re.escape()` before MongoDB $regex (no injection)
- Email notification fires async via BackgroundTasks on minutes creation
- PDF generation handles empty content gracefully
- Mobile bottom nav has Minutes entry, works correctly
- NoSQL query user_id is always enforced in queries
- No rounding violations (rounded-lg/md/xl) in any Minutes page

---

## Feature #2: Vault + Trust Assistant
**Date:** 2026-07-13
**Agents:** 4 (Functional, UX/Visual, API/Data, Cross-Feature)
**Pages tested:** VaultPage, TrustAssistantPage, FileUploadCard, ChatPanel, TrustDocumentSummary, useAnalysisPolling
**Backend:** vault.py (511 lines), chat.py (1659 lines), chat_service.py (1021 lines), trust_doc_analysis.py (204 lines), external_trust_docs.py (354 lines)

---

### Fixes Applied (22 items)

#### Critical (2)
1. **[FIXED] Vault delete button 404 on every call** - VaultPage.js:288. Called `/trusts/{id}/vault/documents/{id}` but backend route is `/vault/documents/{id}`. Fixed path.
2. **[FIXED] Vault download button 404 on every call** - VaultPage.js:305. Same wrong path prefix. Fixed path.

#### Security (8)
3. **[FIXED] vault_summary aggregation missing user_id** - vault.py:478. count_documents and $match had no user_id filter (IDOR defense-in-depth). Added user_id.
4. **[FIXED] chat_service vault_docs query missing user_id** - chat_service.py:516. Vault metadata query only filtered by trust_id. Added user_id.
5. **[FIXED] chat_service health_score query missing user_id** - chat_service.py:319. Added user_id filter.
6. **[FIXED] chat_service tax_calendar query missing user_id** - chat_service.py:470. Added user_id filter.
7. **[FIXED] chat_service trust_doc_analysis query missing user_id** - chat_service.py:487. Added user_id filter.
8. **[FIXED] trust_doc_analysis.py 3 queries missing user_id** - Lines 28, 43, 56. All analysis queries (complete, pending, failed) had no user_id. Added to all 3.
9. **[FIXED] Beneficiary regex queries not escaped** - chat.py:843, 867. holder_name used in $regex without re.escape(). Could match unintended docs with regex special chars. Added re.escape().
10. **[FIXED] SSE error event leaks exception details** - chat.py:1621. Sent `str(e)` to client, could leak internal paths. Replaced with generic message.

#### Frontend Brand/UX (12)
11. **[FIXED] Critical Documents alert: 6 raw red color violations** - VaultPage.js:373-389. border-red-200, bg-red-50, text-red-600/700/800/400 -> warning tokens.
12. **[FIXED] Upload form: 6 raw gray color violations** - VaultPage.js:460-486. text-gray-400/500/700/900, border-gray-200/300 -> foreground/muted-foreground/navy tokens.
13. **[FIXED] Document cards: 3 raw color violations** - VaultPage.js:598, 605, 616. text-neutral-400 hover:text-red-500, text-emerald-700 bg-emerald-50, font-mono bg-slate-100 text-slate-600 -> brand tokens.
14. **[FIXED] 5 form inputs missing input-trust class** - VaultPage.js:413, 498, 509, 525, FileUploadCard.js:247, 259, 277. Added input-trust.
15. **[FIXED] 2 font-mono on body text** - FileUploadCard.js:288, 317. Error message and uploading status. Removed font-mono.
16. **[FIXED] Cancel button missing btn-secondary** - VaultPage.js:565. Added btn-secondary.
17. **[FIXED] FileUploadCard size limit mismatch** - FileUploadCard.js:41. Was 16MB, VaultPage allows 50MB. Aligned to 50MB.
18. **[FIXED] useAnalysisPolling TDZ circular dependency** - useAnalysisPolling.js:172. stopPolling used in pollOnce deps array before definition. Moved stopPolling before pollOnce.
19. **[FIXED] TrustAssistantPage action errors silently swallowed** - Lines 143, 178, 205. approve/edit/discard catches only console.error. Added toast.error notifications.
20. **[FIXED] handleVideoClick empty no-op** - TrustAssistantPage.js:210. Was `() => {}`. Added toast.info("Video playback coming soon").
21. **[FIXED] ChatPanel paperclip enabled without trust** - ChatPanel.js:318. Clicking paperclip with no trust did nothing. Added disabled when !trustId.
22. **[FIXED] AuditTrailPage missing Vault filter** - AuditTrailPage.js:302. No vault filter despite vault events being fetched. Added { value: 'vault', label: 'Vault' }.
23. **[FIXED] MobileBottomNav missing Vault entry** - MobileBottomNav.js:13. No vault in mobile nav. Added { path: '/vault', icon: FolderOpen, label: 'Vault' }.
24. **[FIXED] TrustDocumentSummary polling fallback** - TrustDocumentSummary.js:49. Only 5s and 15s timeouts. Added 30s fallback for slow analysis.
25. **[FIXED] VaultPage link mode URL validation** - VaultPage.js:140. No client-side https:// check. Added validation before fetch.

---

### Fix-Later Backlog (14 items)

#### Architecture (P1)
1. **VaultPage layout inconsistency**: Uses custom wrapper instead of `main-layout > main-content dot-grid > page-container`. Causes spacing differences vs DashboardPage.
2. **Non-streaming /ai/chat endpoint is dead code**: Frontend only uses streaming. ~130 lines of dead code maintained in parallel.
3. **Chat conversation auto-threading creates orphaned conversations**: 2-hour timeout creates new conversation with no link to old one.

#### UX (P2)
4. **TrustAssistantPage missing no-trust empty state**: No frontend guard for !selectedTrust. Backend returns 404, user sees broken chat UI.
5. **VaultPage search sends partial text on category change**: search state updates on every keystroke but only committed on Enter. Category change triggers loadData with stale partial search.
6. **No file type validation on drag-and-drop in FileUploadCard**: input `accept` only filters file picker, not drag-and-drop.
7. **VaultPage empty state doesn't show missing critical docs**: When vault is empty AND summary.missing_critical has entries, should show guided "Upload Trust Instrument first" state.
8. **No onboarding nudge for vault**: Dashboard onboarding links to /vault but vault page itself doesn't guide new users.

#### Cross-Feature (P2)
9. **Dashboard recent activity excludes vault uploads**: governance.py only queries minutes and distributions. Vault uploads not in dashboard activity.
10. **Chat actions not logged to audit trail**: Chat-initiated governance actions (distributions, minutes, beneficiaries) bypass audit trail entirely.
11. **Dashboard has no vault summary widget**: Vault has /vault/summary endpoint but dashboard doesn't surface it.
12. **SnapshotColumn doesn't show vault documents**: Chat context includes vault docs but snapshot column doesn't display them.
13. **Vault documents cannot be attached to minutes/distributions**: No vault document picker in minutes or distribution creation.
14. **Vault analysis not shared with risk dashboard**: Analysis results stored but not surfaced in risk dashboard.

#### Security (P2)
15. **No magic byte validation on file uploads**: File type relies on client Content-Type header. Malicious file could be uploaded with spoofed type.
16. **File download serves with stored (untrusted) Content-Type**: Could enable XSS if HTML/SVG file uploaded with spoofed type.
17. **Prompt injection risk in chat**: User message directly interpolated into AI prompt without delimiters or sanitization.
18. **Trust context data injected into system prompt without full sanitization**: Trust name at chat_service.py:710 is raw f-string, not JSON-encoded.
19. **No rate limiting on vault upload endpoint**: security.py rate limit bypassed for uploads.

---

### What Was Verified Safe
- All vault and chat endpoints require authentication (get_current_user)
- Direct doc_id/conversation_id lookups include user_id (no IDOR on direct access)
- Vault file upload has 16MB size limit with PDF compression
- No path traversal risk (files stored as BSON binary, not filesystem)
- Search parameter uses re.escape() before MongoDB $regex (no injection)
- Asset lookup queries in chat use re.escape() (no injection)
- Vault uploads/downloads/deletes all log to audit trail
- Trust Assistant has strong context: trust info, vault docs, beneficiaries, entities, deadlines, health score
- Vault "Summarize this document" links to Trust Assistant with prompt
- Mobile nav includes Trust Assistant
- All /vault and /trust-assistant links resolve to registered routes

---

## Feature #3: Dashboard + TrustManager
**Date:** 2026-07-13
**Agents:** 4 (Functional, UX/Visual, API/Data, Cross-Feature)
**Pages tested:** DashboardPage, TrustManager, BankingSummaryCard, SpendingThresholdCard, ComplianceSummaryCard, SeparationAlertsPanel, TrialBanner, SubscriptionGate
**Backend:** governance.py (1277 lines), dashboard.py (5 lines - dead code)

---

### Fixes Applied (30 items)

#### Critical (2)
1. **[FIXED] Dashboard upgrade banner CTA 404** - DashboardPage.js:454. Linked to `/billing` but route is `/settings/billing`. Fixed.
2. **[FIXED] SpendingThresholdCard Review button 404** - SpendingThresholdCard.js:111. Navigated to `/transactions` which has no route. Changed to `/distributions`.

#### Security (3)
3. **[FIXED] /activity endpoint missing trust ownership verification** - governance.py:1068. When trust_id provided, no ownership check. Added trust lookup + 404.
4. **[FIXED] /governance/{trust_id}/history days param unbounded** - governance.py:953. Could pass days=999999. Bounded to 1-365.
5. **[FIXED] Activity feed items never clickable** - DashboardPage.js:1234. Checked `activity.source` but backend returns `activity.type`. Fixed field name.

#### Brand Token Violations (19)
6. **[FIXED] Quick action: Add Asset raw blue** - DashboardPage.js:63. `bg-blue-500/10 text-blue-600` -> `bg-navy/10 text-navy`.
7. **[FIXED] Quick action: Open Bank Account raw purple** - DashboardPage.js:70. -> `bg-gold/10 text-gold`.
8. **[FIXED] Quick action: Appoint Trustee raw orange** - DashboardPage.js:77. -> `bg-warning/10 text-warning`.
9. **[FIXED] Upgrade banner 6 amber/yellow violations** - DashboardPage.js:439-462. All amber/yellow -> warning tokens.
10. **[FIXED] Quarterly draft hero 3 blue violations** - DashboardPage.js:757-761. border-l-blue-400, from-blue-400/20, text-blue-600 -> gold tokens.
11. **[FIXED] Tax deadline overdue row raw red** - DashboardPage.js:991. border-red-200 bg-red-50/50 -> error tokens.
12. **[FIXED] Tax deadline overdue text raw red** - DashboardPage.js:995, 1000. text-red-600 -> text-error.
13. **[FIXED] Tax deadline Filed badge raw emerald** - DashboardPage.js:1010. bg-emerald-100 text-emerald-700 -> success tokens.
14. **[FIXED] Tax deadline Overdue badge raw red** - DashboardPage.js:1012. bg-red-100 text-red-700 -> error tokens.
15. **[FIXED] Tax deadline Pending badge raw slate** - DashboardPage.js:1013. bg-slate-100 text-slate-600 -> navy tokens.
16. **[FIXED] ComplianceSummaryCard 4 score color violations** - Lines 21, 22, 25, 27. emerald/red -> success/error tokens.
17. **[FIXED] ComplianceSummaryCard 4 neutral text violations** - Lines 53, 57, 72, 79. text-neutral-* -> text-muted-foreground.
18. **[FIXED] ComplianceSummaryCard all-current message raw emerald** - Line 84. -> text-success.
19. **[FIXED] SeparationAlertsPanel severityConfig 4 red violations** - Lines 18-22. All red -> error tokens.
20. **[FIXED] SeparationAlertsPanel alert badges 2 red violations** - Lines 161-162. -> error tokens.
21. **[FIXED] SeparationAlertsPanel no-alerts empty state 3 emerald violations** - Lines 190-192. -> success tokens.
22. **[FIXED] SeparationAlertsPanel history status badges emerald/orange** - Line 274. -> success/warning tokens.
23. **[FIXED] SeparationAlertsPanel alert card red icon** - Line 306. text-red-500 -> text-error.
24. **[FIXED] SeparationAlertsPanel AlertCountBadge bg-red-500** - Line 355. -> bg-error.

#### Missing Classes (5)
25. **[FIXED] SeparationAlertsPanel Textarea missing input-trust** - Line 235. Added.
26. **[FIXED] SeparationAlertsPanel Scan button missing btn-secondary** - Line 177. Added.
27. **[FIXED] TrustManager sort select missing input-trust** - Line 695. Added.
28. **[FIXED] TrustManager group select missing input-trust** - Line 713. Added.
29. **[FIXED] DashboardPage Maybe Later button missing btn-secondary** - Line 535. Added.

#### Other UX (2)
30. **[FIXED] TrialBanner pl-64 breaks mobile** - Line 41. Hardcoded 16rem left padding. Changed to `pl-4 lg:pl-64`.
31. **[FIXED] TrialBanner upgrade button not using btn-primary** - Line 61. Replaced custom classes with btn-primary.
32. **[FIXED] Health score hardcoded 115 fallback** - DashboardPage.js:930. Removed `|| 115` fallback, uses max_score from API only.
33. **[FIXED] Activity key collision risk** - DashboardPage.js:1219. Added index to key to prevent duplicate React keys.

---

### Fix-Later Backlog (15 items)

#### Architecture (P1)
1. **dashboard.py is dead code**: 5-line file never imported or mounted. Delete or document.
2. **Dashboard API makes ~28 sequential DB queries**: No asyncio.gather(). Performance bottleneck under load.
3. **Dashboard rate limit too high**: Uses default 100/min despite being expensive. Should be 20/min.
4. **Onboarding state scoped to user_id not trust_id**: Multi-trust users share one onboarding checklist.

#### UX (P2)
5. **DashboardPage no error state on API failure**: Falls through to render with null data, showing zeroed scores. No retry button.
6. **TrialBanner shows no countdown**: Has `trial_days_remaining` data but doesn't display it. Should show "X days left".
7. **BankingSummaryCard silently swallows API errors**: Shows "No bank accounts" on 401/500 instead of error state.
8. **SpendingThresholdCard same silent-swallow**: Shows "0 Active Alerts" in green on API failure.
9. **SeparationAlertsPanel handleScan no else branch**: Non-OK response gets no user feedback.
10. **dismissOnboarding crashes if dashboard is null**: Spread on null produces {}, loses state.
11. **window.location.reload() after undismiss onboarding**: Poor UX, should use local state update.
12. **Weekly briefing cta_prompt can be undefined**: encodeURIComponent(undefined) passes "undefined" string to assistant.

#### Cross-Feature (P2)
13. **Activity feed only returns minutes + distributions**: Missing compensation, expenses, vault uploads, entity changes.
14. **No compliance summary card on dashboard**: ComplianceSummaryCard exists but only used on RiskDashboardPage.
15. **Mobile bottom nav missing Compliance section**: Risk, State Compliance, Audit Trail unreachable from mobile nav.
16. **No vault/beneficiaries quick access on dashboard**: Only in onboarding checklist. No card or quick action post-onboarding.
17. **FullSubscriptionGate is dead code**: Exported but never used. Hard paywall component never wired.

---

### What Was Verified Safe
- All dashboard/governance endpoints require authentication (confirmed via live API probing)
- JWT validation includes token revocation checks
- Dashboard and governance health endpoints verify trust ownership
- Subscription status computed server-side (cannot be faked client-side)
- Health score computed server-side (no injection risk)
- All MongoDB queries filter by user_id (no cross-user data leaks)
- Error messages don't leak internal details
- Security headers present (CSP, HSTS, X-Frame-Options)
- Rate limiting exists (per-user sliding window)
- Subscription gating is server-side via check_feature_access
- Alerts router properly uses require_write_access for mutations
- Onboarding allowlist prevents arbitrary field updates