# BCC Email Capture — Implementation Plan

**Feature:** Trustee BCCs a per-trust email address → email auto-logged in Communications  
**Tiers:** Estate ($149/mo) and Advisor ($399/mo) only. Trustee ($79/mo) sees upgrade prompt.  
**Cost:** Zero additional — already on Postmark Platform tier with inbound included.  
**Status:** Planning complete. Awaiting DNS approval from Kenneth.

---

## Architecture Summary

The existing `communications.py` router already has full CRUD (POST/GET/PATCH/DELETE + summary). The existing `MessagingPage.js` (456 lines, recently redesigned as "Royal Ledger email archive") already has a `TrustEmailCard` component with a pseudo-address. The plan extends both — no new pages, no new routers. One webhook endpoint receives Postmark inbound emails, matches the address slug to a trust, and inserts into the existing `communications` collection.

---

## Phase 1: Infrastructure (requires Kenneth's DNS approval)

### 1.1 DNS — MX record for `archive.trustoffice.app`

| Type | Host | Value | Priority | Purpose |
|------|------|-------|----------|---------|
| MX | archive.trustoffice.app | `inbound.postmarkapp.com` | 10 | Route inbound email to Postmark |
| MX | archive.trustoffice.app | `inbound.postmarkapp.com` | 20 | Postmark secondary MX |

> **⚠️ Requires Kenneth's approval** — this is a DNS change. Once approved, I can add via Cloudflare API.

### 1.2 Postmark inbound domain configuration

1. **Add inbound domain** `archive.trustoffice.app` to the TrustOffice Postmark server via Postmark API:
   - `POST /server/inboundDomains` with `{"Domain": "archive.trustoffice.app"}`
   - Postmark returns a verification token for SPF/TXT (optional but recommended)
2. **Set inbound webhook URL** to the real backend endpoint:
   - `PUT /server/{serverId}` with `{"InboundHookUrl": "https://api.trustoffice.app/webhooks/postmark-inbound"}`
   - (Currently set to placeholder `postmark-inbound-test` — will update to real endpoint)
3. **Verify domain active** — Postmark shows inbound domain status as "Verified" once MX resolves

### 1.3 Postmark inbound email format

Postmark delivers inbound emails as JSON POST to the webhook URL:
```json
{
  "FromFull": { "Email": "trustee@gmail.com", "Name": "John Kohler" },
  "ToFull": [{ "Email": "beneficiary@example.com", "Name": "Jane Kohler" }],
  "CcFull": [{ "Email": "kohler-family-trust@archive.trustoffice.app" }],
  "BccFull": [{ "Email": "kohler-family-trust@archive.trustoffice.app" }],
  "Subject": "Q3 Distribution Update",
  "TextBody": "...",
  "HtmlBody": "...",
  "Attachments": [],
  "Date": "Mon, 25 Aug 2025 10:00:00 -0600",
  "MessageId": "..."
}
```

