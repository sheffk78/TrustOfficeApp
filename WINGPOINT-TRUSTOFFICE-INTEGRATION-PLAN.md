# WingPoint to TrustOffice Integration Improvement Plan

**Date:** July 10, 2026
**Status:** Backend changes implemented (5 of 7). Frontend changes pending.
**Codebase:** `/Users/socializerender/Projects/TrustOfficeApp`

---

## Problem Summary

When WingPoint provisions a trust in TrustOffice via the `/external/provision-trustoffice` API, four problems exist:

1. **All users dumped to `/pricing` after provisioning.** Paid users hit a guard: "You're already subscribed. Manage your plan in Settings." This is a dead end.
2. **WingPoint's Builder Bundle (4 trusts) needs an Estate plan**, but nothing tells the user. The provision API bypasses trust limits, creating an over-limit state.
3. **EIN number transfers but CP575 IRS letter doesn't.** User must manually upload the PDF they already have from WingPoint.
4. **Trust details (trustees, beneficiaries, jurisdiction) aren't passed through** from WingPoint (future work, not in this plan).

---

## Architecture: Current State

```
WingPoint purchase
    │
    ▼
POST /external/provision-trustoffice
    │
    ├─ Creates user account (if new) or adds trust to existing account
    ├─ Stores EIN, trust name, jurisdiction on trust record
    ├─ Sends set-password email (new users only)
    ├─ Fires activation webhooks back to WingPoint on password_set / first_login
    │
    ▼
User sets password → redirected to /pricing?coupon=WINGPOINT50
    │
    ├─ New user: picks a plan, subscribes via Stripe ✓
    ├─ Existing free user: same flow ✓
    ├─ Existing paid user: BLOCKED by "already subscribed" guard ✗
    └─ Existing paid user needing upgrade: no path ✗
```

---

## What's Been Implemented (Backend)

### 1. CP575 Document Transfer (DONE)

**File:** `backend/routers/external_trust_docs.py`

The endpoint `/api/external/trust-documents` already existed and was fully built (idempotent, dedup, metadata, EIN update, onboarding checklist auto-update). Two changes applied:

- **Restricted to `ein_confirmation` only.** Other document types (Declaration, Certificate, Binder Kit) are rejected with a clear message. These need notarization/signing before upload.
- **Added HTTPS validation on download URLs** to prevent SSRF attacks.

WingPoint sends a download URL for the CP575 PDF. TrustOffice fetches it server-side and stores it as BSON binary in the vault with `document_type=ein_letter`, `source=wingpoint`.

### 2. Smart Routing in Provision API (DONE)

**File:** `backend/routers/external.py`

Added `_determine_recommended_action()` helper that checks the user's subscription state, trust count, and password status, then returns one of 5 actions:

| User State | `action` | What Happens |
|---|---|---|
| New user, no password | `set_password` | Set-password email sent, user sets password then picks plan |
| Existing free user, no password | `set_password` | Same as above |
| Existing free user, has password | `login_and_subscribe` | Redirect to login, then pricing with suggested plan |
| Existing paid, plan covers trusts | `login` | Redirect to login, trust is there, done |
| Existing paid, plan too small | `login_and_upgrade` | Redirect to login, then billing with upgrade prompt |
| Existing paid, cancel pending | `login_and_resubscribe` | Redirect to login, then pricing to reactivate |

The provision API response now includes a `recommended_action` object:

```json
{
  "status": "trust_added",
  "user_id": "...",
  "trust_id": "...",
  "set_password_url": null,
  "is_new_user": false,
  "email_status": "skipped",
  "recommended_action": {
    "action": "login_and_upgrade",
    "redirect_url": "https://app.trustoffice.app/login?wp=1&action=upgrade&plan=estate",
    "message": "Your trust has been added. Log in to upgrade to the Estate plan to manage all your trusts.",
    "suggested_plan": "estate",
    "suggested_plan_name": "Estate",
    "needs_upgrade": true,
    "requires_payment": true,
    "current_plan": "trustee",
    "current_plan_name": "Trustee",
    "trust_count": 2,
    "current_trust_limit": 1,
    "cancel_pending": false
  }
}
```

WingPoint uses `recommended_action.action` to decide what to show the user on their end, and `recommended_action.redirect_url` to send them to the right place in TrustOffice.

### 3. Conditional Email Sending (DONE)

**File:** `backend/routers/external.py`

- New users (no password): Set-password email sent as before.
- Existing users with password: Set-password email SKIPPED (they already have a password). Logged with reason. TODO: create a dedicated "trust_added" email template.

### 4. Package-to-Plan Mapping (DONE)

**File:** `backend/routers/external.py`

```python
PACKAGE_TO_PLAN = {
    "single_trust": "trustee",      # 1 trust -> Trustee ($79/mo, 1 trust)
    "estate_bundle": "estate",      # 2 trusts -> Estate ($149/mo, 5 trusts)
    "builder_bundle": "estate",     # 4 trusts -> Estate ($149/mo, 5 trusts covers it)
}
```

Fallback: if no `source_package` provided, recommends based on actual trust count in MongoDB.

### 5. Enriched Subscription State Endpoint (DONE)

**File:** `backend/routers/subscriptions.py`

`GET /subscription/state` now returns three additional fields:

```json
{
  "trust_count": 2,
  "trust_limit": 1,
  "needs_upgrade": true
}
```

The frontend can use `needs_upgrade` to show an upgrade banner without any new API calls (AuthContext already loads subscription state on every page).

---

## What's Pending (Frontend)

### 6. Frontend WingPoint-Aware Routing

