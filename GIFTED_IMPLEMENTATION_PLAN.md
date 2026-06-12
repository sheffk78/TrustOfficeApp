# Implementation Plan: Replace "Trial" with "Gifted" Concept

## Executive Summary

This plan replaces the "Trial" concept with "Gifted" across the entire TrustOfficeApp. Currently, the system has:
- **Trial (14 days)** — a time-limited free period with `plan_type: "trial"`, `status: "trialing"`
- **Monthly/Annual complimentary** — admin-granted paid access (the existing "gift" flow via `admin_api.py`)
- **Free Forever** — `plan_type: "forever_free"` for admin/internal accounts
- **Free** — `plan_type: "free"` for individual trustees (no trial, core features only)

The new "Gifted" concept unifies Trial (14 days), Monthly complimentary, and Annual complimentary under one umbrella. Users see "You've been gifted X days/months of TrustOffice Pro" instead of "You're on a trial."

---

## Part 1: Current State Analysis

### 1.1 Backend Models & Enums

| File | Current State |
|------|---------------|
| `backend/models.py:64-68` | `PlanType` enum: `trial`, `monthly`, `annual` |
| `backend/models.py:69-74` | `SubscriptionStatus` enum: `trialing`, `active`, `past_due`, `canceled`, `expired` |
| `backend/models.py:992-1004` | `SubscriptionResponse` model with `plan_type`, `status`, `trial_end_date`, `cancel_at_period_end` |

### 1.2 Backend Subscription Logic

| File | Current State |
|------|---------------|
| `backend/dependencies.py:21` | `TRIAL_DAYS = 14` constant (marked "Legacy") |
| `backend/dependencies.py:63-78` | `SubscriptionState` model: has `is_trial`, `trial_days_remaining`, `trial_start_date`, `trial_end_date` |
| `backend/dependencies.py:81-227` | `get_subscription_state()` — maps legacy `plan_type: "trial"` to `"forever_free"` or `"free"`, handles trialing status with date checking |
| `backend/dependencies.py:232-311` | `PLAN_FEATURES` dict: `"trial"` and `"free"` get core features only; `"forever_free"` same as `"free"` |
| `backend/dependencies.py:483-500` | `should_show_watermark()` — checks trialing status with `trial_end_date` |
| `backend/routers/subscriptions.py:39-60` | `get_or_create_subscription()` — creates new subs with `plan_type: "none"`, `status: "expired"` |
| `backend/routers/subscriptions.py:63-122` | `calculate_subscription_status()` — handles trialing with `trial_end_date` |
| `backend/routers/subscriptions.py:135-166` | `/subscription/state` endpoint — returns `is_trial`, `trial_days_remaining` |

### 1.3 Admin Account Creation (Critical — must force gifted tier)

| File | Current State |
|------|---------------|
| `backend/routers/admin.py:141-143` | `CreateUserRequest` — only `email` and `name` (NO plan type selection) |
| `backend/routers/admin.py:1449-1559` | `create_user()` — **hardcodes** `plan_type: "trial"`, `status: "trialing"`, `trial_end: now + TRIAL_DAYS` — no option to choose a gifted tier |
| `backend/routers/admin.py:124-126` | `GrantAccessRequest` — `plan_type: "trial"`, `days: Optional[int]` |
| `backend/routers/admin.py:445-512` | `grant_access()` — handles `trial`, `forever_free`, and paid complimentary access |

### 1.4 Admin Gift Functionality (Already Exists)

| File | Current State |
|------|---------------|
| `backend/routers/admin_api.py:113-119` | `ExtendTrialRequest(days=14)` — extends trial period |
| `backend/routers/admin_api.py:117-119` | `GiftSubscriptionRequest(plan_type, reason)` — gifts monthly/annual/forever_free |
| `backend/routers/admin_api.py:563-658` | `gift_subscription()` — sets `gifted: True`, `gift_reason`, `gifted_at` fields |

### 1.5 Admin Dashboard Stats

