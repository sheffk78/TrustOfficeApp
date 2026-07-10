# WingPoint → TrustOffice Customer Experience Audit

**Date:** July 10, 2026
**Scope:** The handoff experience when a WingPoint trust purchaser is provisioned into TrustOffice
**Audience:** Product, engineering, and design stakeholders

---

## Section 1: Executive Summary

A customer just paid $3,000–$9,500 on WingPoint to create their trust. Moments later, they receive an email from a company they've never heard of — TrustOffice — asking them to set a password. Then they land on a pricing page asking for $79/month. No one explains the relationship. No one acknowledges the purchase. No one says *why* the monthly fee exists.

This is the #1 risk in the entire WingPoint partnership funnel. It feels like a bait-and-switch — not because the fee is wrong, but because the **context is missing at every step**.

### Top 3 Improvements (Ranked by Impact)

| Rank | Improvement | Why It Matters |
|------|------------|----------------|
| 1 | **Welcome Email redesign** | This is the first touchpoint. If the email is generic, every downstream page starts from a deficit. A warm, context-rich email sets the tone for the entire relationship. |
| 2 | **"Why Am I Paying Again?" explanation on PricingPage** | This is the moment of maximum abandonment risk. The customer sees $79/mo with no explanation. A clear, honest framing — "WingPoint created your trust. TrustOffice manages it." — converts confusion into confidence. |
| 3 | **WingPoint-aware welcome on DashboardPage** | After payment, the customer lands on an empty dashboard with no acknowledgment. A welcome banner ("Your trust is ready. Here's what happens next.") builds confidence that their $3,000+ purchase was real and is being handled. |

---

## Section 2: Journey Map — Current vs Proposed

### Current Flow

```
Customer pays $3,000+ on WingPoint
        ↓
Receives email: "Set your password"
   (Generic. No mention of WingPoint. No mention of trust.
    Looks like any SaaS onboarding email.)
        ↓
Lands on ResetPasswordPage: "Set your password"
   (Clinical form. No welcome. No context. No "here's why you're here.")
        ↓
Redirected to PricingPage: 3 tiers — $79 / $149 / $399
   (Correct plan highlighted with gold ring. But no explanation
    of WHY they're paying again. Feels like an upsell trap.)
        ↓
Picks plan, enters payment via Stripe
   (WINGPOINT50 coupon silently applied. $50 off first month.
    But customer doesn't know the coupon is there until checkout.)
        ↓
Lands on DashboardPage
   (Silent. Empty. No welcome. No "your trust is ready."
    No acknowledgment that they just spent thousands of dollars.)
```

### Proposed Flow

```
Customer pays $3,000+ on WingPoint
        ↓
Receives email: "Welcome from WingPoint + TrustOffice"
   (Warm. Explains the relationship. Mentions the $50 coupon.
    Sets expectations about monthly management subscription.)
        ↓
Lands on Welcome + Set Password page
   (Acknowledges WingPoint purchase by name.
    "You're one step from accessing your WingPoint trust."
    Warm, human, confident.)
        ↓
Redirected to Confirm Subscription page
   (Plan is pre-selected and explained.
    "WingPoint created your trust. TrustOffice keeps it managed, updated,
     and legally current. Choose your management plan to activate access."
    $50 coupon called out explicitly. Monthly fee framed as
    ongoing service, not a new purchase.)
        ↓
Picks plan (or confirms pre-selected), enters payment
   (Customer knows exactly what they're paying for and why.)
        ↓
Lands on DashboardPage
   (Welcome banner or modal: "Your trust is ready."
    Acknowledges WingPoint purchase. Shows trust status.
    Guides next steps: review trust, add beneficiaries, schedule consultation.)
```

---

## Section 3: Email Redesign

### Subject Line Options

1. **"Your WingPoint trust is ready — let's set up your access"**
2. **"Welcome from WingPoint + TrustOffice — activate your trust account"**
3. **"One last step to access your WingPoint trust"**

### Email Body

> **Preheader:** Your trust is ready. Here's how to access it.
>
> ---
>
> Hi {firstName},
>
> You recently purchased a trust package through WingPoint. Great choice — and we're here to make sure it stays in good hands.
>
> **TrustOffice is the platform that manages your trust.** Think of it this way: WingPoint built your trust. TrustOffice keeps it running — updated, secure, and accessible whenever you need it.
>
> Here's what happens next:
>
> **1. Set your password.** The link below takes you to your TrustOffice account. It takes 30 seconds.
>
> **2. Choose your management plan.** Your trust lives on TrustOffice, and your plan covers ongoing management — amendments, beneficiary updates, document storage, and access to your trust documents anytime. WingPoint has covered $50 of your first month as part of your purchase.
>
> **3. Access your trust.** Once your plan is active, you'll land on your dashboard where your trust documents are ready to review.
>
> If you have questions about which plan is right for you, just reply to this email — we're real people, not a chatbot.
>
> **[ Activate My Trust Account ]**
>
> Welcome aboard,
> The TrustOffice Team
> *In partnership with WingPoint*
>
> ---

