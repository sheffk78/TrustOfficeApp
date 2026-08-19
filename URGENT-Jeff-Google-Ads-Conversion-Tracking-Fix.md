# 🔴 URGENT — Jeff Action Required: Google Ads Conversion Tracking Fix

**Status:** Open 12+ weeks · **Priority:** P0 (blocks ALL ROAS measurement) · **Date surfaced:** 2026-08-14

---

## The Problem

Google Ads conversion tracking is **broken** — every paid signup and purchase fires
with a **placeholder conversion label** (`'purchase'`) instead of the real Google Ads
conversion label. This means:

- **Zero ROAS attribution** for TrustOffice Google Ads campaigns
- ~**$1K/week** in ad spend with no conversion data
- Meta lead costs trending up (**$7.48 → $11.90/lead**) with no way to optimize
- Smart bidding strategies cannot work (no conversion signal)

---

## Root Cause (verified in code)

The codebase is a **React SPA**, not Astro — the `thank-you.astro` path referenced in
prior briefs does not exist. The actual tracking code lives in:

### `frontend/src/utils/analytics.js`

**Issue 1 — Placeholder label (line 473):**
```js
// line 469-478 — trackPurchaseConversion()
export const trackPurchaseConversion = (params = {}) => {
  const value = getTierPrice(params.plan_type, params.billing_period);
  trackGoogleAdsConversion({
    conversion_id: 'AW-955235972',
    conversion_label: params.conversion_label || 'purchase',  // ← PLACEHOLDER
    ...
  });
};
```
The caller (`useDashboardData.js:45`) never passes `conversion_label`, so it always
defaults to `'purchase'` — a string that matches **no** real Google Ads conversion action.

**Issue 2 — Signup conversion sends NOTHING to Google Ads (line 445-458):**
```js
export const trackSignupConversion = () => {
  // Only fires GA4 sign_up + Meta CompleteRegistration
  // NO Google Ads conversion event at all
};
```
`trackSignupConversion` is called from `SignUpPage.js:252` and `AuthCallback.js:79`
but never sends a `gtag('event', 'conversion', ...)` call.

**Issue 3 — Enhanced Conversions only enabled for one of two accounts (index.html:69-70):**
```js
gtag('config', 'AW-955235972', { allow_enhanced_conversions: true });   // ✅ on
gtag('config', 'AW-18025732865');                                       // ❌ off
```

---

## Jeff's 3 Steps to Fix

### Step 1 — Get the real conversion label from Google Ads UI
1. Log into Google Ads → **Tools & Settings → Conversions → Summary**
2. Find conversion action **ID 7606346761** (should appear as "TrustOffice_Signup_Complete" or similar)
3. Click it → expand **Tag setup** → copy the **conversion label** (format: alphanumeric string like `abc123XY`)
4. Note which conversion ID it belongs to: `AW-955235972` or `AW-18025732865`

### Step 2 — Replace the placeholder in code
File: `frontend/src/utils/analytics.js`

**(a) Line 473** — replace the `'purchase'` fallback with the real label:
```js
// BEFORE
conversion_label: params.conversion_label || 'purchase',
// AFTER
conversion_label: params.conversion_label || 'REAL_LABEL_HERE',
```

**(b) Lines 445-458** — add a Google Ads conversion call to `trackSignupConversion`:
```js
export const trackSignupConversion = () => {
  if (isGtagAvailable()) {
    window.gtag('event', 'sign_up', { method: 'email' });
    // ADD: Google Ads signup conversion
    window.gtag('event', 'conversion', {
      send_to: 'AW-955235972/REAL_LABEL_HERE',  // use the real label from Step 1
    });
  }
  if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
    window.fbq('track', 'CompleteRegistration', { content_name: 'trustoffice_signup' });
  }
};
```
*(If the conversion action belongs to `AW-18025732865`, use that ID instead.)*

### Step 3 — Toggle Enhanced Conversions ON in Google Ads
1. Google Ads → **Tools & Settings → Conversions → Summary**
2. Click the conversion action (7606346761) → **Edit settings**
3. Toggle **Enhanced Conversions** → ON
4. Save
5. Also update `index.html` line 70 to enable it for the second account if needed:
```js
gtag('config', 'AW-18025732865', { allow_enhanced_conversions: true });
```

---

## Business Impact

| Metric | Current | After Fix |
|--------|---------|-----------|
| ROAS measurement | ❌ Impossible | ✅ Full attribution |
| Google Ads smart bidding | ❌ No signal | ✅ Optimizable |
| Weekly ad spend w/ attribution | $0 tracked | ~$1K/week tracked |
| Meta cost/lead trend | $7.48 → $11.90 ↗ | Stabilize w/ data |
| Time open | 12+ weeks | — |

**This is the single highest-ROI fix in the portfolio** — a 5-minute code change
+ a Google Ads UI toggle unblocks all paid acquisition optimization.

---

## Files Referenced
- `frontend/src/utils/analytics.js` (lines 445-458, 469-478) — **primary fix target**
- `frontend/public/index.html` (lines 69-70) — enhanced conversions config
- `frontend/src/pages/dashboard/useDashboardData.js` (line 45) — purchase conversion caller
- `frontend/src/pages/SignUpPage.js` (line 252) — signup conversion caller
- `frontend/src/pages/AuthCallback.js` (line 79) — OAuth signup conversion caller