| File | Current State |
|------|---------------|
| `backend/routers/admin.py:146-164` | `SystemStats` model: `trial_users`, `expired_trials` |
| `backend/routers/admin.py:936-938` | `/admin/stats` counts `trial_users = count_documents({status: "trialing"})` |
| `frontend/src/pages/AdminPage.js:697-702` | Stats card showing "In Trial" with `stats.trial_users` |
| `frontend/src/pages/AdminPage.js:628` | `getStatusBadge()` — has `trialing` style |

### 1.6 Customer-Facing Frontend

| File | Current State |
|------|---------------|
| `frontend/src/components/TrialBanner.js` | Shows "Free Plan — Core Features Only" for free-tier users. **Not a horizontal sticky banner** — sits below header in page content |
| `frontend/src/components/SubscriptionGate.js` | Wraps pages; shows `TrialBanner` for active free-tier users, `ReadOnlyBanner` for expired |
| `frontend/src/components/ReadOnlyBanner.js` | Shows when expired: "Your free access has ended" — amber banner, **has `lg:ml-64` offset for sidebar** |
| `frontend/src/components/ImpersonationBanner.js` | **Horizontal sticky banner at top of screen** — this is the reference pattern for the new GiftedBanner |
| `frontend/src/App.js:385` | `ImpersonationBanner` rendered at app root level (above all content) |
| `frontend/src/pages/BillingPage.js:255-263` | Shows "Free Access" badge for trial/forever_free/free plans |
| `frontend/src/pages/PricingPage.js:239-242` | Trial note at bottom: "Subscribe to start..." |
| `frontend/src/pages/SignUpPage.js` | No trial messaging; Gift icon used only for referral banner |
| `frontend/src/context/AuthContext.js` | `loadSubscriptionState()` — returns `is_trial`, `plan_type`, `status` from `/subscription/state` |
| `frontend/src/utils/analytics.js` | `trackTrialStarted()`, `trackTrialConverted()`, `trackTrialBannerViewed()`, `trackTrialBannerClicked()` |

### 1.7 Email & External Services

| File | Current State |
|------|---------------|
| `backend/mailercloud_service.py:64-71` | `add_to_trial_list()` — adds to "14-Day Trial" Mailercloud list |
| `backend/routers/auth.py:19` | Imports `add_to_trial_list` (but currently not called — line 142 says "trial model removed") |
| `backend/routers/external.py:390-397` | WingPoint webhook creates sub with `plan_type: "free"`, `trial_start_date: None`, `trial_end_date: None` |

### 1.8 Database (MongoDB)

**Subscriptions collection** — key fields:
- `plan_type`: "trial" | "free" | "forever_free" | "monthly" | "annual" | "none"
- `status`: "trialing" | "active" | "expired" | "canceled" | "past_due"
- `trial_start_date`, `trial_end_date` — ISO timestamps
- `gifted`: Boolean (only set by `admin_api.py` gift flow)
- `gift_reason`, `gifted_at` — only set by `admin_api.py` gift flow

---

## Part 2: Implementation Plan

### Phase 1: Backend — Data Model & Subscription State Changes

#### 2.1 New Enum Values & Constants

**File: `backend/models.py`**
- Add `gifted_14day`, `gifted_monthly`, `gifted_annual` to `PlanType` enum
- Add `gifted` to `SubscriptionStatus` enum (or keep `trialing` as internal status but expose as "gifted" to frontend)
- Keep legacy `trial` and `trialing` for backward compatibility during migration

**File: `backend/dependencies.py`**
- Add `GIFTED_PLAN_TYPES = {"gifted_14day", "gifted_monthly", "gifted_annual"}` constant
- Add `GIFT_TYPE_LABELS` mapping:
  ```python
  GIFT_TYPE_LABELS = {
      "gifted_14day": "14 days of TrustOffice Pro",
      "gifted_monthly": "1 month of TrustOffice Pro",
      "gifted_annual": "1 year of TrustOffice Pro",
  }
  ```
