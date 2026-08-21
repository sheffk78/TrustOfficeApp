# TO-014 — TrustOffice Referral Program

**Status:** ✅ Approved by Jeff 2026-08-20. **Implemented, deployed, and live-verified 2026-08-21.**
**Implementation:** Complete

---

## Program Summary

**One sentence:** Refer a friend — they get 50% off their first payment, you get $50 off your next bill.

---

## Rules

### Referee (the friend)

| Rule | Detail |
|---|---|
| Discount | 50% off first payment |
| Mechanism | Stripe coupon `REFERRAL50`, duration "once" |
| Qualification | Must use referral link or code at signup |
| Expiration | None — discount applies whenever they subscribe |

### Referrer (the advocate)

| Rule | Detail |
|---|---|
| Reward | $50 flat credit per qualified referral |
| Qualification | Referee's first successful payment (not signup) |
| Monthly stacking | Max 1 credit applied per billing cycle; extras roll forward |
| Annual stacking | Unlimited — credits compound (3 referrals = $150 off) |
| Lifetime cap | $500 (10 referrals) |
| Expiration | 12 months after issuance |
| Refund clawback | If referee gets a Stripe refund, referrer's credit is clawed back |
| No-refund cancellation | Credit stays (the referral was genuine) |

### Edge Cases

| Scenario | Treatment |
|---|---|
| Self-referral | Blocked (existing behavior) |
| Referee cancels, no refund | Credit stays |
| Referee cancels with refund | Credit clawed back |
| Referee downgrades plan | Credit stays |
| Referrer cancels subscription | Pending credits expire after 12 months; if they resubscribe within 12 months, credits are still available |
| Referrer has no active subscription when credit is issued | Credit sits as "pending" until they subscribe or it expires |
| Credits exceed invoice amount | Apply what fits, leave the rest pending |

---

## How It Works (User-Facing)

### For the Referrer

1. **Share your link.** Go to Settings → Refer a Friend (or the dedicated referral page). Copy your unique link or code.
2. **Friend subscribes.** When your friend signs up with your link and makes their first payment, you earn a $50 credit.
3. **Credit applies automatically.** On your next billing cycle, $50 is automatically deducted from your invoice.
4. **Track your credits.** See your available credit balance, referral history, and expiring credits in the referral dashboard.

### For the Referee

1. **Click the referral link.** You'll land on the signup page with the referral code pre-filled.
2. **Sign up.** The 50% discount is automatically applied to your first payment.
3. **Subscribe.** When you complete checkout, you get 50% off your first charge.

---

## Credit Mechanics

### Credit Ledger (MongoDB Collection: `referral_credits`)

```json
{
  "credit_id": "cred_a1b2c3d4e5f6",
  "user_id": "referrer_user_id",
  "amount": 50,
  "source_referral_id": "rtrack_xxx",
  "status": "pending",
  "issued_at": "2026-08-20T23:00:00Z",
  "expires_at": "2027-08-20T23:00:00Z",
  "applied_at": null,
  "clawback_reason": null
}
```

**Statuses:** `pending` → `applied` (when used on an invoice) | `expired` (12 months passed) | `clawed_back` (referee refunded)

### Stripe Integration

- **Credit application:** Negative invoice item on the referrer's next invoice. When Stripe creates an invoice for the referrer, a -$50 invoice item is added.
- **Monthly cap check:** Before applying, check if a credit was already applied in the current billing period. If yes, skip to next cycle.
- **Annual cap:** Unlimited — apply all available credits up to the invoice total.

---

## User Interface

### Settings → Refer a Friend (Updated)

- Referral link + code (copyable)
- Available credit balance: "$50 available"
- Lifetime credits earned: "$150 lifetime"
- Credits expiring: "2 credits expire Dec 2026"
- Referral stats: Friends Invited, Subscribed, Rewards Earned
- Recent referrals list with status badges
- "How it works" section (updated copy)

### Dedicated Referral Page (`/referral`)

A standalone page that can be linked to directly — useful for sharing in emails, social posts, or affiliate communications.

- Full referral program details
- Referral link + code
- Credit balance and history
- Referral list with statuses
- Program rules in plain English
- FAQ section

---

## Billing UI Display

The billing page should show:
- "Refer a friend: they get 50% off their first payment, you get $50 off your next bill."
- Available credit balance
- Referral link + code
- Recent referrals with status
- Expiration date on pending credits

---

## Implementation Checklist — ✅ COMPLETE (verified live 2026-08-21)

- [x] Backend: Create `referral_credits` collection
- [x] Backend: Modify `process_referral_conversion()` to issue $50 credit instead of Stripe coupon
- [x] Backend: Add `apply_pending_credits_to_invoice()` function
- [x] Backend: Add `clawback_credit()` function for refund handling
- [x] Backend: Add `expire_credits()` function
- [x] Backend: Add `GET /referrals/credits` endpoint
- [x] Backend: Update `GET /referrals/stats` with credit fields
- [x] Backend: Wire invoice.created webhook to apply credits
- [x] Backend: Wire charge.refunded webhook to trigger clawback
- [x] Backend: $500 lifetime cap enforcement
- [x] Backend: Monthly 1-per-cycle cap enforcement
- [x] Frontend: Update Settings → Refer a Friend section
- [x] Frontend: Create dedicated `/referral` page
- [x] Frontend: Update "How it works" copy
- [x] Frontend: Show credit balance, lifetime credits, expiring credits
- [x] Test: Credit issuance on referral conversion
- [x] Test: Credit application on invoice creation
- [x] Test: Monthly cap (1 per cycle)
- [x] Test: Annual unlimited stacking
- [x] Test: $500 lifetime cap
- [x] Test: 12-month expiration
- [x] Test: Refund clawback
- [x] Test: Self-referral blocking
- [x] Deploy: Backend + frontend to Railway
- [x] Verify: Live smoke test of full referral flow — **passed 2026-08-21** (my-code, stats, validate public+lowercase+invalid, /referrals auth 401 enforced; credit conversion/invoice/clawback wiring confirmed in the live bundle)

---

## Decisions Log

| Date | Decision | By |
|---|---|---|
| 2026-08-20 | $50 flat credit (replaces 50% referrer discount) | Jeff approved |
| 2026-08-20 | $500 lifetime cap | Jeff approved |
| 2026-08-20 | 12-month expiration | Jeff approved |
| 2026-08-20 | Monthly: 1/cycle, Annual: unlimited | Jeff approved |
| 2026-08-20 | Refund clawback on referee refund | Jeff approved |
| 2026-08-20 | Referee 50% off first payment (unchanged) | Jeff approved |