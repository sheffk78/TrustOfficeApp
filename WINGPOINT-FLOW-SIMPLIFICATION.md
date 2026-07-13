# WingPoint → TrustOffice Customer Journey: Simplification Analysis

## Current Flow Summary

### New Customer (5 steps, 4 page transitions)
```
WingPoint purchase
  → Backend provisions account + trust, sends email
    → Customer opens email, clicks link
      → /wingpoint?action=set_password&token=XXX (set password form)
        → After password set, navigate to /wingpoint (logged out)
          → Customer must then log in
            → Redirected to /pricing?wp=1&action=subscribe&plan=XX
              → Click "Confirm and Continue" → Stripe checkout
                → /dashboard?welcome=true
```

**Actual page transitions:** Email → /wingpoint (set password) → /wingpoint (login) → /pricing → Stripe → /dashboard = **5 distinct pages, ~4 clicks, 1 email hop**

### Existing Customer Buying More Trusts (3-5 steps depending on state)
```
WingPoint purchase
  → Backend adds trust to existing account, determines recommended_action
    → If no password: email → set password → login → pricing/upgrade → checkout → dashboard
    → If free/trial: login → /pricing → Stripe → dashboard
    → If needs upgrade: login → /billing → change plan → dashboard
    → If active & covers trusts: login → dashboard (ideal case, 1 click)
```

---

## Identified Friction Points

1. **Email is a hard dependency** — The entire new-user flow can't start until the customer opens their email and clicks a link. Email deliverability, spam filters, and "I didn't see the email" all block activation.

2. **Set-password and plan selection are on separate pages** — After setting a password, the customer sees a success message, gets redirected to /wingpoint (logged out), must log in with the password they just set, then gets sent to /pricing. This is 3 page loads between "password set" and "choose plan."

3. **Plan selection is not pre-confirmed** — The backend already computes `PACKAGE_TO_PLAN` mapping (single_trust→trustee, estate_bundle→estate, builder_bundle→estate). The set-password URL already includes `&action=subscribe&plan=XX`. But the customer still lands on a full pricing page with 3 tiers, a comparison table, and a billing toggle — cognitive load when the system already knows which plan they need.

4. **Post-password-set requires re-login** — After setting a password via the email token, the customer is NOT auto-logged-in. They see "Password set successfully! You can now log in" and must navigate to login, type email + password, and then get redirected. This is an unnecessary round-trip.

5. **The /wingpoint page tries to be 3 things at once** — It's a welcome/landing page, a set-password form, AND a login form (toggle). The `NotLoggedInAction` component handles `set_password`, `subscribe`, and default states with different UI, making it complex and easy to get lost in.

6. **Existing-user flow has 5 possible branches** — `_determine_recommended_action` returns 6 different action types (set_password, login_and_subscribe, login_and_upgrade, login_and_resubscribe, login_and_update_payment, login). Each routes to a different page. The customer may not understand why they're being sent to billing vs. pricing vs. dashboard.

7. **Stripe checkout is a full redirect** — Customer leaves TrustOffice, completes Stripe checkout, then redirects back. No pre-loading or embedded option.

8. **WingPointWelcomePage's "Which package did you purchase?" section** — Asks the customer to self-identify their package, but the backend already knows this from `source_package`. This is informational only — no action is tied to selecting a package card.

---

## Proposals Ranked by Impact × Effort

### 🏆 HIGHEST IMPACT: Auto-login after password set + inline plan confirmation on /wingpoint

**Impact: HIGH | Effort: MEDIUM**

Merge steps 2-4 into a single page: After the customer sets their password from the email link, they are **automatically logged in** and the password-set card transitions directly to a **"Confirm your subscription" card** on the same page — showing the pre-selected plan (already computed from their WingPoint package), the $50 credit, and a single "Confirm and Subscribe" button that goes straight to Stripe.

**What this eliminates:**
- The logged-out limbo after password set (no re-login needed)
- Navigation to /pricing (no separate plan-selection page)
- The full 3-tier comparison table for WingPoint users who already have a recommended plan

**Result:** Email link → set password → **auto-logged-in + confirm plan card** → Stripe → dashboard = **3 pages, 2 clicks**

**Implementation outline:**
- Backend `/api/auth/reset-password` returns a JWT auth token on success (for set_password purpose only)
- Frontend `handleSetPassword` stores the token, sets `AuthContext.user`, and flips a state flag to show the plan-confirmation card instead of the "password set" success message
- The plan-confirmation card reuses the existing `wingPointPlan` pre-selected card logic from PricingPage (already renders a "Recommended for You" card with plan name, price, $50 credit, and a single confirm button)
- "See other plans" link still available for users who want to choose differently

