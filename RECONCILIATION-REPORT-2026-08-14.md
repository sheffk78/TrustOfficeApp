# TrustOffice Revenue Reconciliation Report — 2026-08-14

## Executive Summary

**The Admin API's reported revenue ($803 MRR / $1,106 total) does NOT match Stripe actual charges ($237 verified MRR / $316 verified total).** Both numbers are inflated. The Admin API pulls total revenue from MongoDB `payment_transactions` (which includes orphaned records from a dead Stripe account) and computes MRR from MongoDB subscription counts (which include gifted subs and subs pointing at the old, expired Stripe account).

| Metric | Admin API Reports | Stripe Verified | Discrepancy |
|--------|-------------------|-----------------|-------------|
| Total Revenue | $1,106.00 (5 txns) | $316.00 (4 invoices) | **+$790.00 overstated** |
| MRR | $803.15 (11 paying subs) | $237.00 (3 active subs × $79) | **+$566.15 overstated** |

---

## Root Causes

### 1. Account Migration — Old Stripe Account Dead

TrustOffice migrated from Stripe account `acct_102bZ92lZzmsSFmd` (Sheffk Ventures LLC) to `acct_1TtfNZJE7N1Bszdf` (Agentic Trust). The old account's API key is **expired** (`sk_live_5102bZ92lZzmsSFmd...` returns `AuthenticationError: Expired API Key`).

**4 paying subscriptions** in MongoDB still reference the old account:
- `galeg529@gmail.com` — annual — `cus_Uon7FbCw4yrb7M` / `sub_1Tp9ZB2lZzmsSFmd6g2YsnU8`
- `largecardieselrepair@yahoo.com` — annual — `cus_UYTQMvjJRsOoK0` / `sub_1TZMUJ2lZzmsSFmdk7OeGA7W`
- `waylon@circlebara.com` — annual — `cus_UDQGwmBjV5vjpW` / `sub_1TEzR72lZzmsSFmdz9Wb9Kwa`
- (1 more annual sub — `demovideo@trustoffice.app` — gifted, no Stripe IDs)

These subscription IDs and customer IDs do NOT exist on the new Stripe account. Their status cannot be verified — they may be canceled on the old account but still show "active" in MongoDB.

### 2. Total Revenue from MongoDB, Not Stripe

The `/admin-api/stats/summary` endpoint (`admin_api.py:258`) computes total revenue from the MongoDB `payment_transactions` collection:
```python
revenue_pipeline = [{"$match": {"$or": [
    {"payment_status": "paid"}, {"payment_status": "succeeded"},
    {"status": "succeeded"}, {"status": "paid"}
]}}]
```
This counts 5 transactions totaling $1,106, but only 4 of those correspond to actual Stripe invoices on the current account ($316). The 5th transaction ($790 — an annual payment) is an orphaned record from the old account era with no matching Stripe invoice.

### 3. MRR Counts Non-Paying & Ghost Subscriptions

The MRR calculation (`admin_api.py:328-334`) counts ALL MongoDB subscriptions with `status: "active"` × fixed rates:
- **3 subs** verified active on new Stripe account (3 × $79 = $237/mo)
- **4 subs** with Stripe IDs from the OLD (dead) account — cannot verify if actually still paying
- **4 subs** with NO Stripe subscription at all (gifted or manually created):
  - `martyjensen@gmail.com` (monthly, gifted=True)
  - `monitoring@trustoffice.app` (trustee, gifted=True)
  - `demovideo@trustoffice.app` (annual, gifted=True)
  - `mlgraham79@protonmail.com` (monthly, no Stripe IDs, gifted=None)
  - `btudsbury@fastmail.com` (annual, no Stripe IDs, gifted=None)

**Gifted subscriptions should not count toward MRR** — they generate no revenue.

### 4. Non-Subscription Charges Inflate Stripe Total

The new Stripe account has $29,416 in total succeeded charges, but only $316 are from TrustOffice subscriptions ($79 × 4). The remaining $29,100 consists of 4 large charges ($3,000 / $5,500 / $3,000 / $17,600) that are NOT TrustOffice subscription payments — likely consulting or one-off service charges on the same account.

---

## Stripe Verified Data (New Account — acct_1TtfNZJE7N1Bszdf)

