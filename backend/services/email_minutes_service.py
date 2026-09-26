# Email→Minutes service (W3, Jeff priority 4, 2026-09-25)
# Trustee emails meeting notes to {slug}@minutes.trustoffice.app (or forwards an
# existing thread) → pure extraction builds a MinutesDraftRequest → AI drafts
# minutes → saved as a DRAFT record for trustee review. Never auto-finalizes.
#
# Pure functions only — no DB, no AI calls — so the extraction logic is unit
# testable without mocks.
import re
from datetime import datetime, timezone
from typing import List, Optional


MINUTES_TYPES = ("annual", "quarterly", "distribution", "compensation", "solvency", "special")

# Keywords that signal which minutes type the email describes. Ordered — first
# match wins, strongest signal first.
_TYPE_SIGNALS = [
    ("quarterly", ("quarter", "q1 ", "q2 ", "q3 ", "q4 ")),
    ("annual", ("annual", "yearly", "year-end", "year end")),
    ("distribution", ("distribut", "payout", "disburse")),
    ("compensation", ("compensation", "trustee fee", "fee payment")),
    ("solvency", ("solvency", "solvency determination")),
]

_DATE_PATTERNS = [
    # ISO: 2026-09-25 / 2026-09-25T14:30
    (r"\b(20\d{2})-(\d{1,2})-(\d{1,2})", "%Y-%m-%d"),
    # Long: September 25, 2026 / Sept 25, 2026
    (r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})", None),
    # Numeric: 9/25/2026 or 9-25-2026 (US ordering)
    (r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", None),
]

_RE_LINE_NOISE = re.compile(r"^(>+\s*|\s*)$")


def extract_meeting_signal(email_text: str) -> dict:
    """Extract minutes-type, meeting date, participants, decisions from email text.

    Returns a dict with keys: minutes_type, meeting_date (ISO or None),
    participants (list), decisions (list). Never raises — worst case it
    returns empty signals and the caller falls back to generic 'special'.
    """
    text = email_text or ""
    minutes_type = _detect_type(text)
    meeting_date = _detect_date(text)
    participants = _detect_participants(text)
    decisions = _detect_decisions(text)
    return {
        "minutes_type": minutes_type,
        "meeting_date": meeting_date,
        "participants": participants,
        "decisions": decisions,
    }


def _detect_type(text: str) -> str:
    low = " " + text.lower() + " "
    for mtype, signals in _TYPE_SIGNALS:
        for sig in signals:
            if sig in low:
                return mtype
    return "special"


def _detect_date(text: str) -> Optional[str]:
    # 1) ISO
    m = re.search(_DATE_PATTERNS[0][0], text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc).date().isoformat()
        except ValueError:
            pass
    # 2) Long form
    m = re.search(_DATE_PATTERNS[1][0], text)
    if m:
        month = m.group(1)
        day = int(m.group(2))
        year = int(m.group(3))
        iso = _month_name_to_iso(month, day, year)
        if iso:
            return iso
    # 3) US numeric
    m = re.search(_DATE_PATTERNS[2][0], text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)), tzinfo=timezone.utc).date().isoformat()
        except ValueError:
            pass
    return None


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_name_to_iso(month: str, day: int, year: int) -> Optional[str]:
    n = _MONTHS.get(month.lower())
    if not n:
        return None
    try:
        return datetime(year, n, day, tzinfo=timezone.utc).date().isoformat()
    except ValueError:
        return None


def _detect_participants(text: str) -> List[str]:
    """Look for a Participants/Present/Attendees line, else fall back to
    email From line names. Returns names (not emails) where possible."""
    participants = []
    for marker in ("participants", "present:", "attendees", "in attendance"):
        idx = text.lower().find(marker)
        if idx >= 0:
            # take the same line (and following comma/semicolon-separated lines
            # until a blank line or a line ending in ':' + newline)
            chunk = text[idx + len(marker):].lstrip(":").splitlines()
            for line in chunk[:4]:
                line = line.strip()
                if not line:
                    if participants:
                        break
                    continue
                parts = [p.strip(" -•,") for p in re.split(r"[,;]|\band\b", line) if p.strip(" -•,")]
                if parts:
                    participants.extend(parts)
                if participants:
                    break
            break
    # dedupe preserving order, cap at 12
    seen = set()
    out = []
    for p in participants:
        key = p.lower()
        if key not in seen and len(p) <= 60:
            seen.add(key)
            out.append(p)
    return out[:12]


def _detect_decisions(text: str) -> List[str]:
    """Pull bullet/numbered lines and lines containing decision verbs.
    Cap at 20 items, 300 chars each."""
    decisions = []
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if _RE_LINE_NOISE.match(stripped):
            continue
        # bullet / numbered / mid-sentence "Resolved:" style lines — the
        # RESOLVED: prefix itself is dropped so only the decision text remains
        m = re.match(r"^(?:[-•*]|\d+[\).]|.*?\bRESOLVED:|.*?\bResolved:)\s*(.+)$", stripped, re.IGNORECASE)
        if m:
            item = m.group(1).strip()
        elif re.match(r"^(decisions?|approved|agreed)\b", stripped, re.IGNORECASE):
            item = stripped
        else:
            continue
        item = re.sub(r"^(?:RESOLVED:\s*)+", "", item, flags=re.IGNORECASE).strip()
        item = item[:300]
        if item and item.lower() not in {d.lower() for d in decisions}:
            decisions.append(item)
        if len(decisions) >= 20:
            break
    return decisions


def thread_key(subject: str, message_id: str, references: str = "") -> str:
    """Stable thread key: prefer normalized subject (strip Re:/Fwd: prefixes)."""
    norm = re.sub(r"^\s*((re|fwd|fw)\s*:\s*)+", "", subject or "", flags=re.IGNORECASE).strip().lower()
    if norm in ("", "(no subject)"):
        norm = ""
    return norm or (references or message_id or "")


def is_sender_allowed(sender_email: str, allowed_emails: List[str]) -> bool:
    """Case-insensitive allowlist check on the From address."""
    if not sender_email or not allowed_emails:
        return False
    sender = sender_email.strip().lower()
    return sender in {a.strip().lower() for a in allowed_emails if a}