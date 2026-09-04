"""Tests for tax calendar fiscal-year deadline math.

Verifies that:
- Calendar-year trusts get the right fixed dates
- Fiscal-year trusts get dates offset from their FY start/year-end
- Estimated taxes land on the 15th of the 4th/6th/9th/12th fiscal months
- 1041/K-1 land ~3.5 months after year-end
- Extension lands 6 months after original due date
- Late-season trust creation (month >= 10) seeds next-year deadlines
- Leap-year February is handled correctly
- Q4 estimated tax for fiscal years ending before Dec 15 doesn't spill into next calendar year incorrectly
"""
import pytest
from datetime import date
from utils.tax_calendar_math import (
    _generate_entries,
    _seed_tax_year,
    _fy_start,
    _month_delta,
    _clamp_day,
    FISCAL_RULES,
    CALENDAR_RULES,
)


class TestSeedTaxYear:
    """Tests for _seed_tax_year — the month>=10 rule for late-season trust creation."""

    def test_november_returns_next_year(self):
        assert _seed_tax_year(date(2026, 11, 15)) == 2027

    def test_december_returns_next_year(self):
        assert _seed_tax_year(date(2026, 12, 31)) == 2027

    def test_october_1_returns_next_year(self):
        """Boundary: Oct 1 is the first day that triggers next-year seeding."""
        assert _seed_tax_year(date(2026, 10, 1)) == 2027

    def test_september_30_returns_same_year(self):
        """Just before the boundary — still same year."""
        assert _seed_tax_year(date(2026, 9, 30)) == 2026

    def test_january_returns_same_year(self):
        assert _seed_tax_year(date(2026, 1, 15)) == 2026

    def test_july_returns_same_year(self):
        assert _seed_tax_year(date(2026, 7, 4)) == 2026

    def test_default_none_uses_today(self):
        """When today=None, uses date.today() — exercise code path only."""
        result = _seed_tax_year()  # today=None branch hits date.today()
        assert isinstance(result, int)
        assert result in (2026, 2027, 2028)  # must be a plausible near-year


class TestLateSeasonSeededDeadlinesAreNotPast:
    """Verify that seeding with next-year produces no instantly-overdue deadlines."""

    def test_nov_seeded_calendar_deadlines_all_future(self):
        """A trust created Nov 15 2026 gets 2027 deadlines — all are in the future."""
        trust = {"trust_id": "t1", "is_fiscal_year": False}
        entries = _generate_entries(trust, _seed_tax_year(date(2026, 11, 15)))
        for e in entries:
            assert e["due_date"] >= "2027-01-01", f"Deadline {e['due_date']} is in the past"

    def test_oct_seeded_calendar_deadlines_all_future(self):
        """A trust created Oct 1 2026 gets 2027 deadlines — all are in the future."""
        trust = {"trust_id": "t1", "is_fiscal_year": False}
        entries = _generate_entries(trust, _seed_tax_year(date(2026, 10, 1)))
        for e in entries:
            assert e["due_date"] >= "2027-01-01", f"Deadline {e['due_date']} is in the past"


class TestClampDay:
    def test_february_normal_year(self):
        assert _clamp_day(2025, 2, 29) == 28

    def test_february_leap_year(self):
        assert _clamp_day(2024, 2, 29) == 29
        assert _clamp_day(2024, 2, 30) == 29

    def test_31_day_month(self):
        assert _clamp_day(2025, 3, 31) == 31
        assert _clamp_day(2025, 3, 32) == 31

    def test_30_day_month(self):
        assert _clamp_day(2025, 4, 31) == 30


class TestFyStart:
    def test_calendar_year_default(self):
        # FY ends Dec 31 => starts Jan 1
        assert _fy_start(2025, 12, 31) == date(2025, 1, 1)

    def test_june_30_fiscal(self):
        # FY ends June 30, 2025 => starts July 1, 2024
        assert _fy_start(2025, 6, 30) == date(2024, 7, 1)

    def test_sept_30_fiscal(self):
        # FY ends Sept 30, 2025 => starts Oct 1, 2024
        assert _fy_start(2025, 9, 30) == date(2024, 10, 1)

    def test_leap_year_feb_29(self):
        # FY ends Feb 29, 2024 (leap year) => starts March 1, 2023
        assert _fy_start(2024, 2, 29) == date(2023, 3, 1)


