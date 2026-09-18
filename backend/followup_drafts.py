"""
followup_drafts.py — Note-aware booking-link follow-up drafts for TrustOffice leads.

2026-09-15 (Jeff directive, #trustoffice-main): a button in the admin lead
detail view that drafts a booking-link email to the lead. The draft derives
from Jeff's notes on the lead, so a note like "left a voicemail" or "talked
about the revocable trust" shapes the copy:

  - Voicemail note  -> "I just left you a voicemail a minute ago..."
  - Call note       -> "Good talking with you..." (+ paraphrased topic)
  - No-answer note  -> "I tried you by phone a little earlier..."
  - Always includes the booking link (trustoffice.app/book-a-call)
  - Always includes source attribution ("you came in through one of our
    ads on Facebook") so the lead knows how we got their information.

SAFETY RULE: note text is NEVER interpolated into the email. Only
whitelisted topic phrases derived from pattern matches appear. Raw note
content stays in the admin UI (chips), out of the email body.

Pure functions only — no framework imports. Testable in isolation
(backend/tests/test_followup_drafts.py).
"""

from html import escape
import re
from typing import Any, Dict, List, Optional

BOOKING_URL = "https://trustoffice.app/book-a-call"

# Inline paragraph styles — 2026-09-15 (Jeff): "is the text being pushed together
# as a jumble?" Outlook and some clients strip default <p> margins, collapsing
# everything into a wall of text. Every paragraph carries its own spacing so the
# email reads as clean, separated paragraphs in every client.
_P_STYLE = 'style="margin:0 0 14px 0;color:#1a1a2e;font-size:15px;line-height:1.6;"'
_P_MUTED = 'style="margin:16px 0 20px 0;color:#64748b;font-size:13px;line-height:1.5;"'
_P_SIGN = 'style="margin:0;color:#1a1a2e;font-size:15px;"'

# ── Note signal patterns ────────────────────────────────────────────────────
# Order of checks matters; first hit wins for the primary signal.
_VM_RE = re.compile(
    r"\bvoicemail\b|\bv-?mail\b|left a (?:message|voicemail)|\bvm\b", re.I
)
_NOANSWER_RE = re.compile(
    r"no answer|didn'?t (?:answer|pick(?:\s?up)?)|did not answer|no pick-?up|"
    r"missed (?:the )?call|unreachable|no response (?:by|to) phone",
    re.I,
)
_CALL_RE = re.compile(
    r"\bcall(?:ed)?\b|\bspoke\b|\btalked\b|\bphone\b|\bchat(?:ted)?\b|"
    r"\bconversation\b|\bconnected\b",
    re.I,
)
_TEXT_RE = re.compile(r"\btext(?:ed)?\b|\bsms\b", re.I)
_EMAIL_RE = re.compile(r"\be-?mail(?:ed)?\b", re.I)
_OBJECTION_RE = re.compile(
    r"\bprice\b|\bcost(?:ly)?\b|\bexpensive\b|\btoo much\b|\bbudget\b|\bafford\b|"
    r"\bskeptic(?:al)?\b|\bdoubt|\bnot sure\b|\bbusy\b|\bno time\b|\bmaybe later\b|\bthinking about it\b",
    re.I,
)

# ── Topic phrases (whitelisted — these exact strings are the only note-derived
#    text that may enter an email body) ──────────────────────────────────────
# Ordered: specific before generic. "minutes" is handled specially because the
# word "minute" appears in ordinary notes ("voicemail 5 minutes ago").
_TOPICS: List[tuple] = [
    (re.compile(r"revocable", re.I), "your revocable living trust"),
    (re.compile(r"irrevocable", re.I), "irrevocable trust options"),
    (re.compile(r"special needs", re.I), "special needs planning"),
    (re.compile(r"asset protection|lawsuit|litigation", re.I), "asset protection"),
    (re.compile(r"\bprobate\b", re.I), "keeping assets out of probate"),
    (re.compile(r"\bsuccessor\b|\btrustee\b|\btrust-?ee duties\b", re.I), "your role as trustee"),
    (re.compile(r"\bhems\b|\bdistribut(?:ion|e|ions|es|ed|ing)\b", re.I), "trust distributions (HEMS)"),
    (re.compile(r"\bestate\b", re.I), "your estate plan"),
    (re.compile(r"\btax(?:es|ation)?\b", re.I), "tax considerations for your trust"),
]

