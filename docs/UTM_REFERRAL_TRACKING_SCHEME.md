# TrustOffice — UTM / Referral Tracking Scheme

**Status:** Implemented (documenting the live system) + design notes for gaps.
**Last updated:** 2026-08-14
**Scope:** Full-funnel attribution from first ad/marketing touch → lead capture → signup → checkout → purchase, covering three attribution channels: marketing UTM, friend referrals, and WingPoint partner referrals.

---

## 1. Goals

1. **Durable, server-side attribution** that survives cross-domain redirects, OAuth flows, and ad-blockers (client-side GA4/Meta Pixel alone are not reliable).
2. **Three attribution channels, one canonical source string** per user so reporting can group signups/purchases without ambiguity.
3. **Idempotent event recording** so webhook retries and page reloads cannot duplicate funnel events.
4. **Carry attribution to Stripe checkout metadata** so revenue can be tied back to the campaign/partner that produced it — even for direct-to-checkout users who never create a lead.
5. **Privacy-safe**: UTM/referrer values are sanitized (control chars stripped, length-capped); no PII is placed in URL params that could leak via referrer headers.

---

## 2. Attribution Channels

| Channel | URL param(s) | Canonical `source` value | Where captured | Reward mechanism |
|---|---|---|---|---|
| **Marketing UTM** | `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term` | `{utm_source}_{utm_medium}` (lowercased, non-alnum → `_`) | Landing page → sessionStorage → signup/checkout payload | None (paid/organic) |
| **Friend referral** | `ref` (alias `referral_code`) | `friend_referral` | Landing page → sessionStorage → `UserCreate.referral_code` | 50% off first payment (Stripe coupon `REFERRAL50`) for referee; referrer reward via `process_referral_conversion` |
| **WingPoint partner referral** | `wp_ref` (+ optional `wp_trust_name`) | `wingpoint_referral` | WingPoint redirect → OAuth state doc OR `/connect/wingpoint` flow → persisted on user doc | WingPoint plan gating in `subscriptions.py`; `is_wingpoint` flag on user |

### 2.1 Canonical source resolution priority

`resolve_signup_source()` / `resolve_signup_source_from_payload()` in `backend/tracking/utm_tracker.py`:

1. `wp_ref` present → `wingpoint_referral`
2. `referral_code` present → `friend_referral`
3. `utm_source` present → `{utm_source}_{utm_medium or "unknown"}` (sanitized)
4. Otherwise → `direct`

Priority is deliberate: partner and friend referrals are relationship-based and should override a coincidental UTM click that brought the user to the referral link. UTM is the fallback for cold marketing traffic.

---

## 3. Data Flow — End to End

### 3.1 First touch (landing page, any marketing surface)

```
User clicks ad / referral link with ?utm_source=google&utm_medium=cpc&utm_campaign=trustee-101&ref=JANE50
        │
        ▼
App.js calls captureUtmParams()  [frontend/src/utils/utmCapture.js]
        │  - reads URLSearchParams for all UTM_KEYS
        │  - sanitizes each (strip control chars + <>, cap 200 chars; ref/wp_ref capped 50)
        │  - writes to sessionStorage with "utm_" prefix
        ▼
sessionStorage now holds: utm_utm_source, utm_utm_campaign, utm_utm_medium,
                          utm_utm_content, utm_utm_term, utm_ref, utm_wp_ref, ...
```

**Key behavior:** URL params *overwrite* stored params on every `captureUtmParams()` call, so a fresh ad click always updates attribution. `getUtmParams()` merges stored + current URL with URL taking precedence, so internal navigation does not lose attribution.

### 3.2 Lead capture (marketing form, pre-signup)

```
POST /api/admin/leads/capture
  body: { email, source, utm_source, utm_campaign, utm_medium, ... }
        │
        ▼
  leads.py creates/updates lead doc in db.leads
  leads.py calls record_lead_capture()  →  analytics.py._record_event("lead_captured")
        │  idempotency_key = "lead_capture_{lead_id}_{source}"
        │  metadata = { lead_id, source, utm_source, utm_campaign, utm_medium, referrer, is_returning }
        ▼
  db.analytics_events.insert_one(event_doc)   # idempotent via unique sparse index on idempotency_key
  Discord notification sent (notify_new_lead)
```

**Lead sources** are a fixed enum (`LEAD_SOURCES` in `leads.py`): `trustee-101-landing-page`, `trustee-90-day-checklist`, `commingling-checklist`, `blog-subscribe`, `blog-article-pdf`, `webinar-signup`, `booked-call`, `resources-subscribe`, etc. Each has a `SOURCE_QUALITY` score (1–10) feeding the lead score.

### 3.3 Signup (account creation)

```
POST /api/auth/register
  body: UserCreate { email, password, name, referral_code, wp_ref, wp_trust_name,
                     utm_source, utm_campaign, utm_medium, referrer }
        │
        ▼
  auth.py:
    - _clean_utm() sanitizes each UTM field
    - Creates user doc in db.users with: utm_source, utm_campaign, utm_medium,
      referrer, referral_code, wp_ref, wp_trust_name
    - If referral_code present → looks up referrer in db.referral_codes,
      records referral relationship (best-effort, non-blocking)
    - If wp_ref present → marks is_wingpoint=True, persists wp_ref
        │
        ▼
  (Design note) record_signup_attribution() should be called here:
    - source = resolve_signup_source(user_doc)
    - _record_event("signup_complete", idempotency_key="signup_{user_id}",
        metadata = { email, source, utm_*, referrer, referral_code, wp_ref })
```

**OAuth path** (Google/Apple): `wp_ref` is stored in the OAuth state doc (`/api/auth/oauth/{provider}/init?wp_ref=...`), then read back after callback so partner attribution survives the redirect to Google/Apple and back.

### 3.4 Checkout (Stripe)

```
POST /api/subscriptions/create-checkout
  body: CheckoutRequest { plan_type, billing_period, utm_source, utm_campaign,
                          utm_medium, referrer, referral_id (Rewardful) }
        │
        ▼
  subscriptions.py:
    - Builds Stripe checkout params with metadata:
        { user_id, plan_type, billing_period,
          utm_source, utm_campaign, utm_medium, referrer }   # each ≤200 chars
    - If referral_id (Rewardful affiliate) → client_reference_id = referral_id
    - If user has a friend referral → apply_referral_discount_to_checkout()
        adds coupon REFERRAL50 (50% off once) to the session
    - If direct coupon provided → applies that instead
        │
        ▼
  Stripe Checkout Session created with full attribution in metadata
```

### 3.5 Purchase completion (Stripe webhook)

```
Stripe → POST /api/subscriptions/webhook  (checkout.session.completed)
        │
        ▼
  subscriptions.py webhook handler:
    - Reads session.metadata → { user_id, plan_type, billing_period, utm_* }
    - Creates/updates subscription record in db.subscriptions
    - record_purchase_complete()  →  analytics._record_event("purchase_complete")
        idempotency_key = "purchase_{checkout_session_id}"
        metadata = { user_id, plan_type, billing_period, amount, currency,
                     checkout_session_id, stripe_subscription_id, referral_id, coupon }
    - _process_referral_conversion_safe(user_id)
        → if user was referred by a friend, process_referral_conversion()
          rewards the referrer
        │
        ▼
  db.analytics_events now has the durable, server-confirmed purchase event
  with full attribution carried from the Stripe metadata.
```

**Critical design property:** Because UTM data is in Stripe session metadata, the webhook can record a `purchase_complete` event with attribution *even if the user went directly to checkout and never created a lead or had a signup event*. This closes the "direct-to-checkout" attribution gap.

---

## 4. Data Structures

### 4.1 MongoDB collections

#### `users` (attribution fields on user doc)
```js
{
  user_id: "usr_...",
  email: "...",
  // Attribution (set at signup, immutable)
  utm_source: "google" | null,
  utm_campaign: "trustee-101" | null,
  utm_medium: "cpc" | null,
  referrer: "https://google.com" | null,   // document.referrer
  referral_code: "JANE50" | null,           // friend referral code used
  wp_ref: "WP-XYZ123" | null,               // WingPoint partner ref
  wp_trust_name: "Smith Family Trust" | null,
  // Derived
  is_wingpoint: true | false,
  source: "wingpoint_referral" | "friend_referral" | "google_cpc" | "direct",
  created_via: "register" | "google_oauth" | "apple_oauth" | "wingpoint_provision"
}
```

#### `referral_codes` (friend referral program)
```js
{
  referral_id: "ref_<uuid12>",
  user_id: "usr_...",          // the referrer (code owner)
  code: "JANE50",              // unique, 8 chars (4 name + 4 random)
  created_at: "ISO-8601",
  // Conversion tracking
  referee_user_id: "usr_..." | null,
  discount_applied: true | false,
  converted_at: "ISO-8601" | null,
  reward_status: "pending" | "paid" | "none"
}
```

#### `analytics_events` (durable funnel event log — source of truth for reporting)
```js
{
  _id: ObjectId,
  event_name: "lead_captured" | "signup_complete" | "purchase_complete",
  user_id: "usr_..." | null,    // null for leads (no account yet)
  session_id: "lead_id" | "checkout_session_id" | null,
  metadata: {
    // lead_captured
    lead_id, source, utm_source, utm_campaign, utm_medium, referrer, is_returning,
    // signup_complete
    email, source, utm_source, utm_medium, utm_campaign, utm_content, utm_term,
    referrer, referral_code, wp_ref,
    // purchase_complete
    user_id, plan_type, billing_period, amount, currency, checkout_session_id,
    stripe_subscription_id, referral_id, coupon
  },
  idempotency_key: "lead_capture_{lead_id}_{source}"
                | "signup_{user_id}"
                | "purchase_{checkout_session_id}",
  created_at: "ISO-8601"
}
```
**Index:** unique sparse on `idempotency_key` — the race-safe dedupe gate for concurrent webhook deliveries.

#### `leads` (CRM lead records)
```js
{
  lead_id: "lead_...",
  email: "...",
  name: "..." | null,
  source: "trustee-101-landing-page",   // from LEAD_SOURCES enum
  stage: "new" | "engaged" | "warm" | "converted" | "lost",
  score: 0-100,                          // composite (source_quality + engagement + recency)
  utm_source: "google" | null,
  utm_campaign: "trustee-101" | null,
  utm_medium: "cpc" | null,
  created_at: "ISO-8601",
  converted_user_id: "usr_..." | null,
  activity_log: [{ action, detail, timestamp }]
}
```

### 4.2 Frontend sessionStorage schema

Keys prefixed with `utm_`:
```
utm_utm_source, utm_utm_campaign, utm_utm_medium, utm_utm_content, utm_utm_term,
utm_referrer, utm_ref, utm_wp_ref, utm_wp_trust_name
```
Cleared after successful signup via `clearUtmParams()` to prevent stale attribution of future actions.

### 4.3 Stripe checkout session metadata

```js
{
  user_id: "usr_...",
  plan_type: "trustee" | "estate" | "advisor" | "wingpoint",
  billing_period: "monthly" | "annual",
  utm_source: "google",      // ≤200 chars
  utm_campaign: "trustee-101",
  utm_medium: "cpc",
  referrer: "https://google.com"
}
// client_reference_id = Rewardful referral_id (if affiliate)
// discounts: [{ coupon: "REFERRAL50" }] (if friend referral)
```

---

## 5. Event Taxonomy

| Event | Trigger | Idempotency key | Key metadata |
|---|---|---|---|
| `lead_captured` | Lead form submit (leads.py) | `lead_capture_{lead_id}_{source}` | lead_id, source, utm_*, referrer, is_returning |
| `signup_complete` | Account creation (auth.py) | `signup_{user_id}` | email, source (canonical), utm_*, referrer, referral_code, wp_ref |
| `purchase_complete` | Stripe `checkout.session.completed` webhook | `purchase_{checkout_session_id}` | user_id, plan_type, billing_period, amount, checkout_session_id, referral_id, coupon |

---

## 6. Reporting

`get_attribution_summary(start_date, end_date)` in `utm_tracker.py`:
- Aggregates `analytics_events` by `metadata.source` for both `signup_complete` and `purchase_complete`.
- Returns signups-by-source (count) and purchases-by-source (count + revenue).
- Used by admin dashboards and weekly reporting.

**Funnel join:** `lead_captured` → `signup_complete` is joined on email (lead has no user_id until signup). `signup_complete` → `purchase_complete` is joined on `user_id`. This gives a full lead → signup → purchase funnel with attribution at every stage.

---

## 7. Sanitization & Security

- **`clean_utm()`** (backend) / **`sanitize()`** (frontend): strip control chars (`\x00-\x1f`, `\x7f`), angle brackets (`<>`), collapse whitespace, cap length (200 chars UTM, 500 chars referrer, 50 chars referral codes).
- UTM values are **never** used in SQL/MongoDB queries without sanitization — they are stored as-is after cleaning and only read back for reporting aggregation.
- No PII in URL params: email is never passed via UTM; it only enters the system via POST body at lead capture / signup.
- Referral codes are validated against `db.referral_codes` before any discount is applied — a fabricated `?ref=FAKE` produces no discount.
- Stripe webhook signature verification is the trust boundary for `purchase_complete`; UTM in metadata is informational, not security-critical.

---

## 8. Identified Gaps & Recommendations

### 8.1 `signup_complete` event not yet wired
`record_signup_attribution()` exists in `utm_tracker.py` but is **not called** from `auth.py`'s register endpoint. The user doc stores UTM fields, but no `analytics_events` row is created at signup. **Recommendation:** add the call in `auth.py` after user creation (both password and OAuth paths).

### 8.2 `utm_content` and `utm_term` not persisted on user doc
`UserCreate` model has `utm_source`, `utm_campaign`, `utm_medium`, `referrer` but **not** `utm_content` or `utm_term`. The frontend captures them and `extract_utm_params()` / `record_signup_attribution()` handle them, but they are dropped at the `UserCreate` boundary. **Recommendation:** add `utm_content` and `utm_term` to `UserCreate` and persist on the user doc for full A/B creative attribution.

### 8.3 Lead capture missing `utm_content` / `utm_term` / `referral_code` / `wp_ref`
`LeadCapture` model in `leads.py` has `utm_source`, `utm_campaign`, `utm_medium` but not the full set. A lead arriving via `?ref=JANE50&utm_content=variant-b` loses the referral code and creative variant. **Recommendation:** extend `LeadCapture` to include `utm_content`, `utm_term`, `referral_code`, `wp_ref` and pass them to `record_lead_capture()`.

### 8.4 No first-touch vs. last-touch distinction
Current scheme is last-touch (URL overwrites sessionStorage on every page load). If a user clicks a Google ad, then later clicks a friend's referral link, the referral wins (correct per priority), but the original Google touch is lost. **Recommendation (future):** add a `first_touch_utm` snapshot that is set once and never overwritten, keeping `utm_*` as last-touch. Store both for multi-touch attribution analysis.

### 8.5 External ad platform server-side forwarding not configured
`record_purchase_complete()` documents this: GA4 Measurement Protocol and Meta Conversions API server-side calls are not wired. Events are recorded internally only. **Recommendation:** when ad platform credentials are available, add forwarding calls in `analytics.py` after `_record_event()` succeeds.

### 8.6 No cross-domain cookie / fingerprinting
WingPoint → TrustOffice attribution relies on `wp_ref` surviving the redirect via query params / OAuth state. This is robust for the WingPoint flow but does not cover arbitrary third-party referring sites (those rely on `document.referrer` only). This is acceptable given privacy regulations (no third-party cookies).

---

## 9. File Map

| Component | Path |
|---|---|
| Backend tracking module | `backend/tracking/utm_tracker.py` |
| Backend tracking init | `backend/tracking/__init__.py` |
| Analytics event recording | `backend/routers/analytics.py` |
| Auth (signup attribution) | `backend/routers/auth.py` |
| Leads (lead capture attribution) | `backend/routers/leads.py` |
| Subscriptions (checkout attribution) | `backend/routers/subscriptions.py` |
| Referrals (friend referral program) | `backend/routers/referrals.py` |
| User / checkout models | `backend/models.py` |
| Frontend UTM capture | `frontend/src/utils/utmCapture.js` |
| Frontend analytics | `frontend/src/utils/analytics.js` |
| **This document** | `docs/UTM_REFERRAL_TRACKING_SCHEME.md` |
| **Tracking structure (machine-readable)** | `docs/tracking_structure.json` |