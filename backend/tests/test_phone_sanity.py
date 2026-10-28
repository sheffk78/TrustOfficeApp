"""Tests for phone_sanity (JOB-20261026-TO-RHONDA-FAKEPHONE).

Rhonda (2026-10-25 Meta lead ad) submitted +12345678910 — sequential junk that
still triggered a Call-now ping. is_calling_quality must reject that class of
number while passing real-looking lines (Kirk's +16124758285 dialed fine).
All junk literals below are synthetic patterns, not real numbers.
"""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

import pytest  # noqa: E402

from phone_sanity import is_calling_quality  # noqa: E402


class TestJunkRejected:
    def test_rhonda_sequential_sweep(self):
        # The exact submitted value (typo'd real line — still not call-ping material)
        assert is_calling_quality("+12345678910") is False

    def test_sequential_10_digit(self):
        assert is_calling_quality("+1234567890") is False
        assert is_calling_quality("(123) 456-7890") is False
        assert is_calling_quality("+12109876543") is False

    def test_descending(self):
        assert is_calling_quality("+10987654321") is False

    def test_embedded_sequential_run(self):
        # Junk buried in a real-looking shape (descending run of 9)
        assert is_calling_quality("+14159876543") is False

    def test_all_same_digit(self):
        assert is_calling_quality("+10000000000") is False
        assert is_calling_quality("+1111111111") is False

    def test_dominant_repeated_digit(self):
        # One digit dominating: 1 followed by nine zeros, 4 + six 5s
        zeros9 = "0" * 9
        fives6 = "5" * 6
        assert is_calling_quality("+1" + zeros9) is False
        assert is_calling_quality("+144" + fives6) is False

    def test_fictitious_555_range(self):
        assert is_calling_quality("+18015550123") is False

    def test_invalid_length(self):
        assert is_calling_quality("") is False
        assert is_calling_quality(None) is False
        assert is_calling_quality("12345") is False


class TestRealAccepted:
    def test_kirk_mpls_line(self):
        # Dialed successfully 2026-10-23 (Kenneth reached the line)
        assert is_calling_quality("+16124758285") is True

    def test_common_us_formats(self):
        assert is_calling_quality("+1 (812) 801-5542") is True
        assert is_calling_quality("8128015542") is True
        assert is_calling_quality("+18014273851") is True

    def test_realistic_mixed(self):
        # Real numbers with coincidental small runs (max 4) still pass
        assert is_calling_quality("+13854459012") is True  # 9012 run of 4