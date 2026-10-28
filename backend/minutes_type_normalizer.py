"""
Minutes type normalization for chat-created minutes (2026-10-23).

Root cause of the Jerel Kratt complaint: the intent-extractor LLM emits
human wording for the minutes type ("Quarterly Review", "annual meeting",
"trustee meeting"), but the backend called ``MinutesType(value)`` directly.
Any value outside the enum raised ValueError, and the handler SILENTLY
downgraded to ``MinutesType.general``. The member asked for quarterly
minutes and got a generic empty shell with no trace of the mistake.

This module makes the mapping explicit, auditable, and non-silent:

  1. Normalize the raw string (strip, lower, collapse whitespace/punctuation).
  2. Map human forms onto enum values via an explicit alias table.
  3. If the value still cannot be resolved, the caller gets a FAILED exec
     with a clear error (never a quiet downgrade) plus an intent-derived
     fallback it may use with an explicit caveat attached.

Every fallback is logged at WARNING with the original value so the pattern
shows up in logs rather than disappearing.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# --- Canonical enum values (kept as literals so this module has no import
# --- dependency on models.py and stays unit-testable in isolation).
ANNUAL = "annual"
QUARTERLY = "quarterly"
COMPENSATION = "compensation"
DISTRIBUTION = "distribution"
SOLVENCY = "solvency"
GENERAL = "general"
INITIAL_TRUSTEE_MEETING = "initial_trustee_meeting"
ANNUAL_REVIEW = "annual_review"
QUARTERLY_REVIEW = "quarterly_review"
GENERAL_MEETING = "general_meeting"

# Human wording -> canonical minutes_type.
#
# The left-hand side is the NORMALIZED form (lowercase, punctuation
# collapsed to single spaces). The right-hand side is the MinutesType value
# stored on the minutes record.
#
# NOTE ON QUARTERLY: the member-facing record type for a quarterly review is
# "quarterly" (the enum value). "quarterly_review" is a distinct MinutesType
# enum member used by the template registry; the chat path maps the human
# phrase "quarterly review" onto "quarterly" per the fix spec, because the
# card LLM's "Quarterly Review" wording means the quarterly meeting type.
MINUTES_TYPE_ALIASES = {
    # --- quarterly ---
    "quarterly review": QUARTERLY,
    "quarterly review minutes": QUARTERLY,
    "quarterly minutes": QUARTERLY,
    "quarterly meeting": QUARTERLY,
    "quarterly meeting minutes": QUARTERLY,
    "quarterly trustee meeting": QUARTERLY,
    "quarterly trustee review": QUARTERLY,
    "quarterly business review": QUARTERLY,
    "quarterly": QUARTERLY,
    "q1 review": QUARTERLY,
    "q2 review": QUARTERLY,
    "q3 review": QUARTERLY,
    "q4 review": QUARTERLY,
    "q1": QUARTERLY,
    "q2": QUARTERLY,
    "q3": QUARTERLY,
    "q4": QUARTERLY,
    # --- annual ---
    "annual meeting": ANNUAL,
    "annual review": ANNUAL,
    "annual meeting minutes": ANNUAL,
    "annual review minutes": ANNUAL,
    "annual trustee meeting": ANNUAL,
    "annual trustee review": ANNUAL,
    "yearly meeting": ANNUAL,
    "yearly review": ANNUAL,
    "annual": ANNUAL,
    # --- compensation ---
    "compensation": COMPENSATION,
    "trustee compensation": COMPENSATION,
    "trustee compensation approval": COMPENSATION,
    "compensation approval": COMPENSATION,
    "compensation review": COMPENSATION,
    "compensation minutes": COMPENSATION,
    # --- distribution ---
    "distribution": DISTRIBUTION,
    "distributions": DISTRIBUTION,
    "distribution minutes": DISTRIBUTION,
    "beneficiary distribution": DISTRIBUTION,
    "distributions to beneficiaries": DISTRIBUTION,
    "distribution approval": DISTRIBUTION,
    # --- solvency ---
    "solvency": SOLVENCY,
    "solvency certification": SOLVENCY,
    "solvency review": SOLVENCY,
    "solvency confirmation": SOLVENCY,
    # --- general / meetings ---
    "general": GENERAL,
    "general minutes": GENERAL,
    "general meeting": GENERAL_MEETING,
    "general meeting minutes": GENERAL_MEETING,
    "regular meeting": GENERAL_MEETING,
    "regular trustee meeting": GENERAL_MEETING,
    "trustee meeting": GENERAL_MEETING,
    "trustee meeting minutes": GENERAL_MEETING,
    "ordinary meeting": GENERAL_MEETING,
    "meeting": GENERAL_MEETING,
    "meeting minutes": GENERAL_MEETING,
    # --- initial trustee meeting (context-dependent) ---
    "initial trustee meeting": INITIAL_TRUSTEE_MEETING,
    "initial meeting": INITIAL_TRUSTEE_MEETING,
    "first trustee meeting": INITIAL_TRUSTEE_MEETING,
    "organizational meeting": INITIAL_TRUSTEE_MEETING,
    "first organizational meeting": INITIAL_TRUSTEE_MEETING,
}

# Values that are already-valid MinutesType members (the enum carries both
# canonical types like "quarterly" and template aliases like
# "quarterly_review"). The caller passes the valid-enum set in at runtime so
# this module never has to import models.py.
VALID_MINUTES_TYPES: Tuple[str, ...] = (
    ANNUAL,
    QUARTERLY,
    COMPENSATION,
    DISTRIBUTION,
    SOLVENCY,
    GENERAL,
    INITIAL_TRUSTEE_MEETING,
    ANNUAL_REVIEW,
    QUARTERLY_REVIEW,
    GENERAL_MEETING,
)

# Keys that mean "this is the first/organizational meeting" — used to decide
# whether a bare "trustee meeting" means initial_trustee_meeting.
_INITIAL_CONTEXT_MARKERS = (
    "initial",
    "first",
    "organizational",
    "organisation",
    "organizing",
    "organising",
    "new trust",
    "formation",
    "creating the trust",
    "set up the trust",
    "setting up the trust",
)


def normalize_minutes_type_value(raw: object) -> str:
    """
    Collapse a raw LLM/card value into a comparable key.

    Lower-cases, replaces punctuation (hyphens, underscores, slashes) with
    spaces, collapses repeated whitespace, and strips the ends.
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    lowered = raw.strip().lower()
    lowered = re.sub(r"[\-_/\\]+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _looks_like_initial_context(context_text: str) -> bool:
    """True when the surrounding request mentions creating/holding the FIRST meeting."""
    if not context_text:
        return False
    norm = normalize_minutes_type_value(context_text)
    return any(marker in norm for marker in _INITIAL_CONTEXT_MARKERS)


def resolve_minutes_type(
    raw_value: object,
    context_text: str = "",
    valid_types: Optional[Tuple[str, ...]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve a card/LLM minutes_type to a valid MinutesType value.

    Returns ``(resolved_type, caveat)``:

    * ``resolved_type`` is a valid MinutesType value, or None when the input
      could not be resolved at all.
    * ``caveat`` is None on a clean resolution, or a human-readable note
      describing the substitution (e.g. "type was 'Quarterly Review', saved
      as 'quarterly'"). Callers must attach the caveat to the execution
      result so the member is never silently given a different document type.

    A bare "trustee meeting" resolves to general_meeting UNLESS the context
    mentions an initial/first/organizational meeting, in which case it
    resolves to initial_trustee_meeting.
    """
    valid = tuple(valid_types) if valid_types else VALID_MINUTES_TYPES
    original = raw_value if isinstance(raw_value, str) else ("" if raw_value is None else str(raw_value))
    key = normalize_minutes_type_value(original)

    if not key:
        return None, None

    # 1. Exact enum member (already normalized, e.g. "quarterly").
    if key in valid:
        return key, None

    # 2. Alias table lookup.
    alias = MINUTES_TYPE_ALIASES.get(key)

    # 3. "trustee meeting" is context-dependent.
    if alias == GENERAL_MEETING and key in (
        "trustee meeting",
        "trustee meeting minutes",
        "meeting",
        "meeting minutes",
    ):
        if _looks_like_initial_context(context_text):
            alias = INITIAL_TRUSTEE_MEETING

    if alias and alias in valid:
        if alias != key:
            caveat = f"Minutes type '{original.strip()}' was saved as '{alias}'."
        else:
            caveat = None
        return alias, caveat

    # 4. Unresolvable. Do NOT silently downgrade — the caller decides between
    # a failed exec and an intent-derived fallback WITH a caveat.
    logger.warning(
        "MINUTES_TYPE_UNRESOLVED | raw=%r | normalized=%r | context=%r | "
        "no alias matched — refusing silent downgrade to 'general'",
        original, key, (context_text or "")[:200],
    )
    return None, None


def build_type_fallback_caveat(original: object, fallback_type: str) -> str:
    """Caveat text for a fallback type chosen because the raw value was unresolvable."""
    original_s = (original if isinstance(original, str) else str(original or "")).strip()
    return (
        f"Minutes type '{original_s}' was not recognized — saved as '{fallback_type}'. "
        "Please change the type on the Minutes page if this is not right."
    )
