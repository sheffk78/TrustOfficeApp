# WingPoint → TrustOffice Subscription Upgrade Flow

## Implementation Proposal

**Date:** July 2026
**Status:** Proposed — awaiting approval before implementation

---

## Problem Summary

When WingPoint provisions trusts via the external API, it inserts directly into MongoDB (bypassing the trust limit check in `trusts.py`). This is intentional — the user paid WingPoint for the trust. But it creates a broken state:

- User on **Trustee** (1 trust limit) buys a 2nd trust from WingPoint → trust is created, but the user's plan can't support it
- User on **Free** (1 trust limit) buys an Estate Bundle (2 trusts) → both trusts are created, but the plan only allows 1
- No recommendation system tells the user which TrustOffice plan they need
- The `source_package` field is stored but never used for plan recommendations
- No frontend banner warns users who have more trusts than their plan supports

---

## Current Architecture (As-Built)

### Backend

| File | Key Components |
|------|---------------|
| `backend/routers/external.py` | `provision_trustoffice()` — creates user + trust directly in MongoDB, creates free subscription for new users, stores `source_package` on trust doc and provision record |
| `backend/routers/trusts.py` | `create_trust()` — checks `get_trust_limit(plan_type)` and blocks creation with HTTP 402 if exceeded |
| `backend/routers/subscriptions.py` | `change_plan()` at `/subscription/change-plan` — uses Stripe proration, swaps price ID on existing subscription |
| `backend/dependencies.py` | `PLAN_TRUST_LIMITS` dict, `get_trust_limit()`, `get_subscription_state()`, `SubscriptionState` model |

### Trust Limits (from `dependencies.py`)

```python
PLAN_TRUST_LIMITS = {
    "none": 0,
    "free": 1,
    "forever_free": 1,
    "trustee": 1,
    "estate": 5,
    "advisor": float('inf'),  # unlimited
    "monthly": 10,   # legacy
    "annual": 10,    # legacy
    "trial": 1,
}
```

### WingPoint Package → Trust Count Mapping

| Package | `source_package` value | Trusts Created |
|---------|----------------------|----------------|
| Single Trust | `single_trust` | 1 |
| Estate Bundle | `estate_bundle` | 2 |
| Builder Bundle | `builder_bundle` | 4 |

### Frontend

| File | Role |
|------|------|
| `frontend/src/context/AuthContext.js` | Loads `subscription` state from `/subscription/state` and `trusts` from `/trusts` — both available to all pages via `useAuth()` |
| `frontend/src/pages/BillingPage.js` | Full billing UI — has "Change Plan" section with tier cards, calls `/subscription/change-plan` with proration |
| `frontend/src/pages/PricingPage.js` | Public pricing page — **guards against re-checkout** if `user.subscription.is_active` |
| `frontend/src/pages/DashboardPage.js` | Main dashboard — has access to `trusts` array and `subscription` via `useAuth()`, shows `TrustManager` when `trusts.length >= 2` |

### Existing Upgrade Path (What Works)

The `/subscription/change-plan` endpoint already supports seamless tier changes with Stripe proration. The BillingPage already has a "Change Plan" UI with tier cards. The problem is **discovery** — users don't know they need to upgrade or where to go.

---

## Proposed Changes

### 1. Backend: Add `/subscription/upgrade-recommendation` Endpoint

**File:** `backend/routers/subscriptions.py`

New endpoint that checks the user's current trust count against their plan limit and returns a recommendation.

```python
@router.get("/subscription/upgrade-recommendation")
async def get_upgrade_recommendation(user: dict = Depends(get_current_user)):
    """
    Check if user has more trusts than their plan supports.
    Returns recommended plan and upgrade URL if needed.
    
    Used by:
    - Frontend dashboard banner
    - WingPoint provision API response enrichment
    """
    from dependencies import get_subscription_state, get_trust_limit, PLAN_TRUST_LIMITS
    
    sub_state = await get_subscription_state(user["user_id"])
    trust_count = await db.trusts.count_documents({"user_id": user["user_id"]})
    current_limit = get_trust_limit(sub_state.plan_type, sub_state.legacy_trust_limit)
    
    needs_upgrade = False
    recommended_plan = None
    recommended_plan_name = None
    upgrade_url = None
    
    if current_limit != float('inf') and trust_count > current_limit:
        needs_upgrade = True
        
        # Find the cheapest plan that covers the trust count
        if trust_count <= 1:
            recommended_plan = "trustee"
            recommended_plan_name = "Trustee Plan"
        elif trust_count <= 5:
            recommended_plan = "estate"
            recommended_plan_name = "Estate Plan"
        else:
            recommended_plan = "advisor"
            recommended_plan_name = "Advisor Plan"
        
        upgrade_url = f"/settings/billing?action=upgrade&plan={recommended_plan}"
    
    return {
        "needs_upgrade": needs_upgrade,
        "current_plan": sub_state.plan_type,
        "current_trust_limit": int(current_limit) if current_limit != float('inf') else "unlimited",
        "trust_count": trust_count,
        "recommended_plan": recommended_plan,
        "recommended_plan_name": recommended_plan_name,
        "upgrade_url": upgrade_url,
    }
```

