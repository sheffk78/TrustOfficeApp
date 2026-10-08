"""
Pure share-math tests for named class members (backend/share_math.py).

Council-locked rules under test (CLASS-MEMBERS-COUNCIL-2026-10-07.md):
  - Integer ppm + largest-remainder apportionment, creation-order tie-break.
  - Invariant sum(member share ppm) == pool ppm — exact, always.
  - 100%/3 -> 33.3334 / 33.3333 / 33.3333 in member_order (council worked ex.)
  - Determinism: adding a member only dilutes (existing members' shares never
    increase); the remainder bump is always a prefix in creation order.
  - n=0 -> [] ; n=1 -> whole pool.
  - Display rounding to 4 decimals (ppm/10000 is exact at 4dp).

DB-free by suite convention (mirrors test_allocation_layer_totals.py):
no Mongo, no HTTP, no models import.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

# Ensure backend dir is importable regardless of pytest invocation cwd
_bd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _bd not in sys.path:
    sys.path.insert(0, os.path.abspath(_bd))

import share_math as sm


def _ids(n):
    return [f"cm_{i:02d}" for i in range(n)]


def _members(n, pool=None, status=None):
    """Roster of n members in creation order (member_order = rank)."""
    return [
        {"class_member_id": mid, "member_order": i, **({"member_status": status} if status else {})}
        for i, mid in enumerate(_ids(n))
    ]


# ==================== COUNCIL WORKED EXAMPLES ====================

def test_100_pct_split_three_members():
    """The exact council example: 100%/3 -> 33.3334/33.3333/33.3333 in order."""
    shares = sm.allocate_equal_shares_ordered(sm.pool_ppm_from_percentage(100), 3)
    assert shares == [333334, 333333, 333333]
    assert sum(shares) == sm.pool_ppm_from_percentage(100)


def test_100_pct_split_three_members_via_derive():
    """End-to-end: derive_class_member_shares reproduces the same triple."""
    out = sm.derive_class_member_shares(100, _members(3))
    assert [(s["class_member_id"], s["share_ppm"]) for s in out["per_member_shares"]] == [
        ("cm_00", 333334), ("cm_01", 333333), ("cm_02", 333333),
    ]
    assert out["pool_percentage_ppm"] == 1_000_000
    assert out["sum_check_ppm"] == 1_000_000
    assert out["active_member_count"] == 3


def test_100_pct_split_seven_members():
    shares = sm.allocate_equal_shares_ordered(1_000_000, 7)
    assert shares[0] == 142858
    assert all(s == 142857 for s in shares[1:])
    assert sum(shares) == 1_000_000


def test_50_pct_split_three_members_sums_exactly_50():
    """Council worked example: 50% class among 3 -> sums EXACTLY 50%."""
    pool_ppm = sm.pool_ppm_from_percentage(50)  # 500000
    shares = sm.allocate_equal_shares_ordered(pool_ppm, 3)
    assert shares == [166667, 166667, 166666]
    assert sum(shares) == 500_000
    assert sm.validate_sum_invariant(shares, pool_ppm)


def test_33_pct_split_sums_exactly_33():
    pool_ppm = sm.pool_ppm_from_percentage(33)  # 330000
    shares = sm.allocate_equal_shares_ordered(pool_ppm, 7)
    assert sum(shares) == 330_000
    display = [sm.share_display_pct(s) for s in shares]
    assert round(sum(display), 6) == 33.0


# ==================== SUM-INVARIANT SWEEP n=1..50 ====================

def test_sum_invariant_sweep_n_1_to_50():
    """Council MVP test: every pool {100%, 50%, 33%}, every n in 1..50."""
    for pct in (100, 50, 33):
        pool_ppm = sm.pool_ppm_from_percentage(pct)
        for n in range(1, 51):
            shares = sm.allocate_equal_shares_ordered(pool_ppm, n)
            assert sum(shares) == pool_ppm, (pct, n)
            assert sm.validate_sum_invariant(shares, pool_ppm)
            assert len(shares) == n
            assert max(shares) - min(shares) <= 1, (pct, n)
            assert shares == sorted(shares, reverse=True), (pct, n)


# ==================== DETERMINISM / ADD-MEMBER STABILITY ====================

def test_adding_member_never_increases_earlier_shares():
    """Determinism rule: adding a member only dilutes — an existing member's
    share never goes up; only the remainder distribution moves."""
    pool_ppm = sm.pool_ppm_from_percentage(100)
    for n in range(1, 50):
        before = sm.allocate_equal_shares_ordered(pool_ppm, n)
        after = sm.allocate_equal_shares_ordered(pool_ppm, n + 1)
        for i in range(n):
            assert after[i] <= before[i], (n, i, before, after)
        assert after[n] <= before[0]  # newcomer never outshares the first


def test_remainder_bump_is_always_a_creation_order_prefix():
    """Members receiving the +1 ppm remainder are always the FIRST r in
    creation order — never later members, whoever they are."""
    pool_ppm = sm.pool_ppm_from_percentage(100)
    for n in range(1, 51):
        shares = sm.allocate_equal_shares_ordered(pool_ppm, n)
        base, r = divmod(pool_ppm, n)
        for i, s in enumerate(shares):
            assert s == base + (1 if i < r else 0), (n, i, shares)


def test_pure_function_determinism_repeat_calls():
    """Same (pool, roster) twice -> byte-identical results, no hidden state."""
    members = _members(11)
    a = sm.derive_class_member_shares(100, members)
    b = sm.derive_class_member_shares(100, list(reversed(members)))
    # roster input order must not leak: creation order (member_order) decides
    assert a["per_member_shares"] == b["per_member_shares"]
    assert a["ordered_active_member_ids"] == b["ordered_active_member_ids"]


# ==================== EDGE CASES: n=0 / n=1 ====================

def test_zero_members_empty_roster():
    assert sm.allocate_equal_shares_ordered(1_000_000, 0) == []
    out = sm.derive_class_member_shares(100, [])
    assert out["per_member_shares"] == []
    assert out["active_member_count"] == 0
    assert out["sum_check_ppm"] == 0
    assert out["pool_percentage_ppm"] == 1_000_000  # pool intact, undistributed


def test_one_member_holds_entire_pool():
    assert sm.allocate_equal_shares_ordered(1_000_000, 1) == [1_000_000]
    assert sm.allocate_equal_shares_ordered(330_000, 1) == [330_000]
    out = sm.derive_class_member_shares(50, _members(1))
    assert out["per_member_shares"][0]["share_ppm"] == 500_000
    assert out["sum_check_ppm"] == 500_000


# ==================== DISPLAY ROUNDING ====================

def test_share_display_pct_4dp():
    assert sm.share_display_pct(333334) == 33.3334
    assert sm.share_display_pct(333333) == 33.3333
    assert sm.share_display_pct(500000) == 50.0
    assert sm.share_display_pct(142857) == 14.2857
    assert sm.share_display_pct(142858) == 14.2858
    assert sm.share_display_pct(83333) == 8.3333
    assert sm.share_display_pct(0) == 0.0


def test_display_pct_round_trip():
    for pct in (100, 50, 33.33, 12.5, 0.0001, 66.6667):
        ppm = sm.pool_ppm_from_percentage(pct)
        assert sm.share_display_pct(ppm) == round(pct, 4)


# ==================== POOL CONVERSION VALIDATION ====================

def test_pool_ppm_from_percentage_valid():
    assert sm.pool_ppm_from_percentage(100) == 1_000_000
    assert sm.pool_ppm_from_percentage(0) == 0
    assert sm.pool_ppm_from_percentage(50) == 500_000
    assert sm.pool_ppm_from_percentage(33) == 330_000


def test_pool_ppm_from_percentage_rejects_garbage():
    import pytest
    for bad in ("100", None, [50], {"p": 1}, True):
        try:
            sm.pool_ppm_from_percentage(bad)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(f"accepted {bad!r}")
    with pytest.raises(ValueError):
        sm.pool_ppm_from_percentage(-1)
    with pytest.raises(ValueError):
        sm.pool_ppm_from_percentage(100.0001)
    with pytest.raises(ValueError):
        sm.pool_ppm_from_percentage(101)


def test_pool_ppm_fractional_percent_rounds_half_up():
    assert sm.pool_ppm_from_percentage(0.00005) == 1  # half-up, never drifts down
    assert sm.pool_ppm_from_percentage(12.3456) == 123456


# ==================== MEMBER STATUS FILTERING ====================

def test_status_docs_drop_out_of_division_but_sum_holds():
    members = [
        {"class_member_id": "cm_a", "member_order": 0, "member_status": "active"},
        {"class_member_id": "cm_b", "member_order": 1, "member_status": "deceased"},
        {"class_member_id": "cm_c", "member_order": 2, "member_status": "removed"},
        {"class_member_id": "cm_d", "member_order": 3, "member_status": "inactive"},
    ]
    out = sm.derive_class_member_shares(100, members)
    assert out["active_member_count"] == 1
    assert out["per_member_shares"] == [
        {"class_member_id": "cm_a", "share_ppm": 1_000_000, "share_pct": 100.0}
    ]
    assert out["sum_check_ppm"] == out["pool_percentage_ppm"]


def test_legacy_doc_missing_status_treated_active():
    members = [
        {"class_member_id": "cm_legacy1", "confirmed_at": "2026-01-01T00:00:00+00:00"},
        {"class_member_id": "cm_legacy2", "confirmed_at": "2026-01-02T00:00:00+00:00"},
        {"class_member_id": "cm_x", "member_order": 99, "member_status": "removed"},
    ]
    out = sm.derive_class_member_shares(60, members)
    assert out["active_member_count"] == 2
    assert [s["share_ppm"] for s in out["per_member_shares"]] == [300000, 300000]


def test_unknown_status_not_active_conservative():
    assert sm.doc_is_active({"member_status": "banana"}) is False
    assert sm.doc_is_active({"member_status": "active"}) is True
    assert sm.doc_is_active({"member_status": None}) is True
    assert sm.doc_is_active({"member_status": ""}) is True
    assert sm.doc_is_active({}) is True


# ==================== CREATION-ORDER DETERMINISM ====================

def test_member_order_rank_decides_despite_input_order():
    members = [
        {"class_member_id": "cm_late", "member_order": 1},
        {"class_member_id": "cm_early", "member_order": 0},
    ]
    out = sm.derive_class_member_shares(100, members)
    # 100%/2 splits evenly, so assert on ordering, not values
    assert out["ordered_active_member_ids"] == ["cm_early", "cm_late"]


def test_legacy_fallback_confirmed_at_then_id_tiebreak():
    t = "2026-01-01T00:00:00+00:00"
    members = [
        {"class_member_id": "cm_fff", "confirmed_at": t},          # tie
        {"class_member_id": "cm_aaa", "confirmed_at": t},          # tie -> id wins
        {"class_member_id": "cm_older", "confirmed_at": "2025-12-31T00:00:00+00:00"},
    ]
    out = sm.derive_class_member_shares(30, members)
    assert out["ordered_active_member_ids"] == ["cm_older", "cm_aaa", "cm_fff"]
    # 300000/3 exact -> order does not change values, but keep the invariant
    assert out["sum_check_ppm"] == 300_000


def test_migrated_order_beats_legacy_row():
    members = [
        {"class_member_id": "cm_legacy", "confirmed_at": "2020-01-01T00:00:00+00:00"},
        {"class_member_id": "cm_migrated", "member_order": 5, "confirmed_at": "2026-01-01T00:00:00+00:00"},
    ]
    out = sm.derive_class_member_shares(100, members)
    assert out["ordered_active_member_ids"] == ["cm_migrated", "cm_legacy"]


# ==================== SIBLING-HELPERS (kept honest) ====================

def test_percent_to_ppm_round_trip_and_cap_check():
    assert sm.percent_to_ppm(33.33) == 333300
    assert sm.ppm_to_percent(333300) == 33.33
    assert sm.cap_check_ppm(600000, 400000, 500000) is True    # 60-40+50 = 70 <= 100
    assert sm.cap_check_ppm(600000, 100000, 400001) is True    # 90.0001 <= 100
    assert sm.cap_check_ppm(600000, 500000, 900001) is False   # 1000001 > 1000000
    # Boundary: exactly 100% passes, 100% + 1 ppm fails
    assert sm.cap_check_ppm(0, 0, 1_000_000) is True
    assert sm.cap_check_ppm(0, 0, 1_000_001) is False


def test_share_preview_ppm_stays_invariant():
    preview = sm.share_preview_ppm(1_000_000, 3, 4)
    assert preview["sum_check"] is True
    assert sum(preview["per_member_share_ppm_after"]) == 1_000_000
    assert sum(preview["per_member_share_ppm_before"]) == 1_000_000


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))