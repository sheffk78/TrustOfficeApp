# Trust Assistant Design Review

_Created: 2026-06-30_

## Trust Assistant Improvements — Proactive Guidance & Certificate Emailing

### What Changed

Three capability gaps were identified and addressed:

1. **Missing-info prompting was weak** — The action extractor flagged missing required fields but the system prompt didn't enforce conversational clarification. Users would see technical field names instead of natural questions.

2. **No proactive offers after beneficiary actions** — Adding a beneficiary or updating allocations didn't trigger any follow-up suggestions. The assistant was reactive only.

3. **No certificate emailing** — Beneficiary emails were on file, unit allocations were calculated, and the email service had templated sending, but there was no way to email a beneficiary their certificate showing their unit allocation.

### What Was Built

#### 1. Conversational Missing-Field Prompting

**Files changed:** `prompts/chat_system.md`, `prompts/action_extractor.md`

- System prompt now requires the assistant to ask for missing info in plain language ("What's Jane's email address?" not "Missing field: email")
- Action extractor prompt has strong clarification rules with good/bad examples
- Beneficiary creation: name is required, email/allocation are optional and non-blocking. The assistant generates the card with whatever data was provided and mentions what else could be added.
- User guidance: when users don't know what to do, the assistant points to the specific page, explains what they'll do there, and offers to start the action through chat.

#### 2. Proactive Offers After Beneficiary Actions

**Files changed:** `prompts/chat_system.md`, `knowledge/13-trustoffice-workflows.md`

- After a beneficiary is added or their allocation is updated, the assistant proactively offers to:
  - Email the beneficiary their certificate showing unit allocation (`send_certificate` intent)
  - Document the change in meeting minutes (`log_minutes` intent)
- Not mandatory for every case, but offered when it makes sense (new beneficiaries with units, allocation updates, first-time certificates).

#### 3. Certificate Emailing (New Feature)

**Files changed (11 total):**

| Layer | File | Change |
|-------|------|--------|
| Email template | `email_templates.py` | New `certificate_notice` template with certificate number, holder, units, unit label, percentage, issue date |
| Email service | `email_service.py` | New `send_certificate_notice()` method + `datetime` import |
| Action registry | `action_registry.py` | New `send_certificate` action definition with fields (beneficiary_name required, email/notes optional) |
| Action execution | `routers/chat.py` | New `certificate_preview` in ACTION_EXECUTION_MAP + full execution logic: looks up active certificates, aggregates units, calculates percentage, sends email, logs to Communications |
| Intent classifier | `prompts/intent_classifier.md` | New `send_certificate` intent with trigger examples |
| System prompt | `prompts/chat_system.md` | New `send_certificate` intent listed + proactive guidance rules |
| Action extractor | `prompts/action_extractor.md` | New send request extraction rules + certificate output format example |
| Knowledge: workflows | `knowledge/13-trustoffice-workflows.md` | `send_certificate` added to beneficiary workflow actions |
| Knowledge: playbooks | `knowledge/14-trustoffice-page-playbooks.md` | `send_certificate` added to Beneficiaries page actions |
| Knowledge: features | `knowledge/12-trustoffice-features.md` | Certificate emailing feature documented, common questions table updated, "no AI intents" list updated |
| Frontend: ActionCard | `frontend/src/components/ActionCard.js` | New `certificate_preview` type config with Mail icon |
| Frontend: ActionEditModal | `frontend/src/components/ActionEditModal.js` | New `certificate_preview` field definitions + type label |

### How It Works (End-to-End Flow)

1. User says "Add Jane as a beneficiary" without an email or allocation.
2. Assistant asks conversationally: "I can add Jane as a beneficiary. I'll need her email address and the percentage of units she should receive. Do you want to specify those now, or should I create the record with just her name and you can add details later?"
3. User provides details or says "just add her for now" — assistant generates action card.
4. User approves the action card — Jane is added to the database, Beneficiaries page and dashboard update automatically.
5. Assistant proactively offers: "Would you like me to email Jane her certificate showing her unit allocation?"
6. User says yes — `send_certificate` intent fires, action card appears showing Jane's name and the email on file.
7. User approves — system looks up Jane's active certificates, aggregates units across all certificates, calculates percentage of total authorized units, sends branded email with certificate details, and logs the communication to the Communications page.
8. If no email is on file and user didn't provide one — system returns a clear error: "No email address on file for Jane. Provide an email address or update the beneficiary record first."

### Data Flow

```
User message
  → intent_classifier.md classifies as `send_certificate`
  → action_extractor.md extracts beneficiary_name, optional email/notes
  → action_registry.py looks up action definition (`certificate_preview` type)
  → ActionCard.js renders the card with Mail icon
  → User approves
  → chat.py execute_action: `send_certificate` endpoint_type
    → Looks up active certificates in `trust_unit_certificates` collection
    → Aggregates units, gets trust name + unit settings from `trusts` + `trust_unit_settings`
    → Calls email_service.send_certificate_notice()
    → Logs to `communications` collection
  → ActionCard.js shows success result
```

### Error Cases Handled

- No active certificate found for the named beneficiary
- No email address on file and no override provided
- Email service failure (returns error to user via action card execution result)

### What Was NOT Built (Intentionally Out of Scope)

- Creating new trust unit certificates via chat (still a manual page action)
- Attaching PDF copies of certificates to the email (text/HTML only for now)
- Bulk certificate emailing to all beneficiaries at once
- Certificate email preview before sending (the action card serves as the preview)