### 2. Backend: Enrich Provision API Response

**File:** `backend/routers/external.py`

After trust creation, check the user's subscription state and add upgrade recommendation fields to the response. The trust is **always created** (user paid WingPoint), but the response flags the upgrade need.

**Add a helper function** near the top of `external.py`:

```python
# WingPoint package → recommended TrustOffice tier
PACKAGE_TO_TIER = {
    "single_trust": "trustee",      # 1 trust → Trustee (1 trust limit)
    "estate_bundle": "estate",      # 2 trusts → Estate (5 trust limit)
    "builder_bundle": "estate",     # 4 trusts → Estate (5 trust limit)
}

# Package → cumulative trust count (if all provisions for this package succeed)
PACKAGE_TRUST_COUNT = {
    "single_trust": 1,
    "estate_bundle": 2,
    "builder_bundle": 4,
}


async def _check_upgrade_need(user_id: str, source_package: Optional[str] = None) -> dict:
    """
    Check if user's current subscription can handle their trust count.
    Returns recommendation info for the provision response.
    Does NOT block trust creation — just flags the need.
    """
    from dependencies import get_subscription_state, get_trust_limit
    
    sub_state = await get_subscription_state(user_id)
    trust_count = await db.trusts.count_documents({"user_id": user_id})
    current_limit = get_trust_limit(sub_state.plan_type, sub_state.legacy_trust_limit)
    
    result = {
        "current_plan": sub_state.plan_type,
        "current_trust_limit": int(current_limit) if current_limit != float('inf') else "unlimited",
        "trust_count": trust_count,
        "needs_upgrade": False,
        "recommended_plan": None,
        "recommended_plan_name": None,
        "upgrade_url": None,
    }
    
    if current_limit != float('inf') and trust_count > current_limit:
        result["needs_upgrade"] = True
        
        # Use package-based recommendation if available, otherwise use trust count
        if source_package and source_package in PACKAGE_TO_TIER:
            recommended = PACKAGE_TO_TIER[source_package]
        elif trust_count <= 1:
            recommended = "trustee"
        elif trust_count <= 5:
            recommended = "estate"
        else:
            recommended = "advisor"
        
        result["recommended_plan"] = recommended
        result["recommended_plan_name"] = {
            "trustee": "Trustee Plan",
            "estate": "Estate Plan",
            "advisor": "Advisor Plan",
        }.get(recommended, "Estate Plan")
        
        frontend_url = os.environ.get('FRONTEND_URL', 'https://app.trustoffice.app')
        result["upgrade_url"] = f"{frontend_url}/settings/billing?action=upgrade&plan={recommended}"
    
    return result
```

**Modify the response building section** (around line 587-607 in `external.py`):

```python
    # ---- BUILD RESPONSE ----
    # Check if user needs to upgrade their TrustOffice plan
    upgrade_info = await _check_upgrade_need(user_id, request.source_package)
    
    response = {
        "status": "created" if is_new_user else "trust_added",
        "user_id": user_id,
        "trust_id": trust_id,
        "set_password_url": set_password_url,
        "set_password_expires": expires_at.isoformat(),
        "is_new_user": is_new_user,
        "email": email,
        "trust_name": request.trust_name,
        "email_status": email_status,
        # Upgrade recommendation fields
        "needs_upgrade": upgrade_info["needs_upgrade"],
        "current_plan": upgrade_info["current_plan"],
        "current_trust_limit": upgrade_info["current_trust_limit"],
        "trust_count": upgrade_info["trust_count"],
        "recommended_plan": upgrade_info["recommended_plan"],
        "recommended_plan_name": upgrade_info["recommended_plan_name"],
        "upgrade_url": upgrade_info["upgrade_url"],
    }

    if upgrade_info["needs_upgrade"]:
        response["message"] = (
            f"Trust created. However, the user's current plan ({upgrade_info['current_plan']}) "
            f"supports {upgrade_info['current_trust_limit']} trusts but they now have "
            f"{upgrade_info['trust_count']}. Recommend upgrading to the "
            f"{upgrade_info['recommended_plan_name']}."
        )
    elif email_status == "failed":
        response["message"] = f"Account created, but welcome email failed: {email_result.get('error', 'unknown error')}"
    elif email_status == "skipped":
        response["message"] = "Account created, but email service is not configured. Set-password link generated but not emailed."
    else:
        response["message"] = f"Account {'created' if is_new_user else 'updated'}. Welcome email sent to {email}."

    return response
```

