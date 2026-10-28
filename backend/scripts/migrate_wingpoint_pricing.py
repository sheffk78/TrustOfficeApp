#!/usr/bin/env python3
"""Migrate existing WingPoint subscribers from legacy prices to new 2026-10-28 prices.

Legacy price IDs (must match EXACTLY):
  - annual: price_1U1JcFJE7N1BszdfbSjSSa7c  ($1,188/yr)
  - monthly: price_1U4mSwJE7N1Bszdf9GHSbm89 ($119/mo)

New price IDs (target):
  - annual: price_1UVXj8JE7N1BszdfsPoo3rkm  ($948/yr)
  - monthly: price_1UVXj8JE7N1BszdfjAlfQSaE ($99/mo)

Usage:
  python backend/scripts/migrate_wingpoint_pricing.py --dry-run > backend/scripts/out/migration-dryrun.json
  python backend/scripts/migrate_wingpoint_pricing.py --apply

Guard: ONLY touches subscriptions whose items[0].price.id is one of the two
legacy IDs above. Comped/entitlement accounts (TAS cohorts) typically have no
Stripe subscription on wingpoint price IDs, so they are naturally excluded.
Trustee/estate/advisor price subs are never matched.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Ensure repo root on path for imports if needed
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _REPO)

import stripe

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LEGACY_WINGPOINT_ANNUAL = "price_1U1JcFJE7N1BszdfbSjSSa7c"
LEGACY_WINGPOINT_MONTHLY = "price_1U4mSwJE7N1Bszdf9GHSbm89"

NEW_WINGPOINT_ANNUAL = "price_1UVXj8JE7N1BszdfsPoo3rkm"
NEW_WINGPOINT_MONTHLY = "price_1UVXj8JE7N1BszdfjAlfQSaE"

LEGACY_TO_NEW = {
    LEGACY_WINGPOINT_ANNUAL: NEW_WINGPOINT_ANNUAL,
    LEGACY_WINGPOINT_MONTHLY: NEW_WINGPOINT_MONTHLY,
}

_LEGACY_NAMES = {
    LEGACY_WINGPOINT_ANNUAL: "wingpoint_annual_1188",
    LEGACY_WINGPOINT_MONTHLY: "wingpoint_monthly_119",
}

_NEW_NAMES = {
    NEW_WINGPOINT_ANNUAL: "wingpoint_annual_948",
    NEW_WINGPOINT_MONTHLY: "wingpoint_monthly_99",
}

_PRICE_AMOUNTS = {
    LEGACY_WINGPOINT_ANNUAL: 1188.00,
    LEGACY_WINGPOINT_MONTHLY: 119.00,
    NEW_WINGPOINT_ANNUAL: 948.00,
    NEW_WINGPOINT_MONTHLY: 99.00,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_stripe_key():
    creds_path = os.path.expanduser("~/.hermes/secrets/stripe-trustoffice-agentic.json")
    if os.path.exists(creds_path):
        with open(creds_path) as f:
            data = json.load(f)
        return data.get("secret_key")
    # fallback to env (e.g. in CI)
    return os.environ.get("STRIPE_SECRET_KEY")


def _list_matching_subscriptions():
    """Return every Stripe subscription whose first item price.id is a legacy
    WingPoint price. Yields dicts with sub id, customer email, current price id,
    current amount, proposed new price id, proposed amount, next billing date."""
    stripe.api_key = _load_stripe_key()
    if not stripe.api_key:
        raise RuntimeError("Stripe secret key not found")

    # Paginate through all subscriptions (status=all so we don't miss paused/past_due)
    subs = stripe.Subscription.list(limit=100, status="all")
    while True:
        for sub in subs.auto_paging_iter():
            sub_d = sub.to_dict()
            items = sub_d.get("items", {}).get("data", [])
            if not items:
                continue
            price_id = items[0].get("price", {}).get("id")
            if price_id not in LEGACY_TO_NEW:
                continue

            # Resolve customer email
            customer = sub_d.get("customer")
            email = None
            if isinstance(customer, dict):
                email = customer.get("email")
            elif customer:
                try:
                    cust_obj = stripe.Customer.retrieve(customer)
                    email = cust_obj.get("email")
                except Exception:
                    email = None

            next_billing = None
            cpe = sub_d.get("current_period_end")
            if cpe:
                try:
                    from datetime import datetime as _dt
                    next_billing = _dt.utcfromtimestamp(cpe).isoformat() + "Z"
                except Exception:
                    next_billing = str(cpe)

            yield {
                "subscription_id": sub_d["id"],
                "customer_email": email,
                "current_price_id": price_id,
                "current_price_name": _LEGACY_NAMES.get(price_id, price_id),
                "current_price_amount": _PRICE_AMOUNTS.get(price_id),
                "proposed_new_price_id": LEGACY_TO_NEW[price_id],
                "proposed_new_price_name": _NEW_NAMES.get(LEGACY_TO_NEW[price_id], LEGACY_TO_NEW[price_id]),
                "proposed_new_price_amount": _PRICE_AMOUNTS.get(LEGACY_TO_NEW[price_id]),
                "next_billing_date": next_billing,
                "status": sub_d.get("status"),
            }
        if not subs.has_more:
            break
        subs = stripe.Subscription.list(
            limit=100, status="all", starting_after=subs.data[-1]["id"]
        )


def _update_subscription(sub_id, new_price_id):
    """Update a single subscription to the new price with proration none."""
    stripe.api_key = _load_stripe_key()
    sub = stripe.Subscription.retrieve(sub_id)
    item_id = sub["items"]["data"][0]["id"]
    stripe.Subscription.modify(
        sub_id,
        items=[{"id": item_id, "price": new_price_id}],
        proration_behavior="none",
    )


def main():
    parser = argparse.ArgumentParser(description="Migrate WingPoint subscribers to new pricing")
    parser.add_argument("--dry-run", action="store_true", help="List affected subs without modifying")
    parser.add_argument("--apply", action="store_true", help="Apply price updates to matching subs")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.print_help()
        sys.exit(1)

    rows = list(_list_matching_subscriptions())

    # Dry-run always prints JSON to stdout
    print(json.dumps(rows, indent=2))

    # Summary line to stderr so it doesn't corrupt JSON on stdout
    print(f"Total matching subscriptions: {len(rows)}", file=sys.stderr)

    if args.apply:
        print("Applying updates...", file=sys.stderr)
        for row in rows:
            _update_subscription(row["subscription_id"], row["proposed_new_price_id"])
            print(f"  Updated {row['subscription_id']} -> {row['proposed_new_price_id']}", file=sys.stderr)
        print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
