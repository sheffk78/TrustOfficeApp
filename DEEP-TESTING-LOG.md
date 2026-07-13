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