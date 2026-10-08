# Compat shim: bare `import share_math` → canonical backend/services/share_math.py
"""Compatibility import shim.

2026-10-07 (session 1, named class members): the share-math module exists
once, canonically, at ``backend/services/share_math.py`` — imported that way
by the read-side tests (tests/test_class_share_math.py). This root-level
module keeps the pre-unification call sites working unchanged:

    backend/routers/beneficiaries.py          (import share_math)
    backend/tests/test_share_math.py          (import share_math as sm)
    backend/tests/test_migrate_class_member_shares.py
    backend/scripts/migrate_class_member_shares.py

Every symbol is re-exported verbatim from the canonical module; only the
import path differs. New code: import services.share_math.
"""
from services.share_math import *  # noqa: F401,F403
from services.share_math import (  # noqa: F401  (explicit for linters/IDEs)
    ACTIVE_STATUS,
    MEMBER_STATUSES,
    PPM_HALF,
    PPM_PER_PERCENT,
    PPM_TOTAL,
    active_member_docs,
    allocate_equal_shares,
    allocate_equal_shares_ordered,
    cap_check_ppm,
    compute_member_share_ppm,
    derive_class_member_shares,
    doc_is_active,
    largest_remainder_share_ppm,
    member_sort_key,
    percent_to_ppm,
    pool_ppm_from_percentage,
    pool_ppm_to_display,
    ppm_to_percent,
    share_display_pct,
    share_preview_ppm,
    shares_sum_check,
    shares_sum_ppm,
    sort_members_in_creation_order,
    validate_sum_invariant,
)