The inbound address appears in `CcFull` or `BccFull` (BCC'd by the trustee). We match the local part (before `@`) to a trust's `email_archive_address` slug.

---

## Phase 2: Backend

### 2.1 Schema changes

**`trusts` collection — new fields:**
```python
email_archive_enabled: bool = False
email_archive_address: str | None = None  # "kohler-family-trust"
email_archive_enabled_at: str | None = None  # ISO timestamp
```

**`communications` collection — new fields:**
```python
source: str = "manual"  # "manual" | "bcc_capture"
# (existing fields unchanged: comm_id, trust_id, user_id, comm_type, subject, 
#  content, parties, direction, document_ids, etc.)
```

**Indexes:**
```python
db.trusts.create_index("email_archive_address", sparse=True, unique=True)
# Ensures no two trusts share the same inbound slug
```

### 2.2 New endpoints (added to `communications.py` or new `email_archive.py`)

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| `POST` | `/api/trusts/{trust_id}/email-archive/enable` | Enable BCC capture for a trust — generates slug, stores address | `require_write_access` + tier gate |
| `POST` | `/api/trusts/{trust_id}/email-archive/disable` | Disable — keeps historical entries, stops accepting new BCCs | `require_write_access` |
| `GET` | `/api/trusts/{trust_id}/email-archive/status` | Returns `{enabled, address, full_address, enabled_at}` | `get_current_user` |
| `POST` | `/webhooks/postmark-inbound` | Postmark inbound webhook — no JWT auth, uses Postmark signature | Postmark signature verification |

### 2.3 Address generation logic

```python
def generate_trust_slug(trust_name: str) -> str:
    """Kohler Family Trust → kohler-family-trust"""
    slug = re.sub(r'[^a-z0-9]+', '-', trust_name.lower()).strip('-')
    slug = re.sub(r'-+', '-', slug)[:40]  # max 40 chars
    return slug

# Collision handling: if slug exists for another trust, append short ID
# kohler-family-trust → kohler-family-trust-a3f7
```

### 2.4 Tier gating (backend enforcement)

```python
ALLOWED_PLANS = {"estate", "advisor"}

async def require_email_archive_tier(user: dict):
    state = await get_subscription_state(user["user_id"])
    if state.plan_type not in ALLOWED_PLANS:
        raise HTTPException(
            status_code=403,
            detail="Email Archive is available on Estate and Advisor plans. Upgrade to enable."
        )
```

Enforced at:
- `/enable` endpoint (user-facing — returns 403 with upgrade message)
- Webhook processing (defense-in-depth — if a disabled trust somehow receives email, drop it)

### 2.5 Webhook endpoint — `/webhooks/postmark-inbound`

```python
@router.post("/webhooks/postmark-inbound")
async def postmark_inbound(request: Request):
    # 1. Verify Postmark signature (header: X-Postmark-Secret-Token or 
    #    compare against configured inbound webhook auth token)
    # 2. Parse JSON body (Postmark inbound format)
    # 3. Find which inbound address was BCC'd — check CcFull + BccFull for 
    #    addresses ending in @archive.trustoffice.app
    # 4. Extract the slug (local part before @)
    # 5. Look up trust by email_archive_address == slug AND email_archive_enabled == True
    # 6. If not found or disabled → return 200 (Postmark will retry on non-200)
    #    Actually: return 200 to prevent retries — silently drop unmatched emails
    # 7. Create communication entry:
    #    - comm_type: "email"
    #    - direction: "outbound" (trustee sent it)
    #    - source: "bcc_capture"
    #    - subject: from Postmark payload
    #    - content: TextBody (strip HTML, prefer text)
    #    - parties: [{role: "trustee", name: FromFull.Name}, 
    #                {role: "recipient", name: ToFull[0].Name}]
    #    - created_at: email Date field
    # 8. Insert into db.communications
    # 9. Return 200 OK
```

**Security:**
- Postmark doesn't send a standard signature header for inbound webhooks. Options:
  - Set a custom inbound webhook auth token in Postmark server settings → verify it in the request header
  - Or verify the sender's email domain matches a known Postmark IP range
  - **Recommended:** Set `InboundHookUrl` to include a secret path segment: `https://api.trustoffice.app/webhooks/postmark-inbound/{SECRET_TOKEN}` — obscure but effective
- Rate limiting: Postmark handles inbound throttling on their end. Backend should be idempotent (use `MessageId` to deduplicate).

### 2.6 Consolidation with existing communications

The BCC capture writes directly to the same `communications` collection. The existing GET/PATCH/DELETE endpoints work without changes. The `source` field distinguishes BCC-captured from manual entries. The GET endpoint can optionally filter by `source`:

```python
# Add to existing list_communications query params:
if source:
    query["source"] = source
```

---

## Phase 3: Frontend

### 3.1 Settings UI — Email Archive section

**Location:** Settings page, new "Email Archive" card (between existing sections)

**States:**

1. **Trustee tier user (not eligible):**
   - Card shows "Email Archive" with lock icon
   - Text: "Available on Estate and Advisor plans"
   - Button: "Upgrade to Enable" → links to billing/upgrade flow

2. **Estate/Advisor user — not yet enabled:**
   - Card shows "Email Archive" with description
   - Button: "Enable Email Archive"
   - On click: POST `/enable` → generates address → transitions to enabled state

3. **Estate/Advisor user — enabled:**
   - Card shows the trust's BCC address: `kohler-family-trust@archive.trustoffice.app`
   - Copy button (clipboard)
   - Instructions: "BCC this address on emails to beneficiaries to automatically log them"
   - "Disable" button (small, secondary)
   - "Enabled since {date}" label

4. **Multiple trusts:**
   - Trust selector dropdown at top of card
   - Each trust shows its own enable/disable state and address
   - Address includes trust name slug for easy identification

### 3.2 MessagingPage.js consolidation

The existing `MessagingPage.js` (456 lines) already has the "Royal Ledger" design with `TrustEmailCard`. Changes:

1. **TrustEmailCard** — replace the pseudo-address generation with a real API call to `/email-archive/status`. Show the actual generated address if enabled, or an "Enable Email Archive" prompt if not.

2. **Communications list** — add `source` badge to each entry:
   - 🟢 "BCC Capture" badge for auto-captured emails (source: bcc_capture)
   - No badge for manual entries (source: manual or undefined)
   
3. **Detail view** — already exists (subject, body, recipients, date). Add the BCC source indicator and the raw email metadata (From, To, Date) for BCC-captured items.

4. **Filter** — add a filter toggle: "All | Manual | BCC Captured" (maps to the `source` query param)

5. **Empty states:**
   - Before enabling: "Enable Email Archive to start capturing BCC'd emails" with enable button
   - After enabling, no BCCs yet: "Your address is ready. BCC {address} on your next email to a beneficiary."
   - After first capture: normal list view with the captured email

### 3.3 Mobile experience

- Settings card works in existing mobile layout (stacked, touch-friendly copy button)
- MessagingPage already has mobile-responsive design (recent redesign)
- Copy-to-clipboard uses `navigator.clipboard.writeText` — works on mobile Safari/Chrome
- Address is displayed in a monospace font, large enough to read/select on mobile

### 3.4 Upgrade flow for Trustee tier

When a Trustee user navigates to the Email Archive section in Settings:
1. They see the locked card with "Upgrade to Enable"
2. Clicking opens the existing upgrade modal/page (Stripe checkout for Estate plan)
3. After successful upgrade, the page refreshes and the enable button appears

No new upgrade UI needed — reuse the existing Stripe checkout flow at `/api/subscription/create-checkout` with `plan_type: "estate"`.

---

## Build Order

| Step | What | Files | Dependencies | Requires DNS? |
|------|------|-------|-------------|---------------|
| 1 | Add Postmark inbound domain + set webhook URL | Postmark API | Kenneth's DNS approval | ✅ |
| 2 | Add MX records for archive.trustoffice.app | Cloudflare API | Step 1 | ✅ |
| 3 | Backend: schema + enable/disable endpoints + tier gate | `backend/routers/email_archive.py` (new) or extend `communications.py`, `backend/routers/trusts.py` | None | ❌ |
| 4 | Backend: Postmark inbound webhook endpoint | `backend/routers/email_archive.py`, `backend/server.py` (mount route) | Step 3 | ❌ |
| 5 | Backend: add `source` field to existing communications GET filter | `backend/routers/communications.py` | None | ❌ |
| 6 | Frontend: Settings Email Archive card | `frontend/src/pages/SettingsPage.js`, new `EmailArchiveCard.js` component | Step 3 (API) | ❌ |
| 7 | Frontend: MessagingPage consolidation (real address, BCC badge, filter) | `frontend/src/pages/MessagingPage.js` | Steps 3, 5 | ❌ |
| 8 | Frontend: upgrade prompt for Trustee tier | `frontend/src/pages/SettingsPage.js` or `EmailArchiveCard.js` | Step 6 | ❌ |
| 9 | Test: end-to-end BCC capture (send email → Postmark → webhook → DB → frontend) | Test script | Steps 1-8 | ✅ |
| 10 | Deploy + verify | Railway | Steps 1-9 | ✅ |

> **Steps 3-8 can be built in parallel with DNS setup (steps 1-2).** The code doesn't need DNS to compile — it just won't receive real emails until MX records propagate.

---

## Open Questions for Kenneth

1. **DNS approval** — Can I add the MX record for `archive.trustoffice.app` pointing to `inbound.postmarkapp.com`? (This is the only hard blocker.)
2. **Webhook security** — Should I use a secret token in the webhook URL path (`/webhooks/postmark-inbound/{token}`) or configure a custom auth header in Postmark? Either works; path-based is simpler.
3. **Email body storage** — Store full text body in the communications entry (could be large), or truncate to first 500 chars + store full body separately? My recommendation: store full text body, cap at 10,000 chars, strip HTML.

---

## What's NOT in v1

- Attachment storage (metadata only — filenames, not file content)
- Reply capture (only outbound via BCC)
- Threading/reply chains
- Attorney privilege flagging (beneficiary emails aren't privileged)
- Separate inbox UI (uses existing Communications Log)
- Per-user cost tracking dashboard (Postmark's dashboard is sufficient at current scale)