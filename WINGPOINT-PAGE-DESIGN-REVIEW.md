# WingPoint Welcome Page — Design System Review

**File reviewed:** `frontend/src/pages/WingPointWelcomePage.js` (656 lines)
**Comparisons:** PricingPage.js, DashboardPage.js, LoginPage.js, tailwind.config.js
**Date:** July 2026

---

## Executive Summary

The WingPointWelcomePage is a **solid page** that gets most things right — correct color tokens, good information hierarchy, and working state logic. However, it diverges from TrustOffice's design language in several measurable ways: **rounded corners where the rest of the product uses sharp 0px corners, `font-sans` (DM Sans) headings where every other page uses `font-serif` (Cormorant Garamond), missing `card-trust` / `corner-mark` card patterns, and raw `fetch` calls instead of shared API utilities.** These inconsistencies make the page feel like a *different product* rather than the same TrustOffice experience.

**Severity breakdown:** 7 medium findings, 5 low/minor findings, 3 positive observations.

---

## Findings

### 🔴 MEDIUM: Rounded corners break the TrustOffice design language

**Location:** Lines 201, 213, 233, 238, 257, 300, 324, 356, 373, 429, 477, 490, 619, 644, and many more

**Issue:** The page uses `rounded-xl`, `rounded-lg`, `rounded-full` extensively throughout. The Tailwind config explicitly sets **all border radii to 0px**:

```js
// tailwind.config.js
borderRadius: {
  lg: "0px",
  md: "0px",
  sm: "0px",
  DEFAULT: "0px",
},
```

However, `rounded-full`, `rounded-xl`, and `rounded-lg` are Tailwind *utility classes* that bypass the theme's `borderRadius` config — `rounded-lg` maps to `border-radius: var(--radius)` which is 0px, BUT `rounded-xl` (0.75rem) and `rounded-full` (9999px) are hardcoded in Tailwind's default scale and **are not overridden** by the theme config.

**Comparison:**
- **PricingPage:** Uses `rounded-full` only for badge pills (badges, toggle pills) — same as this page. But cards use `card-trust` class which has **no border radius** (sharp corners).
- **LoginPage:** Cards use `card-trust corner-mark` — sharp corners.
- **DashboardPage:** Banners, modals, and cards all use sharp corners (no `rounded-*` classes on container elements). Only small accent elements like the `w-10 h-10` icon circles use `bg-*` with no radius.

**Fix:** 
- Replace `rounded-xl` on package cards (line 233) and the action card container (line 257) with `card-trust` class (or remove radius to get 0px).
- Replace `rounded-lg` on inner elements (gold info boxes, FAQ items, error/success banners) — remove the class to default to 0px, or use `rounded-none` explicitly.
- Keep `rounded-full` on badge pills and icon circles — this is consistent with how PricingPage uses it for the "Most Popular" badge.

---

### 🔴 MEDIUM: Missing `font-serif` on all major headings

**Location:** Lines 204 (h1), 223 (h2), 235 (h3), 293 (h2), 360 (h3), 452 (h3), 474 (h3), 648 (h3)

**Issue:** All headings use default `font-sans` (DM Sans) or rely on `font-bold` without specifying a serif font. Every other TrustOffice page uses `font-serif` (Cormorant Garamond) for major headings.

**Comparison:**
- **PricingPage:** `font-serif text-4xl` on h1 (line 285), `font-serif text-3xl` on h2 (lines 302, 330), `font-serif text-2xl` on tier names (line 415) and comparison heading (line 460).
- **LoginPage:** `font-serif text-3xl` on "Sign In" heading (line 213).
- **DashboardPage:** `font-serif text-2xl` on "No Trusts Yet" (line 404), `font-serif text-xl` on modal heading (line 495).

**Fix:** Add `font-serif` to:
- `h1` "Welcome to TrustOffice" → `font-serif text-3xl sm:text-4xl lg:text-5xl`
- `h2` "Which package did you purchase?" → `font-serif text-xl sm:text-2xl`
- `h2` "Frequently Asked Questions" → `font-serif text-xl sm:text-2xl`
- `h3` package names → `font-serif text-lg`
- `h3` action section titles → `font-serif text-lg`

---

### 🔴 MEDIUM: Package cards don't use `card-trust` / `corner-mark` pattern

**Location:** Lines 231–251

**Issue:** Package cards use `bg-white rounded-xl border border-border p-6`. This is a generic "white box with border" pattern. Every other card in TrustOffice uses the `card-trust` CSS class with `corner-mark` decoration.

**Comparison:**
- **PricingPage:** Pricing cards use `card-trust corner-mark p-8` (line 406). The comparison table uses `card-trust` (line 461).
- **LoginPage:** Login form card uses `card-trust corner-mark relative` (line 212).
- **DashboardPage:** Cards throughout use `card-trust` (lines 564, 575, etc.).

**Fix:** Replace `bg-white rounded-xl border border-border p-6` with `card-trust p-6` (or `card-trust corner-mark p-6` if corner marks are desired on these cards).