### Paid Invoices (TrustOffice)
| Date | Amount | Invoice ID | Customer |
|------|--------|------------|----------|
| 2026-08-06 | $79.00 | in_1U1XlvJE7N1BszdfswaEuvRP | cus_V1awuelqXLJ5Yx |
| 2026-08-06 | $79.00 | in_1U1XpPJE7N1Bszdfq9GuJYla | cus_V1awuelqXLJ5Yx |
| 2026-08-07 | $79.00 | in_1U1ttiJE7N1BszdfcYnnTwPO | cus_V1xo29sXnhe93N |
| 2026-08-13 | $79.00 | in_1U46XjJE7N1BszdfHu9HWAen | cus_V4EvS3k9fUcgRn |
| **Total** | **$316.00** | | |

### Active Subscriptions (Verified on Stripe)
| Subscription ID | Customer | Price ID | Plan | MRR |
|----------------|----------|----------|------|-----|
| sub_1U1XpTJE7N1BszdfaAJcjzIn | cus_V1awuelqXLJ5Yx | price_1U1JcCJE7N1BszdfJ9A7S35c | trustee_monthly | $79/mo |
| sub_1U1ttkJE7N1BszdffPfiZ8RB | cus_V1xo29sXnhe93N | price_1U1JcCJE7N1BszdfJ9A7S35c | trustee_monthly | $79/mo |
| sub_1U46XmJE7N1BszdfKC0eLWtJ | cus_V4EvS3k9fUcgRn | price_1U1JcCJE7N1BszdfJ9A7S35c | trustee_monthly | $79/mo |
| **Total Verified MRR** | | | | **$237/mo** |

---

## MongoDB Active Subscriptions (Admin API View)

| Email | Plan Type | Stripe Customer | Stripe Sub | Gifted | Verified? |
|-------|-----------|----------------|------------|--------|-----------|
| brandon17504@proton.me | trustee/mo | cus_V4EvS3k9fUcgRn | sub_1U46Xm... | No | ✅ Verified |
| jaylan.haley@gmail.com | trustee/mo | cus_V1awuelqXLJ5Yx | sub_1U1XpT... | No | ✅ Verified |
| bubba.bartlett@outlook.com | trustee/mo | cus_V1xo29sXnhe93N | sub_1U1ttk... | No | ✅ Verified |
| martyjensen@gmail.com | monthly | None | None | **Yes** | ❌ Gifted |
| monitoring@trustoffice.app | trustee | None | None | **Yes** | ❌ Gifted |
| demovideo@trustoffice.app | annual | None | None | **Yes** | ❌ Gifted |
| mlgraham79@protonmail.com | monthly | None | None | No | ❌ No Stripe |
| btudsbury@fastmail.com | annual | None | None | No | ❌ No Stripe |
| galeg529@gmail.com | annual | cus_Uon7FbCw4yrb7M | sub_1Tp9ZB...2lZz... | No | ❌ Old account |
| largecardieselrepair@yahoo.com | annual | cus_UYTQMvjJRsOoK0 | sub_1TZMUJ...2lZz... | No | ❌ Old account |
| waylon@circlebara.com | annual | cus_UDQGwmBjV5vjpW | sub_1TEzR7...2lZz... | No | ❌ Old account |

---

## Recommendations

### Fix 1: Exclude gifted subs from MRR (admin_api.py)
The MRR pipeline should exclude `gifted: true` subscriptions. Currently it counts all `status: "active"` subs.

### Fix 2: Validate Stripe subscription existence for MRR
Subscriptions with `stripe_subscription_id` from the old account (containing `2lZzmsSFmd`) should be flagged as unverified and excluded from MRR until migrated to the new account.

### Fix 3: Pull total revenue from Stripe, not MongoDB
The `/admin-api/stats/summary` endpoint should use `stripe.Invoice.list(status="paid")` with the `_is_trustoffice_invoice` filter (like `stats.py` already does), instead of relying on MongoDB `payment_transactions` which can contain orphaned records.

### Fix 4: Reconcile old-account subscriptions
The 3 paying subs with old-account Stripe IDs need manual reconciliation:
- Either re-subscribe them on the new account, or
- Mark them as canceled if they're no longer paying

### Fix 5: Reconcile non-Stripe "paying" subs
The 2 subs with no Stripe IDs and `gifted != True` (`mlgraham79@protonmail.com`, `btudsbury@fastmail.com`) need investigation — they may be manually created subs that should be marked as gifted or re-subscribed via Stripe.