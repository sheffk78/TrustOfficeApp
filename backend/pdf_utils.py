# backend/pdf_utils.py
# Shared ReportLab utilities — extracted from audit_defense.py, schedule_a.py,
# minutes.py, benevolence.py, and units.py.
#
# This module consolidates the ~100 lines of ReportLab boilerplate that were
# duplicated across 5 routers: brand colors, paragraph styles, separator lines,
# info tables, data tables, signature blocks, notary blocks, watermark footers,
# document templates, and PDF response helpers.
#
# Usage:
#   from pdf_utils import (NAVY, GOLD, GRAY, LIGHT_GRAY,
#       build_styles, separator_line, info_table, data_table,
#       signature_block, notary_block, watermark_footer,
#       create_doc_template, pdf_response)

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors
from fastapi.responses import StreamingResponse


# ==================== BRAND COLORS ====================
# Duplicated in audit_defense.py, schedule_a.py, benevolence.py, units.py
NAVY = colors.HexColor('#010079')
GOLD = colors.HexColor('#d5ad36')
GRAY = colors.HexColor('#666666')
LIGHT_GRAY = colors.HexColor('#f0f0f0')

# Extended palette (audit_defense.py local colors, now shared)
RED = colors.HexColor('#dc2626')
AMBER = colors.HexColor('#d97706')
GREEN = colors.HexColor('#16a34a')


# ==================== STYLES ====================

def build_styles(font_family='Helvetica'):
    """Build a dictionary of ParagraphStyle objects for PDF documents.

    Args:
        font_family: Base font family ('Helvetica' or 'Times-Roman').

    Returns:
        dict with keys: title, subtitle, section, subsection, body, small, label
    """
    base = getSampleStyleSheet()
    bold = f'{font_family}-Bold'

    return {
        'title': ParagraphStyle(
            'DocTitle', parent=base['Heading1'], fontSize=20, spaceAfter=4,
            textColor=NAVY, alignment=1, fontName=bold,
        ),
        'subtitle': ParagraphStyle(
            'DocSubtitle', parent=base['Normal'], fontSize=10, spaceAfter=12,
            textColor=GRAY, alignment=1, fontName=font_family,
        ),
        'section': ParagraphStyle(
            'SectionTitle', parent=base['Heading2'], fontSize=13, spaceBefore=20,
            spaceAfter=8, textColor=NAVY, fontName=bold,
        ),
        'subsection': ParagraphStyle(
            'SubSection', parent=base['Heading3'], fontSize=11, spaceBefore=12,
            spaceAfter=4, textColor=NAVY, fontName=bold,
        ),
        'body': ParagraphStyle(
            'BodyText', parent=base['Normal'], fontSize=9, spaceAfter=4,
            fontName=font_family, leading=12,
        ),
        'small': ParagraphStyle(
            'SmallText', parent=base['Normal'], fontSize=8, textColor=GRAY,
            fontName=font_family, leading=10,
        ),
        'label': ParagraphStyle(
            'Label', parent=base['Normal'], fontSize=9, fontName=bold,
            textColor=NAVY,
        ),
    }


# ==================== LEGAL STYLES (de-branded) ====================

# Times-Roman is the ReportLab built-in PDF font equivalent to Times New Roman.
# It requires no external font registration and renders identically across
# all PDF viewers, making it the safest choice for external legal documents.
LEGAL_FONT = 'Times-Roman'
LEGAL_FONT_BOLD = 'Times-Bold'
LEGAL_FONT_ITALIC = 'Times-Italic'

# Legal documents use pure black text — no brand colors.
LEGAL_BLACK = colors.black
# Subtle dark gray permitted only for truly secondary metadata (e.g. page
# numbering if added by the caller); body/section text stays black.
LEGAL_GRAY = colors.HexColor('#333333')


