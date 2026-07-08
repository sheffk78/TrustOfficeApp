"""
Trustee name parsing utilities.

The backend stores trustees as a comma-separated string in MongoDB. The
naive ``raw.split(",")`` approach breaks names that legitimately contain
commas — most commonly suffixes such as ``Jr.``, ``Sr.``, ``II``, ``III``,
``IV`` and professional designations.

This module provides :func:`parse_trustees` which splits on commas that are
**between** trustees while keeping commas that are **part of** a name
(e.g. ``Smith, Jr.``) intact.

Algorithm
---------
1. Split the raw string on every comma — same as the naive approach.
2. Walk the resulting fragments left-to-right, accumulating a buffer.
3. Before committing a fragment as a completed trustee, check whether the
   fragment looks like a name suffix.  If it does, *append* it to the
   current buffer (with the comma that was stripped during split) instead
   of starting a new trustee.
4. Otherwise the fragment is the start of a new trustee — flush the buffer
   and begin accumulating again.

A fragment is considered a suffix when, after stripping, it matches one of
the known suffix tokens (case-insensitive, with or without a trailing dot):

    Jr  Sr  II  III  IV  V  VI  VII  VIII  IX  X
    Esq PhD MD JD DDS CPA

The numeric suffixes (II–X) are matched only when they are *not* part of a
longer word, so a single-letter fragment is only treated as ``V`` when it
is exactly ``V`` or ``V.`` — ``Smith, Van`` will still split correctly.
"""

from __future__ import annotations

import re
from typing import List, Optional

# Suffixes that legitimately appear *after* a comma inside a single name.
# Matched case-insensitively.  Dotted and undotted forms both recognised.
_NUMERIC_SUFFIXES = {f"{n}" for n in (
    "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
)}
_ALPHA_SUFFIXES = {
    "JR", "SR", "ESQ", "PHD", "MD", "JD", "DDS", "CPA",
}
# Combined set for fast lookup (upper-cased, no trailing dot).
_ALL_SUFFIXES = _NUMERIC_SUFFIXES | _ALPHA_SUFFIXES

# A single uppercase letter V can be a suffix (e.g. "John Smith, V").
_SINGLE_LETTER_SUFFIXES = {"V"}


def _is_suffix(fragment: str) -> bool:
    """Return True if *fragment* (already stripped) looks like a name suffix."""
    if not fragment:
        return False
    # Normalise: strip trailing dot, upper-case.
    norm = fragment.rstrip(".").upper().strip()
    if norm in _ALL_SUFFIXES:
        return True
    # Single-letter "V" or "v" (with optional dot) — numeric suffix V.
    if norm in _SINGLE_LETTER_SUFFIXES:
        return True
    return False


def parse_trustees(raw: Optional[str | list]) -> List[str]:
    """Parse comma-separated trustee names into a list, preserving suffix commas.

    >>> parse_trustees("Smith, Jr.")
    ['Smith, Jr.']
    >>> parse_trustees("John Smith, Jane Doe")
    ['John Smith', 'Jane Doe']
    >>> parse_trustees("John Smith Jr., Jane Doe Sr.")
    ['John Smith Jr.', 'Jane Doe Sr.']
    >>> parse_trustees("John Smith, III, Jane Doe")
    ['John Smith, III', 'Jane Doe']
    >>> parse_trustees("")
    []
    >>> parse_trustees(None)
    []
    >>> parse_trustees([])
    []
    """
    if not raw:
        return []
    # If already a list, just clean it up.
    if isinstance(raw, list):
        return [t.strip() for t in raw if t and t.strip()]
    if not isinstance(raw, str):
        return []

    # Split on every comma — same as naive, then re-join suffix fragments.
    fragments = [f.strip() for f in raw.split(",") if f.strip()]
    if not fragments:
        return []

    trustees: List[str] = []
    buffer = fragments[0]

    for frag in fragments[1:]:
        if _is_suffix(frag):
            # The comma we stripped during split belongs to this name.
            # Re-attach with ", " so the suffix stays with the preceding name.
            buffer = f"{buffer}, {frag}"
        else:
            trustees.append(buffer)
            buffer = frag

    trustees.append(buffer)
    return trustees