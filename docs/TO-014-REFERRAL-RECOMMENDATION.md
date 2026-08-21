# TO-014 — Referral Reward Rules: Kit's Recommendation

**Date:** 2026-08-20
**Author:** Kit (for Jeff review)
**Status:** Pending Jeff decision

---

## Current System (What's Live Today)

| Mechanic | Current Implementation |
|---|---|
| **Referee discount** | 50% off first payment (Stripe coupon `REFERRAL50`, duration "once") |
| **Referrer reward** | 50% off next invoice (same coupon applied to their subscription) |
| **Conversion trigger** | Stripe webhook fires when referee's subscription activates |
| **Self-referral** | Blocked |
| **Idempotency** | One referral tracking record per referee |
| **Pending rewards** | If referrer has no active sub, reward stored as pending |
| **No cap** | Unlimited referrals, unlimited discounts |
| **No monthly/annual distinction** | Same reward regardless of plan |

## Problems With the Current System

1. **50% is unbounded.** On Advisor monthly ($399), the referrer gets $199.50 off. On Trustee monthly ($79), they get $39.50. The reward value swings wildly by plan — expensive on Advisor, modest on Trustee.
2. **No stacking limit.** A user with 10 referrals could theoretically get 10x 50% discounts stacked.
3. **No monthly cap.** A monthly subscriber could get multiple discounts in a single billing cycle.
4. **No expiration.** Pending rewards live forever — a liability on the books.
5. **No clawback on refund.** If the referee cancels and gets a refund, the referrer keeps the reward.

## Recommended Rules

### 1. Referee Incentive — Keep 50% Off First Payment

**Recommendation: Keep as-is.**

It's a strong, simple hook. "Your friend gets you 50% off" is more compelling than "$25 off" or "$50 credit" because the percentage feels like a deal, not a fixed coupon. The cost is bounded — it fires exactly once, on the first payment.

### 2. Referrer Reward — Flat $50 Credit Per Qualified Referral

**Recommendation: Replace the 50% discount with a flat $50 credit.**

| Plan | Monthly Price | $50 Credit = % Off | Annual Price | $50 Credit = % Off |
|---|---|---|---|---|
| Trustee | $79 | 63% | $790 | 6% |
| Estate | $149 | 34% | $1,490 | 3% |
| Advisor | $399 | 13% | $3,990 | 1% |
| WingPoint | $99 | 51% | $1,188 | 4% |

Why flat $50:
- **Controllable cost.** You know exactly what each referral costs: $50.
- **Fair across plans.** No $199 reward for Advisor referrals, $39 for Trustee.
- **Meaningful on monthly.** On Trustee monthly, $50 off is a near-free month — that's a real thank you.
- **Modest on annual.** $50 off a $790 annual renewal is a nice nudge, not a margin killer.
- **Easy to explain.** "Refer a friend, get $50 off your next bill." One sentence.

### 3. Qualification Event — First Successful Payment

**Recommendation: Credit issues only after the referee's first successful payment, not at signup.**

Already handled by the Stripe webhook trigger. No change needed — just formalize the rule: signup alone earns nothing. The referral must convert to a paid subscription.

### 4. Stacking Rules

| Subscriber Type | Stacking |
|---|---|
| **Monthly** | Max 1 credit per billing cycle. If 3 referrals convert in one month, 1 credit applies this cycle, 2 roll forward. |
| **Annual** | No cap. Credits compound. 3 referrals = $150 off the next annual charge. 10 referrals = $500 off. |

Why:
- Monthly subscribers are higher churn risk — capping prevents reward farming.
- Annual subscribers are committed — compounding rewards them for loyalty and advocacy.

### 5. Total Cap

**Recommendation: $500 lifetime credit cap per referrer.**

10 referrals × $50 = $500. That's a generous ceiling — enough to reward serious advocates, bounded enough to not become a liability. If someone exceeds 10 referrals, they're a power user worth talking to about the affiliate program instead.

### 6. Expiration

**Recommendation: Credits expire 12 months after issuance.**

Pending credits (referrer has no active subscription) expire in 12 months. Applied credits are used immediately. This prevents long-tail liability and creates urgency for pending-reward users to subscribe.

### 7. Refund / Cancellation Behavior

| Scenario | Treatment |
|---|---|
| Referee cancels, no refund (partial month used) | Credit stays. The referral was genuine. |
| Referee cancels with refund (within Stripe's 30-day window) | Claw back the referrer's credit. Log the clawback in the audit trail. |
| Referee downgrades plan | Credit stays. They're still a paying customer. |
| Referrer cancels their own subscription | Pending credits expire after 12 months as above. If they resubscribe within 12 months, credits are still there. |

### 8. Billing UI Rules

The billing page must state plainly:
- "Refer a friend: they get 50% off their first payment, you get $50 off your next bill."
- Show available credit balance.
- Show referral link + code.
- Show recent referrals with status (pending / converted / rewarded).
- Expiration date on pending credits: "2 credits expire Dec 2026."

---

## Implementation Notes

### What Changes in Code

1. **`referrals.py`** — Replace `REFERRAL_DISCOUNT_PERCENT = 50` referrer reward with flat $50 credit. The referee 50% discount stays (coupon). The referrer reward shifts from Stripe coupon to a credit ledger.
2. **New collection: `referral_credits`** — Tracks credit_id, user_id, amount ($50), source_referral_id, status (pending/applied/expired/clawed_back), issued_at, expires_at, applied_at.
3. **`subscriptions.py` checkout flow** — Apply pending credits to the next invoice via Stripe credit_notes or invoice item discounts.
4. **Webhook** — On referee subscription activation: issue $50 credit to referrer. On referee refund: claw back.
5. **Stats endpoint** — Add `available_credit`, `lifetime_credits_earned`, `credits_expiring` to the response.
6. **Frontend** — Billing page shows credit balance + referral section in Settings > Refer tab.

### Stripe Mechanics

Two approaches:
- **Stripe Credit Notes** (cleaner): Issue a credit note on the referrer's customer object. Stripe auto-applies it to the next invoice.
- **Negative Invoice Item** (simpler): Add a negative-amount invoice item (-$50) to the referrer's next invoice.

Recommendation: **Stripe Credit Notes** — they're auditable, visible in the Stripe dashboard, and auto-apply without webhook timing issues.

---

## Summary Table

| Rule | Current | Recommended |
|---|---|---|
| Referee gets | 50% off first payment | 50% off first payment (unchanged) |
| Referrer gets | 50% off next invoice | **$50 flat credit** |
| Qualification | First payment | First payment (unchanged) |
| Monthly cap | None | **1 credit per billing cycle** |
| Annual cap | None | **No cap (compounds)** |
| Lifetime cap | None | **$500** |
| Expiration | None | **12 months** |
| Refund clawback | None | **Yes** |
| Self-referral | Blocked | Blocked (unchanged) |

---

## What I Need From Jeff

1. **Approve / adjust the $50 flat credit amount** (vs. keeping 50%)
2. **Approve / adjust the $500 lifetime cap**
3. **Approve / adjust the 12-month expiration**
4. **Confirm the stacking rules** (monthly: 1/cycle, annual: unlimited)
5. **Confirm refund clawback** (claw back on refund, keep on no-refund cancellation)

Once approved, I'll implement the credit ledger, update the webhook, and update the billing UI.