---

### 🟡 MEDIUM: Action section card doesn't use `card-trust`

**Location:** Line 257

**Issue:** `bg-white rounded-xl border border-border p-6 sm:p-8` — same issue as package cards. Should use `card-trust` for consistency.

**Fix:** Replace with `card-trust p-6 sm:p-8`.

---

### 🟡 MEDIUM: FAQ items use `rounded-lg` instead of sharp corners

**Location:** Line 300

**Issue:** FAQ items use `bg-white rounded-lg border border-border overflow-hidden`. Should match card-trust pattern (no radius).

**Fix:** Replace `rounded-lg` with `card-trust` or remove `rounded-lg` (defaults to 0px radius).

---

### 🟡 MEDIUM: `font-mono` labels missing on section metadata

**Location:** Throughout the page

**Issue:** TrustOffice uses `font-mono text-xs uppercase tracking-widest` for small descriptive labels, micro-labels, and metadata text. The WingPoint page does not use this pattern anywhere.

**Comparison:**
- **LoginPage:** "Sign in to your account" subtitle uses `font-mono text-xs uppercase tracking-widest text-muted-foreground` (line 214). Labels use `font-mono text-[10px] uppercase tracking-widest` (lines 271, 290). "Powered by TrustOffice" footer uses `font-mono text-[10px] uppercase tracking-widest` (line 345).
- **PricingPage:** Feature comparison table headers use `font-mono text-xs uppercase` (line 465).
- **DashboardPage:** Quick action labels use `font-mono text-xs uppercase` pattern implicitly via badge classes.

**Fix:** Add `font-mono text-xs uppercase tracking-widest` to:
- "WingPoint Customer" badge text (line 202)
- "Maps to TrustOffice" micro-label (line 239)
- Section subtitles like "Recognize your WingPoint package below..." (line 226) — consider the mono treatment
- Footer "wingpointtrust.com" link (line 328)

---

### 🟡 MEDIUM: Raw `fetch` calls instead of shared API utilities

**Location:** Lines 88, 118, 144

**Issue:** The page uses raw `fetch()` for token verification (line 88), password reset (line 118), and login (line 144). Other pages use shared utilities.

**Comparison:**
- **LoginPage:** Uses a custom `xhrPost` helper (lines 14–42) for maximum mobile compatibility — raw XMLHttpRequest, not fetch.
- **PricingPage:** Also uses `xhrPost` (lines 11–42).
- **DashboardPage:** Uses `fetchWithAuth` from `@/utils/api` (line 7).

**Fix:** 
- For the login call, use the same `xhrPost` pattern as LoginPage for mobile compatibility, or extract `xhrPost` into a shared utility.
- For authenticated calls (if any were needed), use `fetchWithAuth` from `@/utils/api`.
- Use `showError` from `@/utils/errors` for error handling (as DashboardPage does, line 9) instead of raw `toast.error(error.message)`.

---

### 🟢 LOW: Header logo missing — uses text only

**Location:** Lines 182–184

**Issue:** The header uses a text-only "TrustOffice" link. PricingPage and LoginPage use the actual logo image.

**Comparison:**
- **PricingPage:** Uses `<img src="...Trust%20Office%20Logo%20%281%29.svg" className="h-8 brightness-0 invert" />` (lines 265–269).
- **LoginPage:** Uses `<img src="/assets/trustoffice-logo.svg" />` (line 205) and `<img src="/assets/trustoffice-logo-vertical.svg" />` (line 190).

**Fix:** Use the same logo image as PricingPage. Since the header has a navy background, apply `brightness-0 invert` to make the logo white.

---

### 🟢 LOW: Header padding and spacing differs from PricingPage

**Location:** Line 180

**Issue:** Header uses `py-4 px-4 sm:px-6` with `max-w-5xl`. PricingPage uses `py-6 px-8` with `max-w-6xl`.

**Comparison:**
- **PricingPage:** `className="bg-navy text-white py-6 px-8"` with `max-w-6xl mx-auto` (lines 262–263).
- **LoginPage:** No navy header bar (uses split layout).

**Fix:** Consider aligning to `py-6 px-8` and `max-w-6xl` for header consistency. The content area `max-w-5xl` is fine since this page has less content than pricing.

---

### 🟢 LOW: Gold accent badges use `/10` opacity; PricingPage uses `/20`

**Location:** Lines 201, 213, 238, 477, 619

**Issue:** Gold info badges/banners use `bg-gold/10 border border-gold/30`. PricingPage's equivalent banners use `bg-gold/20`.

**Comparison:**
- **PricingPage:** Coupon badge uses `bg-gold/20 text-navy` (line 292). WingPoint banner uses `bg-gold/20 text-white` (line 308).
- **DashboardPage:** WingPoint persistent banner uses `bg-gold/10` (line 466) and icon circle uses `bg-gold/20` (line 470). WP welcome modal uses `bg-gold/10` (line 491).
- **LoginPage:** WP welcome-back banner uses `bg-gold/10 border border-gold/30` (line 220) — **matches WingPointWelcomePage**.

