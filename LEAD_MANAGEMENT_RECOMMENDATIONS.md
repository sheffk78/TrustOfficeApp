# TrustOffice Lead Management: Feature Recommendations

## Analysis Date: June 22, 2026
## Status: Strategy & Architecture Document

---

## Executive Summary

TrustOffice has a solid lead management backend — capture, scoring, staging, email automation, Discord notifications, and an admin table view are all built and functional. The gap is **real-time awareness and follow-up speed**. Jeff personally handles every lead and currently relies on Discord pings + manual tab-checking. The recommendations below focus on making leads feel **live and actionable** inside the app itself, with minimal new infrastructure.

**Key architectural constraints discovered:**
- Frontend: React SPA (CRA/Craco), no WebSocket or SSE infrastructure exists
- Backend: FastAPI on Railway, MongoDB Atlas, APScheduler for background jobs
- No `notifications` collection in MongoDB exists yet
- Sidebar has no notification/bell icon; AdminPage has 7 tabs (customers, revenue, admins, referrals, leads, lead-analytics, + stats)
- `governance_tasks` collection exists but is trust-scoped (tied to `trust_id` + `user_id`) — not suitable for lead follow-up tasks without schema changes
- Discord webhook already fires on every new lead and stage change
- `notification_preferences` collection exists but only covers user-facing app notifications (minutes, distributions, tasks) — not admin lead alerts

---

## Priority Build Order

### P0 — Build Now (Immediate ROI, Low Effort)

---

### 1. In-App Notification Bell with Polling (P0)
**Effort: 4–5 hours | Priority: P0**

**Why:** This is the single highest-ROI feature. Jeff lives in the app. A bell icon with a red badge count gives him instant awareness without switching tabs or checking Discord. Polling is sufficient — TrustOffice's lead volume doesn't justify WebSocket complexity.

**What to build:**

**Backend (1.5h):**
- New `notifications` collection in MongoDB:
  ```python
  {
    "notification_id": "notif_abc123",
    "user_id": "admin_user_id",  # Jeff's user_id
    "type": "new_lead" | "lead_stage_change" | "booked_call" | "lead_converted",
    "title": "New Lead: John Smith",
    "body": "john@example.com via trustee-101-landing-page",
    "lead_id": "lead_xyz789",
    "read": False,
    "created_at": "2026-06-22T10:30:00Z"
  }
  ```
- New router `routers/notifications.py` with 4 endpoints:
  - `GET /admin/notifications` — list notifications (paginated, filter by read/unread)
  - `GET /admin/notifications/unread-count` — returns `{ "count": N }` (lightweight, called every 30s)
  - `POST /admin/notifications/{id}/read` — mark as read
  - `POST /admin/notifications/mark-all-read` — bulk mark as read
- Hook into existing `leads.py` capture endpoint: after `notify_new_lead()` Discord call, also insert a notification document
- Hook into `notify_lead_stage_change` calls similarly
- Hook into TidyCal webhook to create "booked call" notification (high priority — different type)

**Frontend (3h):**
- New `NotificationCenter` component (bell icon + dropdown panel) added to `Sidebar.js` header area
- Poll `GET /admin/notifications/unread-count` every 30 seconds when admin is logged in
- Show red badge with count on bell icon when unread > 0
- Dropdown panel shows last 10 notifications with lead name, type icon, timestamp
- Click a notification → navigate to AdminPage leads tab with that lead's detail dialog open
- "Mark all as read" button
- Notification types get color-coded icons: 🆕 new_lead (blue), 📞 booked_call (gold), 📧 stage_change (purple), ✅ converted (green)

**Implementation notes:**
- Polling at 30s intervals is fine for TrustOffice's volume (likely <50 leads/day). No need for SSE/WebSocket.
- Store notifications for 30 days, then auto-purge via a daily background job
- The `unread-count` endpoint should be extremely lightweight — just a `count_documents` query

**What NOT to do:**
- Don't build WebSocket infrastructure for this. It's overkill for a single admin user.
- Don't build a separate notifications page — the dropdown panel is sufficient

---

### 2. Lead Triage Dashboard View (P0)
**Effort: 3–4 hours | Priority: P0**

**Why:** The current leads table is a flat list. Jeff needs a "what needs my attention right now" view. This is a frontend-only change — the backend already has everything needed.

