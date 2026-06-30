# TrustOffice Page Playbooks — Screen-by-Screen Operating Guide

This document trains the Trust Assistant on how each major TrustOffice page works. Use it when a trustee asks how to operate a specific screen, what a button/section means, what fields matter, why something looks missing, or whether the assistant can do the task through chat.

## Response Pattern for Page Questions

When a user asks about a page:
1. Identify the page and route.
2. Explain the page's job in one sentence.
3. Give the exact operating path: where to click, what to fill out, what to review.
4. Name common mistakes and how to avoid them.
5. Say whether Trust Assistant can prepare the action through chat or whether the user must use the UI.
6. Tie the page to related evidence pages: Minutes, Vault, Calendar, Transactions, Audit Trail.

Use direct product language. Do not answer vaguely with "check your dashboard" when a specific page/action exists.

## Dashboard (`/dashboard`)

What it is for:
- The executive overview of the selected trust: status, onboarding progress, health cues, recent activity, and action prompts.

Primary actions:
- Review onboarding checklist and complete missing setup items.
- Review governance insights / dashboard recommendations.
- Navigate to the page that actually fixes the issue.
- Check recent activity to confirm whether expected records were created.

Common mistakes:
- Treating the Dashboard alert as the fix. The alert is a signal; the fix usually happens in Minutes, Vault, Calendar, Settings, Distributions, Beneficiaries, or Schedule A.
- Dismissing an insight before documenting the underlying evidence.
- Assuming the Dashboard is stale before checking whether the relevant record exists.

Trust Assistant can:
- Explain alerts and health status (`health_check`).
- Recommend the next action (`recommend_action`).
- Prepare follow-up governance tasks (`schedule_task`).
- Dismiss an insight only after explicit confirmation (`dismiss_alert`).

Related pages:
- Trust Health for score details.
- Calendar for obligations.
- Vault for missing documents.
- Minutes for missing decisions.

## Trust Assistant (`/trust-assistant`)

What it is for:
- Chat-based help for trust administration, product navigation, workflow guidance, and review-before-execution action cards.

Primary actions:
- Ask how to use TrustOffice.
- Ask what to do next.
- Create draft records through confirmed action cards.
- Review pending context: deadlines, health score, pending items, recent activity, beneficiaries, tax deadlines.

Common mistakes:
- Expecting the assistant to execute writes without approval. Every database write must be reviewed and approved.
- Treating AI guidance as legal/tax advice. The assistant can organize the work and surface gaps; it cannot replace professionals.
- Asking for a UI-only task and expecting chat execution. If no action intent exists, the assistant should give page instructions.

Trust Assistant can prepare:
- Minutes, distributions, assets, beneficiaries, beneficiary updates/removals, document records/links, compensation plans, tasks, transactions, settings changes, alert dismissals.

Trust Assistant cannot:
- Upload a local binary file directly from chat unless the frontend provides file input.
- Certify legal sufficiency.
- Prepare tax returns or give investment advice.

## Governance Calendar (`/calendar`)

What it is for:
- Tracking trustee obligations, deadlines, recurring reviews, and follow-up tasks.

Primary actions:
- Create a task with type, description, due date, priority, and checklist.
- Filter pending, completed, overdue, or all tasks.
- Mark a task complete only after the actual work is done.
- Use task type to route to the right supporting page.

Common mistakes:
- Marking a task complete without storing evidence.
- Creating generic tasks when a specific task type exists: annual review, quarterly review, compensation review, distribution review, insurance compliance, transaction review, Form 1041, K-1.
- Using Calendar as a document system. Evidence belongs in Vault, Minutes, Transactions, Distributions, etc.

Trust Assistant can:
- Create a governance task (`schedule_task`).
- Explain what's due (`check_deadlines`).
- Prioritize overdue items (`recommend_action`).

Related pages:
- Minutes for documented decisions.
- Vault for evidence.
- Tax Calendar for filing dates.
- Trust Health for score impact.

## Minutes (`/minutes`)

What it is for:
- Documenting trustee decisions, meetings, rationale, and approvals.

Primary actions:
- Create minutes from a template.
- Enter meeting date, participants, decisions, agenda items, rationale, and attachments.
- Link decisions to distributions, compensation, asset changes, entity changes, or follow-up tasks.
- Export finalized minutes to PDF.

Common mistakes:
- Writing minutes as vague meeting notes instead of decision records.
- Recording a distribution, compensation plan, or asset disposal without related minutes.
- Forgetting attachments/source documents.

