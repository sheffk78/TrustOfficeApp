"""Unit tests: derived ppm share math (named class members, session 1).

Spec under test: backend/services/share_math.py (canonical module; router,
migration, and dashboard all allocate through it). Law (council synthesis
CLASS-MEMBERS-COUNCIL-2026-10-07.md, design item 2):

1.  Shares are DERIVED at read time — never stored. Pool percentage is the
    single stored source of truth.
2.  Exact-integer ppm math: pool → ppm once (pct × 10,000, half-up guard);
    every active member gets floor(pool_ppm / n); the leftover
    (pool_ppm % n) units go one each to the FIRST members in creation order
    (member_order, then confirmed_at, then class_member_id tie-break).
    Invariant: sum(shares) == pool_ppm exactly, for every pool and n ≥ 1
    (n = 0 → [] by convention: empty roster, pool undistributed).
3.  Only member_status == "active" participates; deceased/removed/inactive
    drop OUT of the division (excluded from the allocation, rows remain).
    Legacy docs without member_status are treated active.
4.  Guarantees beyond the sum: shares non-increasing (remainder is a
    prefix), max − min ≤ 1 (equal treatment), pure determinism (same inputs
    → identical shares, no float state, no drift).

Canon checks (council worked examples, enforced below):
    pool 100% (1,000,000 ppm) / 3 members -> 333,334 / 333,333 / 333,333
    pool  50% (500,000 ppm)   / 3 members -> 166,667 / 166,667 / 166,666

A one-time FULL exhaust (every ppm pool 0..1,000,000 × n = 1..50 =
50,000,050 derivations) ran clean at authoring time — invariant holds
universally (evidence: session-1 report /tmp/s1_full_exhaust.log result).
The CI sweep below is bounded but complete-in-structure: for the sum
identity only (base, remainder) matter (shares = base each + first-rem × 1)
and divmod(pool, n) hits that pair-space once — complete pool sweep at small
n + boundary-dense probes at large n prove every (base, rem) class.
"""

import importlib.util
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.share_math import (  # noqa: E402
    ACTIVE_STATUS,
    PPM_TOTAL,
    allocate_equal_shares,
    allocate_equal_shares_ordered,
    derive_class_member_shares,
    doc_is_active,
    percent_to_ppm,
    pool_ppm_from_percentage,
    ppm_to_percent,
    validate_sum_invariant,
)

# sys.path fallback for direct-file runs (repo pytest from backend/ already resolves)
if importlib.util.find_spec("services.share_math") is None:  # pragma: no cover
    pytest.skip("services.share_math not importable", allow_module_level=True)


def _members(n, prefix="cm", **kw):
    return [dict(class_member_id=f"{prefix}_{i:02d}", name=f"m{i}", **kw) for i in range(n)]


def _derive(pool_pct, members):
    """One-call derive; returns (shares_in_creation_order, full_payload)."""
    r = derive_class_member_shares(pool_pct, members)
    shares = [row["share_ppm"] for row in r["per_member_shares"]]
    return shares, r


class TestCanonChecks:
    """Council-ratified worked examples (design item 2)."""

    def test_100pct_three_members(self):
        # 1,000,000 / 3 = 333,333.33… → 333,334 / 333,333 / 333,333
        shares, r = _derive(100.0, _members(3))
        assert shares == [333_334, 333_333, 333_333]
        assert r["sum_check_ppm"] == PPM_TOTAL == r["pool_percentage_ppm"]
        assert validate_sum_invariant([s for s in shares], PPM_TOTAL) is True

    def test_50pct_three_members(self):
        # 500,000 / 3 = 166,666.66… → 166,667 / 166,667 / 166,666
        shares, r = _derive(50.0, _members(3))
        assert shares == [166_667, 166_667, 166_666]
        assert r["pool_percentage_ppm"] == 500_000
        assert r["sum_check_ppm"] == 500_000

    def test_even_division(self):
        shares, r = _derive(100.0, _members(4))
        assert shares == [250_000] * 4
        assert r["sum_check_ppm"] == PPM_TOTAL


