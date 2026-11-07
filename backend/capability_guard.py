"""No-fabricated-capability guard (Day-0 audit, contract Rules 3/6).

Root cause this fixes: the Trust Assistant must never claim, in plain text,
an action that has no execution path. The canonical failure (Jerel Kratt,
2026-11-05): he asked the assistant to "move the Schedule A to the vault" and
the assistant replied as though it had done it. There is no backend write for
that, so nothing happened and the member chased a phantom record. Same for
"clean up the alerts" -- the client-computed inline alerts had no durable
resolution path until the Day-0 fix.

This module is the lightweight reply-builder check: it scans assistant text
for completed-action claims about the Vault / documents / alerts and, when
the turn produced no execution_result, rewrites the message to the honest
form. Regex-based and dependency-free so it can be unit-tested in isolation.

It is NOT a substitute for the action layer -- it is the last line of defence
that keeps the member from being told a false thing. The system prompt
(backend/prompts/chat_system_core.md) carries the same rule up front.
"""
import re

# ---------------------------------------------------------------------------
# Completed-action claims about the Vault / documents / alerts.
#
# These patterns target PAST-TENSE / COMPLETED phrasing ("moved ... to the
# vault", "is now in the vault", "cleaned up the alerts"). Legitimate
# guidance ("upload it in the Vault page", "the Vault shows uploaded
# documents", "I've prepared an action card") does not match, so the guard
# does not fire on honest replies.
# ---------------------------------------------------------------------------
_CAPABILITY_CLAIMS = [
    # "<verb> ... to/in the vault" (the Jerel failure mode).
    re.compile(
        r"\b(?:moved|placed|uploaded|added|saved|put|stored|dropped|filed|archived)\b"
        r"[^.!?\n]{0,80}\b(?:to|in(?:to)?)\s+(?:the\s+)?(?:document\s+)?vault\b",
        re.IGNORECASE,
    ),
    # "is/are now in the vault".
    re.compile(
        r"\b(?:is|are)\s+(?:now\s+)?in\s+(?:the\s+)?(?:document\s+)?vault\b",
        re.IGNORECASE,
    ),
    # "<verb> ... document/file/pdf" (a claimed file the assistant cannot
    # produce in plain text). "card" is excluded so "created a document
    # upload card" (an honest pre-action statement) does not trip it.
    re.compile(
        r"\b(?:created|uploaded|added|saved|put|stored|filed|generated)\b"
        r"[^.!?\n]{0,40}\b(?:document|file|pdf)\b(?!\s*(?:upload\s+)?card)",
        re.IGNORECASE,
    ),
    # Alert housekeeping claims ("cleaned up the alerts", "resolved the
    # alerts") -- the inline alerts had no durable path before Day-0.
    re.compile(
        r"\b(?:cleaned\s+up|cleared|resolved|taken\s+care\s+of|handled)\b"
        r"[^.!?\n]{0,60}\b(?:the\s+)?alerts?\b",
        re.IGNORECASE,
    ),
]

# The honest form. Names the real locations and the real path forward.
_HONEST_FORM = (
    "I can't move files into the Vault directly - the Vault holds documents "
    "you upload, and Schedule A assets live on the Schedule A page "
    "(/schedule-a). Nothing was changed. To add a document, upload it in the "
    "Vault page; to record a Schedule A asset, approve an action card and "
    "I'll create it."
)


def capability_claim_detected(text: str) -> bool:
    """True when assistant text claims a completed vault/document/alert action."""
    if not text:
        return False
    return any(rx.search(text) for rx in _CAPABILITY_CLAIMS)


def apply_capability_guard(
    text: str, execution_result: dict | None = None
) -> tuple[str, bool]:
    """Return ``(text, flagged)``.

    When ``execution_result`` is a successful envelope, the turn DID execute
    something, so a claim about it is legitimate and the text is untouched.
    Otherwise a detected claim is rewritten to the honest form.
    """
    if not text:
        return text, False
    if execution_result and execution_result.get("success"):
        return text, False
    if capability_claim_detected(text):
        return _HONEST_FORM, True
    return text, False
