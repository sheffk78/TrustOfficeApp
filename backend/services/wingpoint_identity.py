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
"""

from typing import Any, Mapping, Optional

_WINGPOINT_CREATED_VIA = ("wingpoint_provision", "wingpoint_connect")


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