---

### Proposal 2: WingPoint redirect link with embedded token (skip the email)

**Impact: HIGH | Effort: MEDIUM-HIGH**

WingPoint's purchase confirmation page includes a button: "Activate your TrustOffice account" that links directly to `/wingpoint?action=set_password&token=XXX` — the same token that would be in the email. The email becomes a **backup**, not the primary activation path.

**What this eliminates:**
- The email-as-gatestep for customers who are still on the WingPoint site
- The "I didn't get the email" support burden for the most common case

**Result:** Customer finishes WingPoint purchase → clicks "Activate" → lands directly on TrustOffice set-password page = **0 email hops for the happy path**

**Implementation outline:**
- The provision API response already returns `set_password_url` — WingPoint just needs to render it as a button on their confirmation page
- This is primarily a **WingPoint-side change** (their confirmation page needs the button), with no TrustOffice backend changes needed
- The email is still sent as a fallback, and the resend endpoint exists for support
- Coordinate with WingPoint team to add the button to their purchase-confirmation page

---

### Proposal 3: Skip pricing page entirely — single confirm card on /wingpoint

**Impact: HIGH | Effort: LOW**

Even without auto-login (Proposal 1), the logged-in `/wingpoint` page can show a **single plan-confirmation card** instead of redirecting to /pricing. The backend already determines the recommended plan. The /wingpoint page's `LoggedInAction` component (which already shows contextual cards for upgrade/no-subscription/all-set states) can show a "Confirm your subscription" card with:
- Pre-selected plan name + price (from `PACKAGE_TO_PLAN` mapping)
- $50 WingPoint credit badge
- Monthly/annual toggle
- Single "Confirm and Continue →" button → Stripe checkout
- Small "See other plans" link

**What this eliminates:**
- Full-page pricing page navigation for WingPoint users
- The 3-tier comparison table and feature lists (information overload)
- The cognitive step of "which plan do I choose?"

**Result:** Login → confirm card on same page → Stripe → dashboard = **2 pages, 1 click for existing users**

**Implementation outline:**
- `LoggedInAction` already has a `!hasActiveSubscription` branch that navigates to `/pricing?wp=1...` — replace that `navigate()` call with rendering an inline `<PlanConfirmCard>` component
- The card's checkout handler calls the same `/api/subscription/create-checkout` endpoint
- The `source_package` → plan mapping already exists in `PACKAGE_TO_PLAN` and is passed via URL params

---

### Proposal 4: Auto-login after password set (standalone)

**Impact: HIGH | Effort: LOW**

Even without the inline plan card, simply **auto-logging-in after password set** eliminates one full page transition and reduces confusion. Currently: set password → "success, now log in" → type email+password → redirect. Instead: set password → automatically logged in → smart routing to next step.

**What this eliminates:**
- The "you can now log in" success message → login form → submit round-trip
- Customer confusion of "I just set a password, why do I need to log in?"

**Implementation outline:**
- Modify `/api/auth/reset-password` to optionally return a JWT when `purpose=set_password`
- Frontend stores token, sets `AuthContext.user`, calls `loadTrusts()` + `loadSubscriptionState()`
- The existing smart-routing logic in `LoginPage`'s `useEffect` (which checks `wp` + `action` params) runs naturally
- ~20 lines of backend change, ~15 lines of frontend change

---

### Proposal 5: Existing-user zero-click flow (login → dashboard, auto-handle everything)

**Impact: HIGH | Effort: HIGH**

For existing users whose plan already covers their trusts, the flow is already close to zero-click: login → dashboard. But for users who need to subscribe, upgrade, or update payment, there are intermediate steps. This proposal makes **all of those happen automatically** with a confirmation banner on the dashboard instead of a separate page:

- **Subscribe:** After login, if user has no subscription, auto-create a Stripe checkout session for the recommended plan and show an interstitial "Setting up your subscription…" → redirect to Stripe. Or, if the $50 credit + WingPoint package warrants it, auto-start a trial and show a "Complete your subscription" banner on the dashboard.
- **Upgrade:** After login, if `needs_upgrade`, show a dismissible banner on the dashboard (already partially implemented as `upgrade-banner`) with a one-click "Upgrade Now" button that uses Stripe's `change-plan` API (no checkout redirect needed — prorated instantly).
- **Update payment:** After login, if `past_due`, show a "Update payment method" banner with a Stripe portal link.