**What to build:**

**Frontend only (3–4h):**
- Add a "Triage" sub-view toggle at the top of the Leads tab in AdminPage.js (next to the stage filter pills)
- Triage view shows 3 priority columns/sections:

  **🔥 Hot — Action Needed Now**
  - Leads with `booked_call: true` and `stage != converted` (someone booked a call — call them back/prep)
  - Leads with `score >= 70` (high intent)
  - Leads where `next_action` contains "Send subscription pitch" or "Prepare for upcoming"

  **⏰ Aging — Don't Forget**
  - Leads in `new` stage for 3+ days with 0 lessons watched
  - Leads in `warm` stage (been around 7+ days, no engagement)
  - Leads where `next_action` contains "re-engagement"

  **✅ Recent Wins**
  - Leads moved to `converted` in the last 7 days
  - Leads moved to `engaged` in the last 3 days (positive momentum)

- Each lead card in triage shows: name, email, source, score bar, next_action, days since capture, and quick-action buttons (view detail, change stage, add note)
- One-click stage advancement: buttons for the most likely next stage (e.g., "Mark Engaged" for a new lead who watched a lesson)

**Backend support needed:** Minimal. The existing `GET /admin/leads` endpoint already returns enriched leads with `score`, `next_action`, `stage`, `booked_call`, `created_at`. May need to add `sort_by=score` support (already exists via query param).

**What NOT to do:**
- Don't build a Kanban board. Jeff has 5 stages and low volume — a triage view with 3 priority buckets is more useful than a 5-column board.
- Don't add drag-and-drop. The dropdown stage selector already works.

---

### 3. One-Click Follow-Up Email (P0)
**Effort: 3–4 hours | Priority: P0**

**Why:** When Jeff sees a lead in triage, his next action is almost always "email them." Currently he has to copy the email, go to Postmark or his mail client, and compose from scratch. One-click templates make this 10x faster.

**What to build:**

**Backend (1.5h):**
- New `routers/lead_templates.py` router:
  - `GET /admin/leads/templates` — list email templates
  - `POST /admin/leads/{lead_id}/send-email` — send a templated email to a lead
  - `POST /admin/leads/templates` — create/save a custom template (for future)
- Store templates in MongoDB `lead_email_templates` collection:
  ```python
  {
    "template_id": "tmpl_abc123",
    "name": "Course Nudge",
    "subject": "Ready to continue Trustee 101?",
    "body": "Hi {name},\n\nI noticed you enrolled in Trustee 101 but haven't started yet...",
    "variables": ["name", "course_url"],
    "created_at": "...",
    "is_default": True
  }
  ```
- Pre-seed 5 templates based on the existing `get_next_action()` logic:
  1. **"Course Nudge"** — for new leads who haven't started (3+ days, 0 lessons)
  2. **"Subscription Pitch"** — for engaged leads (3+ lessons watched)
  3. **"Value Email"** — for warm leads (7+ days, no engagement)
  4. **"Call Follow-Up"** — for booked-call leads (post-call thank you + subscription CTA)
  5. **"Win-Back"** — for lost leads (discount offer or check-in)
- Sending email logs to `lead_activities` with `action_type: "email"` and template name
- Uses existing `email_service` Postmark integration — no new email infrastructure

**Frontend (2h):**
- In the lead detail dialog (existing `fetchLeadDetail` dialog), add a "Send Email" section
- Template dropdown → preview pane (with variables filled in from lead data) → "Send" button
- After sending, show toast confirmation and refresh activity log
- Also add a "Quick Email" button in the triage view that opens the template picker pre-selected with the recommended template based on `next_action`

**What NOT to do:**
- Don't build a full email editor/WYSIWYG. Template + send is enough. Jeff can edit templates in the database or via a simple textarea settings page later.
- Don't build email threading or reply tracking. That's a CRM feature for a much larger team.

---

### P1 — Build Next (High Value, Medium Effort)

---

### 4. Browser Push Notifications (P1)
**Effort: 4–5 hours | Priority: P1**

**Why:** Jeff wants notifications even when the app tab isn't actively focused (but browser is open). Browser notifications fire on the OS level — more attention-grabbing than a tab badge.

**What to build:**

