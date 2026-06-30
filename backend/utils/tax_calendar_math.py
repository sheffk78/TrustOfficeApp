"""Pure tax-calendar date math. No database, no FastAPI imports."""
from datetime import date, timedelta
import calendar

CALENDAR_RULES = [
    {"deadline_type": "federal_1041",          "month": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","month": 9,  "day": 15, "desc": "Form 1041 — Extended filing deadline"},
    {"deadline_type": "k1_beneficiaries",      "month": 3,  "day": 15, "desc": "Schedule K-1 — Beneficiary income allocations"},
    {"deadline_type": "estimated_q1",          "month": 4,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "month": 6,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "month": 9,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "month": 1,  "day": 15, "desc": "Q4 Estimated tax payment (due following year)"},
]

FISCAL_RULES = [
    {"deadline_type": "federal_1041",          "months_after": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","months_after": 10, "day": 15, "desc": "Form 1041 — Extended filing deadline"},
    {"deadline_type": "k1_beneficiaries",      "months_after": 4,  "day": 15, "desc": "Schedule K-1 — Beneficiary income allocations"},
    {"deadline_type": "estimated_q1",          "fy_month_offset": 3,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "fy_month_offset": 5,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "fy_month_offset": 8,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "fy_month_offset": 11, "day": 15, "desc": "Q4 Estimated tax payment"},
]


def _clamp_day(year: int, month: int, day: int) -> int:
    """Clamp day to the last valid day of the month (handles Feb, leap years)."""
    last = calendar.monthrange(year, month)[1]
    return min(day, last)


def _fy_start(tax_year: int, fy_month: int, fy_day: int) -> date:
    """First day of the fiscal year that ends in `tax_year`."""
    effective_day = _clamp_day(tax_year, fy_month, fy_day)
    year_end = date(tax_year, fy_month, effective_day)
    # FY starts the day after the PREVIOUS year-end
    prev_year = tax_year - 1
    prev_effective_day = _clamp_day(prev_year, fy_month, fy_day)
    prev_year_end = date(prev_year, fy_month, prev_effective_day)
    return prev_year_end + timedelta(days=1)

def _month_delta(base: date, months: int) -> date:
    """Add/subtract months from a date, clamping to last day if needed."""
    m = base.month + months
    y = base.year
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    d = _clamp_day(y, m, base.day)
    return date(y, m, d)


def _calendar_due_date(tax_year: int, month: int, day: int) -> date:
    """Handle Q4 which may spill into next calendar year."""
    if month == 1:
        return date(tax_year + 1, month, day)
    return date(tax_year, month, day)


def _generate_entries(trust: dict, tax_year: int) -> list:
    """Generate deadline entries based on trust's tax year configuration."""
    entries = []
    from datetime import datetime, timezone  # local import to keep this module light
    now = datetime.now(timezone.utc).isoformat()

    is_fiscal = trust.get("is_fiscal_year") is True
    fy_month = trust.get("tax_year_end_month")
    fy_day_raw = trust.get("tax_year_end_day")

    if is_fiscal and fy_month and fy_day_raw:
        fy_day = _clamp_day(tax_year, fy_month, fy_day_raw)
        year_end = date(tax_year, fy_month, fy_day)
        fy_start = _fy_start(tax_year, fy_month, fy_day)

        for rule in FISCAL_RULES:
            if "fy_month_offset" in rule:
                due = _month_delta(fy_start, rule["fy_month_offset"])
                due = due.replace(day=_clamp_day(due.year, due.month, rule["day"]))
            else:
                due = _month_delta(year_end, rule["months_after"])
                due = due.replace(day=_clamp_day(due.year, due.month, rule["day"]))

            entries.append({
                "entry_id": f"tax_{_mock_uuid()}",
                "trust_id": trust["trust_id"],
                "tax_year": tax_year,
                "deadline_type": rule["deadline_type"],
                "due_date": due.isoformat(),
                "filing_status": "pending",
                "filed_date": None,
                "description": rule["desc"],
                "notes": None,
                "accountant_engaged": False,
                "created_at": now,
                "updated_at": now,
            })
    else:
        for rule in CALENDAR_RULES:
            due = _calendar_due_date(tax_year, rule["month"], rule["day"])
            entries.append({
                "entry_id": f"tax_{_mock_uuid()}",
                "trust_id": trust["trust_id"],
                "tax_year": tax_year,
                "deadline_type": rule["deadline_type"],
                "due_date": due.isoformat(),
                "filing_status": "pending",
                "filed_date": None,
                "description": rule["desc"],
                "notes": None,
                "accountant_engaged": False,
                "created_at": now,
                "updated_at": now,
            })

    return entries


def _days_remaining(due_date_str: str) -> int:
    """Calculate days remaining until a due date. Returns negative if past."""
    from datetime import datetime, timezone
    try:
        if isinstance(due_date_str, str):
            due = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        else:
            return 999
        now = datetime.now(timezone.utc)
        delta = due - now
        return max(-999, delta.days)
    except (ValueError, TypeError, AttributeError):
        return 999


def _mock_uuid():
    """Deterministic uuid for tests."""
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]