**What this eliminates:**
- All intermediate page transitions for existing users
- The `/billing` and `/pricing` pages as mandatory stops

**Result:** Login → dashboard with smart banners = **1 page, 0 extra clicks for most cases**

**Implementation outline:**
- The dashboard already has `upgrade-banner` and `wp-welcome-modal` components
- Add a `subscribe-banner` for no-subscription users and a `payment-banner` for past_due users
- The upgrade flow already uses `/subscription/change-plan` (no Stripe redirect)
- The subscribe flow would need a new "quick checkout" endpoint that returns a Stripe checkout URL in the banner's CTA
- Most complex proposal because it touches dashboard, billing, and subscription logic

---

### Proposal 6: Pre-load Stripe checkout session during set-password

**Impact: MEDIUM | Effort: MEDIUM**

When the backend generates the set-password token, it also **pre-creates a Stripe Checkout Session** for the recommended plan (with the $50 coupon applied). The session URL is embedded in the set-password page's metadata. When the user clicks "Confirm and Subscribe," the redirect to Stripe is instant — no API call needed.

**What this eliminates:**
- The 1-3 second loading spinner while `/api/subscription/create-checkout` runs
- A potential failure point (checkout session creation can fail)

**Implementation outline:**
- After provisioning, call Stripe to create a checkout session and store the `checkout_url` on the provision record
- The set-password page receives the checkout URL via the verify-token endpoint
- When user clicks confirm, `window.location.href = checkout_url` — instant redirect
- Stripe sessions expire after 24 hours, so this only works if the user activates within that window. For longer windows, create the session lazily but cache it.
- Consider: Stripe's [Payment Links](https://stripe.com/docs/payments/payment-links) (no-session, permanent URLs) as an alternative

---

### Proposal 7: Remove the "Which package did you purchase?" section

**Impact: LOW | Effort: LOW**

The `WINGPOINT_PACKAGES` section on the WingPointWelcomePage asks customers to self-identify their package. But the backend already knows the package from `source_package` in the provision record. This section is purely informational and adds scroll length + cognitive load.

**What this eliminates:**
- 3 package cards the customer has to read through
- The implicit question "which one am I?" that creates uncertainty

**Implementation outline:**
- Remove the `WINGPOINT_PACKAGES` section from `WingPointWelcomePage.js` (lines 221-253)
- Or, replace it with a single "Your package: [Single Trust] → Trustee plan" confirmation card that reads from the token's provision data
- ~30 lines deleted, 0 backend changes

---

### Proposal 8: Unified /wingpoint route that handles all states

**Impact: MEDIUM | Effort: MEDIUM**

Currently the flow bounces between `/wingpoint`, `/reset-password`, `/login`, `/pricing`, and `/billing`. Consolidate into a single `/wingpoint` route that:
- If token present: shows set-password form
- After set password: auto-login, shows plan confirm card
- If logged in + no subscription: shows plan confirm card
- If logged in + needs upgrade: shows upgrade card
- If logged in + all set: redirects to dashboard

**What this eliminates:**
- URL-hopping between 3-4 different pages
- The need for WingPoint to construct different redirect URLs for different scenarios (the `_determine_recommended_action` function returns 6 different redirect URLs — all could be `/wingpoint` with different internal state)

**Implementation outline:**
- `/wingpoint` already handles `set_password` and `subscribe` actions — extend it to handle `upgrade`, `resubscribe`, and `update_payment` actions too
- The `LoggedInAction` component already has branches for all these states — just add the inline confirm cards
- The backend's `_determine_recommended_action` would always return `/wingpoint?action=XXX` instead of `/login?wp=1&action=XXX`

---

## Summary Ranking

| # | Proposal | Impact | Effort | Pages Saved | Clicks Saved |
|---|----------|--------|--------|-------------|---------------|
| 1 | Auto-login + inline plan confirm on /wingpoint | **HIGH** | MEDIUM | 2 | 2 |
| 4 | Auto-login after password set (standalone) | **HIGH** | LOW | 1 | 1 |
| 3 | Skip pricing page — confirm card on /wingpoint | **HIGH** | LOW | 1 | 1 |
| 2 | WingPoint redirect link (skip email) | **HIGH** | MED-HIGH | 1 | 1 |
| 5 | Existing-user zero-click flow | **HIGH** | HIGH | 1-2 | 1-2 |
| 8 | Unified /wingpoint route | MEDIUM | MEDIUM | 1-2 | 0-1 |
| 6 | Pre-load Stripe checkout | MEDIUM | MEDIUM | 0 | 0 (faster) |
| 7 | Remove package self-identification section | LOW | LOW | 0 | 0 (cleaner) |