_MINUTES_RE = re.compile(r"\bminutes?\b", re.I)
_MINUTES_AGO_RE = re.compile(r"minutes? (?:ago|later|earlier)|a minute (?:ago|later|earlier)", re.I)
_TRUST_RE = re.compile(r"\btrust\b", re.I)


def _topic_phrases(note_text: str) -> List[str]:
    """Return whitelisted topic phrases mentioned in a note (deduped, ordered)."""
    phrases: List[str] = []
    for rx, phrase in _TOPICS:
        if rx.search(note_text) and phrase not in phrases:
            phrases.append(phrase)
    # "minutes" only counts when tied to trust minutes, not "5 minutes ago"
    if (
        _MINUTES_RE.search(note_text)
        and _TRUST_RE.search(note_text)
        and not _MINUTES_AGO_RE.search(note_text)
        and "trust minutes" not in phrases
    ):
        phrases.append("trust minutes")
    return phrases



def _sort_key(note: Dict[str, Any]) -> str:
    """Normalize created_at to a sortable ISO string.

    lead_activities stores created_at as string (2305 rows) AND BSON date (32 rows);
    Python's sorted() crashes comparing datetime vs str ('<' not supported).
    """
    from datetime import datetime, timezone

    v = note.get("created_at")
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    if isinstance(v, str) and v.strip():
        return v
    return ""


