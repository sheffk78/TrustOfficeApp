"""Monthly AFR (Applicable Federal Rate) reference table — IRS Revenue Rulings.

Source: IRS revenue rulings publishing AFRs each month
(https://www.irs.gov/applicable-federal-rates). Table holds the ANNUAL
compounding AFR for each term bucket (IRC 1274(d) / 7872(e) buckets:
short-term ≤3yr, mid-term >3yr ≤9yr, long-term >9yr).

Update monthly — the build_loan_rate_clause lookup uses the latest rows.
Revue Ruling 2026-19 (October 2026 rates), extracted from
https://www.irs.gov/pub/irs-drop/rr-26-19.pdf.
"""
from datetime import datetime, timezone

# (month_key, short_term, mid_term, long_term, revenue_ruling)
AFR_TABLE = [
    ("2026-10", 4.25, 4.61, 5.22, "Rev. Rul. 2026-19"),
]


def _month_key(month_date: str | None) -> str:
    """Month of the loan → 'YYYY-MM'. Defaults to the current month (UTC)."""
    if not month_date:
        return datetime.now(timezone.utc).strftime("%Y-%m")
    # Accept '2026-10-15', 'October 2026', '10/2026', '2026/10' etc.
    s = str(month_date)
    if s[:4].isdigit() and len(s) >= 7:
        return f"{s[:4]}-{s[5:7]}"
    import re
    m = re.search(r"(\d{1,2})[/\-](\d{4})", s)          # 10/2026, 10-2026
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    # Month-name form: "October 2026" / "Oct 2026"
    ml = s.lower()
    for name, i in months.items():
        if name in ml:
            year = re.search(r"(\d{4})", s)
            return f"{year.group(1)}-{i:02d}" if year else ""
    return ""


months = {mon: i + 1 for i, mon in enumerate(
    ("january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"))}


def bucket_for(term_months) -> str:
    """IRC 1274(d) term bucket: short ≤36, mid ≤108, long >108."""
    try:
        t = int(term_months)
    except (TypeError, ValueError):
        t = 60
    if t <= 36:
        return "short"
    if t <= 108:
        return "mid"
    return "long"


def lookup_afr(term_months, month_date: str | None = None) -> tuple[str, str] | None:
    """AFR (annual compounding) for the loan's term bucket and month.

    Returns (rate_str, source_str) or None when the month is not in the table.
    """
    key = _month_key(month_date)
    for row in AFR_TABLE:
        if row[0] == key:
            idx = {"short": 1, "mid": 2, "long": 3}[bucket_for(term_months)]
            return f"{row[idx]:.2f}%", row[4]
    return None