**Also enrich the dry-run response** (around line 291-324) to include upgrade preview:

```python
    # ---- DRY RUN ----
    if request.dry_run:
        # ... existing dry_run_response building ...
        
        # Preview upgrade need if user exists
        if existing_user:
            upgrade_preview = await _check_upgrade_need(existing_user["user_id"], request.source_package)
            dry_run_response["would_need_upgrade"] = upgrade_preview["needs_upgrade"]
            dry_run_response["would_recommend_plan"] = upgrade_preview["recommended_plan"]
        
        return dry_run_response
```

### 3. Backend: Add `needs_upgrade` to `/subscription/state` Response

**File:** `backend/routers/subscriptions.py`

Enrich the existing `/subscription/state` endpoint (line 194) to include upgrade recommendation info, so the frontend AuthContext can use it without an extra API call.

```python
@router.get("/subscription/state")
async def get_subscription_state_endpoint(user: dict = Depends(get_current_user)):
    # ... existing admin check and state retrieval ...
    
    state = await get_subscription_state(user["user_id"])
    state_dict = state.model_dump()
    
    # Add upgrade recommendation
    from dependencies import get_trust_limit
    trust_count = await db.trusts.count_documents({"user_id": user["user_id"]})
    current_limit = get_trust_limit(state.plan_type, state.legacy_trust_limit)
    
    state_dict["trust_count"] = trust_count
    state_dict["trust_limit"] = int(current_limit) if current_limit != float('inf') else "unlimited"
    state_dict["needs_upgrade"] = (
        current_limit != float('inf') and trust_count > current_limit
    )
    
    if state_dict["needs_upgrade"]:
        if trust_count <= 1:
            state_dict["recommended_plan"] = "trustee"
        elif trust_count <= 5:
            state_dict["recommended_plan"] = "estate"
        else:
            state_dict["recommended_plan"] = "advisor"
    
    return state_dict
```

### 4. Frontend: Add Upgrade Banner to DashboardPage

**File:** `frontend/src/pages/DashboardPage.js`

Add a conditional banner at the top of the dashboard when `subscription.needs_upgrade` is true. The banner includes a one-click "Upgrade Now" button that navigates to BillingPage with a pre-selected plan.

```jsx
// Add to imports
import { AlertCircle, ArrowUpCircle } from 'lucide-react';

// Inside DashboardPage component, after the existing useAuth() destructure:
const { user, selectedTrust, trusts, trustsLoading, loadTrusts, seedDemoData, subscription } = useAuth();

// Add upgrade banner before the main dashboard content, after the page header:
{subscription?.needs_upgrade && (
  <div className="mb-6 p-4 bg-gold/10 border border-gold/30 rounded-lg flex items-center justify-between" data-testid="upgrade-banner">
    <div className="flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-gold flex-shrink-0 mt-0.5" />
      <div>
        <p className="font-medium text-navy">
          Your plan supports {subscription.trust_limit} {subscription.trust_limit === 1 ? 'trust' : 'trusts'}, but you have {trusts.length}.
        </p>
        <p className="text-sm text-muted-foreground mt-0.5">
          Upgrade to the {subscription.recommended_plan === 'estate' ? 'Estate Plan' : subscription.recommended_plan === 'advisor' ? 'Advisor Plan' : 'Trustee Plan'} to manage all your trusts.
        </p>
      </div>
    </div>
    <Button
      onClick={() => navigate(`/settings/billing?action=upgrade&plan=${subscription.recommended_plan}`)}
      className="btn-primary"
      data-testid="upgrade-now-btn"
    >
      <ArrowUpCircle className="w-4 h-4 mr-2" />
      Upgrade Now
    </Button>
  </div>
)}
```

### 5. Frontend: Auto-Scroll to Recommended Plan on BillingPage

**File:** `frontend/src/pages/BillingPage.js`

When the BillingPage loads with `?action=upgrade&plan=estate` query params, auto-scroll to the "Change Your Plan" section and highlight the recommended tier card.