def build_legal_styles(font_family='Times-Roman'):
    """Build a dictionary of ParagraphStyle objects for external legal documents.

    De-branded counterpart to build_styles(). Intended for documents that go
    to external parties (banks, courts, IRS, opposing counsel) and must look
    like they were produced by a regular professional — no TrustOffice
    branding, no NAVY/GOLD colors, no decorative styling.

    Args:
        font_family: Base font family. Defaults to 'Times-Roman' (the
            ReportLab built-in that matches Times New Roman). Callers should
            almost never override this for legal output.

    Returns:
        dict with the same keys as build_styles(): title, subtitle, section,
        subsection, body, small, label — all in Times-Roman, black text.
    """
    base = getSampleStyleSheet()
    # Use explicit Times font variant names. ReportLab's built-in Times
    # family uses 'Times-Roman' / 'Times-Bold' / 'Times-Italic' — NOT the
    # '{family}-Bold' pattern (which produces 'Times-Roman-Bold', invalid).
    regular = font_family if font_family else LEGAL_FONT
    bold = LEGAL_FONT_BOLD if regular == LEGAL_FONT else f'{regular}-Bold'

    return {
        'title': ParagraphStyle(
            'LegalTitle', parent=base['Heading1'], fontSize=16, spaceAfter=4,
            textColor=LEGAL_BLACK, alignment=1, fontName=bold,
        ),
        'subtitle': ParagraphStyle(
            'LegalSubtitle', parent=base['Normal'], fontSize=11, spaceAfter=12,
            textColor=LEGAL_BLACK, alignment=1, fontName=regular,
        ),
        'section': ParagraphStyle(
            'LegalSection', parent=base['Heading2'], fontSize=12, spaceBefore=18,
            spaceAfter=6, textColor=LEGAL_BLACK, fontName=bold,
        ),
        'subsection': ParagraphStyle(
            'LegalSubSection', parent=base['Heading3'], fontSize=11,
            spaceBefore=12, spaceAfter=4, textColor=LEGAL_BLACK,
            fontName=bold,
        ),
        'body': ParagraphStyle(
            'LegalBody', parent=base['Normal'], fontSize=11, spaceAfter=6,
            fontName=regular, leading=14,
        ),
        'small': ParagraphStyle(
            'LegalSmall', parent=base['Normal'], fontSize=9,
            textColor=LEGAL_BLACK, fontName=regular, leading=11,
        ),
        'label': ParagraphStyle(
            'LegalLabel', parent=base['Normal'], fontSize=10, fontName=bold,
            textColor=LEGAL_BLACK,
        ),
    }


def legal_separator_line(width=6.5 * inch, thickness=0.5, color=LEGAL_BLACK):
    """Return a thin black horizontal separator line for legal documents.

    De-branded counterpart to separator_line(). Uses a thin (0.5pt) black line
    instead of the default 1pt NAVY line, consistent with standard legal
    document formatting.

    Args:
        width: Line width in ReportLab units (default 6.5 inch).
        thickness: Line thickness in points (default 0.5).
        color: Line color (default LEGAL_BLACK — pure black).

    Returns:
        Table flowable rendering as a horizontal separator line.
    """
    t = Table([[""]], colWidths=[width], rowHeights=[1])
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), thickness, color)]))
    return t


def legal_info_table(rows, label_width=2.0 * inch, value_width=4.5 * inch):
    """Build a two-column label/value info table for legal documents.

    De-branded counterpart to info_table(). Uses Times-Roman fonts and black
    text throughout — no NAVY labels, no brand coloring.

    Args:
        rows: List of [label, value] pairs.
        label_width: Width of the label column (default 2.0 inch).
        value_width: Width of the value column (default 4.5 inch).

    Returns:
        Table flowable with bold right-aligned labels and left-aligned values,
        all in Times-Roman black text.
    """
    t = Table(rows, colWidths=[label_width, value_width])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), LEGAL_FONT_BOLD),
        ('FONTNAME', (1, 0), (1, -1), LEGAL_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (-1, -1), LEGAL_BLACK),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def legal_data_table(header, rows, col_widths=None):
    """Build a data table for legal documents — no zebra striping, no brand color.

    De-branded counterpart to data_table(). Uses a simple thin black grid,
    Times-Roman fonts, a plain bold header row (no NAVY background, no white
    text), and no alternating row backgrounds.

    Args:
        header: List of column header strings.
        rows: List of row lists.
        col_widths: Optional list of column widths. If None, divides 6.5 inch
            evenly across columns.

    Returns:
        Table flowable with a clean black-on-white legal table style.
    """
    data = [header] + rows
    if not col_widths:
        col_widths = [6.5 * inch / len(header)] * len(header)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), LEGAL_FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), LEGAL_BLACK),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, LEGAL_BLACK),
        ('FONTNAME', (0, 1), (-1, -1), LEGAL_FONT),
        ('LINEBELOW', (0, 0), (-1, 0), 1, LEGAL_BLACK),
    ]))
    return t