**Assessment:** This is actually inconsistent across the app itself. LoginPage and DashboardPage use `/10`, PricingPage uses `/20`. The WingPoint page follows the LoginPage/Dashboard convention, so this is **acceptable** but worth noting for overall system alignment.

**Fix (optional):** Standardize all gold accent backgrounds to either `/10` or `/20` across the app. Recommend `/10` with `border-gold/30` as the baseline since it's more common.

---

### 🟢 LOW: Check icon color — gold vs success green

**Location:** Line 245

**Issue:** Feature list checkmarks use `text-gold` (via `CheckCircle` icon). PricingPage uses `text-success` (green, via `Check` icon, line 436).

**Comparison:**
- **PricingPage:** `Check className="w-5 h-5 text-success"` (line 436).
- **DashboardPage:** Uses `CheckCircle2` with default coloring in some places, `text-gold` for WingPoint-related items (line 502).

**Assessment:** Using gold checks on a WingPoint-specific page is a defensible design choice — it visually ties the page to the WingPoint/gold accent. However, for consistency with how features are listed on the pricing page, `text-success` is the standard.

**Fix (optional):** If the gold checks are intentional branding for the WingPoint page, keep them. If consistency matters more, switch to `text-success` and use the `Check` icon (not `CheckCircle`) to match PricingPage exactly.

---

### 🟢 LOW: Page lacks `data-testid` attributes

**Location:** Throughout

**Issue:** The page has zero `data-testid` attributes. Other pages are heavily instrumented for testing.

**Comparison:**
- **PricingPage:** Every interactive element has `data-testid` (lines 300, 323, 379, 387, 407, 446, etc.).
- **DashboardPage:** Extensive `data-testid` usage (lines 396, 424, 428, 461, 487, etc.).
- **LoginPage:** `data-testid` on all key elements (lines 183, 219, 231, 254, 283, etc.).

**Fix:** Add `data-testid` attributes to key elements: the welcome section, package cards, action buttons, FAQ items, and form inputs.

---

## Positive Observations

### ✅ Color tokens are correct
The page correctly uses `navy`, `gold`, `subtle-bg`, `muted-foreground`, `border`, and `success`/`error` tokens from the Tailwind config. No hardcoded hex colors that duplicate theme values.

### ✅ Spacing and layout structure is sound
The `max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-12` content container is reasonable. The section spacing (`mb-12` between sections) creates good rhythm. The grid layout for package cards (`grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6`) is responsive and appropriate.

### ✅ Visual hierarchy is correct
The page follows the intended order: Welcome (largest, centered) → Package cards (grid) → Smart Action (conditional content) → FAQ (collapsible). This is the right narrative flow for a WingPoint customer arriving at TrustOffice.

### ✅ Existing UI components are used
The page correctly imports and uses `Button`, `Input`, `Label` from `@/components/ui/` — the shared component library. It doesn't reinvent these.

### ✅ Gold/navy usage on banners is consistent
The gold accent badges with navy text match the pattern used in LoginPage's WingPoint welcome-back banner (line 220) and DashboardPage's persistent WingPoint banner (line 466).

---

## Summary of Required Fixes

| Priority | Finding | Effort |
|----------|---------|--------|
| 🔴 High | Remove `rounded-xl`/`rounded-lg` from cards; use `card-trust` | 30 min |
| 🔴 High | Add `font-serif` to all h1/h2/h3 headings | 15 min |
| 🔴 High | Replace package card styling with `card-trust` class | 10 min |
| 🟡 Med | Replace action card styling with `card-trust` class | 5 min |
| 🟡 Med | Remove `rounded-lg` from FAQ items | 5 min |
| 🟡 Med | Add `font-mono text-xs uppercase tracking-widest` to metadata labels | 20 min |
| 🟡 Med | Use `xhrPost` or shared API utility instead of raw `fetch` | 30 min |
| 🟢 Low | Add logo image to header | 5 min |
| 🟢 Low | Align header padding to match PricingPage | 5 min |
| 🟢 Low | Standardize gold opacity (`/10` vs `/20`) across app | 15 min |
| 🟢 Low | Decide on gold vs success-green check icons | 5 min |
| 🟢 Low | Add `data-testid` attributes to key elements | 20 min |

**Total estimated effort:** ~2.5 hours

---

## Verdict

The page **works functionally** and gets the color tokens right, but it **does not feel like the same product** as the rest of TrustOffice. The two most impactful issues are:

1. **Rounded corners** — the entire TrustOffice design language is built on sharp 0px corners (the Tailwind config literally zeros out all radii). The rounded-xl/rounded-lg usage makes this page look like a different design system.
2. **Missing serif headings** — Cormorant Garamond is the heading font across every other page. Using DM Sans for headings here breaks the typographic hierarchy that defines TrustOffice's editorial, professional feel.

Fixing these two issues alone would bring the page 80% of the way to full design consistency.