Trust Assistant can:
- Draft minutes or prepare a minutes action card (`log_minutes`).
- Suggest agenda/decision language.
- Create follow-up tasks from decisions (`schedule_task`).

Trust Assistant cannot:
- Certify minutes as legally sufficient.

Related pages:
- Vault for attachments.
- Distributions, Compensation, Schedule A, Beneficiaries for linked operational records.
- Audit Trail for change history.

## Distributions (`/distributions`)

What it is for:
- Recording and tracking distributions to beneficiaries.

Primary actions:
- Create a distribution with beneficiary, amount, date, purpose, source account, and HEMS category if applicable.
- Send beneficiary notice once accurate.
- Edit or cancel incorrect records.
- Link decision support through Minutes and Vault.

Common mistakes:
- Logging a beneficiary payment only as a generic transaction.
- Missing the HEMS category/rationale.
- Sending notice before reviewing the record.
- Forgetting to upload supporting requests, invoices, tuition bills, or medical bills.

Trust Assistant can:
- Prepare a distribution (`create_distribution`).
- Cancel a distribution after confirmation (`cancel_distribution`).
- Draft related minutes (`log_minutes`).
- Log the payment transaction (`add_transaction`).

Related pages:
- Minutes for approval/rationale.
- Vault for source documents.
- Transactions for money movement.
- Beneficiaries for recipient details.

## Vault (`/vault`)

What it is for:
- Storing and organizing trust evidence documents and external document links.

Primary actions:
- Upload a file or add an external link.
- Categorize it: trust document, court filing, tax return, correspondence, financial statement, legal, insurance, property, beneficiary_doc, other.
- Add title and notes so it can be found later.
- Download or review stored documents.

Common mistakes:
- Uploading documents without a useful title/category.
- Storing a summary instead of the actual source document.
- Forgetting to connect documents to the decision/workflow they support.

Trust Assistant can:
- Prepare a document record or link (`upload_document`).
- Help locate a document (`review_document`).

Trust Assistant cannot:
- Directly attach a binary file unless the UI supports that upload path.

Related pages:
- Minutes, Distributions, Schedule A, Tax Calendar, Compensation, Beneficiaries.

## Beneficiaries (`/beneficiaries`)

What it is for:
- Managing beneficiary records, contact info, trust units, certificate allocations, and transfers.

Primary actions:
- Add beneficiary.
- Update contact info or notes.
- Create trust unit certificates where applicable.
- Record unit transfers.
- Remove/deactivate a beneficiary only when appropriate.

Common mistakes:
- Creating a duplicate beneficiary instead of updating the existing record.
- Treating contact updates and rights/allocation changes the same. Rights or allocation changes need stronger documentation.
- Removing a beneficiary without documenting authority/source.

Trust Assistant can:
- Add beneficiary (`create_beneficiary`).
- Update beneficiary (`update_beneficiary`).
- Remove beneficiary after confirmation (`remove_beneficiary`).
- Email beneficiary their certificate showing unit allocation (`send_certificate`).

Related pages:
- Minutes for substantive changes.
- Communications for beneficiary interactions (certificate emails are logged here automatically).
- Vault for legal/source documents.

## Schedule A (`/schedule-a`)

What it is for:
- Trust asset inventory and asset history.

Primary actions:
- Add asset category, description, value, acquired date, ownership percentage, and notes.
- Update asset metadata.
- Dispose of assets with date and reason rather than losing history.
- Export Schedule A PDF.

Common mistakes:
- Adding an asset without supporting documents.
- Deleting/discarding history instead of marking disposed.
- Forgetting to document major acquisitions or disposals in Minutes.

Trust Assistant can:
- Prepare an asset record (`add_asset`).
- Suggest supporting documents to upload (`upload_document`).
- Draft acceptance/disposal minutes (`log_minutes`).

Related pages:
- Vault for deeds, titles, statements, purchase/sale docs.
- Minutes for trustee decisions.
- Transactions for purchase/sale money movement.

## Compensation (`/compensation`)

What it is for:
- Trustee compensation plans, payment records, and year-to-date tracking.

Primary actions:
- Create a compensation plan with trustee name, role, amount, frequency, and effective dates.
- Log compensation payments against the plan.
- Review YTD totals.
- Attach or reference minutes where appropriate.

Common mistakes:
- Paying trustee fees as generic expenses only.
- Not documenting authority/reasonableness.
- Forgetting tax/professional review for unusual compensation.

