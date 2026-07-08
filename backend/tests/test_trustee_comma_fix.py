"""
Unit tests for trustee comma-splitting fix.

These tests demonstrate the bug where a trustee name containing a comma
(e.g. 'Smith, Jr.') is incorrectly split into ['Smith', 'Jr.'] by the
naive ``split(",")`` approach, and verify that the new
:func:`trustee_utils.parse_trustees` function handles suffixes correctly.

Run with:
    cd /Users/socializerender/Projects/TrustOfficeApp/backend
    python3 -m pytest tests/test_trustee_comma_fix.py -v
"""

import pytest

from trustee_utils import parse_trustees


# ---------------------------------------------------------------------------
# Correct behaviour (the fix)
# ---------------------------------------------------------------------------

class TestParseTrusteesFixed:
    """Verify parse_trustees() handles comma-containing names correctly."""

    def test_single_name_with_suffix_jr(self):
        assert parse_trustees("Smith, Jr.") == ["Smith, Jr."]

    def test_single_name_with_suffix_sr(self):
        assert parse_trustees("Smith, Sr.") == ["Smith, Sr."]

    def test_single_name_with_numeric_suffix(self):
        assert parse_trustees("Smith, III") == ["Smith, III"]

    def test_single_name_with_single_letter_v(self):
        assert parse_trustees("Smith, V") == ["Smith, V"]

    def test_two_distinct_names(self):
        assert parse_trustees("John Smith, Jane Doe") == [
            "John Smith",
            "Jane Doe",
        ]

    def test_two_names_both_with_suffix(self):
        assert parse_trustees("John Smith Jr., Jane Doe Sr.") == [
            "John Smith Jr.",
            "Jane Doe Sr.",
        ]

    def test_suffix_with_dot_jr(self):
        assert parse_trustees("John Smith, Jr., Jane Doe") == [
            "John Smith, Jr.",
            "Jane Doe",
        ]

    def test_suffix_without_dot_jr(self):
        assert parse_trustees("John Smith Jr, Jane Doe") == [
            "John Smith Jr",
            "Jane Doe",
        ]

    def test_three_names_one_with_suffix(self):
        assert parse_trustees("John Smith, III, Jane Doe, Bob Ray") == [
            "John Smith, III",
            "Jane Doe",
            "Bob Ray",
        ]

    def test_empty_string(self):
        assert parse_trustees("") == []

    def test_none(self):
        assert parse_trustees(None) == []

    def test_list_input_passthrough(self):
        assert parse_trustees(["John Smith, Jr.", "Jane Doe"]) == [
            "John Smith, Jr.",
            "Jane Doe",
        ]

    def test_empty_list(self):
        assert parse_trustees([]) == []

    def test_whitespace_only(self):
        assert parse_trustees("  ,  ,  ") == []

    def test_names_with_extra_whitespace(self):
        assert parse_trustees("  John Smith ,  Jane Doe  ") == [
            "John Smith",
            "Jane Doe",
        ]

    def test_esq_suffix(self):
        assert parse_trustees("John Smith, Esq., Jane Doe") == [
            "John Smith, Esq.",
            "Jane Doe",
        ]

    def test_multiple_suffixes(self):
        assert parse_trustees("John Smith, Jr., Jane Doe, Sr.") == [
            "John Smith, Jr.",
            "Jane Doe, Sr.",
        ]


# ---------------------------------------------------------------------------
# Demonstration of the bug (naive split)
# ---------------------------------------------------------------------------

class TestNaiveSplitBug:
    """Show that the naive ``split(',')`` approach breaks on suffix names.

    These tests deliberately replicate the broken logic found throughout
    the codebase (see files listed in the task) so we can prove the bug
    exists and that parse_trustees() fixes it.
    """

    @staticmethod
    def _naive_split(raw: str) -> list:
        """Replicate the existing broken split logic."""
        if not raw:
            return []
        return [t.strip() for t in raw.split(",") if t.strip()]

    def test_bug_jr_split_into_two(self):
        """BUG: 'Smith, Jr.' splits into ['Smith', 'Jr.']."""
        result = self._naive_split("Smith, Jr.")
        assert result == ["Smith", "Jr."]  # This is the BUG
        # The fix produces the correct result:
        assert parse_trustees("Smith, Jr.") == ["Smith, Jr."]

    def test_bug_jr_and_other_trustee(self):
        """BUG: 'John Smith, Jr., Jane Doe' splits into 3 parts instead of 2."""
        result = self._naive_split("John Smith, Jr., Jane Doe")
        assert result == ["John Smith", "Jr.", "Jane Doe"]  # BUG: 3 parts
        assert parse_trustees("John Smith, Jr., Jane Doe") == [
            "John Smith, Jr.",
            "Jane Doe",
        ]