- Add `gift_type` field to `SubscriptionState` model: `Optional[str]` — "14day" | "monthly" | "annual"
- Add `is_gifted` field to `SubscriptionState` model: `bool = False`
- Update `get_subscription_state()`:
  - When `plan_type in GIFTED_PLAN_TYPES`, set `is_gifted=True`, `is_trial=True` (for feature parity), compute `gift_days_remaining`
  - Map `plan_type: "trial"` (legacy) → treat as `gifted_14day` for display purposes
  - Keep `is_trial=True` for feature gating (same core features), but add `is_gifted=True` for UI differentiation
- Update `PLAN_FEATURES`:
  - `"gifted_14day"` → same as current `"trial"` (core features)
  - `"gifted_monthly"` → same as `"monthly"` (all premium features)
  - `"gifted_annual"` → same as `"annual"` (all premium features)

#### 2.2 Subscription Creation Changes

**File: `backend/routers/admin.py` — `CreateUserRequest` model**
```python
class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str
    gifted_tier: str = "gifted_14day"  # REQUIRED: "gifted_14day", "gifted_monthly", "gifted_annual", "forever_free"
```

**File: `backend/routers/admin.py` — `create_user()` endpoint**
- Replace hardcoded `plan_type: "trial"`, `status: "trialing"`, `trial_end: now + TRIAL_DAYS`
- Instead, use `request.gifted_tier` to determine subscription creation:
  - `"gifted_14day"` → `plan_type: "gifted_14day"`, `status: "gifted"`, `gift_start_date: now`, `gift_end_date: now + 14 days`, `gift_type: "14day"`, `gifted: True`, `gifted_at: now`
  - `"gifted_monthly"` → `plan_type: "gifted_monthly"`, `status: "active"`, `gift_start_date: now`, `gift_end_date: now + 30 days`, `gift_type: "monthly"`, `gifted: True`, `gifted_at: now`
  - `"gifted_annual"` → `plan_type: "gifted_annual"`, `status: "active"`, `gift_start_date: now`, `gift_end_date: now + 365 days`, `gift_type: "annual"`, `gifted: True`, `gifted_at: now`
  - `"forever_free"` → existing behavior

**File: `backend/routers/admin.py` — `GrantAccessRequest` model**
```python
class GrantAccessRequest(BaseModel):
    plan_type: str = "gifted_14day"  # "gifted_14day", "gifted_monthly", "gifted_annual", "forever_free"
    days: Optional[int] = None  # For custom gifted_14day extension
```

**File: `backend/routers/admin.py` — `grant_access()` endpoint**
- Replace `plan_type: "trial"` handling with `gifted_14day`
- Add `gifted: True`, `gifted_at`, `gift_type`, `gift_start_date`, `gift_end_date` fields

**File: `backend/routers/admin_api.py` — `ExtendTrialRequest`**
- Rename to `ExtendGiftRequest` (keep backward-compatible alias)
- Update response messages: "Gift extended" instead of "Trial extended"

**File: `backend/routers/admin_api.py` — `gift_subscription()`**
- Already sets `gifted: True`, `gift_reason`, `gifted_at` — good foundation
- Add `gift_type` field based on `plan_type`
- Add `gift_start_date`, `gift_end_date` fields
- Accept `"gifted_14day"` as a valid plan_type option

#### 2.3 Subscription State Endpoint

**File: `backend/routers/subscriptions.py`**
- `calculate_subscription_status()` — handle `plan_type: "gifted_14day"` like current trialing logic
- `/subscription/state` — return `is_gifted`, `gift_type`, `gift_days_remaining` in addition to existing fields
- `/subscription/features` — include `is_gifted` in response

#### 2.4 Admin Stats

**File: `backend/routers/admin.py` — `SystemStats` model**
```python
class SystemStats(BaseModel):
    # Replace trial_users with gifted_users
    gifted_users_14day: int      # Users currently on 14-day gift
    gifted_users_monthly: int    # Users on gifted monthly
    gifted_users_annual: int     # Users on gifted annual
    gifted_users_total: int      # Total gifted users
    expired_gifts: int           # Expired gifts (was expired_trials)
    # Keep for backward compat during migration:
    trial_users: int = 0         # Legacy — same as gifted_users_14day during migration
    expired_trials: int = 0      # Legacy — same as expired_gifts during migration
```

