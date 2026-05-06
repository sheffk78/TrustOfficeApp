"""Tests for tax calendar fiscal-year deadline math.

Verifies that:
- Calendar-year trusts get the right fixed dates
- Fiscal-year trusts get dates offset from their FY start/year-end
- Estimated taxes land on the 15th of the 4th/6th/9th/12th fiscal months
- 1041/K-1 land ~3.5 months after year-end
- Extension lands 6 months after original due date
- Leap-year February is handled correctly
- Q4 estimated tax for fiscal years ending before Dec 15 doesn't spill into next calendar year incorrectly
"""
import pytest
from datetime import date
from utils.tax_calendar_math import (
    _generate_entries,
    _fy_start,
    _month_delta,
    _clamp_day,
    FISCAL_RULES,
    CALENDAR_RULES,
)


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