```jsx
// Add to existing useEffect (around line 117):
useEffect(() => {
  loadSubscription();
  
  // Handle upgrade redirect: scroll to plan section
  const action = searchParams.get('action');
  const plan = searchParams.get('plan');
  if (action === 'upgrade' && plan) {
    // Slight delay to ensure DOM is rendered
    setTimeout(() => {
      const tierSection = document.querySelector('[data-testid="tier-change-section"]');
      if (tierSection) {
        tierSection.scrollIntoView({ behavior: 'smooth' });
      }
      // Highlight the recommended card
      const targetCard = document.querySelector(`[data-testid="tier-change-card-${plan}"]`);
      if (targetCard) {
        targetCard.classList.add('ring-2', 'ring-gold');
        setTimeout(() => {
          targetCard.classList.remove('ring-2', 'ring-gold');
        }, 3000);
      }
    }, 500);
  }
  
  // Check for payment verification
  const sessionId = searchParams.get('session_id');
  if (sessionId) {
    verifyPayment(sessionId);
  }
}, [searchParams]);
```

### 6. Frontend: Add Upgrade Banner to BillingPage (for free-plan users with multiple trusts)

**File:** `frontend/src/pages/BillingPage.js`

For users on the free plan who have multiple trusts (from WingPoint), show a specific banner above the pricing cards.

```jsx
// Add inside the BillingPage component, before the pricing tiers grid:
// This applies to free-plan users who have trusts from WingPoint
{isFreePlan && subscription?.trust_count > 1 && (
  <div className="mb-6 p-4 bg-gold/10 border border-gold/30 rounded-lg" data-testid="free-plan-upgrade-banner">
    <div className="flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-gold flex-shrink-0 mt-0.5" />
      <div>
        <p className="font-medium text-navy">
          You have {subscription.trust_count} trusts but are on the Free plan (1 trust limit).
        </p>
        <p className="text-sm text-muted-foreground mt-1">
          Subscribe to the {subscription.trust_count <= 5 ? 'Estate Plan ($149/mo)' : 'Advisor Plan ($399/mo)'} 
          {' '}to manage all your trusts. Your trusts are safe — upgrade to unlock full management features.
        </p>
      </div>
    </div>
  </div>
)}
```

### 7. WingPoint Integration: Pass `source_package` on All Provisions

Ensure WingPoint always sends the `source_package` field. This is already supported in the API model (`WingPointProvisionRequest.source_package`) but WingPoint may not always send it. The `_check_upgrade_need` helper falls back to trust-count-based recommendation when `source_package` is absent, so this is a nice-to-have, not a blocker.

---

## Complete User Flow (After Implementation)

### Flow 1: New WingPoint Customer — Estate Bundle (2 trusts)

1. **WingPoint** provisions 2 trusts via `/external/provision-trustoffice` (two API calls, each with `source_package="estate_bundle"`)
2. **TrustOffice** creates user, creates free subscription, creates both trusts in MongoDB
3. **Provision API response** includes:
   ```json
   {
     "status": "created",
     "needs_upgrade": true,
     "current_plan": "free",
     "current_trust_limit": 1,
     "trust_count": 2,
     "recommended_plan": "estate",
     "recommended_plan_name": "Estate Plan",
     "upgrade_url": "https://app.trustoffice.app/settings/billing?action=upgrade&plan=estate"
   }
   ```
4. **WingPoint** can display this info to the customer or include it in the welcome email
5. **User logs in** → AuthContext loads `/subscription/state` which now includes `needs_upgrade: true, recommended_plan: "estate", trust_count: 2, trust_limit: 1`
6. **Dashboard** shows upgrade banner: "Your plan supports 1 trust, but you have 2. Upgrade to the Estate Plan."
7. **User clicks "Upgrade Now"** → navigates to `/settings/billing?action=upgrade&plan=estate`
8. **BillingPage** auto-scrolls to the "Change Your Plan" section, highlights the Estate Plan card
9. **User clicks "Subscribe to Estate Plan"** → Stripe checkout → prorated billing → subscription active
10. **User can now manage all 2 trusts**

### Flow 2: Existing Trustee Customer — Buys 2nd Trust from WingPoint

1. User is on **Trustee plan** ($79/mo, 1 trust), already has 1 trust
2. **WingPoint** provisions a 2nd trust via `/external/provision-trustoffice`
3. **TrustOffice** creates the 2nd trust in MongoDB (bypassing limit check — intentional)
4. **Provision API response** includes `needs_upgrade: true, current_plan: "trustee", recommended_plan: "estate"`
5. **User's next dashboard load** shows upgrade banner
6. **User clicks "Upgrade Now"** → BillingPage → "Change Plan" section → Estate Plan card highlighted
7. **User clicks "Upgrade"** → calls `/subscription/change-plan` with `{plan_type: "estate", billing_period: "monthly"}` → Stripe proration → plan changed
8. **User can now manage all 2 trusts**