def legal_signature_block(signatories, styles=None):
    """Build a signature block for legal documents — no brand separator.

    De-branded counterpart to signature_block(). Uses a thin black separator
    line, Times-Roman fonts, and black text. Certification wording is
    unchanged (it is standard legal language, not branding).

    Args:
        signatories: List of names (strings) who should sign.
        styles: Optional styles dict from build_legal_styles(). If None,
            builds default legal styles.

    Returns:
        List of flowables for the signature block.
    """
    if styles is None:
        styles = build_legal_styles()

    flowables = []
    flowables.append(Spacer(1, 24))
    flowables.append(legal_separator_line())
    flowables.append(Spacer(1, 8))
    flowables.append(Paragraph('CERTIFICATION', styles['section']))
    flowables.append(Paragraph(
        'The undersigned hereby certifies that the foregoing document constitutes a true, '
        'accurate, and complete record and that all decisions recorded herein were '
        'made in good faith and in accordance with the Trust Indenture.',
        styles['body'],
    ))
    flowables.append(Spacer(1, 24))

    label_style = ParagraphStyle(
        'LegalSigLabel', parent=styles['small'],
        fontName=LEGAL_FONT, fontSize=10, textColor=LEGAL_BLACK,
    )

    for name in signatories[:2]:
        flowables.append(Spacer(1, 16))
        flowables.append(Paragraph('_' * 45, styles['body']))
        flowables.append(Paragraph(f'{name}', label_style))
        flowables.append(Paragraph('Date: _________________', label_style))

    return flowables


def legal_notary_block(state='', county='', styles=None):
    """Build a notary acknowledgment block for legal documents.

    De-branded counterpart to notary_block(). Uses a thin black separator,
    Times-Roman fonts, and black text. The [NOTARIAL SEAL] placeholder is
    rendered in black rather than gray.

    Args:
        state: State name for the acknowledgment (e.g., 'Texas').
        county: County name for the acknowledgment (e.g., 'Dallas County').
        styles: Optional styles dict from build_legal_styles(). If None,
            builds default legal styles.

    Returns:
        List of flowables for the notary acknowledgment section.
    """
    if styles is None:
        styles = build_legal_styles()

    flowables = []
    flowables.append(Spacer(1, 30))
    flowables.append(legal_separator_line())
    flowables.append(Spacer(1, 8))
    flowables.append(Paragraph('NOTARY ACKNOWLEDGMENT', styles['section']))

    state_text = state or '_______________'
    county_text = county or '_______________'

    flowables.append(Paragraph(f'State of {state_text}', styles['body']))
    flowables.append(Paragraph(f'County of {county_text}', styles['body']))
    flowables.append(Spacer(1, 12))

    flowables.append(Paragraph(
        'On this _____ day of _______________, 20___, before me, a Notary Public in '
        'and for said State, personally appeared the above-named person(s), known to me '
        '(or satisfactorily proven) to be the person(s) whose name(s) is/are subscribed '
        'to the within instrument and acknowledged that he/she/they executed the same for '
        'the purposes therein contained.',
        styles['body'],
    ))
    flowables.append(Spacer(1, 20))

    flowables.append(Paragraph('_______________________________________', styles['body']))
    flowables.append(Paragraph('Notary Public Signature', styles['small']))
    flowables.append(Spacer(1, 8))
    flowables.append(Paragraph('My Commission Expires: _________________', styles['small']))
    flowables.append(Spacer(1, 20))

    flowables.append(Paragraph(
        '[NOTARIAL SEAL]',
        ParagraphStyle(
            'LegalSealPlaceholder', parent=styles['small'],
            fontSize=9, alignment=1, textColor=LEGAL_BLACK,
        ),
    ))

    return flowables


def legal_footer(trust_name, doc_type, styles=None):
    """Build a plain footer for legal documents — no watermark, no brand line.

    De-branded counterpart to watermark_footer(). Omits the "Generated by
    TrustOffice" watermark entirely and uses a thin black separator instead
    of the NAVY branded line. The confidentiality notice is retained because
    it is standard legal language, not software branding.

    Args:
        trust_name: Name of the trust for the footer line.
        doc_type: Document type label (e.g., 'Private Trust Minutes').
        styles: Optional styles dict from build_legal_styles(). If None,
            builds default legal styles.

    Returns:
        List of flowables for the footer section (no watermark).
    """
    if styles is None:
        styles = build_legal_styles()

    flowables = []
    flowables.append(Spacer(1, 20))
    flowables.append(legal_separator_line())
    flowables.append(Spacer(1, 8))

    footer_style = ParagraphStyle(
        'LegalFooter', parent=styles['small'],
        fontName=LEGAL_FONT_ITALIC, fontSize=9, alignment=1,
        textColor=LEGAL_BLACK,
    )

    flowables.append(Paragraph(
        f'{trust_name} – {doc_type} – Confidential',
        footer_style,
    ))

    return flowables


