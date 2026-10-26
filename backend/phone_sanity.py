"""Phone sanity check for lead intake.

 Kenneth calls phone leads immediately (Call-now Discord ping). Junk numbers
 typed into lead forms (sequential sweeps, repeated digits, placeholder
 patterns) must not trigger a call ping — the lead stays email-only and the
 nurture pipeline continues.

 2026-10-26: Rhonda (Meta lead ad) submitted +12345678910 (typed sequentially),
 Kenneth flagged it mid-call-attempt. Root cause was the submitter, not the
 pipeline — this filter keeps the same class of junk from pinging again.
"""

import re
from typing import Optional

# Explicit placeholder/movie digits (555-01XX is the reserved fictitious range).
_PLACEHOLDER_PATTERNS = (
    re.compile(r"55501\d\d"),
)


def _digit_runs(digits: str) -> bool:
    """True if digits contain an ascending or descending consecutive run of >= 5."""
    n = len(digits)
    for size in range(5, n + 1):
        for start in range(0, n - size + 1):
            window = digits[start:start + size]
            vals = [int(c) for c in window]
            if all(b - a == 1 for a, b in zip(vals, vals[1:])):
                return True
            if all(a - b == 1 for a, b in zip(vals, vals[1:])):
                return True
    return False


def _repeated_run(digits: str, min_len: int = 6) -> bool:
    """True if any single digit repeats consecutively >= min_len times
    (1000000000's nine zeros, 1-445-555-5555's six 5s, ...)."""
    run = 1
    for a, b in zip(digits, digits[1:]):
        run = run + 1 if a == b else 1
        if run >= min_len:
            return True
    return False


def is_calling_quality(phone: Optional[str]) -> bool:
    """True when a phone number looks like a real, callable line.

    Format validation (allowed characters, length) is _normalize_phone's job;
    this is the plausibility layer: it catches numbers that parse fine but are
    obviously typed junk. Conservative by design — real numbers essentially
    never contain a 5+ digit monotonic run or repeated-digit blocks.
    """
    if not phone:
        return False
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7 or len(digits) > 15:
        return False
    # All same digit (0000000000, 1111111111, ...)
    if len(set(digits)) == 1:
        return False
    # One digit dominating (1000000000, 4455555555, ...)
    if _repeated_run(digits):
        return False
    # Sequential sweeps, anywhere in the number (123..., ...9876)
    if _digit_runs(digits):
        return False
    for pat in _PLACEHOLDER_PATTERNS:
        if pat.search(digits):
            return False
    return True