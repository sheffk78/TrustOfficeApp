"""Tests for followup_drafts.py — note-aware booking-link email drafts.

2026-09-15 (Jeff directive, #trustoffice-main): the leads → booking-email button
must derive tone/topics from admin notes, never leak raw note text into the
email, always include the booking link and source attribution.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from followup_drafts import classify_notes, derive_draft, BOOKING_URL  # noqa: E402


def _lead(**over):
    base = {
        "name": "Jane Smith",
        "email": "jane@example.com",
        "source": "facebook-lead-ad",
        "origin_source": "facebook-lead-ad",
        "utm_source": "facebook",
    }
    base.update(over)
    return base


def _note(content, created_at="2026-09-15T12:00:00"):
    return {"content": content, "action_type": "manual", "created_at": created_at}


# ── classify_notes ──────────────────────────────────────────────────────────

def test_voicemail_signal_detected():
    cls = classify_notes([_note("Left a voicemail just now")])
    assert cls["signal"] == "voicemail"


def test_vm_shorthand_detected():
    cls = classify_notes([_note("VM at 3pm, no pickup")])
    assert cls["signal"] == "voicemail"


# ── Failed-voicemail notes route to no_answer (2026-09-18 Jeff bug) ─────────
# Jeff's actual note: "called and was unable to leave a voicemail because the
# mailbox was full" — the old classifier keyed on the bare word "voicemail" and
# drafted "I just left you a voicemail a minute ago." A FAILED voicemail attempt
# must never produce left-a-voicemail copy.

def test_failed_vm_mailbox_full_routes_to_no_answer():
    cls = classify_notes([
        _note("called and was unable to leave a voicemail because the mailbox was full")
    ])
    assert cls["signal"] == "no_answer"


def test_failed_vm_couldnt_leave_routes_to_no_answer():
    cls = classify_notes([_note("Couldn't leave a voicemail — their box is full")])
    assert cls["signal"] == "no_answer"


def test_failed_vm_draft_uses_no_answer_copy():
    d = derive_draft(_lead(), [_note("Called, unable to leave a voicemail — mailbox full")])
    assert "voicemail" not in d["subject"].lower()
    assert "just left you a voicemail" not in d["body_html"].lower()
    assert "tried you by phone" in d["body_html"].lower()
    assert BOOKING_URL in d["body_html"]


def test_failed_vm_newest_note_overrides_older_left_vm():
    cls = classify_notes([
        _note("Left a voicemail just now", "2026-09-17T09:00:00"),
        _note("Called and was unable to leave a voicemail because the mailbox was full",
              "2026-09-18T19:42:49"),
    ])
    assert cls["signal"] == "no_answer"


def test_left_vm_newest_still_wins_over_older_failed_attempt():
    cls = classify_notes([
        _note("Unable to leave a voicemail, mailbox was full", "2026-09-17T09:00:00"),
        _note("Left a voicemail just now", "2026-09-18T09:00:00"),
    ])
    assert cls["signal"] == "voicemail"


def test_no_answer_signal():
    cls = classify_notes([_note("Called twice, didn't answer")])
    assert cls["signal"] == "no_answer"


def test_call_signal():
    cls = classify_notes([_note("Spoke with her about the trust")])
    assert cls["signal"] == "call"


def test_priority_voicemail_beats_call():
    # voicemail note is newer; but even if order flipped, "voicemail" mentions
    # "call" patterns? No — priority comes from newest note first.
    cls = classify_notes([
        _note("Spoke last week", "2026-09-14T10:00:00"),
        _note("Left a voicemail a minute ago", "2026-09-15T09:00:00"),
    ])
    assert cls["signal"] == "voicemail"


def test_topics_whitelisted():
    cls = classify_notes([_note("Talked about revocable trust and probate worries")])
    assert "your revocable living trust" in cls["topics"]
    assert "keeping assets out of probate" in cls["topics"]


def test_minutes_only_counts_with_trust_word():
    cls = classify_notes([_note("Voicemail 5 minutes ago")])
    assert "trust minutes" not in cls["topics"]
    cls2 = classify_notes([_note("Discussed trust minutes he still needs to sign")])
    assert "trust minutes" in cls2["topics"]


def test_objection_detected():
    cls = classify_notes([_note("Said it's too expensive right now")])
    assert cls["objection"] is True


def test_no_raw_note_leak():
    """CRITICAL: raw note text must never appear in the email body."""
    secret = "PRIVATE-4729-DO-NOT-EMAIL"
    draft = derive_draft(
        _lead(),
        [_note(f"Voicemail left. Internal: {secret}")],
    )
    assert secret not in draft["body_html"]
    assert secret not in draft["subject"]


# ── derive_draft ────────────────────────────────────────────────────────────

def test_draft_voicemail_copy():
    d = derive_draft(_lead(), [_note("Left a voicemail just now")])
    assert "voicemail" in d["body_html"].lower()
    assert BOOKING_URL in d["body_html"]
    assert "voicemail" in d["subject"].lower()


def test_draft_call_copy_mentions_topic():
    d = derive_draft(_lead(), [_note("Good call — talked about her revocable trust")])
    assert "Good talking with you" in d["body_html"]
    assert "your revocable living trust" in d["body_html"]


def test_draft_always_has_booking_link():
    for notes in ([], [_note("no signal here")], [_note("voicemail"), _note("talked pricing, expensive")]):
        d = derive_draft(_lead(), notes)
        assert BOOKING_URL in d["body_html"]


def test_draft_always_has_source_attribution():
    d = derive_draft(_lead(), [])
    assert "ads on Facebook" in d["body_html"]


def test_source_attribution_variants():
    cases = [
        (_lead(source="trustee-101-landing-page", origin_source=None, utm_source=None), "Trustee 101 course"),
        (_lead(source="lead-gen-pdf", origin_source=None, utm_source=None), "free guides"),
        (_lead(source="website-blog", origin_source=None, utm_source=None), "our blog"),
        (_lead(source="something-else", origin_source=None, utm_source=None), "our website"),
    ]
    for lead, expected in cases:
        d = derive_draft(lead, [])
        assert expected in d["body_html"], f"{lead['source']} → expected '{expected}'"


def test_draft_objection_line():
    d = derive_draft(_lead(), [_note("Thinks it's too expensive")])
    assert "WELCOME29" in d["body_html"]


def test_first_name_only():
    d = derive_draft(_lead(name="Robert J. Doe III"), [])
    assert "Hi Robert," in d["body_html"]
    assert "Doe" not in d["body_html"]


def test_html_escaped():
    d = derive_draft(_lead(name="<script>x</script> Bob"), [])
    assert "<script>" not in d["body_html"]
    assert "Hi &lt;script&gt;x&lt;/script&gt;," in d["body_html"]


def test_empty_name_fallback():
    d = derive_draft(_lead(name=""), [])
    assert "Hi there," in d["body_html"]


def test_draft_shape():
    d = derive_draft(_lead(), [])
    for key in ("subject", "body_html", "signal", "topics", "objection", "notes_used", "booking_url"):
        assert key in d
    assert d["signal"] == "general"