### Call-to-Action Button Text

- **Primary:** "Activate My Trust Account"
- **Alternative:** "Set Up My Trust Access"
- **Shorter variant:** "Access My Trust"

---

## Section 4: Page-by-Page Copy

### ResetPasswordPage

**Current State:**
- Headline: "Set Your Password"
- Body: Generic password form with two fields and a submit button
- Context: Zero acknowledgment of WingPoint, the trust purchase, or why the user is here

**Recommended Copy:**

> **Headline:** Welcome — your WingPoint trust is ready
>
> **Subheadline:** You're one step away from accessing your trust account. Let's set your password and get you in.
>
> **Body (small, below form):**
> TrustOffice is the management platform for your WingPoint trust. WingPoint created it. We keep it current, secure, and accessible — for as long as you need it.
>
> **Button:** Continue to My Trust
>
> *(If ?wp=1 parameter is present, show this version. Otherwise, show standard "Set Your Password" for non-WingPoint users.)*

---

### PricingPage (WingPoint users — when `?wp=1`)

**Current State:**
- Standard 3-tier pricing page: Trustee $79/mo, Estate $149/mo, Advisor $399/mo
- Correct plan highlighted with gold ring
- No context about WingPoint, the trust purchase, or why a monthly fee exists
- WINGPOINT50 coupon silently applied at checkout (customer doesn't know until they're already paying)

**Recommended Copy:**

**WingPoint Welcome Banner (top of page, above pricing tiers):**

> **Your trust is ready. Choose your management plan to access it.**
>
> You purchased your trust through WingPoint. TrustOffice is where that trust lives — managed, updated, and accessible whenever you need it.
>
> Your monthly plan covers ongoing trust management: amendments, beneficiary updates, secure document storage, and access to your trust documents. **$50 off your first month, courtesy of WingPoint** — already applied at checkout.
>
> Not sure which plan is right? We've highlighted our recommendation based on your WingPoint purchase.

**Plan Card Additions (WingPoint-specific context):**

- Trustee ($79/mo): "Perfect for your single WingPoint trust. Manage one trust with full access to documents and amendments."
- Estate ($149/mo): "Ideal if you have WingPoint's Estate Bundle. Manage up to 5 trusts — for family, properties, or business entities."
- Advisor ($399/mo): "For WingPoint Builder Bundle customers managing multiple trusts. Unlimited trusts, priority support."

**Coupon Callout (near the recommended plan):**

> 🎯 **$50 off your first month** — your WingPoint coupon (WINGPOINT50) is already applied. You'll see it at checkout.

---

### LoginPage (WingPoint users — when `?wp=1`)

**Current State:**
- Standard login form: email + password, "Forgot password?" link
- No recognition of WingPoint context

**Recommended Copy:**

**Welcome-Back Banner (small, above login form):**

> **Welcome back.** Your WingPoint trust is waiting in your TrustOffice account. Log in to continue setting up your management plan.

**Form labels remain standard.** The banner is the only change — subtle, warm, no friction added.

---

### DashboardPage (first visit from WingPoint)

**Current State:**
- Empty dashboard with standard nav
- No welcome, no context, no acknowledgment of the $3,000+ purchase
- Customer doesn't know where their trust is or what to do next

**Recommended Copy:**

**Welcome Modal (first visit only, dismissible):**

> **Welcome to TrustOffice — your WingPoint trust is here.**
>
> You're all set. Your trust documents are ready to review, and your management plan is active.
>
> Here's what you can do right now:
>
> - ✅ **Review your trust** — your documents are in the Trust Documents tab
> - ✅ **Add beneficiaries** — make sure your trust reflects your wishes
> - ✅ **Schedule a consultation** — talk to a trust advisor about your setup
>
> Your trust is managed and kept current through TrustOffice. If you ever need to amend, update, or access your documents, this is where you'll find them.
>
> **[ Go to My Trust Documents ]**  **[ Maybe Later ]**

**Persistent Banner (replaces modal after dismissal):**

> 📄 Your WingPoint trust is ready. [Review your trust documents →]

---

### BillingPage (upgrade flow — existing WingPoint users buying additional trusts)