---

## Recommended Implementation Path

### Phase 1: Quick wins (1-2 days)
1. **Proposal 4** — Auto-login after password set (LOW effort, HIGH impact)
2. **Proposal 3** — Skip pricing page with inline confirm card (LOW effort, HIGH impact)
3. **Proposal 7** — Remove package self-identification section (LOW effort, LOW impact)

**Result:** New customer flow becomes: Email link → set password (auto-logged-in) → confirm plan card → Stripe → dashboard = **3 pages, 2 clicks**

### Phase 2: Merge into single page (3-5 days)
4. **Proposal 1** — Merge auto-login + inline plan confirm into one seamless page transition
5. **Proposal 8** — Unify all states under /wingpoint route

**Result:** New customer flow becomes: Email link → set password → confirm plan (same page) → Stripe → dashboard = **2 pages, 2 clicks**

### Phase 3: Eliminate email dependency (1-2 weeks, WingPoint coordination)
6. **Proposal 2** — WingPoint confirmation page button with direct activation link
7. **Proposal 6** — Pre-load Stripe checkout for instant redirect

**Result:** New customer flow becomes: WingPoint "Activate" button → set password + confirm plan → Stripe → dashboard = **2 pages, 2 clicks, 0 email hops**

### Phase 4: Existing-user zero-click (1-2 weeks)
8. **Proposal 5** — Dashboard smart banners replace all intermediate pages

**Result:** Existing user flow becomes: Login → dashboard (with contextual banner if action needed) = **1 page, 0-1 clicks**

---

## The Ideal 2-Step Flow (New Customers)

```
Step 1: Set password
  ┌─────────────────────────────────────────────┐
  │  Welcome to TrustOffice                     │
  │  Your WingPoint trust is ready.             │
  │                                             │
  │  New Password:  [________________]          │
  │  Confirm:       [________________]          │
  │                                             │
  │         [ Set Password & Continue → ]       │
  │                                             │
  │  $50 WingPoint credit applied ✓             │
  └─────────────────────────────────────────────┘

Step 2: Confirm subscription (auto-logged-in, same page transition)
  ┌─────────────────────────────────────────────┐
  │  ✓ Password set — welcome!                  │
  │                                             │
  │  Your Plan: Trustee — $79/month              │
  │  WingPoint credit: $50 off first month       │
  │                                             │
  │  [Monthly] [Annual (2 months free)]         │
  │                                             │
  │      [ Confirm & Start Managing → ]          │
  │                                             │
  │      See other plans                        │
  └─────────────────────────────────────────────┘
```

**Then:** Stripe checkout → dashboard with welcome modal.

Total: **2 steps, 1 page, 0 re-logins, 0 plan-browsing.**

---

## The Ideal 1-Step Flow (Existing Customers)

```
Step 1: Log in
  ┌─────────────────────────────────────────────┐
  │  Welcome back — your new trust is ready      │
  │                                             │
  │  Email:    [________________]               │
  │  Password: [________________]               │
  │                                             │
  │         [ Log In → ]                        │
  └─────────────────────────────────────────────┘
```

**Then:** Auto-routed to dashboard with a contextual banner:

```
  ┌─────────────────────────────────────────────┐
  │  ⚡ Your new trust has been added!           │
  │  Your Estate plan covers 5 trusts (3 active) │
  │  [Go to Dashboard]                          │
  └─────────────────────────────────────────────┘
```

Or if upgrade needed:

```
  ┌─────────────────────────────────────────────┐
  │  ⚡ Your plan supports 1 trust but you have 3 │
  │  Upgrade to Estate ($149/mo) to manage all  │
  │  [Upgrade Now] (prorated, no checkout)      │
  └─────────────────────────────────────────────┘
```

Total: **1 step, 0 extra pages, 0-1 clicks beyond login.**

---

## Single Highest-Impact Simplification

**Auto-login after password set (Proposal 4) + inline plan confirmation card on /wingpoint (Proposal 3).**

These two changes together collapse the current 5-page, 4-click flow into a 3-page, 2-click flow with minimal engineering effort. The backend already computes the recommended plan. The frontend already has the plan-confirmation card component (in PricingPage's `wingPointPlan` section). The only missing piece is returning a JWT from the reset-password endpoint and rendering the card inline instead of navigating to /pricing.

**Combined effort: LOW-MEDIUM (1-2 days). Combined impact: HIGH (eliminates 2 pages + 2 clicks + re-login friction).**