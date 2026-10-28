"""WingPoint customer identity — single source of truth.

Every code path that answers "is this user a WingPoint customer?" must call
`is_wingpoint_user()` instead of re-deriving the check inline. The check kept
drifting: three of four copies missed `created_via == "wingpoint_connect"`
(accounts created through the Connect Flow v2 signup), which surfaced regular
pricing / 403s to real WingPoint customers. 2026-10-28 fix (JOB-20261028-TO-WP-PRICING-DISCONNECT).

A user is a WingPoint customer when ANY of these hold on their user document:

- ``wp_ref`` is set                — carries the WingPoint attribution id
- ``source == "wingpoint"``        — legacy direct marking
- ``created_via == "wingpoint_provision"``  — provisioned via the email/set-password flow
- ``created_via == "wingpoint_connect"``    — created through the Connect Flow v2 signup

Checkout-path membership (2026-10-28): the /pricing?wp=1 flow reaches checkout
with WingPoint context riding in the URL, but pre-existing accounts may carry
none of the markers above (created before attribution existed, or via admin).
`wp_ref_belongs_to_referrer()` closes that loop by checking the user's email
against the provisioning ledger (``external_provisions``) — the same ledger the
WingPoint provisioning email flow writes. This is server-verified: no client
payload can confer the WingPoint plan.
"""

import re
from typing import Any, Mapping, Optional

_WINGPOINT_CREATED_VIA = ("wingpoint_provision", "wingpoint_connect")

# WingPoint provisioning refs look like WP-XXXXXXXX-XXXX (uppercase A-Z0-9).
_WP_REF_RE = re.compile(r"^WP-[A-Z0-9]{8}-[A-Z0-9]{4}$", re.IGNORECASE)


def normalize_wp_ref(value: Any) -> Optional[str]:
    """Return a clean WingPoint ref, or None if malformed/missing.

    Accepts URL-decoded values from query params or Stripe metadata. Returns
    the canonical uppercase form. Never trusts a value that doesn't match the
    provisioning-ref shape — those are not WingPoint attribution ids.
    """
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not _WP_REF_RE.match(v):
        return None
    return v.upper()


def is_wingpoint_user(user_doc: Optional[Mapping[str, Any]]) -> bool:
    """Return True if the user document identifies a WingPoint customer.

    Safe on None / empty documents — returns False.
    """
    if not user_doc:
        return False

    if user_doc.get("wp_ref"):
        return True
    if user_doc.get("source") == "wingpoint":
        return True

    created_via = user_doc.get("created_via")
    if created_via in _WINGPOINT_CREATED_VIA:
        return True

    return False


async def wp_ref_belongs_to_referrer(db, user_id: str, wp_ref: str) -> bool:
    """True if `wp_ref` verifiably belongs to this user in the provision ledger.

    Server-side proof that a checkout-time `wp_ref` is genuine: the WingPoint
    provisioning flow (POST /external/provision-trustoffice) records every
    referral as an external_provisions doc keyed by wingpoint_ref + user_id.
    An attacker cannot forge membership without a ledger row; legitimate
    members always have one when they were provisioned from WingPoint.
    """
    ref = normalize_wp_ref(wp_ref)
    if not ref or not user_id:
        return False
    doc = await db.external_provisions.find_one(
        {"wingpoint_ref": ref, "user_id": user_id},
        {"_id": 1},
    )
    return bool(doc)