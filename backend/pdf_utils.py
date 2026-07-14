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