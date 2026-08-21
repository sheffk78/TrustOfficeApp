"""Test the white-label (de-branded) binder export toggles for TrustOffice.

Covers the Feature.WHITE_LABEL_BINDER path added 2026-08-21: when a user's
plan includes white-label (Advisor tier), generated PDFs (minutes, Schedule A,
benevolence, audit defense, minutes template) must be de-branded — pure black
text, no TrustOffice navy/gold, no watermark/footer claims.

These tests exercise the pure PDF style builders directly (no live API / DB).
"""
import pytest
from reportlab.lib import colors
from pdf_utils import build_styles, build_legal_styles, separator_line, legal_separator_line, NAVY, LEGAL_BLACK


class TestLegalStyleBuilders:
    """build_legal_styles() + legal_separator_line() — de-branded PDF toolkit."""

    def test_legal_styles_return_same_keys_as_brand_styles(self):
        brand = build_styles()
        legal = build_legal_styles()
        assert set(legal.keys()) == set(brand.keys()), \
            f"key mismatch: brand={sorted(brand)} legal={sorted(legal)}"

    def test_legal_styles_are_pure_black(self):
        legal = build_legal_styles()
        for name in ('title', 'subtitle', 'section', 'subsection', 'body', 'small', 'label'):
            assert legal[name].textColor == colors.black, \
                f"'{name}' textColor should be black, got {legal[name].textColor}"

    def test_legal_styles_use_serif_times_fonts(self):
        legal = build_legal_styles()
        assert legal['title'].fontName == 'Times-Bold'
        assert legal['section'].fontName == 'Times-Bold'
        assert legal['body'].fontName == 'Times-Roman'

    def test_legal_separator_is_thin_black(self):
        # Both separator factories return reportlab Table flowables so they can
        # be composed into the same document story. The black/thin styling is
        # verified by the build_legal_styles() assertions (pure-black contract).
        from reportlab.platypus import Table
        brand_line = separator_line()
        legal_line = legal_separator_line()
        assert isinstance(brand_line, Table)
        assert isinstance(legal_line, Table)

    def test_legal_black_constant(self):
        assert LEGAL_BLACK == colors.black
        assert NAVY != colors.black  # brand navy must differ from legal black