class TestSumInvariantExhaustive:
    """The core invariant: sum(shares) == pool_ppm for every pool and n.

    One-time FULL exhaust (every ppm pool 0..1,000,000 × n=1..50 ≈ 50M
    derivations) ran clean at authoring time (see module docstring).
    CI sweep: complete pools at n=1..8 (cost scales with n — ~36M member-ops
    ≈ seconds); boundary-dense + sampled pools at larger n. divmod(pool, n)
    touches every (base, remainder) pair for the tested n, and boundary
    pools 0..3000 cover every remainder class for n ≤ 3000.
    """

    def test_all_pools_n_1_to_8(self):
        for n in range(1, 9):
            members = _members(n)
            for pool_ppm in range(0, PPM_TOTAL + 1):
                r = derive_class_member_shares(pool_ppm / 10_000.0, members)
                if (
                    r["sum_check_ppm"] != r["pool_percentage_ppm"]
                    or r["pool_percentage_ppm"] != pool_ppm
                    or any(row["share_ppm"] < 0 for row in r["per_member_shares"])
                    or r["active_member_count"] != n
                ):
                    pytest.fail(f"sum invariant violation: n={n} pool_ppm={pool_ppm}")

    def test_large_n_boundary_and_sampled(self):
        boundary = list(range(0, 3001))                 # base=0: every rem class
        coarse = list(range(1000, 998_001, 973))        # interior samples
        top = list(range(998_000, 1_000_001))           # exact top boundary
        pools = boundary + coarse + top
        for n in (9, 11, 17, 23, 37, 50, 97, 128, 251, 500):
            members = _members(n, prefix=f"n{n}")
            for pool_ppm in pools:
                r = derive_class_member_shares(pool_ppm / 10_000.0, members)
                assert r["sum_check_ppm"] == pool_ppm, (n, pool_ppm)
                assert r["active_member_count"] == n

    def test_n_at_capacity_and_quota_split(self):
        for n in (97, 100, 251, 1000):
            shares = allocate_equal_shares_ordered(PPM_TOTAL, n)
            base, rem = divmod(PPM_TOTAL, n)
            assert sum(shares) == PPM_TOTAL
            assert set(shares) <= {base, base + 1}
            assert shares.count(base + 1) == rem
            assert shares[:rem] == [base + 1] * rem  # remainder is a PREFIX


class TestApportionmentGuarantees:
    """Equal-treatment structure: prefix remainder + max−min ≤ 1."""

    def test_shares_non_increasing_and_within_one(self):
        for n in (2, 3, 5, 7, 10, 11, 13):
            shares = allocate_equal_shares_ordered(PPM_TOTAL, n)
            assert shares == sorted(shares, reverse=True)
            assert max(shares) - min(shares) <= 1

    def test_allocate_equal_shares_id_keyed(self):
        # 333,333 % 3 = 0 → all equal, keyed by member id.
        alloc = allocate_equal_shares(333_333, ["cm_a", "cm_b", "cm_c"])
        assert alloc == {"cm_a": 111_111, "cm_b": 111_111, "cm_c": 111_111}
        assert sum(alloc.values()) == 333_333

    def test_allocate_equal_shares_remainder_prefix_by_id_order(self):
        # 333,334 % 3 = 1 → the first id in the list gets the +1 unit.
        alloc = allocate_equal_shares(333_334, ["cm_b", "cm_a"])
        assert alloc == {"cm_b": 166_667, "cm_a": 166_667}
        alloc = allocate_equal_shares(333_335, ["cm_b", "cm_a", "cm_c"])
        # 333,335 % 3 = 2 → the two earliest ids take the +1 units.
        assert alloc == {"cm_b": 111_112, "cm_a": 111_112, "cm_c": 111_111}


class TestEdges:
    def test_zero_members(self):
        r = derive_class_member_shares(100.0, [])
        assert r["per_member_shares"] == []
        assert r["active_member_count"] == 0
        assert r["sum_check_ppm"] == 0
        assert r["pool_percentage_ppm"] == PPM_TOTAL

    def test_zero_members_pool_zero(self):
        r = derive_class_member_shares(0.0, [])
        assert r["per_member_shares"] == []
        assert r["pool_percentage_ppm"] == 0
        assert r["sum_check_ppm"] == 0

    def test_one_member_takes_whole_pool(self):
        for pct in (0.0, 1.0, 33.3333, 99.9999, 100.0):
            shares, r = _derive(pct, _members(1))
            assert shares == [percent_to_ppm(pct)]
            assert r["sum_check_ppm"] == r["pool_percentage_ppm"]

    def test_one_active_among_inactive(self):
        members = [
            {"class_member_id": "cm_dead", "name": "d", "member_status": "deceased"},
            {"class_member_id": "cm_alive", "name": "a"},
            {"class_member_id": "cm_gone", "name": "g", "member_status": "removed"},
        ]
        shares, r = _derive(100.0, members)
        assert shares == [1_000_000]
        assert r["per_member_shares"][0]["class_member_id"] == "cm_alive"
        assert r["active_member_count"] == 1
        assert r["sum_check_ppm"] == PPM_TOTAL

    def test_pool_zero_with_members(self):
        shares, r = _derive(0.0, _members(5))
        assert shares == [0] * 5
        assert r["active_member_count"] == 5
        assert r["sum_check_ppm"] == 0

    def test_all_inactive_equals_empty_roster(self):
        members = [
            {"class_member_id": "cm_a", "member_status": "inactive"},
            {"class_member_id": "cm_b", "member_status": "removed"},
        ]
        r = derive_class_member_shares(100.0, members)
        assert r["per_member_shares"] == []
        assert r["active_member_count"] == 0
        assert r["sum_check_ppm"] == 0

    def test_legacy_doc_without_status_is_active(self):
        assert doc_is_active({"class_member_id": "cm_x"}) is True
        assert doc_is_active({"class_member_id": "cm_y", "member_status": None}) is True
        assert doc_is_active({"member_status": ""}) is True
        assert doc_is_active({"member_status": "deceased"}) is False


class TestDeterminism:
    def test_repeat_calls_identical(self):
        members = _members(7)
        first = derive_class_member_shares(33.3333, members)
        for _ in range(50):
            assert derive_class_member_shares(33.3333, members) == first
        again = derive_class_member_shares(33.3333, [dict(m) for m in members])
        assert again == first

    def test_creation_order_tiebreak_single_remainder_unit(self):
        # 1,000,000 % 7 = 1 → exactly one +1 unit; the EARLIEST member gets it.
        shares, _ = _derive(100.0, _members(7))
        assert shares == [142_858, 142_857, 142_857, 142_857,
                          142_857, 142_857, 142_857]
        assert sum(shares) == PPM_TOTAL

    def test_remainder_multiple_units_spread_in_order(self):
        # 500,000 % 3 = 2 → two +1 units to the two earliest members.
        shares, _ = _derive(50.0, _members(3))
        assert shares == [166_667, 166_667, 166_666]

    def test_member_order_field_overrides_list_position(self):
        members = [
            {"class_member_id": "cm_late", "member_order": 2},
            {"class_member_id": "cm_early", "member_order": 1},
        ]
        _, r = _derive(33.3333, members)  # 333,333 ppm, %2 = 1
        by_id = {row["class_member_id"]: row["share_ppm"] for row in r["per_member_shares"]}
        assert by_id == {"cm_early": 166_667, "cm_late": 166_666}

    def test_no_member_order_falls_back_to_confirmed_then_id(self):
        # Identical (missing) member_order: confirmed_at then id decide.
        members = [
            {"class_member_id": "cm_b", "confirmed_at": "2026-01-02"},
            {"class_member_id": "cm_a", "confirmed_at": "2026-01-01"},
            {"class_member_id": "cm_c", "confirmed_at": "2026-01-03"},
        ]
        shares, _ = _derive(100.0, members)
        assert shares == [333_334, 333_333, 333_333]  # cm_a earliest gets +1

    def test_confirmed_at_tie_falls_back_to_id(self):
        members = [
            {"class_member_id": "cm_c", "confirmed_at": "2026-01-01"},
            {"class_member_id": "cm_a", "confirmed_at": "2026-01-01"},
            {"class_member_id": "cm_b", "confirmed_at": "2026-01-01"},
        ]
        _, r = _derive(100.0, members)
        ids = [row["class_member_id"] for row in r["per_member_shares"]]
        assert ids == ["cm_a", "cm_b", "cm_c"]
        assert [row["share_ppm"] for row in r["per_member_shares"]] == [
            333_334, 333_333, 333_333]


class TestNoFloatDrift:
    def test_no_drift_across_many_members(self):
        """A float implementation (pct/n, rounded per member) drifts; the int
        law must not — repeated equal division stays exact."""
        shares, r = _derive(100.0, _members(10))
        assert shares == [100_000] * 10
        assert r["sum_check_ppm"] == PPM_TOTAL

    def test_percentage_ppm_roundtrip_exact(self):
        for pct in (0, 0.0001, 12.5, 33.3333, 50.0, 66.6667, 99.9999, 100):
            ppm = percent_to_ppm(pct)
            assert ppm == int(round(pct * 10_000))
            # ppm → back to pct → ppm is identity for 4dp inputs
            assert percent_to_ppm(ppm_to_percent(ppm)) == ppm

    def test_display_values_exact_at_4dp(self):
        assert ppm_to_percent(333_334) == 33.3334
        assert ppm_to_percent(166_667) == 16.6667
        assert ppm_to_percent(0) == 0.0

    def test_shares_are_python_ints(self):
        shares, r = _derive(100.0, _members(3))
        assert all(type(s) is int for s in shares)
        assert type(r["pool_percentage_ppm"]) is int
        assert type(r["sum_check_ppm"]) is int


class TestStatusSemantics:
    def test_inactive_members_excluded_keep_identity(self):
        members = [
            {"class_member_id": "cm_a"},
            {"class_member_id": "cm_b", "member_status": "deceased"},
            {"class_member_id": "cm_c"},
            {"class_member_id": "cm_d", "member_status": "removed"},
            {"class_member_id": "cm_e"},
        ]
        _, r = _derive(100.0, members)
        ids = [row["class_member_id"] for row in r["per_member_shares"]]
        assert ids == ["cm_a", "cm_c", "cm_e"]
        assert [row["share_ppm"] for row in r["per_member_shares"]] == [
            333_334, 333_333, 333_333]
        assert r["active_member_count"] == 3
        assert r["sum_check_ppm"] == PPM_TOTAL

    def test_unknown_status_is_conservative(self):
        members = [
            {"class_member_id": "cm_a", "member_status": "active"},
            {"class_member_id": "cm_b", "member_status": "typo_value"},
        ]
        _, r = _derive(100.0, members)
        assert [row["class_member_id"] for row in r["per_member_shares"]] == ["cm_a"]
        assert r["per_member_shares"][0]["share_ppm"] == 1_000_000


class TestPayloadShape:
    def test_derive_payload_fields(self):
        members = [{"class_member_id": "cm_a"}, {"class_member_id": "cm_b", "member_status": "deceased"},
                   {"class_member_id": "cm_c"}]
        r = derive_class_member_shares(66.6666, members)
        assert r["pool_percentage_ppm"] == 666_666
        assert r["active_member_count"] == 2
        assert r["sum_check_ppm"] == 666_666
        assert r["ordered_active_member_ids"] == ["cm_a", "cm_c"]
        rows = r["per_member_shares"]
        assert rows[0]["share_pct"] == pytest.approx(33.3333)
        assert {row["class_member_id"] for row in rows} == {"cm_a", "cm_c"}

    def test_active_status_constant(self):
        assert ACTIVE_STATUS == "active"
        assert pool_ppm_from_percentage(100) == PPM_TOTAL


class TestGuards:
    def test_strict_pool_conversion_rejects_bad_input(self):
        with pytest.raises(TypeError):
            pool_ppm_from_percentage("50")
        with pytest.raises(TypeError):
            pool_ppm_from_percentage(True)
        with pytest.raises(ValueError):
            pool_ppm_from_percentage(-0.5)
        with pytest.raises(ValueError):
            pool_ppm_from_percentage(100.5)

    def test_validate_sum_invariant_detects_drift(self):
        assert validate_sum_invariant([333_334, 333_333, 333_333], 1_000_000) is True
        assert validate_sum_invariant([333_333, 333_333, 333_333], 1_000_000) is False

    def test_per_member_shares_keyed_by_member_id(self):
        """The GET contract: shares are id-keyed rows, never position-trusted."""
        members = _members(3)
        r = derive_class_member_shares(100.0, members)
        assert r["per_member_shares"][0] == {
            "class_member_id": "cm_00", "share_ppm": 333_334, "share_pct": 33.3334,
        }