### Flow 3: Existing Estate Customer — Buys 6th Trust (edge case)

1. User is on **Estate plan** ($149/mo, 5 trusts), has 5 trusts
2. **WingPoint** provisions a 6th trust
3. Trust created, `needs_upgrade: true, recommended_plan: "advisor"`
4. Dashboard banner → "Upgrade to Advisor Plan" → change-plan → prorated → done

---

## Design Decisions

### Trust creation is NEVER blocked by the provision API

**Rationale:** The user paid WingPoint for the trust. Blocking creation would create a worse experience — the user would have paid but have no trust. Instead, the trust is created and the upgrade path is made obvious.

### Upgrade recommendation uses trust count, not just `source_package`

**Rationale:** `source_package` tells us what WingPoint package was purchased, but the user might have pre-existing trusts from earlier purchases. The actual trust count in MongoDB is the source of truth. `source_package` is used as a tiebreaker/hint when available.

### The `/subscription/state` endpoint is enriched (not a new endpoint)

**Rationale:** AuthContext already calls `/subscription/state` on every page load. Adding `needs_upgrade`, `trust_count`, `trust_limit`, and `recommended_plan` to this existing response avoids an extra API call. The dedicated `/subscription/upgrade-recommendation` endpoint is also added for cases where only the recommendation is needed (e.g., WingPoint calling it directly).

### The banner appears on the Dashboard, not as a modal

**Rationale:** A modal can be dismissed and forgotten. A persistent banner on the main dashboard is visible every time the user logs in, creating consistent pressure to upgrade without being intrusive. The banner uses the existing `gold` color token (warning/attention) rather than `error` (red) — this is an opportunity, not an error.

### BillingPage auto-scrolls and highlights the recommended plan

**Rationale:** Reducing friction in the upgrade path. The user should not have to figure out which plan they need — we already know, and we show them.

---

## Files to Modify

| File | Change | Complexity |
|------|--------|------------|
| `backend/routers/external.py` | Add `_check_upgrade_need()` helper, enrich provision response, enrich dry-run response | Medium |
| `backend/routers/subscriptions.py` | Enrich `/subscription/state` with trust count + upgrade info, add `/subscription/upgrade-recommendation` endpoint | Medium |
| `frontend/src/pages/DashboardPage.js` | Add upgrade banner component | Low |
| `frontend/src/pages/BillingPage.js` | Add auto-scroll/highlight on `?action=upgrade&plan=X`, add free-plan upgrade banner | Low-Medium |
| `frontend/src/context/AuthContext.js` | No changes needed — `subscription` state already flows through | None |

## Files NOT Modified

| File | Reason |
|------|--------|
| `backend/routers/trusts.py` | The trust limit check here is for user-initiated trust creation. WingPoint provisions bypass it intentionally. No change needed. |
| `backend/dependencies.py` | `PLAN_TRUST_LIMITS` and `get_trust_limit()` are correct as-is. No change needed. |
| `frontend/src/pages/PricingPage.js` | The guard against re-checkout is correct. Upgrades go through BillingPage, not PricingPage. No change needed. |

---

## Testing Checklist

- [ ] Provision new user with `source_package="single_trust"` → response has `needs_upgrade: false` (1 trust, free plan allows 1)
- [ ] Provision new user with `source_package="estate_bundle"` (2 trusts) → after 2nd provision, response has `needs_upgrade: true, recommended_plan: "estate"`
- [ ] Provision new user with `source_package="builder_bundle"` (4 trusts) → after 4th provision, response has `needs_upgrade: true, recommended_plan: "estate"` (4 ≤ 5)
- [ ] Provision 6th trust for existing Estate user → `recommended_plan: "advisor"`
- [ ] `/subscription/state` returns `needs_upgrade: true` when trust_count > trust_limit
- [ ] `/subscription/state` returns `needs_upgrade: false` when trust_count <= trust_limit
- [ ] Dashboard shows upgrade banner when `subscription.needs_upgrade` is true
- [ ] Dashboard does NOT show banner when `needs_upgrade` is false
- [ ] "Upgrade Now" button navigates to `/settings/billing?action=upgrade&plan=estate`
- [ ] BillingPage auto-scrolls to "Change Your Plan" section when `?action=upgrade` present
- [ ] BillingPage highlights recommended tier card when `?plan=estate` present
- [ ] Free-plan user with 2 trusts sees upgrade banner on both Dashboard and BillingPage
- [ ] Change-plan via BillingPage successfully upgrades with Stripe proration (existing flow, should still work)
- [ ] Dry-run provision includes `would_need_upgrade` field for existing users