**File: `backend/routers/admin.py` — `get_system_stats()`**
```python
gifted_users_14day = await db.subscriptions.count_documents({"plan_type": "gifted_14day", "status": {"$in": ["gifted", "active"]}})
gifted_users_monthly = await db.subscriptions.count_documents({"plan_type": "gifted_monthly", "status": "active"})
gifted_users_annual = await db.subscriptions.count_documents({"plan_type": "gifted_annual", "status": "active"})
# Also count legacy trial users during migration
legacy_trial_users = await db.subscriptions.count_documents({"status": "trialing"})
gifted_users_total = gifted_users_14day + gifted_users_monthly + gifted_users_annual + legacy_trial_users
expired_gifts = await db.subscriptions.count_documents({"plan_type": {"$in": ["gifted_14day", "gifted_monthly", "gifted_annual"]}, "status": "expired"})
```

#### 2.5 Watermark Logic

**File: `backend/dependencies.py` — `should_show_watermark()`**
- Add handling for `plan_type: "gifted_14day"` — show watermark (same as trial)
- `gifted_monthly` / `gifted_annual` — no watermark (same as paid)

---

### Phase 2: Frontend — New GiftedBanner & UI Updates

#### 2.6 New GiftedBanner Component

**New file: `frontend/src/components/GiftedBanner.js`**

This replaces `TrialBanner.js` for gifted users. Design based on the existing `ImpersonationBanner.js` pattern (horizontal, sticky at top of screen).

```jsx
// Key features:
// - Sticky horizontal banner at TOP of viewport (position: fixed, top: 0, z-index: 50)
// - Shows for any user where subscription.is_gifted === true
// - Dynamic messaging based on gift_type:
//   - gifted_14day: "You've been gifted 14 days of TrustOffice Pro" + countdown
//   - gifted_monthly: "You've been gifted 1 month of TrustOffice Pro" + expiry date
//   - gifted_annual: "You've been gifted 1 year of TrustOffice Pro" + expiry date
// - CTA button: "Upgrade to Keep Access" → links to /settings/billing
// - Warm, appreciative tone: "We've gifted you..." not "You're on a trial..."
// - Gradient background: gold/navy themed (matches brand)
// - Dismissible on daily basis (localStorage dismiss date check)
```

The banner should account for the sidebar offset (same as `ReadOnlyBanner` uses `lg:ml-64`).

#### 2.7 Update App.js

**File: `frontend/src/App.js`**
- Import and render `GiftedBanner` at the root level (next to `ImpersonationBanner`):
```jsx
<GiftedBanner />
<ImpersonationBanner />
<AppRouter />
```

#### 2.8 Update SubscriptionGate