class TestMonthDelta:
    def test_add_months_same_year(self):
        base = date(2025, 6, 15)
        assert _month_delta(base, 3) == date(2025, 9, 15)

    def test_add_months_year_rollover(self):
        base = date(2025, 10, 15)
        assert _month_delta(base, 4) == date(2026, 2, 15)

    def test_clamp_to_last_day(self):
        base = date(2025, 1, 31)
        # Feb has 28 days in 2025
        assert _month_delta(base, 1) == date(2025, 2, 28)

    def test_leap_year_february(self):
        base = date(2024, 1, 31)
        assert _month_delta(base, 1) == date(2024, 2, 29)


class TestCalendarYearEntries:
    def test_generates_7_entries(self):
        trust = {"trust_id": "t1", "is_fiscal_year": False}
        entries = _generate_entries(trust, 2025)
        assert len(entries) == 7
        types = {e["deadline_type"] for e in entries}
        assert types == {
            "federal_1041", "federal_1041_extension", "k1_beneficiaries",
            "estimated_q1", "estimated_q2", "estimated_q3", "estimated_q4",
        }

    def test_1041_due_april_15(self):
        trust = {"trust_id": "t1", "is_fiscal_year": False}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "federal_1041")
        assert e["due_date"] == "2025-04-15"

    def test_estimated_q4_january_15_next_year(self):
        trust = {"trust_id": "t1", "is_fiscal_year": False}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "estimated_q4")
        # Q4 for 2025 calendar year is due Jan 15, 2026
        assert e["due_date"] == "2026-01-15"

    def test_k1_march_15(self):
        trust = {"trust_id": "t1", "is_fiscal_year": False}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "k1_beneficiaries")
        assert e["due_date"] == "2025-03-15"


class TestFiscalYearEntries:
    def test_june_30_fy_1041(self):
        """FY ends June 30: 1041 due 3.5 months later = Oct 15"""
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 6, "tax_year_end_day": 30}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "federal_1041")
        assert e["due_date"] == "2025-10-15"

    def test_june_30_fy_extension(self):
        """Extension: 6 months from original due = April 15"""
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 6, "tax_year_end_day": 30}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "federal_1041_extension")
        assert e["due_date"] == "2026-04-15"

    def test_june_30_fy_estimated_q1(self):
        """FY starts July 1. Q1 estimated = 15th of 4th month = Oct 15"""
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 6, "tax_year_end_day": 30}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "estimated_q1")
        assert e["due_date"] == "2024-10-15"

    def test_june_30_fy_estimated_q4(self):
        """Q4 estimated = 15th of 12th month = June 15"""
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 6, "tax_year_end_day": 30}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "estimated_q4")
        assert e["due_date"] == "2025-06-15"

    def test_sept_30_fy_1041(self):
        """FY ends Sept 30: 1041 due Jan 15"""
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 9, "tax_year_end_day": 30}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "federal_1041")
        assert e["due_date"] == "2026-01-15"

    def test_sept_30_fy_estimated_q1(self):
        """FY starts Oct 1. Q1 = 15th of 4th month = Jan 15"""
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 9, "tax_year_end_day": 30}
        entries = _generate_entries(trust, 2025)
        e = next(e for e in entries if e["deadline_type"] == "estimated_q1")
        assert e["due_date"] == "2025-01-15"

    def test_feb_28_fy_leap_year(self):
        """FY ends Feb 28 (non-leap). Make sure Feb 29 isn't generated."""
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 2, "tax_year_end_day": 28}
        entries = _generate_entries(trust, 2025)
        # FY starts March 1, 2024. Extension = 10 months after year-end = Dec 28.
        e = next(e for e in entries if e["deadline_type"] == "federal_1041_extension")
        assert "-02-29" not in e["due_date"]  # Should never happen in 2025


class TestEntryMetadata:
    def test_all_entries_have_required_fields(self):
        trust = {"trust_id": "t1", "is_fiscal_year": True, "tax_year_end_month": 6, "tax_year_end_day": 30}
        entries = _generate_entries(trust, 2025)
        for e in entries:
            assert e["trust_id"] == "t1"
            assert e["tax_year"] == 2025
            assert e["filing_status"] == "pending"
            assert e["entry_id"].startswith("tax_")
            assert "deadline_type" in e
            assert "due_date" in e
            assert "description" in e

class TestTaxStatusGating:
    """Tax-status gating — tax-exempt trusts don't generate income-tax deadlines.

    508 (church/religious, tax exempt): generates NOTHING.
    501c3 (tax-exempt org): skips income-tax deadlines, gets Form 990 instead.
    private / default: full fiduciary calendar (unchanged).
    """

    def test_508_generates_nothing(self):
        entries = _generate_entries({"trust_id": "t1", "tax_status": "508"}, 2026)
        assert entries == []

    def test_508_fiscal_generates_nothing(self):
        entries = _generate_entries(
            {"trust_id": "t1", "tax_status": "508", "is_fiscal_year": True,
             "tax_year_end_month": 6, "tax_year_end_day": 30}, 2026)
        assert entries == []

    def test_501c3_gets_only_form_990(self):
        entries = _generate_entries({"trust_id": "t1", "tax_status": "501c3"}, 2026)
        assert [e["deadline_type"] for e in entries] == ["form_990"]
        assert entries[0]["due_date"] == "2026-05-15"

    def test_501c3_fiscal_form_990_five_months_after_fy_end(self):
        entries = _generate_entries(
            {"trust_id": "t1", "tax_status": "501c3", "is_fiscal_year": True,
             "tax_year_end_month": 6, "tax_year_end_day": 30}, 2026)
        assert [e["deadline_type"] for e in entries] == ["form_990"]
        # 15th day of 5th month after June 30 = Nov 15.
        assert entries[0]["due_date"] == "2026-11-15"

    def test_private_keeps_full_calendar(self):
        entries = _generate_entries({"trust_id": "t1", "tax_status": "private"}, 2026)
        types = {e["deadline_type"] for e in entries}
        assert types == {"federal_1041", "federal_1041_extension", "k1_beneficiaries",
                         "estimated_q1", "estimated_q2", "estimated_q3", "estimated_q4"}

    def test_missing_tax_status_defaults_to_private(self):
        entries = _generate_entries({"trust_id": "t1"}, 2026)
        assert len(entries) == 7


class TestExemptReadPathFilter:
    """filter_income_tax_entries hides legacy income-tax entries for exempt trusts."""

    def test_filters_1041_for_508(self):
        from utils.tax_calendar_math import filter_income_tax_entries
        legacy = [
            {"deadline_type": "federal_1041", "due_date": "2025-04-15"},
            {"deadline_type": "form_990", "due_date": "2026-05-15"},
        ]
        out = filter_income_tax_entries(legacy, {"tax_status": "508"})
        assert [e["deadline_type"] for e in out] == ["form_990"]

    def test_passes_through_for_private(self):
        from utils.tax_calendar_math import filter_income_tax_entries
        legacy = [{"deadline_type": "federal_1041"}]
        out = filter_income_tax_entries(legacy, {"tax_status": "private"})
        assert out == legacy

    def test_missing_trust_status_passes_through(self):
        from utils.tax_calendar_math import filter_income_tax_entries
        legacy = [{"deadline_type": "federal_1041"}]
        out = filter_income_tax_entries(legacy, {})
        assert out == legacy


class TestBenevolenceExemption:
    """Benevolence (508c3) trusts are tax-exempt — no deadlines generated."""

    def test_benevolence_calendar_year_returns_empty(self):
        trust = {"trust_id": "t1", "is_fiscal_year": False, "benevolence_enabled": True}
        assert _generate_entries(trust, 2025) == []

    def test_benevolence_fiscal_year_returns_empty(self):
        trust = {
            "trust_id": "t1", "is_fiscal_year": True,
            "tax_year_end_month": 6, "tax_year_end_day": 30,
            "benevolence_enabled": True,
        }
        assert _generate_entries(trust, 2025) == []

    def test_non_benevolence_unaffected(self):
        trust = {"trust_id": "t1", "is_fiscal_year": False, "benevolence_enabled": False}
        entries = _generate_entries(trust, 2025)
        assert len(entries) == len(CALENDAR_RULES)

    def test_missing_flag_defaults_to_generate(self):
        """Trusts without the benevolence_enabled field keep current behavior."""
        trust = {"trust_id": "t1", "is_fiscal_year": False}
        entries = _generate_entries(trust, 2025)
        assert len(entries) == len(CALENDAR_RULES)

    def test_benevolence_with_501c3_status_still_generates_990(self):
        """Benevolence + explicit 501c3 tax_status: Form 990 applies (per-status refinement)."""
        trust = {"trust_id": "t1", "is_fiscal_year": False, "benevolence_enabled": True, "tax_status": "501c3"}
        entries = _generate_entries(trust, 2025)
        assert [e["deadline_type"] for e in entries] == ["form_990"]