def classify_notes(notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Scan notes (any order) and return detected signals.

    Returns {"signal": str, "topics": [str], "objection": bool, "notes_used": [str]}.
    Priority: voicemail > no_answer > call > text > email > general.
    """
    notes = sorted(
        [n for n in (notes or []) if (n.get("content") or "").strip()],
        key=_sort_key,
        reverse=True,  # newest first
    )
    signal = "general"
    topics: List[str] = []
    objection = False
    notes_used: List[str] = []

    for note in notes:
        text = note.get("content") or ""
        notes_used.append(text.strip())
        for ph in _topic_phrases(text):
            if ph not in topics:
                topics.append(ph)
        if signal == "general":
            if _VM_RE.search(text):
                signal = "voicemail"
            elif _NOANSWER_RE.search(text):
                signal = "no_answer"
            elif _CALL_RE.search(text):
                signal = "call"
            elif _TEXT_RE.search(text):
                signal = "text"
            elif _EMAIL_RE.search(text):
                signal = "email"

    objection = any(_OBJECTION_RE.search(n) for n in notes_used)
    return {
        "signal": signal,
        "topics": topics[:3],  # cap: email stays short
        "objection": objection,
        "notes_used": notes_used[:5],
    }


def _source_phrase(lead: Dict[str, Any]) -> str:
    """Map the lead's capture source to the attribution phrase Jeff asked for
    (so the lead knows how we got their information — Facebook/Meta ads etc.)."""
    s = ((lead.get("origin_source") or lead.get("source") or "") or "").lower()
    utm = (lead.get("utm_source") or "").lower()
    if "facebook" in s or "facebook" in utm or "meta" in s or s == "fb":
        return "one of our ads on Facebook"
    if "meta" in utm:
        return "one of our Meta ads"
    if "101" in s:
        return "the free Trustee 101 course"
    if "webinar" in s:
        return "our webinar"
    if any(k in s for k in ("pdf", "kit", "guide", "checklist", "template")):
        return "one of our free guides"
    if "blog" in s or "subscribe" in s:
        return "our blog"
    if "booked-call" in s or s == "call":
        return "our booking page"
    return "our website"


def _name(lead: Dict[str, Any]) -> str:
    raw = (lead.get("name") or "").strip()
    return escape(raw.split(" ")[0] if raw else "there")


def _link_p(url: str) -> str:
    return (
        f'<p style="margin:0 0 14px 0;"><a href="{url}" '
        f'style="color:#010079;font-weight:bold;text-decoration:underline;'
        f'font-size:16px;">{url.replace("https://", "")}</a></p>'
    )


def derive_draft(lead: Dict[str, Any], notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the booking-link follow-up email draft for a lead.

    lead: the lead dict (name, email, origin_source/source, utm_source).
    notes: list of {content, action_type?, created_at?} — lead activities.
    Returns {subject, body_html, signal, topics, objection, notes_used, booking_url}.
    """
    cls = classify_notes(notes)
    signal = cls["signal"]
    topics = cls["topics"]
    objection = cls["objection"]
    name = _name(lead)
    link_p = _link_p(BOOKING_URL)

    # ── Subject ──
    if signal == "voicemail":
        subject = f"Just left you a voicemail, {name}"
    elif signal == "no_answer":
        subject = f"Tried you by phone, {name}"
    elif signal == "call":
        subject = f"Good talking with you, {name}"
    elif signal == "text":
        subject = f"Following up on my text, {name}"
    elif topics:
        subject = f"{topics[0].capitalize()} — got 20 minutes, {name}?"
    else:
        subject = f"A quick walkthrough of TrustOffice, {name}?"

    # ── Body ── (every <p> carries inline spacing — survives Outlook margin-stripping)
    parts: List[str] = [f"<p {_P_STYLE}>Hi {name},</p>"]

    if signal == "voicemail":
        parts.append(
            f"<p {_P_STYLE}>I just left you a voicemail a minute ago — no need to call back "
            "for the details. Easier to grab a time here:</p>"
        )
        parts.append(link_p)
    elif signal == "no_answer":
        parts.append(
            f"<p {_P_STYLE}>I tried you by phone a little earlier — phone tag isn't anyone's "
            "favorite, so here's a direct way to lock in a time:</p>"
        )
        parts.append(link_p)
    elif signal == "call":
        parts.append(f"<p {_P_STYLE}>Good talking with you.</p>")
        if topics:
            parts.append(f"<p {_P_STYLE}>Since {topics[0]} is on your mind, we'll start there.</p>")
        parts.append(
            f"<p {_P_STYLE}>Let's put a time on the calendar to go through TrustOffice together:</p>"
        )
        parts.append(link_p)
        parts.append(f"<p {_P_STYLE}>About 20 minutes — no prep needed, just bring your questions.</p>")
    elif signal == "text":
        parts.append(
            f"<p {_P_STYLE}>Quick follow-up to my text — booking a time here is easier than "
            "playing calendar tag:</p>"
        )
        parts.append(link_p)
    elif signal == "email":
        parts.append(
            f"<p {_P_STYLE}>Wanted to follow up on my earlier note — if a quick walkthrough "
            "would help, grab whatever time suits you:</p>"
        )
        parts.append(link_p)
    else:
        # general (no notes, or notes with no contact signal)
        parts.append(
            f"<p {_P_STYLE}>I'd love to show you around TrustOffice personally — how it handles "
            "minutes, distributions, and keeping every decision defensible.</p>"
        )
        if topics:
            parts.append(f"<p {_P_STYLE}>Since {topics[0]} is on your mind, we'll start there.</p>")
        parts.append(f"<p {_P_STYLE}>Grab whatever time works for you:</p>")
        parts.append(link_p)
        parts.append(f"<p {_P_STYLE}>About 20 minutes — bring your questions.</p>")

    if objection:
        parts.append(
            f"<p {_P_STYLE}>And if cost is the sticking point: the first month is $29 with code "
            "WELCOME29 — see the value first, decide after.</p>"
        )

    # ── Source attribution (always) ──
    parts.append(
        f"<p {_P_MUTED}>P.S. So you know how we "
        f"connected — you reached us through {_source_phrase(lead)}.</p>"
    )

    parts.append(f"<p {_P_SIGN}>— Kenneth (Jeff)</p>")
    body_html = "\n".join(parts)

    return {
        "subject": subject,
        "body_html": body_html,
        "signal": signal,
        "topics": topics,
        "objection": objection,
        "notes_used": cls["notes_used"],
        "booking_url": BOOKING_URL,
    }


# ── Signal label map (shared with the frontend chips) ──────────────────────
SIGNAL_LABELS = {
    "voicemail": "Voicemail follow-up",
    "no_answer": "Phone follow-up (no answer)",
    "call": "Call recap",
    "text": "Text follow-up",
    "email": "Email follow-up",
    "general": "General intro",
}