**File: `frontend/src/components/SubscriptionGate.js`**
- Replace `TrialBanner` import/usage with `GiftedBanner`
- The `GiftedBanner` is now at the app root, so remove the inline `<TrialBanner>` from `SubscriptionGate`
- Keep `ReadOnlyBanner` inline (it's conditional and page-level)

#### 2.9 Update AdminPage

**File: `frontend/src/pages/AdminPage.js`**
- Replace "In Trial" stat card (line 700) with "Gifted" breakdown:
  - Show 3 sub-cards: "14-Day Gifted" / "Monthly Gifted" / "Annual Gifted" OR
  - Single card: "Gifted" with `stats.gifted_users_total`, expandable to see breakdown
- Update `grantAccessForm` default from `plan_type: 'trial'` to `plan_type: 'gifted_14day'`
- Update grant access dialog dropdown options:
  - `gifted_14day` → "Gift 14 Days"
  - `gifted_monthly` → "Gift 1 Month"
  - `gifted_annual` → "Gift 1 Year"
  - `forever_free` → "Free Forever"
- Remove `trial` option from dropdown
- Update `getStatusBadge()` — change `trialing` badge to show "Gifted" with appropriate styling
- Update status filter options: replace "Trialing" with "Gifted"
- Update create-user dialog: add **required** `gifted_tier` selector

#### 2.10 Update BillingPage

**File: `frontend/src/pages/BillingPage.js`**
- Update `getStatusBadge()` for trialing → show "Gifted" status
- Update plan name display: `plan_type: "gifted_14day"` → "Gifted (14 Days)"
- Update free plan detection: include `gifted_14day` in `isFreePlan` check (or create separate `isGiftedPlan`)
- Show gift-specific messaging: "Your gifted access expires on [date]"

#### 2.11 Update PricingPage

**File: `frontend/src/pages/PricingPage.js`**
- Replace "Trial Note" (line 239-242) with: "Subscribe to start — or contact us about gifted access"

#### 2.12 Update Analytics

**File: `frontend/src/utils/analytics.js`**
- Rename `trackTrialStarted` → `trackGiftStarted` (keep alias for backward compat)
- Rename `trackTrialConverted` → `trackGiftConverted` (keep alias)
- Rename `trackTrialBannerViewed` → `trackGiftBannerViewed`
- Rename `trackTrialBannerClicked` → `trackGiftBannerClicked`
- Update event names: `subscription_trial_started` → `subscription_gift_started`

#### 2.13 Delete TrialBanner

**File: `frontend/src/components/TrialBanner.js`**
- Delete this file after `GiftedBanner` is live and `SubscriptionGate` no longer references it

---

### Phase 3: Database Migration

#### 2.14 MongoDB Migration Script

**New file: `backend/migrations/trial_to_gifted.py`**

```python
"""
Migration: Convert existing "trial" subscriptions to "gifted_14day"
"""
async def migrate_trial_to_gifted():
    # 1. Update all subscriptions with plan_type="trial" and status="trialing"
    #    → plan_type="gifted_14day", status="gifted"
    #    Add gift_type="14day", gifted=True, gifted_at=created_at
    
    # 2. Update all subscriptions with plan_type="trial" and status="expired"  
    #    → plan_type="gifted_14day", status="expired"
    #    Add gift_type="14day", gifted=True
    
    # 3. Update all subscriptions with gifted=True but no gift_type
    #    → Infer gift_type from plan_type: monthly→"monthly", annual→"annual"
    
    # 4. Add gift_start_date and gift_end_date where missing
    #    For gifted_14day: use trial_start_date/trial_end_date
    #    For gifted_monthly: use created_at and created_at+30days
    #    For gifted_annual: use created_at and created_at+365days
```

Run with: `python -m migrations.trial_to_gifted`

**Important**: Run migration BEFORE deploying the new code, or deploy with backward-compatible handling that accepts both old and new plan_type values.

---

### Phase 4: Cleanup & Renaming

#### 2.15 Backend Renaming

| File | Change |
|------|--------|
| `backend/dependencies.py:21` | Rename `TRIAL_DAYS` → `GIFTED_14DAY_DURATION` (keep alias) |
| `backend/dependencies.py:63-78` | Add `gift_type`, `is_gifted`, `gift_days_remaining` to `SubscriptionState` |
| `backend/routers/admin_api.py:113` | Rename `ExtendTrialRequest` → `ExtendGiftRequest` |
| `backend/mailercloud_service.py:64-71` | Rename `add_to_trial_list()` → `add_to_gifted_list()` |
| `backend/routers/auth.py:19` | Update import from `add_to_trial_list` to `add_to_gifted_list` |

#### 2.16 Frontend Renaming

| File | Change |
|------|--------|
| Delete `frontend/src/components/TrialBanner.js` | Replaced by `GiftedBanner.js` |
| `frontend/src/components/SubscriptionGate.js` | Remove TrialBanner import, GiftedBanner handled at app root |
| `frontend/src/context/AuthContext.js` | Add `isGifted` derived from subscription state |

#### 2.17 Test Updates

| File | Change |
|------|--------|
| `backend/tests/test_trial_expired_features.py` | Rename to `test_gifted_expired_features.py`, update plan_type references |
| `backend/tests/test_subscription_state.py` | Add test cases for `gifted_14day`, `gifted_monthly`, `gifted_annual` |
| `backend/tests/test_subscription_state_v2.py` | Same as above |
| `backend/tests/test_subscription_gating.py` | Add gift plan feature gating tests |
| `backend/tests/test_subscription_watermark.py` | Add watermark tests for gifted plans |
| `backend/tests/test_admin_endpoints.py` | Update create_user tests to use `gifted_tier` field |
| `backend/tests/test_demo_forever_free.py` | Verify forever_free still works correctly |

---

## Part 3: File Change Summary

### Backend Files to Modify

| # | File | Changes |
|---|------|---------|
| 1 | `backend/models.py` | Add `gifted_14day`, `gifted_monthly`, `gifted_annual` to `PlanType`; add `gifted` to `SubscriptionStatus` |
| 2 | `backend/dependencies.py` | Add `GIFTED_PLAN_TYPES`, `GIFT_TYPE_LABELS`; update `SubscriptionState` with `gift_type`, `is_gifted`, `gift_days_remaining`; update `get_subscription_state()`, `PLAN_FEATURES`, `should_show_watermark()` |
| 3 | `backend/routers/admin.py` | Update `CreateUserRequest` (add `gifted_tier`), `SystemStats` (add `gifted_users_*`), `GrantAccessRequest`, `create_user()`, `grant_access()`, `get_system_stats()`, `remove_admin()` |
| 4 | `backend/routers/admin_api.py` | Rename `ExtendTrialRequest` → `ExtendGiftRequest`, update `gift_subscription()`, update `ExtendTrialRequest` response messages |
| 5 | `backend/routers/subscriptions.py` | Update `calculate_subscription_status()`, `/subscription/state`, `/subscription/features` to handle gifted plans |
| 6 | `backend/mailercloud_service.py` | Rename `add_to_trial_list` → `add_to_gifted_list` |
| 7 | `backend/routers/auth.py` | Update import of renamed mailercloud function |
| 8 | `backend/routers/external.py` | Update WingPoint webhook sub creation (add `gifted: False`) |
| 9 | `backend/routers/demo.py` | Update any trial references if present |

### Backend Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `backend/migrations/trial_to_gifted.py` | MongoDB migration script |

### Frontend Files to Create

| # | File | Purpose |
|---|------|---------|
| 1 | `frontend/src/components/GiftedBanner.js` | Sticky horizontal gifted status banner (replaces TrialBanner) |

### Frontend Files to Modify

| # | File | Changes |
|---|------|---------|
| 1 | `frontend/src/App.js` | Add `GiftedBanner` at root level |
| 2 | `frontend/src/components/SubscriptionGate.js` | Remove TrialBanner import/usage |
| 3 | `frontend/src/pages/AdminPage.js` | Update stats (In Trial → Gifted), grant access form, create user form, status badges, filters |
| 4 | `frontend/src/pages/BillingPage.js` | Update status badges, plan names, free plan detection for gifted |
| 5 | `frontend/src/pages/PricingPage.js` | Replace trial note |
| 6 | `frontend/src/context/AuthContext.js` | Add `isGifted` derived state |
| 7 | `frontend/src/utils/analytics.js` | Rename trial tracking functions to gift |

### Frontend Files to Delete

| # | File | Reason |
|---|------|--------|
| 1 | `frontend/src/components/TrialBanner.js` | Replaced by GiftedBanner |

### Test Files to Update

| # | File |
|---|------|
| 1 | `backend/tests/test_trial_expired_features.py` |
| 2 | `backend/tests/test_subscription_state.py` |
| 3 | `backend/tests/test_subscription_state_v2.py` |
| 4 | `backend/tests/test_subscription_gating.py` |
| 5 | `backend/tests/test_subscription_watermark.py` |
| 6 | `backend/tests/test_admin_endpoints.py` |
| 7 | `backend/tests/test_demo_forever_free.py` |
| 8 | `backend/tests/test_auth_router.py` |
| 9 | `backend/tests/test_premium_feature_gating.py` |
| 10 | `backend/tests/test_export_subscription.py` |

---

## Part 4: Migration Considerations

### 4.1 Existing Users on Trial

- Users currently with `plan_type: "trial"`, `status: "trialing"` need migration to `plan_type: "gifted_14day"`, `status: "gifted"`
- The migration script should be idempotent and safe to run multiple times
- During the transition period, `get_subscription_state()` should handle both old and new plan_type values

### 4.2 Backward Compatibility Strategy

Deploy in this order:
1. **Backend first** — Add new `gifted_*` plan types to enums while keeping `trial` and `trialing` as valid values. `get_subscription_state()` handles both.
2. **Run migration** — Convert existing DB records from `trial` → `gifted_14day`
3. **Frontend** — Deploy new `GiftedBanner`, updated AdminPage, BillingPage
4. **Cleanup** — Remove `trial` and `trialing` from enums (after confirming zero DB records use them)

### 4.3 Stripe Integration

- No changes needed to Stripe webhooks — they operate on `status: "active"` for paid subscriptions
- The `gifted_*` plans are NOT Stripe-managed; they're internal-only
- When a gifted user purchases, the webhook sets `plan_type: "monthly"/"annual"`, `status: "active"` — this overwrites the gifted status correctly

### 4.4 Key Risk: Admin Create User Flow

Currently `create_user()` hardcodes a 14-day trial. The new flow MUST force admin to select a gifted tier. This is the highest-priority change since it's the only entry point for new accounts via admin.

---

## Part 5: GiftedBanner Component Specification

### Design Requirements

1. **Position**: Fixed at top of viewport, `z-index: 40` (below ImpersonationBanner at z-50)
2. **Layout**: Full-width horizontal bar, `lg:ml-64` to account for sidebar
3. **Content**:
   - Left: Gift icon + status text ("You've been gifted 14 days of TrustOffice Pro — 8 days remaining")
   - Right: CTA button ("Upgrade to Keep Access →")
4. **Color**: Warm gradient (gold-to-navy subtle), NOT amber/warning (that's the read-only/expired feel)
5. **Behavior**:
   - Shows when `subscription.is_gifted === true` AND `subscription.is_active === true`
   - Auto-hides when gifted period expires (user sees ReadOnlyBanner instead)
   - Dismissable per-session (optional: dismiss button with "Remind me later")
   - Admin users never see it
6. **Responsive**: Collapses to 2-line layout on mobile

### Gift Type Specific Messaging

| Gift Type | Banner Text | CTA |
|-----------|-------------|-----|
| `gifted_14day` | "You've been gifted 14 days of TrustOffice Pro — {N} days remaining" | "Upgrade Now" |
| `gifted_monthly` | "You've been gifted 1 month of TrustOffice Pro — expires {date}" | "Continue with Paid Plan" |
| `gifted_annual` | "You've been gifted 1 year of TrustOffice Pro — expires {date}" | "Continue with Paid Plan" |

When days_remaining ≤ 3 for `gifted_14day`, add urgency: "Your gifted access ends soon — upgrade to keep your workspace"

---

## Part 6: Implementation Priority

| Priority | Task | Effort |
|----------|------|--------|
| P0 | Backend: Add new PlanType/SubscriptionStatus values + backward compat | Small |
| P0 | Backend: Update SubscriptionState model + get_subscription_state() | Medium |
| P0 | Backend: Update admin create_user() to force gifted_tier selection | Small |
| P0 | Backend: MongoDB migration script | Medium |
| P1 | Frontend: Create GiftedBanner component | Medium |
| P1 | Frontend: Update App.js to render GiftedBanner at root | Small |
| P1 | Frontend: Update AdminPage (stats, grant access, create user) | Medium |
| P1 | Backend: Update admin stats endpoint | Small |
| P2 | Frontend: Update BillingPage | Small |
| P2 | Frontend: Update SubscriptionGate (remove TrialBanner) | Small |
| P2 | Frontend: Update PricingPage | Tiny |
| P2 | Frontend: Update analytics.js | Small |
| P2 | Backend: Rename mailercloud function | Tiny |
| P3 | Frontend: Delete TrialBanner.js | Tiny |
| P3 | Backend: Remove legacy trial/trialing enum values (after migration) | Small |
| P3 | Update all test files | Medium |