**Current State:**
- Standard billing page with an "Upgrade your plan" banner
- No explanation of *why* an upgrade is needed
- Customer who bought an Estate Bundle (2 credits) on a Trustee plan (1 trust) sees "upgrade required" with no context

**Recommended Copy:**

**Contextual Upgrade Banner:**

> **You have more trusts than your current plan supports.**
>
> Your WingPoint purchase included additional trust credits, but your current Trustee plan covers 1 trust. To access all your trusts, upgrade to Estate (up to 5 trusts) or Advisor (unlimited trusts).
>
> **Good news:** Your $50 WingPoint coupon still applies if you upgrade now.
>
> **[ Upgrade My Plan ]**

---

## Section 5: Flow Simplification

### Proposal A: Combined Password + Plan Confirmation Page
**Effort:** Medium
**Description:** Instead of separate pages for setting a password and choosing a plan, combine them into a single page. Top half: set password. Bottom half: plan confirmation (pre-selected). One submit, one redirect to dashboard.
**Pros:** Fewer steps, less abandonment surface, feels like one cohesive onboarding
**Cons:** More complex to build, harder to handle edge cases (user already has an account, plan mismatch)
**Recommendation:** Worth building as a Phase 2 improvement. Not a blocker for launch.

### Proposal B: Pre-Selected Plan with One-Click Confirm
**Effort:** Low
**Description:** Instead of showing all 3 tiers and asking the customer to choose, pre-select the recommended plan based on their WingPoint purchase (Single Trust → Trustee, Estate Bundle → Estate, Builder Bundle → Advisor). Show a single card with the plan, price, coupon, and a "Confirm and Continue" button. Offer a "See other plans" link for users who want to change.
**Pros:** Reduces decision friction, removes the "why am I choosing?" confusion, feels guided
**Cons:** Some customers may want to see all options. Need to make the "other plans" link prominent enough.
**Recommendation:** **Do this first.** Highest impact-to-effort ratio. Can be built in a day.

### Proposal C: Magic Link Activation (Skip Password Entirely)
**Effort:** High
**Description:** The email link logs the user in directly — no password to set. They land on the plan confirmation page already authenticated. Password can be set later from settings.
**Pros:** Frictionless. Feels like magic. Eliminates the "why do I need a password?" moment entirely.
**Cons:** Security considerations (link forwarding, session expiration). More infrastructure work. Some customers expect a password.
**Recommendation:** **Not yet.** Too much engineering risk for the current phase. Revisit after the core experience is solid.

---

## Section 6: Quick Wins (< 30 min each)

These are small, high-impact changes that can be shipped immediately without new design assets or significant engineering effort.

| # | Quick Win | Where | Effort |
|---|-----------|-------|--------|
| 1 | Add WingPoint welcome banner to PricingPage when `?wp=1` — the copy from Section 4, pasted above the pricing tiers | PricingPage | ~20 min |
| 2 | Add WingPoint context to the set-password email body — replace the generic "Set your password" body with the Section 3 email draft | Email template | ~15 min |
| 3 | Add welcome banner to DashboardPage for first-time WingPoint users — the persistent banner variant from Section 4 | DashboardPage | ~25 min |
| 4 | Add contextual message to BillingPage upgrade banner — the Section 4 copy, replacing the generic "Upgrade your plan" text | BillingPage | ~15 min |

**Total time: ~75 minutes for all four.** These four changes alone would transform the WingPoint handoff from "confusing upsell" to "guided, confident onboarding."

---

## Appendix: Tone Principles

These principles govern every piece of copy in this document.

1. **Trusted advisor, not software company.** The customer should feel like they're being guided by someone who knows what they're doing — not being processed by a billing system.

2. **Short sentences.** If a sentence has more than 20 words, cut it. If a paragraph has more than 4 sentences, break it up.

3. **No jargon.** "Provisioning," "subscription management," "tiered pricing" — all out. "Your trust is ready," "choose your plan," "we keep it current" — all in.

4. **Acknowledge the money.** The customer paid $3,000+. Never pretend that didn't happen. Reference it. Honor it. Make them feel it was worth it.

5. **Explain the "why" before the "what."** Before asking them to pay, explain *why* the fee exists. Before asking them to set a password, explain *why* they need one. Context first, action second.

6. **Warm, not corporate.** "Hi {firstName}" not "Dear Valued Customer." "We're real people" not "Contact our support team." The tone should feel like a letter from someone who cares, not a notification from a system.

7. **Never feel like an upsell.** The monthly fee is ongoing management, not a new purchase. Frame it as service, not product. The customer should feel like they're subscribing to peace of mind, not being charged again.

---

*This audit was prepared to guide the WingPoint → TrustOffice handoff experience. All copy is draft and ready for design + engineering implementation.*