**Frontend (3h):**
- On admin login, request `Notification.permission` 
- When the notification polling (from P0 #1) detects a new unread notification, also fire a browser `new Notification()` if:
  - Permission is granted
  - Document is not visible (`document.hidden` is true) — don't fire when Jeff is already looking at the app
  - The notification is < 60 seconds old (don't fire stale notifications on page load)
- Notification body: `New lead: John Smith (john@example.com) from trustee-101-landing-page`
- Click on notification → focus the TrustOffice tab and navigate to the lead

**Backend:** None — the existing unread-count polling endpoint from P0 #1 handles this. The browser notification is purely a frontend concern triggered by the same poll.

**Implementation:**
```javascript
// In NotificationCenter component
useEffect(() => {
  if (!isAdmin) return;
  
  const checkAndNotify = async () => {
    const count = await fetchUnreadCount();
    if (count > previousCount && document.hidden) {
      const latest = await fetchLatestNotification();
      new Notification('TrustOffice: ' + latest.title, {
        body: latest.body,
        icon: '/favicon.png',
        tag: latest.notification_id
      });
    }
  };
  
  const interval = setInterval(checkAndNotify, 30000);
  return () => clearInterval(interval);
}, [isAdmin]);
```

**What NOT to do:**
- Don't use the Push API / Service Workers for true push notifications. That requires a push service (FCM, OneSignal), service worker setup, and VAPID key management. It's significant infrastructure for a single admin user. Browser notifications via the Notifications API are sufficient and zero-cost.
- Don't send browser notifications when the tab is visible — the bell badge already handles that case.

---

### 5. Follow-Up Task System for Leads (P1)
**Effort: 5–6 hours | Priority: P1**

**Why:** Some leads need scheduled follow-up ("call them next Tuesday," "check if they started the course in a week"). Currently there's no way to create a task tied to a specific lead with a due date. The existing `governance_tasks` system is trust-scoped, not lead-scoped.

**What to build:**

**Backend (2.5h):**
- New `lead_tasks` collection (separate from `governance_tasks`):
  ```python
  {
    "task_id": "ltask_abc123",
    "lead_id": "lead_xyz789",
    "user_id": "admin_user_id",
    "title": "Call John re: discovery call follow-up",
    "due_date": "2026-06-25T09:00:00Z",
    "completed": False,
    "completed_at": None,
    "created_at": "...",
    "lead_snapshot": {  # denormalized for quick display
      "name": "John Smith",
      "email": "john@example.com",
      "stage": "engaged"
    }
  }
  ```
- New endpoints in `leads.py` or a new `lead_tasks.py` router:
  - `POST /admin/leads/{lead_id}/tasks` — create follow-up task
  - `GET /admin/leads/{lead_id}/tasks` — list tasks for a lead
  - `GET /admin/lead-tasks` — list all pending lead tasks (for a "my tasks" view)
  - `PATCH /admin/lead-tasks/{task_id}/complete` — mark complete
  - `DELETE /admin/lead-tasks/{task_id}` — delete
- Background job (add to `background_tasks.py`): check for overdue lead tasks daily, create a notification in the `notifications` collection for the admin

**Frontend (3h):**
- In the lead detail dialog, add a "Tasks" section below the activity log
- Task input: title + date picker + "Add Task" button
- Tasks display as a checklist with complete/delete actions
- Add a "Tasks" sub-tab or section in the Leads tab showing all pending lead tasks sorted by due date
- Overdue tasks shown in red

**What NOT to do:**
- Don't try to extend the existing `governance_tasks` system. It's fundamentally trust-scoped with different schema requirements. A separate `lead_tasks` collection is cleaner.
- Don't build recurring task templates. Manual task creation is fine for Jeff's volume.

---

### 6. Lead Quick-Action Toolbar (P1)
**Effort: 2–3 hours | Priority: P1**

**Why:** The current lead detail dialog shows information but requires multiple clicks to take action. A toolbar with the 4 most common actions speeds up workflow significantly.

**What to build:**

**Frontend only (2–3h):**
- Add a sticky action bar at the bottom of the lead detail dialog with 4 buttons:
  1. **📧 Email** — opens the template picker (from P0 #3)
  2. **📅 Schedule** — deep-link to TidyCal booking page (to suggest a call time to the lead)
  3. **✏️ Note** — quick inline note input (no need to open a separate dialog)
  4. **🔄 Stage** — the existing stage dropdown, but as a prominent button

- Also add keyboard shortcuts when the detail dialog is open:
  - `E` → email
  - `N` → note
  - `S` → stage change
  - `Escape` → close dialog

**What NOT to do:**
- Don't add SMS. SMS APIs are metered, add compliance complexity (opt-out management), and Jeff is budget-conscious. Email + Discord is sufficient for now.

---

### P2 — Build Later (Nice to Have, Lower Priority)

---

### 7. Lead Source Performance Widget (P2)
**Effort: 2 hours | Priority: P2**

**Why:** The lead-analytics tab already has conversion-by-source data, but it's buried. A small widget on the triage dashboard showing top 3 performing sources helps Jeff know where to invest marketing effort.

**What to build:**
- Small 3-card widget at the top of the triage view: "Best converting source this month" with source name, conversion rate, and lead count
- Uses existing `GET /admin/leads/analytics` endpoint — no backend changes
- Pure frontend, 2 hours max

---

### 8. Daily Lead Digest Email (P2)
**Effort: 2 hours | Priority: P2**

**Why:** If Jeff isn't in the app for a day or two, a daily summary email ensures he doesn't miss leads. This is a safety net, not a primary notification channel.

**What to build:**
- New background job in `background_tasks.py` running at 9 AM UTC (alongside existing daily reminders)
- Query: leads created in the last 24 hours, leads that changed stage, leads with overdue tasks
- Send a formatted summary email to Jeff via Postmark
- Include direct links to the admin leads tab

**What NOT to do:**
- Don't make this the primary notification method. It's a backup. The bell + browser notifications are primary.

---

### 9. Lead Notes with Rich Text (P2)
**Effort: 2 hours | Priority: P2**

**Why:** The current notes are plain text activity log entries. Rich notes (with the ability to edit, pin, and search) would help when Jeff is doing call prep.

**What to build:**
- Upgrade the notes section in the lead detail dialog to support:
  - Pinned notes (shown at top)
  - Edit/delete notes (currently notes are append-only via activity log)
  - Note search within a lead

**What NOT to do:**
- Don't build full CRM note features (mentions, attachments, collaborative notes). Jeff is the only user.

---

## What NOT to Build (Explicitly Rejecting)

### ❌ Lead Routing/Assignment
**Why skip:** Jeff is the only person handling leads. Routing/assignment is for teams of 3+ sales reps. Building this adds complexity with zero value.

### ❌ SMS Follow-Up
**Why skip:** Metered API costs (Twilio is ~$0.0079/message), TCPA compliance requirements, opt-out management. Email + Discord + browser notifications cover the notification spectrum. If Jeff specifically asks for SMS later, it's a clean add via Twilio, but don't preemptively build it.

### ❌ Real-Time WebSocket/SSE Infrastructure
**Why skip:** For a single admin user with low-to-moderate lead volume, polling every 30 seconds is indistinguishable from real-time. WebSocket infrastructure on Railway adds connection management complexity, reconnection handling, and memory overhead. Polling the `unread-count` endpoint is a single MongoDB `count_documents` query — practically free.

### ❌ Automated Call Scheduling
**Why skip:** TidyCal already handles this. Jeff has a booking page. The system already creates a notification when a call is booked. Building custom call scheduling would duplicate TidyCal's functionality.

### ❌ Third-Party CRM Integration (HubSpot, Pipedrive, etc.)
**Why skip:** The built-in lead system already has capture, scoring, staging, activity logging, email automation, and analytics. It covers 90% of what a CRM does for a single-operator business. Integrating with an external CRM adds sync complexity, data duplication, and monthly subscription costs. Jeff is budget-conscious.

### ❌ Lead Status Dashboard (Separate Page)
**Why skip:** The triage view (P0 #2) inside the existing Leads tab achieves the same goal without adding a new page to the sidebar. A separate dashboard page would fragment the admin experience.

---

## Implementation Priority Summary

| # | Feature | Priority | Effort | Dependency |
|---|---------|----------|--------|------------|
| 1 | In-App Notification Bell (polling) | **P0** | 4-5h | None |
| 2 | Lead Triage Dashboard View | **P0** | 3-4h | None |
| 3 | One-Click Follow-Up Email Templates | **P0** | 3-4h | None |
| 4 | Browser Push Notifications | **P1** | 4-5h | Depends on #1 |
| 5 | Follow-Up Task System | **P1** | 5-6h | None |
| 6 | Lead Quick-Action Toolbar | **P1** | 2-3h | Depends on #3 |
| 7 | Lead Source Performance Widget | **P2** | 2h | Depends on #2 |
| 8 | Daily Lead Digest Email | **P2** | 2h | None |
| 9 | Lead Notes with Rich Text | **P2** | 2h | None |

**Total P0 effort: ~11-13 hours** (can be built in a 2-day sprint)
**Total P1 effort: ~11-14 hours** (follow-up sprint)
**Total P2 effort: ~6 hours** (incremental additions)

---

## Technical Architecture Notes

### Notification Collection Schema (for P0 #1)
```python
# MongoDB collection: notifications
{
  "notification_id": "notif_<uuid12>",
  "user_id": "<admin_user_id>",
  "type": "new_lead" | "lead_stage_change" | "booked_call" | "lead_converted" | "task_overdue",
  "priority": "high" | "normal",  # booked_call = high, others = normal
  "title": "New Lead: John Smith",
  "body": "john@example.com via trustee-101-landing-page",
  "lead_id": "lead_xyz789",
  "lead_email": "john@example.com",
  "lead_name": "John Smith",
  "read": False,
  "created_at": "2026-06-22T10:30:00Z",
  "read_at": None,
}

# Indexes needed
# - (user_id, read, created_at) — for listing unread notifications
# - (user_id, read) — for the unread-count query
# - TTL index on created_at: expireAfterSeconds=2592000 (30 days)
```

### Files to Create
1. `backend/routers/notifications.py` — notification CRUD endpoints
2. `backend/routers/lead_templates.py` — email template management + send
3. `backend/routers/lead_tasks.py` — lead follow-up task CRUD
4. `frontend/src/components/NotificationCenter.js` — bell icon + dropdown
5. `frontend/src/components/LeadTriageView.js` — triage dashboard view
6. `frontend/src/components/LeadEmailDialog.js` — template picker + send
7. `frontend/src/components/LeadTaskList.js` — task list in lead detail

### Files to Modify
1. `backend/routers/leads.py` — add notification creation in capture + stage change handlers
2. `backend/server.py` — register new routers
3. `backend/background_tasks.py` — add daily lead digest job (P2), overdue task check (P1)
4. `frontend/src/components/Sidebar.js` — add NotificationCenter to header
5. `frontend/src/pages/AdminPage.js` — add triage view toggle, quick-action toolbar, email dialog, task list

### New Environment Variables
- None required. All features use existing infrastructure (MongoDB, Postmark, Railway).

---

## Build Sequence (Recommended Sprint Plan)

### Sprint 1: Awareness (2 days)
1. Day 1 AM: Backend — `notifications.py` router + collection + hook into `leads.py` capture endpoint
2. Day 1 PM: Frontend — `NotificationCenter` component + add to Sidebar + polling logic
3. Day 2 AM: Frontend — Lead Triage View in AdminPage
4. Day 2 PM: Backend+Frontend — Email template system + send flow

**Result after Sprint 1:** Jeff sees a red bell badge when leads come in, can triage by priority, and can send a templated follow-up email in 2 clicks.

### Sprint 2: Follow-Up Workflow (2 days)
1. Day 1: Browser push notifications (frontend only, builds on Sprint 1 polling)
2. Day 1 PM: Lead follow-up task system (backend + frontend)
3. Day 2: Quick-action toolbar + keyboard shortcuts in lead detail dialog

**Result after Sprint 2:** Jeff gets OS-level notifications when not looking at the app, can create scheduled follow-up tasks, and has a streamlined action toolbar.

### Sprint 3: Polish (1 day, optional)
- Lead source performance widget
- Daily digest email
- Rich notes

---

## Budget Impact

**Zero new recurring costs.** All features use existing infrastructure:
- MongoDB Atlas (existing) — new collections, minimal storage
- Postmark (existing) — template emails use existing send quota
- Railway (existing) — new routers run on existing FastAPI process
- No new SaaS subscriptions, no metered APIs, no third-party services

The only cost consideration is Postmark email volume for the one-click follow-up emails, which is marginal (a few emails per day) and well within existing Postmark plan limits.