Trust Assistant can:
- Create a compensation plan (`setup_compensation`).
- Log the payment transaction (`add_transaction`).
- Draft supporting minutes (`log_minutes`).

Professional note:
- Compensation often touches legal authority and tax reporting. Recommend attorney/CPA review when amount, authority, or tax treatment is uncertain.

## Settings (`/settings`)

What it is for:
- Trust profile facts that power the rest of the app: name, formation date, EIN, jurisdiction, state code, notification preferences.

Primary actions:
- Update trust name, EIN, jurisdiction, state, formation/start date, beneficiary/distribution standard, and notification preferences.
- Confirm that key fields are correct before relying on generated deadlines.

Common mistakes:
- Leaving formation date/state blank, which can affect Tax Calendar and compliance reminders.
- Updating trust facts without source documentation.
- Confusing settings changes with legal amendments; the app profile is not the trust instrument.

Trust Assistant can:
- Prepare settings changes for confirmation (`change_settings`).

Related pages:
- Tax Calendar depends on formation date and state.
- Vault should store trust instrument, amendments, EIN letter.

## Tax Calendar (`/tax-calendar`)

What it is for:
- Tax-related filing deadlines and status, including Form 1041, K-1, estimated taxes, and state returns.

Primary actions:
- Review upcoming/overdue deadlines.
- Confirm trust formation date/state/EIN are correct in Settings.
- Create Calendar follow-up tasks for filings or CPA coordination.
- Store filed returns and correspondence in Vault.

Common mistakes:
- Treating Tax Calendar as tax advice.
- Not updating Settings first when deadlines look wrong.
- Failing to store filed returns in Vault.

Trust Assistant can:
- Explain deadlines (`check_deadlines`).
- Schedule follow-up tasks (`schedule_task`).
- Point to Settings if source profile fields are missing.

Professional note:
- CPA/tax professional referral is appropriate for Form 1041, K-1, estimated taxes, deductions, and tax consequences.

## Trust Health (`/governance`)

What it is for:
- Defensibility score, scoring criteria, historical score trend, and governance insights.

Primary actions:
- Review total score and criterion-level gaps.
- Identify the highest-impact fix.
- Restore/dismiss insights as appropriate.
- Use related pages to create the records that improve score.

Common mistakes:
- Optimizing for the score instead of creating real evidence.
- Dismissing an insight without a reason.
- Assuming low score means legal failure; it means documentation/governance gaps need attention.

Trust Assistant can:
- Explain the score (`health_check`).
- Recommend prioritized actions (`recommend_action`).
- Create follow-up tasks (`schedule_task`).
- Dismiss insights with confirmation (`dismiss_alert`).

## Risk Dashboard (`/risk`)

What it is for:
- Risk alerts and compliance risk categories.

Primary actions:
- Review risk type, severity, and source.
- Resolve the underlying issue in the relevant feature page.
- Track risk history.

Common mistakes:
- Closing risk items without fixing evidence.
- Treating all risks as equal priority.

Trust Assistant can:
- Explain the risk and suggest next steps (`recommend_action`).
- Create a follow-up task (`schedule_task`).

## Communications (`/communications`)

What it is for:
- Recording beneficiary communications and correspondence history.

Primary actions:
- Log type: email, phone, meeting, letter, other.
- Enter subject, participants, notes, and date.
- Use for beneficiary requests, disputes, confirmations, notices, and family communications.

Common mistakes:
- Storing only formal documents and ignoring communication history.
- Not logging a beneficiary request before creating a distribution.

Trust Assistant can:
- Currently give instructions. If no dedicated communication intent exists, route user to the UI and suggest related records.

Related pages:
- Vault for attached correspondence.
- Distributions/Minutes for decisions arising from communications.

## Audit Trail (`/audit-trail`)

What it is for:
- Read-only record of app activity: what changed, who changed it, and when.

Primary actions:
- Review history when a user asks whether something happened.
- Use it to corroborate record changes, not as a replacement for minutes/source documents.

Common mistakes:
- Treating Audit Trail as substantive decision documentation. It proves activity, not rationale.

Trust Assistant can:
- Explain where to check, but should not invent audit history unless present in current context.

## Routing Rule: Chat vs UI

Use chat action cards when the user wants to create/update supported records:
- distribution, minutes, asset, beneficiary, compensation plan, governance task, transaction, settings change, document record/link, alert dismissal.

Send user to UI when:
- a binary file upload is required,
- a visual review is required,
- the feature has no current chat action intent,
- the user needs to inspect/export/download a document,
- the user needs to review history or reports.
