#!/usr/bin/env python3
"""Generate the Trustee's First 7 Days Checklist PDF"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem,
    Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus.flowables import HRFlowable
import os

NAVY = HexColor('#010079')
GOLD = HexColor('#D5AD36')
WHITE = HexColor('#FFFFFF')
DARK = HexColor('#1a1a2e')
GRAY = HexColor('#555555')
LIGHT_GRAY = HexColor('#f5f5f5')

output_path = os.path.expanduser(
    '~/.openclaw/workspace/Kit/life/brands/TrustOffice/TrustOfficeApp/backend/static/trustees-first-7-days-checklist.pdf'
)

doc = SimpleDocTemplate(
    output_path,
    pagesize=letter,
    topMargin=0.75*inch,
    bottomMargin=0.75*inch,
    leftMargin=0.75*inch,
    rightMargin=0.75*inch,
)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle(
    'CustomTitle', parent=styles['Title'],
    fontName='Helvetica-Bold', fontSize=24, textColor=NAVY,
    spaceAfter=6, alignment=TA_LEFT,
)

subtitle_style = ParagraphStyle(
    'Subtitle', parent=styles['Normal'],
    fontName='Helvetica', fontSize=14, textColor=GRAY,
    spaceAfter=20, leading=18,
)

section_style = ParagraphStyle(
    'Section', parent=styles['Heading2'],
    fontName='Helvetica-Bold', fontSize=16, textColor=NAVY,
    spaceBefore=20, spaceAfter=10, leading=20,
)

day_style = ParagraphStyle(
    'Day', parent=styles['Heading3'],
    fontName='Helvetica-Bold', fontSize=13, textColor=NAVY,
    spaceBefore=16, spaceAfter=4, leading=16,
)

body_style = ParagraphStyle(
    'Body', parent=styles['Normal'],
    fontName='Helvetica', fontSize=10, textColor=DARK,
    spaceAfter=6, leading=14,
)

item_style = ParagraphStyle(
    'Item', parent=styles['Normal'],
    fontName='Helvetica', fontSize=10, textColor=DARK,
    spaceAfter=3, leading=14,
    leftIndent=20,
)

check_style = ParagraphStyle(
    'Check', parent=styles['Normal'],
    fontName='Helvetica', fontSize=10, textColor=DARK,
    spaceAfter=3, leading=14,
    leftIndent=20,
)

note_style = ParagraphStyle(
    'Note', parent=styles['Normal'],
    fontName='Helvetica-Oblique', fontSize=9, textColor=GRAY,
    spaceAfter=8, leading=12,
    leftIndent=20,
)

footer_style = ParagraphStyle(
    'Footer', parent=styles['Normal'],
    fontName='Helvetica', fontSize=8, textColor=GRAY,
    spaceBefore=20, alignment=TA_CENTER,
)

cta_style = ParagraphStyle(
    'CTA', parent=styles['Normal'],
    fontName='Helvetica-Bold', fontSize=11, textColor=NAVY,
    spaceBefore=16, spaceAfter=4, alignment=TA_CENTER,
    leading=16,
)

# Build content
elements = []

# Header bar
header_data = [[Paragraph('TRUSTEE 101', ParagraphStyle(
    'HeaderLabel', fontName='Helvetica-Bold', fontSize=10, textColor=GOLD,
    alignment=TA_CENTER))]]
header_table = Table(header_data, colWidths=[7*inch])
header_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, -1), NAVY),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('TOPPADDING', (0, 0), (-1, -1), 8),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
]))
elements.append(header_table)
elements.append(Spacer(1, 20))

# Title
elements.append(Paragraph("The Trustee's First 7 Days", title_style))
elements.append(Paragraph("Checklist", ParagraphStyle(
    'TitleSub', parent=title_style, fontSize=20, textColor=GOLD,
    spaceAfter=4)))
elements.append(Paragraph(
    "A day-by-day guide for new trustees — from appointment to action.",
    subtitle_style))
elements.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=16))

# Intro
elements.append(Paragraph(
    "You've been named trustee. The trust document is in your hands. "
    "Beneficiaries may already be waiting. This checklist walks you through "
    "the first seven days — one day at a time, one task at a time. "
    "Complete each day's items before moving to the next.",
    body_style))
elements.append(Spacer(1, 8))

# Day 1
elements.append(Paragraph("Day 1: Read the Trust Document", day_style))
elements.append(Paragraph("Open the document and read it cover to cover. "
    "You're looking for five things:", body_style))
day1_items = [
    "☐ Trust type — is it revocable or irrevocable? This changes almost everything about your obligations.",
    "☐ Distribution standard — look for HEMS (Health, Education, Maintenance, Support) or other language. This governs every dollar you distribute.",
    "☐ Your powers — what can you do? Sell real estate? Borrow? Hire professionals? If it's not listed, you probably don't have that power.",
    "☐ Removal provisions — can you be removed? By whom? Under what conditions?",
    "☐ Termination rules — when does the trust end? What happens to the assets?",
]
for item in day1_items:
    elements.append(Paragraph(item, check_style))
elements.append(Paragraph(
    "Tip: Use a highlighter. Mark distribution standards in one color, "
    "your powers in another, beneficiary names in a third.",
    note_style))

# Day 2
elements.append(Paragraph("Day 2: Get an EIN (or Confirm You Don't Need One)", day_style))
day2_items = [
    "☐ If the trust is irrevocable, or if the grantor has died → Get an EIN from the IRS website (irs.gov/ein). Takes about 10 minutes.",
    "☐ If it's a revocable living trust and the grantor is still alive → Use the grantor's SSN. No EIN needed yet.",
    "☐ Save the EIN confirmation letter. You'll need it for tax filings and bank accounts.",
]
for item in day2_items:
    elements.append(Paragraph(item, check_style))
elements.append(Paragraph(
    "Note: You'll need a separate EIN when the trust becomes irrevocable "
    "(usually when the grantor dies).",
    note_style))

# Day 3
elements.append(Paragraph("Day 3: Open Dedicated Trust Accounts", day_style))
day3_items = [
    "☐ Open a dedicated trust checking account (not your personal account).",
    "☐ If the trust holds significant assets, open a trust savings or investment account.",
    "☐ Use the trust's EIN (or grantor's SSN) for the account.",
    "☐ Get debit cards and checks in the trust's name, not yours.",
    "☐ Never mix trust funds with personal funds — not for convenience, not for a day.",
]
for item in day3_items:
    elements.append(Paragraph(item, check_style))
elements.append(Paragraph(
    "This is the single most important separation rule. Commingling is the #1 "
    "way trustees create personal liability.",
    note_style))

# Day 4
elements.append(Paragraph("Day 4: Inventory the Assets", day_style))
day4_items = [
    "☐ List every asset the trust owns: real estate, bank accounts, investment accounts, personal property.",
    "☐ Note the current value and valuation date for each asset.",
    "☐ Take photos of physical assets (real estate, vehicles, valuables).",
    "☐ Get appraisals if needed (real estate, business interests, collectibles).",
    "☐ Note any debts or liabilities attached to trust assets.",
    "☐ Create a master asset list and store it with the trust document.",
]
for item in day4_items:
    elements.append(Paragraph(item, check_style))
elements.append(Paragraph(
    "You need to know what's in the safe before you can guard it.",
    note_style))

# Day 5
elements.append(Paragraph("Day 5: Notify the Beneficiaries", day_style))
day5_items = [
    "☐ Identify all beneficiaries named in the trust document.",
    "☐ Send a written notice to each beneficiary (email or certified mail).",
    "☐ Include: your name and contact information, the trust's name and date, what beneficiaries can expect (annual reports, distribution process).",
    "☐ Keep proof of delivery for every notice sent.",
    "☐ Note: UTC §813 requires keeping beneficiaries informed. This isn't optional in most states.",
]
for item in day5_items:
    elements.append(Paragraph(item, check_style))
elements.append(Paragraph(
    "Transparency is your best defense. A beneficiary who knows what's happening "
    "is far less likely to sue.",
    note_style))

# Day 6
elements.append(Paragraph("Day 6: Set Your Calendar", day_style))
day6_items = [
    "☐ Mark tax filing deadlines (Form 1041 due April 15 for calendar-year trusts).",
    "☐ Set annual report dates (if required by your state or the trust document).",
    "☐ Schedule required investment reviews (at minimum: annual).",
    "☐ Note any upcoming deadlines from the trust document (distributions, reviews, reports).",
    "☐ Set a recurring monthly reminder: 30 minutes to review trust activity.",
]
for item in day6_items:
    elements.append(Paragraph(item, check_style))
elements.append(Paragraph(
    "Put these on your calendar now, before life gets busy. "
    "Missed deadlines are the most common — and most preventable — trustee mistake.",
    note_style))

# Day 7
elements.append(Paragraph("Day 7: Document Everything", day_style))
day7_items = [
    "☐ Write a trustee log entry for each of the first six days.",
    "☐ For each entry: date, what you did, why you did it, what you decided.",
    "☐ Save copies of: trust document, EIN confirmation, bank account opening docs, beneficiary notices, asset inventory.",
    "☐ Store everything in one place (physical binder or digital vault).",
    "☐ Create a system for ongoing documentation (minutes, memos, dated notes).",
]
for item in day7_items:
    elements.append(Paragraph(item, check_style))
elements.append(Paragraph(
    "The court doesn't care what you intended. It cares what you can prove. "
    "Every decision, every communication, every action — write it down, date it, save it.",
    note_style))

# Divider
elements.append(Spacer(1, 16))
elements.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=16))

# After the first week
elements.append(Paragraph("After the First Week", section_style))
elements.append(Paragraph(
    "The first seven days are the hardest. Once the system is in place, "
    "maintenance drops to about one hour per month. Here's what to do next:",
    body_style))
after_items = [
    "☐ First 30 days: Complete asset valuations, set up recordkeeping system, confirm EIN and accounts.",
    "☐ First 60 days: Send initial beneficiary report, schedule first annual review, establish documentation routine.",
    "☐ First 90 days: Review tax strategy with a CPA, set up investment framework if applicable, confirm all formalities are in place.",
]
for item in after_items:
    elements.append(Paragraph(item, check_style))

# CTA
elements.append(Spacer(1, 20))
elements.append(HRFlowable(width="60%", thickness=1, color=GOLD, spaceAfter=12))
elements.append(Paragraph(
    "Want the full system?",
    cta_style))
elements.append(Paragraph(
    "TrustOffice automates everything this checklist covers — "
    "minutes, accounting, distributions, and beneficiary communication. "
    "Subscribe at trustoffice.app and get the full 27-lesson Trustee 101 course included.",
    ParagraphStyle('CTABody', parent=body_style, alignment=TA_CENTER, textColor=NAVY, fontSize=10)))

# Footer
elements.append(Spacer(1, 24))
elements.append(Paragraph(
    "Trustee 101 · Module 1 · Lesson 3",
    footer_style))
elements.append(Paragraph(
    "This checklist is educational, not legal advice. Consult your attorney for your specific situation.",
    footer_style))

# Build
doc.build(elements)
print(f"PDF generated: {output_path}")
print(f"Size: {os.path.getsize(output_path)} bytes")
