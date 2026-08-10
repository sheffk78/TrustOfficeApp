# Customer Memory System — TrustOffice

This document describes the customer memory layer that powers TrustOffice's
support agents: how contact context is stored, retrieved, and updated; how the
global knowledge base is searched for grounding; and the rules for what
belongs in each store.

## Overview

The customer memory system has three MongoDB collections for per-contact data
plus one global knowledge base:

| Store | Collection | Purpose |
|---|---|---|
| Contact profile summary | `contact_profile_summary` | Durable facts about a contact — the agent's long-term memory |
| Interaction history | `support_interactions` | Episodic records of each support touchpoint |
| Contacts | `contacts` | Identity & account record for a contact (email, name, account link) |
| Global knowledge base | `knowledge_articles` | Product docs, FAQs, policy — shared, not per-contact |

Support agents follow a four-step flow for each inbound email:
**get contact context → draft reply (grounded with knowledge retrieval) →
log interaction → update profile summary.**

---

## Schema definitions

### `contacts`

The identity record for a contact. One document per contact.

| Field | Type | Purpose |
|---|---|---|
| `id` | string | Unique contact id (e.g. `ct_<hex>`). Primary key. |
| `email` | string | Contact's primary email address. Used for lookup. |
| `name` | string | Display name of the contact. |
| `account_id` | string (optional) | Linked trust/account id, if the contact is a known account holder. |
| `created_at` | string (ISO 8601) | When the contact record was created. |
| `updated_at` | string (ISO 8601) | When the contact record was last modified. |

### `support_interactions`

An episodic record of a single support touchpoint (email, chat, phone
summary, in-app message). One document per interaction.

| Field | Type | Purpose |
|---|---|---|
| `id` | string | Unique interaction id (e.g. `si_<hex>`). |
| `contact_id` | string | FK to `contacts.id`. |
| `channel` | string | Source channel: `email`, `chat`, `phone`, `in_app`. (See Extensibility.) |
| `direction` | string | `inbound` or `outbound`. |
| `subject` | string (optional) | Subject line / topic label. |
| `raw_content` | string | The inbound message as received (email body, chat transcript, phone summary). |
| `reply` | string (optional) | The agent's outbound reply, if any. |
| `summary` | string | Short agent-written summary of the interaction. |
| `topics` | string[] | Topic tags (e.g. `["distributions", "1041"]`). |
| `sentiment` | string | `positive`, `neutral`, `negative`, `unknown`. |
| `urgency` | string | `low`, `normal`, `high`, `urgent`. |
| `status` | string | `open`, `resolved`, `escalated`, `waiting`. |
| `created_at` | string (ISO 8601) | When the interaction was logged. |
| `updated_at` | string (ISO 8601) | When the interaction was last updated. |

### `contact_profile_summary`

The agent's long-term memory of a contact — durable facts only. One document
per contact.

| Field | Type | Purpose |
|---|---|---|
| `contact_id` | string | FK to `contacts.id`. Primary lookup key. |
| `status` | string | Current relationship status (e.g. `active`, `onboarding`, `churned`). |
| `preferences` | object | Durable preferences (e.g. `{"reply_format": "detailed", "language": "en"}`). |
| `open_issues` | string[] | Long-running issues not yet resolved. |
| `resolved_issues` | string[] | Recently resolved long-running issues (kept for context). |
| `recommended_next_actions` | string[] | Suggested next actions for the agent. |
| `key_facts` | string[] | Durable facts worth remembering (e.g. "prefers quarterly distributions"). |
| `updated_at` | string (ISO 8601) | When the summary was last updated. |

---

## Support agent email handling flow

For each inbound support email, the agent executes:

1. **Get contact context** — `GET /api/contact-memory/context/{contact_id}`<br>
   Fetch the contact record, recent `support_interactions`, and the
   `contact_profile_summary`. This gives the agent the full per-contact context.

2. **Ground the reply with knowledge retrieval** — `GET /api/knowledge-retrieval/search?q=...&limit=...`<br>
   Search the global knowledge base (`knowledge_articles`) for published
   articles matching the contact's question across title, summary, tags, and
   content. Returns a compact list of `{id, title, category, summary,
   content_snippet}`. Use these to ground the drafted reply in product docs,
   FAQs, and policy.

3. **Draft reply** — The agent composes a reply using the contact context
   (step 1) and the retrieved knowledge (step 2).