# ==================== FLOWABLE HELPERS ====================

def separator_line(width=6.5 * inch, thickness=1, color=NAVY):
    """Return a Table flowable that renders as a horizontal separator line.

    Args:
        width: Line width in ReportLab units (default 6.5 inch).
        thickness: Line thickness in points (default 1).
        color: Line color (default NAVY).

    Returns:
        Table flowable.
    """
    t = Table([[""]], colWidths=[width], rowHeights=[1])
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), thickness, color)]))
    return t


def info_table(rows, label_width=1.8 * inch, value_width=4.7 * inch):
    """Build a two-column label/value info table.

    Args:
        rows: List of [label, value] pairs.
        label_width: Width of the label column (default 1.8 inch).
        value_width: Width of the value column (default 4.7 inch).

    Returns:
        Table flowable with bold right-aligned labels and left-aligned values.
    """
    t = Table(rows, colWidths=[label_width, value_width])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), NAVY),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def data_table(header, rows, col_widths=None):
    """Build a data table with a styled header row and zebra-striped body rows.

    Args:
        header: List of column header strings.
        rows: List of row lists.
        col_widths: Optional list of column widths. If None, divides 6.5 inch
            evenly across columns.

    Returns:
        Table flowable with NAVY header, white text, and alternating row backgrounds.
    """
    data = [header] + rows
    if not col_widths:
        col_widths = [6.5 * inch / len(header)] * len(header)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
    ]
    t.setStyle(TableStyle(style))
    return t


def signature_block(signatories, styles=None):
    """Build a signature block with certification text and signature lines.

    Args:
        signatories: List of names (strings) who should sign.
        styles: Optional styles dict from build_styles(). If None, builds default.

    Returns:
        List of flowables (Spacer, Paragraph, etc.) for the signature block.
    """
    if styles is None:
        styles = build_styles()

    flowables = []
    flowables.append(Spacer(1, 24))
    flowables.append(separator_line())
    flowables.append(Spacer(1, 8))
    flowables.append(Paragraph('CERTIFICATION', styles['section']))
    flowables.append(Paragraph(
        'The undersigned hereby certifies that the foregoing document constitutes a true, '
        'accurate, and complete record and that all decisions recorded herein were '
        'made in good faith and in accordance with the Trust Indenture.',
        styles['body'],
    ))
    flowables.append(Spacer(1, 24))

    label_style = ParagraphStyle(
        'SigLabel', parent=styles['small'],
        fontName='Helvetica', fontSize=9, textColor=GRAY,
    )

    for name in signatories[:2]:
        flowables.append(Spacer(1, 16))
        flowables.append(Paragraph('_' * 45, styles['body']))
        flowables.append(Paragraph(f'{name}', label_style))
        flowables.append(Paragraph('Date: _________________', label_style))

    return flowables


def notary_block(state='', county='', styles=None):
    """Build a notary acknowledgment block.

    This is a NEW utility — no existing router has a factored notary block.
    The conveyance document templates reference notary acknowledgments in their
    generated text, but this flowable can be used when building standalone PDFs
    (e.g., bill of sale as its own PDF) that need a formal notary section.

    Args:
        state: State name for the acknowledgment (e.g., 'Texas').
        county: County name for the acknowledgment (e.g., 'Dallas County').
        styles: Optional styles dict from build_styles(). If None, builds default.

    Returns:
        List of flowables for the notary acknowledgment section.
    """
    if styles is None:
        styles = build_styles()

    flowables = []
    flowables.append(Spacer(1, 30))
    flowables.append(separator_line())
    flowables.append(Spacer(1, 8))
    flowables.append(Paragraph('NOTARY ACKNOWLEDGMENT', styles['section']))

    state_text = state or '_______________'
    county_text = county or '_______________'

    flowables.append(Paragraph(
        f'State of {state_text}', styles['body'],
    ))
    flowables.append(Paragraph(
        f'County of {county_text}', styles['body'],
    ))
    flowables.append(Spacer(1, 12))

    # Acknowledgment text — standard civil law format
    flowables.append(Paragraph(
        'On this _____ day of _______________, 20___, before me, a Notary Public in '
        'and for said State, personally appeared the above-named person(s), known to me '
        '(or satisfactorily proven) to be the person(s) whose name(s) is/are subscribed '
        'to the within instrument and acknowledged that he/she/they executed the same for '
        'the purposes therein contained.',
        styles['body'],
    ))
    flowables.append(Spacer(1, 20))

    # Notary signature line and seal area
    flowables.append(Paragraph('_______________________________________', styles['body']))
    flowables.append(Paragraph('Notary Public Signature', styles['small']))
    flowables.append(Spacer(1, 8))
    flowables.append(Paragraph('My Commission Expires: _________________', styles['small']))
    flowables.append(Spacer(1, 20))

    # Notary seal placeholder
    flowables.append(Paragraph(
        '[NOTARIAL SEAL]',
        ParagraphStyle(
            'SealPlaceholder', parent=styles['small'],
            fontSize=8, alignment=1, textColor=GRAY,
        ),
    ))

    return flowables


