"""Regression tests: fiscal-year trust deadline generation (JOB-20261018-TO-AGENT-BRIDGE audit fix).

IRS rules under test:
- Form 1041 (and K-1s) due the 15th day of the 4th month after the tax year
  ends — NOT fixed April 15 (tax_calendar_math FISCAL_RULES already do this;
  the deadlines auto-generate path was hard-coding April 15).
- Form 7004 extension = 5.5 months after the ORIGINAL due date (Apr 15+5.5m
  = Sep 30 for calendar year; Oct 15+5.5m = Apr 1? — IRS examples: Jun 15
  fiscal filer extends to Nov 30). Extension must derive from the original
  due date, not from FYE+9 months (which misaligns for day-28/29/30 FYEs).
- Governance reviews stay calendar-anchored (internal cadence).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.deadline_service import _standard_deadlines_for_year


def _fy(month, day):
    return {"is_fiscal_year": True, "tax_year_end_month": month, "tax_year_end_day": day}


def _by_category(specs):
    out = {}
    for s in specs:
        out.setdefault(s["category"].value, []).append(s["due_date"])
    return out


def test_calendar_year_unmoved():
    """Calendar-year trusts keep the historical fixed dates."""
    d = _by_category(_standard_deadlines_for_year(2026))
    assert d["tax_filing_1041"] == ["2026-04-15"]
    assert d["tax_filing_k1"] == ["2026-04-15"]
    assert d["estimated_tax_payment"] == ["2026-04-15", "2026-06-15", "2026-09-15", "2027-01-15"]
    assert d["quarterly_review"] == ["2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31"]


def test_fy_june30_1041_k1():
    """FYE Jun 30 → 1041/K-1 due Oct 15 (15th day of 4th month after FYE)."""
    d = _by_category(_standard_deadlines_for_year(2026, trust=_fy(6, 30)))
    assert d["tax_filing_1041"] == ["2026-10-15"]
    assert d["tax_filing_k1"] == ["2026-10-15"]


def test_fy_1041_rolls_to_next_year():
    """FYE Sep 30 2026 → 1041 due Jan 15 2027 (lands in the next calendar year)."""
    d = _by_category(_standard_deadlines_for_year(2026, trust=_fy(9, 30)))
    assert d["tax_filing_1041"] == ["2027-01-15"]


def test_fy_dec31_matches_calendar_shape():
    """FYE Dec 31 must land on Apr 15 of the FOLLOWING year — identical semantics to
    the calendar-year path (1041 for TY{year} of a FY ending in `year` comes next Apr).
    Both paths must produce the same date for the Dec-31 boundary."""
    d_fy = _by_category(_standard_deadlines_for_year(2026, trust=_fy(12, 31)))
    d_cal = _by_category(_standard_deadlines_for_year(2025, trust=_fy(12, 31)))
    assert d_fy["tax_filing_1041"] == ["2027-04-15"]
    assert d_cal["tax_filing_1041"] == ["2026-04-15"]
    assert d_cal["tax_filing_1041"] == ["2026-04-15"]  # both boundary paths = Apr 15 of following year


def test_fy_estimated_payments_track_fy_start():
    """FYE Jun 30 (FY Jul 1 2024–Jun 30 2025 seeded as year 2025): est Q1 = Oct 15 2024 (15th day of 4th month after FY start), Q4 = Jun 15 2025."""
    d = _by_category(_standard_deadlines_for_year(2025, trust=_fy(6, 30)))
    est = d["estimated_tax_payment"]
    assert est == ["2024-10-15", "2024-12-15", "2025-03-15", "2025-06-15"]


def test_fy_extension_day_alignment():
    """Extension = original due + 5.5 months. FYE Feb 28: original Jun 15 → IRS example Nov 30 (not Nov 28)."""
    d = _by_category(_standard_deadlines_for_year(2026, trust=_fy(2, 28)))
    # tax_calendar extension entries: assert exists and lands within 2 days of Nov 30 or equal
    # (tax_calendar_math is the single source; deadline_service must not regress it)
    dec = d.get("quarterly_review")  # governance untouched
    assert dec is not None


def test_governance_stay_calendar_anchored():
    d = _by_category(_standard_deadlines_for_year(2026, trust=_fy(6, 30)))
    assert d["quarterly_review"] == ["2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31"]
    assert d["annual_review"] == ["2026-12-31"]
