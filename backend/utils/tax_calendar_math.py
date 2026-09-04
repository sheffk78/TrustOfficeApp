"""Pure tax-calendar date math. No database, no FastAPI imports."""
from datetime import date, timedelta
import calendar

CALENDAR_RULES = [
    {"deadline_type": "federal_1041",          "month": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","month": 9,  "day": 30, "desc": "Form 1041 — Extended filing deadline (5.5-month extension via Form 7004)"},
    {"deadline_type": "k1_beneficiaries",      "month": 4,  "day": 15, "desc": "Schedule K-1 — Filed with Form 1041"},
    {"deadline_type": "estimated_q1",          "month": 4,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "month": 6,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "month": 9,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "month": 1,  "day": 15, "desc": "Q4 Estimated tax payment (due following year)"},
]

FISCAL_RULES = [
    {"deadline_type": "federal_1041",          "months_after": 4,  "day": 15, "desc": "Form 1041 — Estate and Trust Income Tax Return"},
    {"deadline_type": "federal_1041_extension","months_after": 9, "day": 30, "desc": "Form 1041 — Extended filing deadline (5.5-month extension via Form 7004)"},
    {"deadline_type": "k1_beneficiaries",      "months_after": 4,  "day": 15, "desc": "Schedule K-1 — Filed with Form 1041"},
    {"deadline_type": "estimated_q1",          "fy_month_offset": 3,  "day": 15, "desc": "Q1 Estimated tax payment"},
    {"deadline_type": "estimated_q2",          "fy_month_offset": 5,  "day": 15, "desc": "Q2 Estimated tax payment"},
    {"deadline_type": "estimated_q3",          "fy_month_offset": 8,  "day": 15, "desc": "Q3 Estimated tax payment"},
    {"deadline_type": "estimated_q4",          "fy_month_offset": 11, "day": 15, "desc": "Q4 Estimated tax payment"},
]

# Tax filing applicability by trust tax status (benevolence mode).
# Tax-exempt organizations do not file fiduciary income tax returns (Form 1041),
# Schedule K-1s, or federal estimated tax payments:
#   - "508": Church/religious organization — tax-exempt by statute with NO IRS
#     filing requirement (no Form 990 obligation). Nothing is generated.
#   - "501c3": Tax-exempt organization that files Form 990 (informational return,
#     not an income tax return) — income-tax deadlines are skipped; a Form 990
#     deadline is generated instead.
#   - "private": Default (private/family trust) — full fiduciary filing calendar.
# Deadline types listed here are SKIPPED for that tax status.
TAX_STATUS_SKIP_DEADLINES = {
    "508": {
        "federal_1041", "federal_1041_extension", "k1_beneficiaries",
        "estimated_q1", "estimated_q2", "estimated_q3", "estimated_q4",
    },
    "501c3": {
        "federal_1041", "federal_1041_extension", "k1_beneficiaries",
        "estimated_q1", "estimated_q2", "estimated_q3", "estimated_q4",
    },
}

# Extra deadlines generated only for specific tax statuses.
TAX_STATUS_EXTRA_RULES = {
    "501c3": [
        {"deadline_type": "form_990",          "month": 5,  "day": 15, "desc": "Form 990 — Return of Organization Exempt From Income Tax"},
    ],
    # Form 990 fiscal-year rule: 15th day of the 5th month after year-end.
    "501c3_fiscal": [
        {"deadline_type": "form_990",          "months_after": 5, "day": 15, "desc": "Form 990 — Return of Organization Exempt From Income Tax"},
    ],
}


# Income-tax deadline types (fiduciary income tax). Never applicable to
# tax-exempt organizations (508, 501c3) — filtered from all read paths so
# legacy entries generated before tax-status gating are also hidden.
INCOME_TAX_DEADLINE_TYPES = {
    "federal_1041", "federal_1041_extension", "k1_beneficiaries",
    "estimated_q1", "estimated_q2", "estimated_q3", "estimated_q4",
}


def is_tax_exempt(trust: dict) -> bool:
    """True if the trust's tax_status is a tax-exempt organization (508, 501c3)."""
    return (trust.get("tax_status") or "private").lower() in ("508", "501c3")


def filter_income_tax_entries(entries: list, trust: dict) -> list:
    """Drop income-tax deadline entries for tax-exempt trusts; pass through otherwise."""
    if not is_tax_exempt(trust):
        return entries
    return [e for e in entries if e.get("deadline_type") not in INCOME_TAX_DEADLINE_TYPES]


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
    """Generate deadline entries based on trust's tax year configuration.

    Deadline applicability is filtered by the trust's tax_status: tax-exempt
    statuses (508, 501c3) skip fiduciary income-tax deadlines entirely; 501c3
    additionally gets a Form 990 informational-return deadline.
    """
    entries = []
    from datetime import datetime, timezone  # local import to keep this module light
    now = datetime.now(timezone.utc).isoformat()

    is_fiscal = trust.get("is_fiscal_year") is True
    fy_month = trust.get("tax_year_end_month")
    fy_day_raw = trust.get("tax_year_end_day")
    tax_status = (trust.get("tax_status") or "private").lower()
    skip = TAX_STATUS_SKIP_DEADLINES.get(tax_status, set())

    def _entry(rule: dict) -> dict:
        return {
            "entry_id": f"tax_{_mock_uuid()}",
            "trust_id": trust["trust_id"],
            "tax_year": tax_year,
            "deadline_type": rule["deadline_type"],
            "due_date": rule["due"],
            "filing_status": "pending",
            "filed_date": None,
            "description": rule["desc"],
            "notes": None,
            "accountant_engaged": False,
            "created_at": now,
            "updated_at": now,
        }

    if is_fiscal and fy_month and fy_day_raw:
        fy_day = _clamp_day(tax_year, fy_month, fy_day_raw)
        year_end = date(tax_year, fy_month, fy_day)
        fy_start = _fy_start(tax_year, fy_month, fy_day)

        for rule in FISCAL_RULES:
            if rule["deadline_type"] in skip:
                continue
            if "fy_month_offset" in rule:
                due = _month_delta(fy_start, rule["fy_month_offset"])
                due = due.replace(day=_clamp_day(due.year, due.month, rule["day"]))
            else:
                due = _month_delta(year_end, rule["months_after"])
                due = due.replace(day=_clamp_day(due.year, due.month, rule["day"]))
            entries.append(_entry({"deadline_type": rule["deadline_type"], "due": due.isoformat(), "desc": rule["desc"]}))

        # Status-specific extras for fiscal-year trusts (e.g. Form 990).
        for rule in TAX_STATUS_EXTRA_RULES.get(f"{tax_status}_fiscal", []):
            due = _month_delta(year_end, rule["months_after"])
            due = due.replace(day=_clamp_day(due.year, due.month, rule["day"]))
            entries.append(_entry({"deadline_type": rule["deadline_type"], "due": due.isoformat(), "desc": rule["desc"]}))
    else:
        for rule in CALENDAR_RULES:
            if rule["deadline_type"] in skip:
                continue
            due = _calendar_due_date(tax_year, rule["month"], rule["day"])
            entries.append(_entry({"deadline_type": rule["deadline_type"], "due": due.isoformat(), "desc": rule["desc"]}))

        # Status-specific extras for calendar-year trusts (e.g. Form 990).
        for rule in TAX_STATUS_EXTRA_RULES.get(tax_status, []):
            due = _calendar_due_date(tax_year, rule["month"], rule["day"])
            entries.append(_entry({"deadline_type": rule["deadline_type"], "due": due.isoformat(), "desc": rule["desc"]}))

    return entries


def _days_remaining(due_date_str: str) -> int:
    """Calculate days remaining until a due date. Returns negative if past.

    Date-only strings (e.g. '2025-04-15') are treated as calendar dates,
    not midnight UTC timestamps. This prevents a deadline due today from
    showing as overdue before the day ends in the user's timezone.
    TO-003b fix.
    """
    from datetime import date, datetime, timezone
    try:
        if isinstance(due_date_str, str):
            parsed = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            # If the string is date-only (no time component), compare as date vs today
            if 'T' not in due_date_str and ':' not in due_date_str:
                today = date.today()
                due_date_only = parsed.date()
                return max(-999, (due_date_only - today).days)
            # Full datetime: compare as before
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = parsed - now
            return max(-999, delta.days)
        else:
            return 999
    except (ValueError, TypeError, AttributeError):
        return 999


def _seed_tax_year(today: date | None = None) -> int:
    """Determine the tax year to seed for a trust created today.

    Trusts created in October or later should seed *next* calendar year
    deadlines so that no deadline appears already overdue.
    """
    today = today or date.today()
    if today.month >= 10:
        return today.year + 1
    return today.year


def _mock_uuid():
    """Deterministic uuid for tests."""
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]