def watermark_footer(trust_name, doc_type, hide_watermark, styles=None):
    """Build watermark/footer flowables for a PDF document.

    Args:
        trust_name: Name of the trust for the footer line.
        doc_type: Document type label (e.g., 'Private Trust Minutes').
        hide_watermark: If False, show the "Generated by TrustOffice" watermark.
        styles: Optional styles dict from build_styles(). If None, builds default.

    Returns:
        List of flowables for the footer/watermark section.
    """
    if styles is None:
        styles = build_styles()

    flowables = []
    flowables.append(Spacer(1, 20))
    flowables.append(separator_line())
    flowables.append(Spacer(1, 8))

    footer_style = ParagraphStyle(
        'Footer', parent=styles['small'],
        fontName='Helvetica-Oblique', fontSize=8, alignment=1, textColor=GRAY,
    )

    if not hide_watermark:
        flowables.append(Paragraph(
            'Generated by TrustOffice',
            footer_style,
        ))

    flowables.append(Paragraph(
        f'{trust_name} – {doc_type} – Confidential',
        ParagraphStyle(
            'FooterNote', parent=footer_style,
            textColor=GRAY,
        ),
    ))

    return flowables


# ==================== LEGAL DOCUMENT TEMPLATE (de-branded) ====================

def legal_document_template(buffer=None, margins=None):
    """Create a SimpleDocTemplate for external legal documents.

    De-branded counterpart to create_doc_template(). Uses slightly wider
    margins (1 inch) consistent with standard legal document formatting
    (courts and banks typically expect 1-inch margins). No TrustOffice
    branding is applied — the template is a plain SimpleDocTemplate.

    Args:
        buffer: io.BytesIO buffer. If None, a new one is created.
        margins: Optional dict with topMargin, bottomMargin, leftMargin,
            rightMargin keys (in inch units). Defaults to 1.0 inch all around,
            the standard legal document margin.

    Returns:
        Tuple of (SimpleDocTemplate, buffer) — the buffer is returned so the
        caller can call .getvalue() or .seek(0) after building.
    """
    if buffer is None:
        buffer = io.BytesIO()

    if margins is None:
        margins = {
            'topMargin': 1.0 * inch,
            'bottomMargin': 1.0 * inch,
            'leftMargin': 1.0 * inch,
            'rightMargin': 1.0 * inch,
        }

    doc = SimpleDocTemplate(buffer, pagesize=letter, **margins)
    return doc, buffer


# ==================== DOCUMENT TEMPLATE ====================

def create_doc_template(buffer=None, margins=None):
    """Create a SimpleDocTemplate with standard TrustOffice margins.

    Args:
        buffer: io.BytesIO buffer. If None, a new one is created.
        margins: Optional dict with topMargin, bottomMargin, leftMargin,
            rightMargin keys (in inch units). Defaults to 0.75 inch all around.

    Returns:
        Tuple of (SimpleDocTemplate, buffer) — the buffer is returned so the
        caller can call .getvalue() or .seek(0) after building.
    """
    if buffer is None:
        buffer = io.BytesIO()

    if margins is None:
        margins = {
            'topMargin': 0.75 * inch,
            'bottomMargin': 0.75 * inch,
            'leftMargin': 0.75 * inch,
            'rightMargin': 0.75 * inch,
        }

    doc = SimpleDocTemplate(buffer, pagesize=letter, **margins)
    return doc, buffer


# ==================== PDF RESPONSE ====================

def pdf_response(buffer, filename):
    """Create a StreamingResponse for a PDF buffer.

    Args:
        buffer: io.BytesIO containing the built PDF data.
        filename: Download filename for the Content-Disposition header.

    Returns:
        StreamingResponse with application/pdf media type and attachment header.
    """
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )