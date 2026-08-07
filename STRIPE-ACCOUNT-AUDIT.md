# Stripe Account Audit — TrustOfficeApp (app.trustoffice.app)

**Date:** 2026-08-05
**Scope:** Verify the Agentic Trust Stripe account is used for ALL TrustOffice products for sale on app.trustoffice.app.
**Method:** Static code review + live Railway env-var inspection.

---

## 1. Summary

**YES — a single Stripe account is used for every TrustOffice payment flow.** There is no evidence of a second/stray Stripe account anywhere in the codebase or in the live Railway environment.

All four backend modules that touch Stripe (`subscriptions.py`, `admin.py`, `stats.py`, `referrals.py`) read their key from one and the same env var, `STRIPE_SECRET_KEY`, and that single key is set once on the `TrustOfficeApp-backend-v2` Railway service. Every product/price ID configured in production shares the same Stripe account hash (`2lZzmsSFmd`), which is embedded in every `price_...` ID Stripe issues. The frontend never loads Stripe.js or a publishable key — it uses Stripe Checkout via server-side redirect, so the only Stripe identity the client ever sees is the one the backend creates the session on.

**Account identification confidence:** The code does not name the account "Agentic Trust" (Stripe account display names are not visible from keys/price IDs). However, (a) only one `STRIPE_SECRET_KEY` exists, (b) it is a **live** key (`sk_live_…`, masked as `sk_l...Hvpd`), and (c) every price ID decodes to the same Stripe account ID via the shared hash `2lZzmsSFmd`. To confirm the account is literally the "Agentic Trust" account, log in to the Stripe Dashboard and verify the account whose price IDs begin with `price_1…2lZzmsSFmd…`.

---

## 2. Stripe Account Identification

### 2.1 The single secret key

Every backend file that calls the Stripe API sets it the same way:

```python
# backend/routers/subscriptions.py:31
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
# backend/routers/admin.py:40
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
# backend/routers/stats.py:22
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
# backend/routers/referrals.py:21
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
```

No file reads `STRIPE_SECRET_KEY_2`, `STRIPE_LIVE_KEY`, `STRIPE_TEST_KEY`, or any alternate key name. There is exactly one secret key in the live environment:

```
STRIPE_SECRET_KEY = sk_l...Hvpd      # on Railway service TrustOfficeApp-backend-v2
```

The `sk_l` prefix (masked by Railway) is the start of `sk_live_…` — a **live** key, not a test key (`sk_test_…`). No test key is configured anywhere.

### 2.2 The single webhook signing secret

```python
# backend/routers/subscriptions.py:32
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
# subscriptions.py:1057
event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
```

Live value: `STRIPE_WEBHOOK_SECRET = whse...Z4bH` → `whsec_…` (live webhook secret). One webhook endpoint only: `POST /api/stripe/webhook`.

### 2.3 The account hash proves one account owns all prices

Stripe price IDs embed the issuing account. Every configured price ID shares the segment `2lZzmsSFmd`:

| Env var | Live price ID | Shared hash |
|---|---|---|
| `STRIPE_TRUSTEE_MONTHLY_PRICE_ID` | `price_1T4RVI2lZzmsSFmdoWliQfMu` | `2lZzmsSFmd` |
| `STRIPE_TRUSTEE_ANNUAL_PRICE_ID` | `price_1T4RWl2lZzmsSFmdvQAnlrOY` | `2lZzmsSFmd` |
| `STRIPE_ESTATE_MONTHLY_PRICE_ID` | `price_1TrTJJ2lZzmsSFmdHZgH7FBF` | `2lZzmsSFmd` |
| `STRIPE_ESTATE_ANNUAL_PRICE_ID` | `price_1TrTJJ2lZzmsSFmd6UJwi79P` | `2lZzmsSFmd` |
| `STRIPE_ADVISOR_MONTHLY_PRICE_ID` | `price_1TrTJK2lZzmsSFmdNJRkqUsM` | `2lZzmsSFmd` |
| `STRIPE_ADVISOR_ANNUAL_PRICE_ID` | `price_1TrTJK2lZzmsSFmdWY8viTg0` | `2lZzmsSFmd` |
| `STRIPE_WINGPOINT_ANNUAL_PRICE_ID` | `price_1Twn252lZzmsSFmdQJp3T97X` | `2lZzmsSFmd` |
| `STRIPE_MONTHLY_PRICE_ID` (legacy) | `price_1T4RVI2lZzmsSFmdoWliQfMu` | `2lZzmsSFmd` |
| `STRIPE_ANNUAL_PRICE_ID` (legacy) | `price_1T4RWl2lZzmsSFmdvQAnlrOY` | `2lZzmsSFmd` |

The legacy monthly/annual price IDs are **identical** to the trustee monthly/annual IDs — the same price objects, just aliased. Every sale therefore settles to the same Stripe account.

---

## 3. All Payment Flows Found

All flows use the single `STRIPE_SECRET_KEY`. File + line references:

### 3.1 Checkout session creation (the sale)
- `backend/routers/subscriptions.py:417` — `stripe.checkout.Session.create(**checkout_params)` for trustee/estate/advisor/wingpoint/legacy plans. Price resolved from `PRICE_IDS` map (lines 46–54) or legacy fallback (line 323). Customer created at `subscriptions.py:348` (`stripe.Customer.create`).
- Frontend triggers: `frontend/src/pages/BillingPage.js:120` (`POST /subscription/create-checkout`) and `frontend/src/pages/PricingPage.js:235` (same endpoint, unauthenticated signup flow). Frontend gets back `checkout_url` and redirects — **no Stripe.js, no publishable key on the client**.

### 3.2 Payment verification
- `subscriptions.py:444` — `stripe.checkout.Session.retrieve(session_id)` with an ownership check (lines 447–451) ensuring the session's `metadata.user_id` matches the caller.

### 3.3 Billing portal
- `subscriptions.py:506` — `stripe.billing_portal.Session.create(customer=…, return_url=…)`.

### 3.4 Subscription lifecycle (cancel / reactivate / upgrade / change-plan)
- Cancel: `subscriptions.py:526` — `stripe.Subscription.modify(…, cancel_at_period_end=True)`
- Reactivate: `subscriptions.py:569` — `stripe.Subscription.modify(…, cancel_at_period_end=False)`
- Upgrade (legacy): `subscriptions.py:616` — `stripe.Subscription.modify` with new `price` from `PRICE_IDS`
- Change plan (3-tier): `subscriptions.py:692` — same pattern, `new_price_id` from `PRICE_IDS.get((plan_type, billing_period))`

### 3.5 Webhook handler
- `subscriptions.py:1050` — `POST /api/stripe/webhook`, signature verified at line 1057 with `STRIPE_WEBHOOK_SECRET`.
- Handled events (dispatch table at line 1042):
  - `checkout.session.completed` → activates subscription, records txn, sends emails
  - `customer.subscription.updated` → plan change / cancel-scheduled detection
  - `customer.subscription.deleted` → marks canceled
  - `invoice.paid` → renewal emails
  - `invoice.payment_failed` → past_due + payment-failed email
- Webhook re-injected into Stripe APIs at `subscriptions.py:156, 614, 688, 758, 988` (all `stripe.Subscription.retrieve`).

### 3.6 Referral program (Stripe coupons)
- `backend/routers/referrals.py:40-61` — `get_or_create_stripe_coupon()` creates/retrieves coupon id `REFERRAL50` (50% off, once) on the same Stripe account.
- Applied to checkout at `subscriptions.py:378-381` (`checkout_params["discounts"] = [{"coupon": referral_coupon}]`).
- Applied to referrer's existing subscription at `referrals.py:337` — `stripe.Subscription.modify(…, coupon=coupon_id)`.

### 3.7 Admin revenue / customer management
- `backend/routers/admin.py:1060, 1270, 1306` — `stripe.Invoice.list(…)` for revenue reporting. Filters invoices by `_is_trustoffice_invoice` (line 98–110) which only counts invoices whose line-item price ID is in `TRUSTOFFICE_PRICE_IDS` (the same set built from the env price IDs).
- `admin.py:1210` — `stripe.Customer.retrieve(customer_id)`.
- `admin.py:477, 681, 1117` — `stripe.Subscription.modify(…, cancel_at_period_end=True)` for admin-driven cancellation.
- `admin.py:689` — `stripe.Customer.delete(stripe_customer_id)` on user deletion.
- `backend/routers/stats.py:191` — `stripe.Invoice.list` for stats; same `_is_trustoffice_invoice` filter (line 81–93).
- `backend/routers/admin_api.py:1116-1117` — `stripe.Subscription.modify` on user deletion.

### 3.8 Frontend Stripe usage
- The frontend does **not** load Stripe.js. No `loadStripe`, no `@stripe/…` import, no `Stripe(…)` constructor, no `pk_live_`/`pk_test_` anywhere in `frontend/src`. Checkout is server-created and the browser is redirected to `checkout.stripe.com` — the publishable key is implicit in the checkout session and is never configured client-side.

### 3.9 Non-flows (fields exist but unused)
- `backend/routers/courses.py:188-189`, `educational.py:99-100`, `external.py:731-732` initialize `stripe_session_id`/`stripe_customer_id` to `None` in default subscription docs but make **no Stripe API calls**. These are placeholder fields only — no separate course-purchase or educational-payment flow exists.

---

## 4. All Stripe Product / Price References

### 4.1 Referenced in code (via env vars)
| Env var | Used in code | Live value |
|---|---|---|
| `STRIPE_TRUSTEE_MONTHLY_PRICE_ID` | subscriptions.py:37,47; admin.py:43,63; stats.py:25,45 | `price_1T4RVI2lZzmsSFmdoWliQfMu` |
| `STRIPE_TRUSTEE_ANNUAL_PRICE_ID` | subscriptions.py:38,48; admin.py:44,64; stats.py:26,46 | `price_1T4RWl2lZzmsSFmdvQAnlrOY` |
| `STRIPE_ESTATE_MONTHLY_PRICE_ID` | subscriptions.py:39,49; admin.py:45,65; stats.py:27,47 | `price_1TrTJJ2lZzmsSFmdHZgH7FBF` |
| `STRIPE_ESTATE_ANNUAL_PRICE_ID` | subscriptions.py:40,50; admin.py:46,66; stats.py:28,48 | `price_1TrTJJ2lZzmsSFmd6UJwi79P` |
| `STRIPE_ADVISOR_MONTHLY_PRICE_ID` | subscriptions.py:41,51; admin.py:47,67; stats.py:29,49 | `price_1TrTJK2lZzmsSFmdNJRkqUsM` |
| `STRIPE_ADVISOR_ANNUAL_PRICE_ID` | subscriptions.py:42,52; admin.py:48,68; stats.py:30,50 | `price_1TrTJK2lZzmsSFmdWY8viTg0` |
| `STRIPE_WINGPOINT_ANNUAL_PRICE_ID` | subscriptions.py:43,53; admin.py:49,69; stats.py:31,51 | `price_1Twn252lZzmsSFmdQJp3T97X` |
| `STRIPE_MONTHLY_PRICE_ID` (legacy) | subscriptions.py:33,79,323; admin.py:41,61; stats.py:23,43 | `price_1T4RVI2lZzmsSFmdoWliQfMu` |
| `STRIPE_ANNUAL_PRICE_ID` (legacy) | subscriptions.py:34,80,323; admin.py:42,62; stats.py:24,44 | `price_1T4RWl2lZzmsSFmdvQAnlrOY` |

### 4.2 Hardcoded price IDs in source
- `memory/PRD.md:1438-1439` — docs only, not code: `price_1T4RVI2lZzmsSFmdoWliQfMu` and `price_1T4RWl2lZzmsSFmdvQAnlrOY`. Match the live env. No `prod_…` IDs are referenced anywhere.

### 4.3 Configured on Railway but NOT referenced in code
These exist on the `TrustOfficeApp-backend-v2` service but are **never read** by the app:
- `STRIPE_BUILDER_BUNDLE_PRICE_ID = price_1T4nXn2lZzmsSFmd2kT3nhb9`
- `STRIPE_ESTATE_BUNDLE_PRICE_ID = price_1T4nXO2lZzmsSFmdurQ12rhQ`
- `STRIPE_SINGLE_TRUST_PRICE_ID = price_1T4nWX2lZzmsSFmdYtMuGTPD`
- `STRIPE_COURSE_LIBRARY_PRICE_ID = price_1TCMHz2lZzmsSFmd3MtEsc3Z`

All four still carry the `2lZzmsSFmd` account hash (same account), so they are not a stray-account risk — but they are dead config. See §5.

---

## 5. Issues Found

### 5.1 (Low) Orphaned Stripe price env vars on Railway
`STRIPE_BUILDER_BUNDLE_PRICE_ID`, `STRIPE_ESTATE_BUNDLE_PRICE_ID`, `STRIPE_SINGLE_TRUST_PRICE_ID`, and `STRIPE_COURSE_LIBRARY_PRICE_ID` are set on Railway but referenced **nowhere** in the codebase (grep returns zero hits). They appear to be leftovers from earlier WingPoint-bundle / course-library product ideas that were never wired up, or are handled on the WingPoint side instead. They do not create a wrong-account risk (same `2lZzmsSFmd` hash), but they are misleading config. **Recommendation:** remove the four unused vars from Railway, or document why they are retained.

### 5.2 (Low) Revenue filter silently degrades to "all invoices"
`backend/routers/admin.py:98-110` and `backend/routers/stats.py:81-93`:
```python
def _is_trustoffice_invoice(inv) -> bool:
    if not any(TRUSTOFFICE_PRICE_IDS):
        logger.warning("No TrustOffice price IDs configured — including all invoices in revenue")
        return True
```
If the price-ID env vars are ever unset, the revenue endpoints silently count **every invoice on the Stripe account** as TrustOffice revenue. Today the vars are set, so this is dormant. **Recommendation:** change the fallback to `return False` (exclude unknown invoices) so a misconfiguration can't inflate reported revenue with unrelated account activity.

### 5.3 (Informational) No Stripe publishable key on the frontend — correct by design
The frontend never loads Stripe.js; it relies on server-created Checkout sessions. This is the right pattern and means there is no second publishable key that could point at a different account. No action needed; noted for completeness.

### 5.4 (Informational) Account display name not verifiable from code
The code/keys prove *one* account is used, and that all prices belong to *that one account* via the shared `2lZzmsSFmd` hash. But nothing in the repo labels that account "Agentic Trust." Confirm in the Stripe Dashboard that the account with these price IDs is the Agentic Trust account. This is the only step that requires human verification outside the codebase.

---

## 6. Recommendations

1. **Confirm in the Stripe Dashboard** that the live account holding `price_1T4RVI2lZzmsSFmdoWliQfMu` (and the other `…2lZzmsSFmd…` prices) is the "Agentic Trust" account. This is the one item the audit cannot close from code alone.
2. **Remove the four unused Railway vars** (`STRIPE_BUILDER_BUNDLE_PRICE_ID`, `STRIPE_ESTATE_BUNDLE_PRICE_ID`, `STRIPE_SINGLE_TRUST_PRICE_ID`, `STRIPE_COURSE_LIBRARY_PRICE_ID`) to keep config honest, OR add code that uses them if those products are meant to be sold.
3. **Harden `_is_trustoffice_invoice`** in `admin.py:98` and `stats.py:81` to `return False` (not `True`) when no price IDs are configured, so a future env misconfiguration can't silently merge unrelated invoices into TrustOffice revenue.
4. No other changes needed. The Agentic Trust Stripe account is the only account wired into checkout, webhooks, coupons, the billing portal, subscription mutations, and revenue reporting.

---

## Appendix — Evidence

- **One secret key, live mode:** Railway `TrustOfficeApp-backend-v2 → STRIPE_SECRET_KEY = sk_l...Hvpd` (sk_live prefix). No `STRIPE_SECRET_KEY_*` alternates, no test key, no key in any other Railway service.
- **One webhook secret:** `STRIPE_WEBHOOK_SECRET = whse...Z4bH` (whsec prefix). One handler at `POST /api/stripe/webhook`.
- **One account hash across all 9 prices:** `2lZzmsSFmd` appears in every configured `price_…` ID.
- **No hardcoded keys in source:** grep for `sk_live_|sk_test_|pk_live_|pk_test_|acct_` returns only `acct_test` literals in `backend/tests/test_stripe_webhook_event_access.py` (test fixtures, not real keys).
- **No frontend Stripe.js:** grep for `loadStripe|@stripe|stripe.js|Stripe(|pk_live|pk_test|publishable` in `frontend/src` returns zero hits.