4. **Log the interaction** — `POST /api/contact-memory/interactions`<br>
   Record the touchpoint in `support_interactions`: the raw inbound content,
   the agent's reply, a short summary, topics, sentiment, urgency, and status.
   This is episodic history — log every touchpoint.

5. **Update contact profile summary** — `PATCH /api/contact-memory/profile-summary/{contact_id}`<br>
   If something durable changed (new preference, status change, a long-running
   issue resolved), update `contact_profile_summary`. If nothing durable
   changed, skip this step.

---

## What belongs in each store

### Contact profile summary → durable facts ONLY

The profile summary is long-term memory. Write to it only when a durable fact
emerges:

- ✅ Status changes (`active` → `onboarding`, account churned)
- ✅ New durable preferences ("prefers quarterly distributions", "wants replies in Spanish")
- ✅ Resolution of a long-running issue (move from `open_issues` to `resolved_issues`)
- ✅ Recommended next actions for the next agent
- ❌ NOT transient chatter ("asked about distributions today")
- ❌ NOT the full email body (that goes in `support_interactions`)
- ❌ NOT a duplicate of anything already captured in interaction history

### Interaction history → episodic records

Every support touchpoint gets logged as one `support_interactions` document:

- ✅ The raw inbound content (email body, chat transcript, phone summary)
- ✅ The agent's reply
- ✅ A short agent-written summary
- ✅ Topics, sentiment, urgency, status
- ❌ NOT durable preferences (those go in the profile summary)
- ❌ NOT knowledge-base articles (those live in `knowledge_articles`)

### Global knowledge base → shared docs, not per-contact data

The `knowledge_articles` collection holds product documentation, FAQs, and
policy. It is shared across all contacts and never stores per-contact data.

- ✅ Product docs (trust basics, tax, distributions, governance, …)
- ✅ FAQs and best-practice articles
- ✅ Policy and compliance material
- ❌ NOT contact-specific history or preferences
- ❌ NOT interaction transcripts

---

## Privacy & governance

### Contact-level history deletion / redaction

- `DELETE /api/contact-memory/history/{contact_id}` — deletes all
  `support_interactions` for a contact (and optionally redacts the
  `contact_profile_summary`). Use this to honor data-deletion requests (e.g.
  GDPR "right to be forgotten") keyed by contact id.
- Deletion is contact-scoped: it never touches the global knowledge base or
  other contacts' data.
- Prefer structured fields and short summaries over large free-text dumps.
  Store the minimal raw content needed for context; lean on short `summary`
  fields and topic tags for retrieval. This keeps the per-contact footprint
  small and makes redaction straightforward.

### Role-based access

| Role | Contact profile summary | Interaction history | Knowledge retrieval |
|---|---|---|---|
| **Support** | read / write | read / write | read |
| **Marketing** | read (durable facts) | read (aggregated, not raw) | read |
| **Engineering** | read (for debugging) | read (for debugging) | read / write (manage articles) |

- Support agents have full read/write on per-contact stores (that is their
  domain).
- Marketing agents may read durable profile facts and aggregated interaction
  metadata, but should not read raw inbound message content. They reuse the
  same endpoints with a reduced scope enforced by auth.
- Engineering manages the global knowledge base (`knowledge_articles`) via the
  `/api/knowledge` CRUD router and may read per-contact stores for debugging.
- The `/api/knowledge-retrieval/search` endpoint is read-only and available to
  any authenticated support/marketing/engineering role — it only returns
  published articles and never per-contact data.

---

## Extensibility

### New channels reuse the same `support_interactions` schema

The `channel` field on `support_interactions` is just a string — adding a new
channel does not require a new collection or new endpoints:

| Channel | `channel` value | `raw_content` |
|---|---|---|
| Email | `email` | Email body |
| Chat | `chat` | Chat transcript |
| Phone | `phone` | Agent-written call summary |
| In-app | `in_app` | In-app message text |

To add a channel, simply log interactions with the new `channel` value. The
retrieval, context, and profile-summary flows all work unchanged.

### New agent roles reuse the same endpoints

Sales and marketing agents reuse the same customer-memory endpoints:

- **Sales agents** read `contact_profile_summary` for account context and log
  sales touchpoints as `support_interactions` with `channel = "phone"` or
  `"in_app"` and a sales-oriented `topics` set.
- **Marketing agents** read aggregated `support_interactions` metadata and
  durable `contact_profile_summary` facts to segment contacts — no new
  per-contact collection required.

Because every channel and every role write into the same two per-contact
stores, the contact's history stays unified and the deletion/redaction
endpoint covers all of it in one call.