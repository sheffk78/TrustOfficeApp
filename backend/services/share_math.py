"""
Pure integer share math for named class members (TrustOffice).

Council-locked design (CLASS-MEMBERS-COUNCIL-2026-10-07.md):
  - Per-member shares are DERIVED at read time — never stored per member.
  - The class pool percentage is the single stored source of truth.
  - Integer parts-per-million (ppm) math + largest-remainder apportionment
    with creation-order (member_order) tie-break.
  - Invariant: sum(member ppm) == pool ppm, enforced in code.

Functions here are pure (no I/O, no Mongo, no models) so they can be used by
routers, migrations, and tests interchangeably.
"""
from typing import List, Tuple

# 1,000,000 ppm == 100%. 4-decimal display (0.0001%) == 1 ppm.
PPM_PER_PERCENT = 10_000
PPM_TOTAL = 1_000_000
PPM_HALF = (PPM_TOTAL + 1) // 2  # rounds 0.5 ppm up


def percent_to_ppm(percent: float) -> int:
    """Convert a percent (e.g. 50.0) to integer ppm (500000). Round-half-up
    so 0.00005% edge cases never silently round down into drift."""
    return int(round(percent * PPM_PER_PERCENT + 1e-9))


def ppm_to_percent(ppm: int) -> float:
    """Convert integer ppm back to a 4-decimal percent display value."""
    return round(ppm / PPM_PER_PERCENT, 4)


def pool_ppm_to_display(ppm: int) -> float:
    """Alias kept explicit for template/UI math."""
    return ppm_to_percent(ppm)


def largest_remainder_share_ppm(pool_ppm: int, member_order: List[int]) -> List[int]:
    """
    Split pool_ppm across members so shares sum EXACTLY to pool_ppm.

    member_order: roster order (member_order field), index-aligned with output.
    Algorithm: floor(pool / n) for everyone, then hand the leftover ppm to the
    members with the largest positive remainders, tie-broken by roster order
    (creation-order tie-break per council design #2).
    """
    n = len(member_order)
    if n == 0:
        return []
    base = pool_ppm // n
    remainder = pool_ppm - base * n
    # remainder of a positive pool divided by n is always 0 <= r < n
    shares = [base] * n
    if remainder:
        # remainder = pool - n*base; distribute 'remainder' units, one each,
        # to the members whose fractional leftover (base) was cut shortest.
        # All members have identical base, so everyone has the same remainder
        # r/n > 0 — roster order (creation-order tie-break) decides.
        for i in range(remainder):
            shares[i % n] += 1
    return shares


def compute_member_share_ppm(pool_ppm: int, member_order: List[int], excluded_indexes: List[int] = None) -> List[Tuple[int, int]]:
    """
    Compute per-member shares. Members whose index is in excluded_indexes
    (deceased/removed/inactive) drop out of the division but stay in roster
    order for the remaining members. Returns [(index, share_ppm), ...] for
    included members only — index is the position in member_order.
    """
    excluded = set(excluded_indexes or [])
    included = [i for i in range(len(member_order)) if i not in excluded]
    orders = [member_order[i] for i in included]
    split = largest_remainder_share_ppm(pool_ppm, orders)
    return list(zip(included, split))


def shares_sum_check(pool_ppm: int, share_ppm_list: List[int]) -> bool:
    """Locked invariant: member shares must sum exactly to the pool."""
    return sum(share_ppm_list) == pool_ppm


def share_preview_ppm(pool_ppm: int, active_count_before: int, active_count_after: int) -> dict:
    """
    Before/after per-member share preview for an event API response.
    100%/3 members example: before 333333 each → after 250000 each (exact);
    odd splits use largest-remainder so sums stay pinned to the pool.
    """
    before_split = largest_remainder_share_ppm(pool_ppm, list(range(active_count_before)))
    after_split = largest_remainder_share_ppm(pool_ppm, list(range(active_count_after)))
    return {
        "pool_ppm": pool_ppm,
        "active_members_before": active_count_before,
        "active_members_after": active_count_after,
        "per_member_share_ppm_before": before_split,
        "per_member_share_ppm_after": after_split,
        "per_member_share_percent_before": [ppm_to_percent(p) for p in before_split],
        "per_member_share_percent_after": [ppm_to_percent(p) for p in after_split],
        "sum_check": shares_sum_check(pool_ppm, after_split),
    }


def cap_check_ppm(existing_pool_ppm: int, new_pool_ppm: int, other_class_pool_ppm: int) -> bool:
    """
    Same 100%-cap aggregate rule used on the create path: a trust's class
    pool percentages must total <= 100% (1,000,000 ppm).
    """
    return existing_pool_ppm - new_pool_ppm + other_class_pool_ppm <= PPM_TOTAL


# ====================================================================
# Creation-order roster + derived-share layer (build session 2026-10-07)
# Mirrors CLASS-MEMBERS-COUNCIL-2026-10-07.md § Locked Design:
# shares DERIVED from member_status-active members, never stored.
# ====================================================================

ACTIVE_STATUS = "active"
# Closed set for member_status; unknown non-empty values are treated as NOT
# active (conservative: a typo'd status must not silently inherit shares).
MEMBER_STATUSES = ("active", "deceased", "removed", "inactive")

# Sentinel that sorts legacy docs (no member_order) to the back of the
# creation-order key so their confirmed_at / class_member_id ranking applies.
_LEGACY_ORDER_SENTINEL = 1 << 53