**Files to modify:**
- `frontend/src/pages/PricingPage.js` — Relax the "already subscribed" guard for WingPoint users with `?wp=1&action=subscribe` or `?wp=1&action=upgrade` URL params
- `frontend/src/pages/ResetPasswordPage.js` — After password set, check URL params for `plan=` and redirect to pricing with that plan pre-selected instead of always going to `/pricing`
- `frontend/src/pages/BillingPage.js` — Accept `?plan=estate` param and auto-scroll/highlight the recommended plan card
- `frontend/src/pages/LoginPage.js` (or equivalent) — After login, check `?wp=1&action=*` params and redirect accordingly (subscribe -> pricing, upgrade -> billing, welcome -> dashboard)

**Key design decisions:**
- Use URL params (`?wp=1&action=...`) rather than session storage or server-side state. Simpler, bookmarkable, works across devices.
- PricingPage guard should show a different message for WingPoint users: "You're already subscribed. Your new trust has been added. To manage more trusts, upgrade your plan in Settings." with a button to go to billing.
- BillingPage should auto-scroll to the recommended plan card and highlight it with a subtle border or badge.

### 7. Upgrade Banner on Dashboard

**Files to modify:**
- `frontend/src/pages/DashboardPage.js` — Show a dismissible banner when `needs_upgrade === true` from subscription state
- `frontend/src/context/AuthContext.js` — Already loads subscription state; just needs to pass through the new `trust_count`, `trust_limit`, `needs_upgrade` fields

**Banner design:**
- Gold/amber color (attention, not error)
- Text: "You have 2 trusts but your Trustee plan supports 1. Upgrade to Estate to manage all your trusts."
- Button: "Upgrade Plan" -> links to `/settings/billing?plan=estate`
- Dismissible per session (not permanent)

---

## Trust Plan Tiers (Reference)

| Plan | Price | Trust Limit |
|---|---|---|
| Free | $0 | 1 |
| Trustee | $79/mo or $790/yr | 1 |
| Estate | $149/mo or $1490/yr | 5 |
| Advisor | $399/mo or $3990/yr | Unlimited |

## WingPoint Packages (Reference)

| Package | Price | Trust Credits | Recommended TO Plan |
|---|---|---|---|
| Single Trust | $3,000 | 1 | Trustee ($79/mo) |
| Estate Bundle | $5,500 | 2 | Estate ($149/mo) |
| Builder Bundle | $9,500 | 4 | Estate ($149/mo) |

Coupon: `WINGPOINT50` = $50 off first payment.

---

## Files Modified

| File | Change | Status |
|---|---|---|
| `backend/routers/external_trust_docs.py` | Restricted to ein_confirmation only; HTTPS validation | DONE |
| `backend/routers/external.py` | Added `_determine_recommended_action()` helper; conditional email; enriched response | DONE |
| `backend/routers/subscriptions.py` | Enriched `/subscription/state` with trust_count, trust_limit, needs_upgrade | DONE |
| `frontend/src/pages/PricingPage.js` | WingPoint-aware guard bypass | PENDING |
| `frontend/src/pages/ResetPasswordPage.js` | Post-password-set routing based on plan param | PENDING |
| `frontend/src/pages/BillingPage.js` | Auto-scroll/highlight recommended plan | PENDING |
| `frontend/src/pages/DashboardPage.js` | Upgrade banner when needs_upgrade=true | PENDING |
| `frontend/src/context/AuthContext.js` | Pass through new subscription state fields | PENDING |

---

## Security Considerations

- CP575 transfer: HTTPS-only URLs, API-key auth on endpoint, documents stored as BSON binary in MongoDB (not filesystem)
- Provision API: Already uses API-key auth, rate limiting (100 req/hour), idempotency keys, audit logging
- No secrets or passwords are passed through the API. Set-password tokens are generated server-side.

---

## What WingPoint Needs to Change (Phase 3)

WingPoint's provision call-site needs to:

1. Read `recommended_action.action` from the provision response
2. If `action == "set_password"`: tell user "check your email" (current behavior, no change needed)
3. If `action == "login"`: provide a button/link to `recommended_action.redirect_url`
4. If `action == "login_and_subscribe"`: tell user "your trust is ready, log in to choose your plan" with link
5. If `action == "login_and_upgrade"`: tell user "your trust is ready, log in to upgrade your plan" with link
6. If `action == "login_and_resubscribe"`: tell user "your trust is ready, log in to reactivate"

For CP575 transfer, WingPoint needs to call `/api/external/trust-documents` after the CP575 is available (may be days after SS-4 submission since the IRS mails the letter):
```json
{
  "wingpoint_ref": "WP-123",
  "documents": [
    {
      "type": "ein_confirmation",
      "url": "https://wingpointtrust.com/docs/wp-123-cp575.pdf",
      "filename": "CP575-Smith-Family-Trust.pdf"
    }
  ]
}
```

---

## Edge Cases Handled

- **Idempotent provision:** Same `wingpoint_ref` returns existing provision, no duplicate trust created
- **Existing user gets 2nd trust:** Trust added, `needs_upgrade` flag set, user routed to upgrade path
- **CP575 not yet available:** WingPoint calls document endpoint later when IRS letter arrives. Endpoint is idempotent (dedup by wingpoint_ref + document type).
- **User on canceled subscription:** Routed to `login_and_resubscribe` instead of being blocked
- **No `source_package` provided:** Falls back to trust-count-based plan recommendation
- **Advisor plan users:** `trust_limit` returns "unlimited", `needs_upgrade` is always false