def pool_ppm_from_percentage(percentage) -> int:
    """Percent (0..100) -> integer ppm, e.g. 50 -> 500000 (canonical name).

    Strict variant of percent_to_ppm: raises TypeError/ValueError on
    non-numeric or out-of-range input — callers shadow-store this value, so
    silent clamping is not acceptable.
    """
    if isinstance(percentage, bool) or not isinstance(percentage, (int, float)):
        raise TypeError(f"percentage must be a number, got {type(percentage).__name__}")
    pct = float(percentage)
    if pct < 0 or pct > 100:
        raise ValueError(f"percentage must be within 0..100, got {percentage}")
    return percent_to_ppm(pct)


def doc_is_active(member_doc) -> bool:
    """True when the member doc counts in the share division.

    Docs missing member_status (pre-migration legacy) count as active.
    """
    status = member_doc.get("member_status")
    if status is None or status == "":
        return True  # legacy doc — treated active
    return status == ACTIVE_STATUS


def active_member_docs(member_docs) -> list:
    """Filter a member list down to share-participating (active) docs."""
    return [doc for doc in member_docs if doc_is_active(doc)]


def member_sort_key(member_doc):
    """Creation-order sort key.

    Migrated docs carry member_order (creation rank) and sort by it first.
    Legacy docs without member_order rank by confirmed_at, then
    class_member_id — which reproduces the historical created_at order for
    existing rosters (confirmed_at == created_at on legacy inserts) and is
    fully deterministic on ties.
    """
    order = member_doc.get("member_order")
    if order is None:
        order = _LEGACY_ORDER_SENTINEL
    return (
        order,
        str(member_doc.get("confirmed_at") or ""),
        str(member_doc.get("class_member_id") or ""),
    )


def sort_members_in_creation_order(member_docs) -> list:
    """Deterministic creation order: member_order, then confirmed_at, then id."""
    return sorted(member_docs, key=member_sort_key)


def allocate_equal_shares_ordered(pool_ppm: int, n: int) -> List[int]:
    """n integer shares of pool_ppm, largest-remainder, ordered split.

    Thin validating wrapper over largest_remainder_share_ppm: every member
    gets base floor(pool_ppm / n) and the first r = pool_ppm % n members
    (creation order) each get +1 ppm. Guarantees:

      sum(shares) == pool_ppm            (exact, integers)
      max(shares) - min(shares) <= 1     (equal treatment)
      shares is non-increasing           (remainder is a prefix)

    n = 0 -> []         (empty roster: pool undistributed)
    n = 1 -> [pool_ppm] (sole member holds the entire pool)
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    if pool_ppm < 0:
        raise ValueError(f"pool_ppm must be >= 0, got {pool_ppm}")
    return largest_remainder_share_ppm(pool_ppm, list(range(n)))


def allocate_equal_shares(pool_ppm: int, ordered_member_ids) -> dict:
    """Same apportionment, keyed by member id (input order = creation order)."""
    shares = allocate_equal_shares_ordered(pool_ppm, len(ordered_member_ids))
    return dict(zip(ordered_member_ids, shares))


def share_display_pct(share_ppm: int) -> float:
    """ppm -> percent rounded to 4 decimals for display, 333334 -> 33.3334.

    ppm/10000 has at most 4 decimals, so this rounding is exact — the sum of
    displayed shares can differ from the displayed pool only by float repr
    dust, never by real rounding error.
    """
    return ppm_to_percent(share_ppm)


def shares_sum_ppm(share_ppms) -> int:
    """Exact integer sum of member share ppms (the sum-check value)."""
    return sum(int(s) for s in share_ppms)


def validate_sum_invariant(share_ppms, pool_ppm: int) -> bool:
    """True iff the member shares still sum exactly to the pool."""
    return shares_sum_check(pool_ppm, [int(s) for s in share_ppms])


def derive_class_member_shares(pool_percentage, member_docs) -> dict:
    """One call the read-side endpoints share (GET .../members + dashboard).

    Takes the class pool percentage and the raw member docs, and returns the
    computed share block:

      per_member_shares          [{class_member_id, share_ppm, share_pct}]
                                 for ACTIVE members in creation order
      active_member_count        len(per_member_shares)
      pool_percentage_ppm        integer shadow of the pool percentage
      sum_check_ppm              sum of member ppms — MUST equal
                                 pool_percentage_ppm
      ordered_active_member_ids  ids in creation order (test/debug aid)

    Legacy docs missing member_status are treated active. n = 0 yields an
    empty shares list with the pool intact (undistributed pool).
    """
    pool_ppm = pool_ppm_from_percentage(pool_percentage)
    ordered_active = [
        doc for doc in sort_members_in_creation_order(member_docs) if doc_is_active(doc)
    ]
    ordered_ids = [doc.get("class_member_id") for doc in ordered_active]
    alloc = allocate_equal_shares(pool_ppm, ordered_ids)
    per_member_shares = [
        {
            "class_member_id": mid,
            "share_ppm": alloc[mid],
            "share_pct": share_display_pct(alloc[mid]),
        }
        for mid in ordered_ids
    ]
    return {
        "per_member_shares": per_member_shares,
        "active_member_count": len(ordered_active),
        "pool_percentage_ppm": pool_ppm,
        "sum_check_ppm": shares_sum_ppm(alloc.values()),
        "ordered_active_member_ids": ordered_ids,
    }