# Minutes router - handles minutes records and templates
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import io
import base64
import re

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from database import db
from dependencies import get_current_user, require_write_access, should_show_watermark, auto_update_onboarding
from models import MinutesCreate, MinutesResponse, MinutesTemplateCreate, MinutesTemplateResponse
from email_service import email_service

router = APIRouter(tags=["minutes"])


@router.post("/minutes", response_model=MinutesResponse)
async def create_minutes(minutes: MinutesCreate, background_tasks: BackgroundTasks, user: dict = Depends(require_write_access)):
    trust = await db.trusts.find_one({"trust_id": minutes.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": minutes.trust_id,
        "user_id": user["user_id"],
        "minutes_type": minutes.minutes_type.value,
        "meeting_date": minutes.meeting_date,
        "participants_text": minutes.participants_text,
        "decisions_text": minutes.decisions_text,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.minutes_records.insert_one(minutes_doc)
    
    # Link to distribution if provided
    if minutes.distribution_id:
        await db.distribution_records.update_one(
            {"distribution_id": minutes.distribution_id},
            {"$set": {"minutes_record_id": minutes_id}}
        )
    
    # Link to compensation payment if provided
    if minutes.compensation_payment_id:
        await db.compensation_payments.update_one(
            {"payment_id": minutes.compensation_payment_id},
            {"$set": {"minutes_record_id": minutes_id}}
        )
    
    await auto_update_onboarding(user["user_id"], minutes.trust_id)
    
    # Send notification email
    background_tasks.add_task(
        email_service.send_minutes_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", ""),
        minutes_type=minutes.minutes_type.value,
        meeting_date=minutes.meeting_date,
        participants=minutes.participants_text,
        decisions=minutes.decisions_text
    )
    
    return MinutesResponse(**minutes_doc)

@router.get("/minutes", response_model=List[MinutesResponse])
async def get_minutes(
    trust_id: Optional[str] = None, 
    search: Optional[str] = None,
    minutes_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Get minutes with optional search and filters"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    if minutes_type:
        query["minutes_type"] = minutes_type
    if date_from or date_to:
        date_query = {}
        if date_from:
            date_query["$gte"] = date_from
        if date_to:
            date_query["$lte"] = date_to
        query["meeting_date"] = date_query
    
    # Add text search across participants and decisions
    if search:
        search_term = re.escape(search.strip())
        query["$or"] = [
            {"participants_text": {"$regex": search_term, "$options": "i"}},
            {"decisions_text": {"$regex": search_term, "$options": "i"}}
        ]
    
    minutes = await db.minutes_records.find(query, {"_id": 0}).sort("meeting_date", -1).to_list(1000)
    return [MinutesResponse(**m) for m in minutes]

@router.get("/minutes/{minutes_id}", response_model=MinutesResponse)
async def get_minutes_by_id(minutes_id: str, user: dict = Depends(get_current_user)):
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return MinutesResponse(**minutes)


@router.put("/minutes/{minutes_id}")
async def update_minutes(minutes_id: str, request: Request, user: dict = Depends(require_write_access)):
    """Update minutes content, participants, or other attendees"""
    data = await request.json()
    
    # Only allow updating specific fields
    allowed_fields = ['decisions_text', 'participants_text', 'other_attendees_text']
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.minutes_records.update_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    return {"message": "Minutes updated", "updated_fields": list(update_data.keys())}


@router.delete("/minutes/{minutes_id}")
async def delete_minutes(minutes_id: str, user: dict = Depends(require_write_access)):
    result = await db.minutes_records.delete_one({"minutes_id": minutes_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return {"message": "Minutes deleted"}

def generate_minutes_pdf(minutes: dict, trust: dict, hide_watermark: bool = False) -> bytes:
    """Generate a professional legal-style PDF for minutes record with proper formatting"""
    import re
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        topMargin=0.75*inch, 
        bottomMargin=0.75*inch,
        leftMargin=1*inch,
        rightMargin=1*inch
    )
    
    # Custom styles for legal document appearance
    styles = getSampleStyleSheet()
    
    # Document title - trust name
    title_style = ParagraphStyle(
        'TrustTitle',
        parent=styles['Heading1'],
        fontName='Times-Bold',
        fontSize=16,
        alignment=1,  # Center
        spaceAfter=4,
        textColor=colors.HexColor('#010079')
    )
    
    # Document subtitle
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=12,
        alignment=1,  # Center
        spaceAfter=20,
        textColor=colors.HexColor('#333333')
    )
    
    # Section headers (WHEREAS, RESOLVED, etc.)
    section_header_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Times-Bold',
        fontSize=11,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor('#010079'),
        borderWidth=0,
        borderPadding=0,
        borderColor=colors.HexColor('#010079'),
    )
    
    # WHEREAS clause style - indented, formal
    whereas_style = ParagraphStyle(
        'Whereas',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        leading=15,
        leftIndent=0.25*inch,
        spaceBefore=6,
        spaceAfter=6,
        firstLineIndent=0,
    )
    
    # RESOLVED clause style - bold lead-in
    resolved_style = ParagraphStyle(
        'Resolved',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        leading=15,
        leftIndent=0.25*inch,
        spaceBefore=8,
        spaceAfter=8,
        firstLineIndent=0,
    )
    
    # Regular body text
    body_style = ParagraphStyle(
        'TrustBody',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        leading=15,
        spaceAfter=8,
        alignment=4,  # Justify
    )
    
    # Bullet point style
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=11,
        leading=15,
        leftIndent=0.5*inch,
        spaceBefore=4,
        spaceAfter=4,
        bulletIndent=0.25*inch,
    )
    
    # Label style (for signature lines)
    label_style = ParagraphStyle(
        'TrustLabel',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=10,
        textColor=colors.HexColor('#666666')
    )
    
    # Divider line style
    divider_style = ParagraphStyle(
        'Divider',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=8,
        alignment=1,  # Center
        spaceBefore=12,
        spaceAfter=12,
        textColor=colors.HexColor('#999999')
    )
    
    story = []
    
    # ==== DOCUMENT HEADER ====
    # Decorative top border
    story.append(Paragraph("═" * 60, divider_style))
    
    # Trust name as main title
    trust_name = trust.get('name', 'Trust')
    story.append(Paragraph(trust_name.upper(), title_style))
    
    # Meeting type as subtitle
    minutes_type = minutes.get('minutes_type', 'General').replace('_', ' ').title()
    story.append(Paragraph(f"MINUTES OF {minutes_type.upper()} MEETING", subtitle_style))
    
    story.append(Paragraph("═" * 60, divider_style))
    story.append(Spacer(1, 12))
    
    # ==== MEETING DETAILS TABLE ====
    meeting_date = minutes.get('meeting_date', 'N/A')
    if 'T' in meeting_date:
        meeting_date = meeting_date.split('T')[0]
    
    details_data = [
        ['Date of Meeting:', meeting_date],
        ['Type:', minutes_type],
        ['Trust:', trust.get('name', 'N/A')],
        ['Jurisdiction:', trust.get('jurisdiction', 'N/A')]
    ]
    
    details_table = Table(details_data, colWidths=[1.5*inch, 4.5*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Times-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Times-Roman'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#333333')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 16))
    
    # ==== TRUSTEES PRESENT ====
    if minutes.get('participants_text'):
        story.append(Paragraph("TRUSTEES PRESENT", section_header_style))
        participants = minutes.get('participants_text', '').split(',')
        for p in participants:
            if p.strip():
                story.append(Paragraph(f"• {p.strip()}, Trustee", bullet_style))
        story.append(Spacer(1, 12))
    
    # ==== OTHER ATTENDEES (if present) ====
    if minutes.get('other_attendees_text'):
        story.append(Paragraph("ALSO PRESENT", section_header_style))
        other_attendees = minutes.get('other_attendees_text', '').split(',')
        for a in other_attendees:
            if a.strip():
                story.append(Paragraph(f"• {a.strip()}", bullet_style))
        story.append(Spacer(1, 12))
    
    # ==== MINUTES BODY - WITH FORMATTING PRESERVATION ====
    decisions_text = minutes.get('decisions_text', '')
    if decisions_text:
        story.append(Paragraph("─" * 50, divider_style))
        story.append(Paragraph("MATTERS CONSIDERED AND RESOLUTIONS ADOPTED", section_header_style))
        story.append(Spacer(1, 8))
        
        # Process the text to preserve formatting
        story.extend(_parse_legal_document_text(decisions_text, styles, whereas_style, resolved_style, body_style, bullet_style, section_header_style))
    
    # ==== SIGNATURE BLOCK ====
    story.append(Spacer(1, 30))
    story.append(Paragraph("─" * 50, divider_style))
    story.append(Paragraph("CERTIFICATION", section_header_style))
    story.append(Paragraph(
        "The undersigned Trustee(s) hereby certify that the foregoing Minutes constitute a true, "
        "accurate, and complete record of the meeting and that all decisions recorded herein were "
        "made in good faith and in accordance with the Trust Indenture.",
        body_style
    ))
    story.append(Spacer(1, 24))
    
    # Signature lines
    participants = minutes.get('participants_text', '').split(',') if minutes.get('participants_text') else ['Trustee']
    for p in participants[:2]:  # Max 2 signature lines
        if p.strip():
            story.append(Spacer(1, 16))
            story.append(Paragraph('_' * 40, body_style))
            story.append(Paragraph(f'{p.strip()}, Trustee', label_style))
            story.append(Paragraph('Date: _________________', label_style))
    
    # ==== FOOTER ====
    story.append(Spacer(1, 30))
    story.append(Paragraph("═" * 60, divider_style))
    if not hide_watermark:
        story.append(Paragraph(
            f"Generated by TrustOffice on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}",
            ParagraphStyle('Footer', parent=styles['Normal'], fontName='Times-Italic', fontSize=8, alignment=1, textColor=colors.HexColor('#999999'))
        ))
    story.append(Paragraph(
        f"{trust_name} – Private Trust Minutes – Confidential",
        ParagraphStyle('FooterNote', parent=styles['Normal'], fontName='Times-Italic', fontSize=8, alignment=1, textColor=colors.HexColor('#666666'))
    ))
    
    doc.build(story)
    return buffer.getvalue()


def _parse_legal_document_text(text: str, styles, whereas_style, resolved_style, body_style, bullet_style, section_header_style) -> list:
    """
    Parse legal document text and return a list of ReportLab flowables with proper formatting.
    Handles WHEREAS clauses, RESOLVED clauses, section headers, bullet points, and regular paragraphs.
    """
    import re
    
    flowables = []
    
    # Split by double newlines first (paragraph breaks)
    paragraphs = re.split(r'\n\s*\n', text)
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Check for section dividers (═══ or ─── lines)
        if re.match(r'^[═─]{10,}$', para):
            flowables.append(Paragraph("─" * 40, ParagraphStyle(
                'InlineDivider', parent=styles['Normal'], fontSize=8, alignment=1, 
                spaceBefore=8, spaceAfter=8, textColor=colors.HexColor('#cccccc')
            )))
            continue
        
        # Check for all-caps section headers
        if para.isupper() and len(para) < 80 and not para.startswith('WHEREAS') and not para.startswith('RESOLVED'):
            flowables.append(Paragraph(para, section_header_style))
            continue
        
        # Handle multi-line paragraphs - split by single newlines
        lines = para.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Escape special characters for ReportLab
            safe_line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            # WHEREAS clauses
            if line.upper().startswith('WHEREAS'):
                # Bold the "WHEREAS" part
                formatted = safe_line.replace('WHEREAS', '<b>WHEREAS</b>', 1)
                flowables.append(Paragraph(formatted, whereas_style))
            
            # NOW THEREFORE or BE IT RESOLVED
            elif 'NOW, THEREFORE' in line.upper() or 'NOW THEREFORE' in line.upper():
                formatted = re.sub(r'(NOW,?\s*THEREFORE)', r'<b>\1</b>', safe_line, flags=re.IGNORECASE)
                flowables.append(Paragraph(formatted, resolved_style))
            
            elif line.upper().startswith('BE IT RESOLVED') or line.upper().startswith('RESOLVED'):
                formatted = re.sub(r'^(BE IT RESOLVED|RESOLVED)', r'<b>\1</b>', safe_line, flags=re.IGNORECASE)
                flowables.append(Paragraph(formatted, resolved_style))
            
            elif line.upper().startswith('BE IT FURTHER RESOLVED'):
                formatted = re.sub(r'^(BE IT FURTHER RESOLVED)', r'<b>\1</b>', safe_line, flags=re.IGNORECASE)
                flowables.append(Paragraph(formatted, resolved_style))
            
            # Bullet points (• or -)
            elif line.startswith('•') or line.startswith('-') or line.startswith('*'):
                bullet_text = line[1:].strip()
                safe_bullet = bullet_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                flowables.append(Paragraph(f"• {safe_bullet}", bullet_style))
            
            # Indented bullet points (starting with spaces then bullet)
            elif re.match(r'^\s+[•\-\*]', line):
                bullet_text = re.sub(r'^\s+[•\-\*]\s*', '', line)
                safe_bullet = bullet_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                # Deeper indent for nested bullets
                nested_bullet_style = ParagraphStyle(
                    'NestedBullet', parent=bullet_style, leftIndent=0.75*inch
                )
                flowables.append(Paragraph(f"○ {safe_bullet}", nested_bullet_style))
            
            # Section dividers (═══ or ─── lines)
            elif re.match(r'^[═─]{10,}$', line):
                flowables.append(Paragraph("─" * 40, ParagraphStyle(
                    'InlineDivider', parent=styles['Normal'], fontSize=8, alignment=1, 
                    spaceBefore=8, spaceAfter=8, textColor=colors.HexColor('#cccccc')
                )))
            
            # Key-value pairs (Label: Value)
            elif ':' in line and line.index(':') < 30:
                parts = line.split(':', 1)
                if len(parts) == 2 and parts[0].strip():
                    label = parts[0].strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    value = parts[1].strip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    formatted = f"<b>{label}:</b> {value}"
                    flowables.append(Paragraph(formatted, body_style))
                else:
                    flowables.append(Paragraph(safe_line, body_style))
            
            # Regular paragraph
            else:
                flowables.append(Paragraph(safe_line, body_style))
    
    return flowables

@router.get("/minutes/{minutes_id}/pdf")
async def get_minutes_pdf(minutes_id: str, user: dict = Depends(get_current_user)):
    """Generate and return PDF for minutes record"""
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    trust = await db.trusts.find_one(
        {"trust_id": minutes["trust_id"], "user_id": user["user_id"]},
        {"_id": 0}
    )
    
    # Check if watermark should be shown (soft gating based on subscription)
    show_watermark = await should_show_watermark(user["user_id"])
    
    pdf_bytes = generate_minutes_pdf(minutes, trust or {}, hide_watermark=not show_watermark)
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    return {
        "pdf_base64": pdf_base64,
        "filename": f"minutes_{minutes_id}.pdf"
    }

# ==================== MINUTES TEMPLATES ====================

# ==================== MINUTES TEMPLATES ENDPOINTS ====================

def generate_template_document(trust: dict, template_type: str, template_data: dict) -> str:
    """Generate the full text minutes document from template"""
    trust_name = trust.get("name", "[Trust Name]")
    trustees = trust.get("trustees", [])
    trustee_names = trustees if trustees else [trust.get("role", "Trustee")]
    
    # Get data from template_data with defaults
    minute_number = template_data.get("minute_number", f"{datetime.now().year}-001")
    meeting_date = template_data.get("meeting_date", datetime.now().strftime("%B %d, %Y"))
    meeting_time = template_data.get("meeting_time", "10:00 AM")
    meeting_type = template_data.get("meeting_type", "unanimous_written_consent")
    trustees_present = template_data.get("trustees_present", trustee_names)
    trust_indenture_date = template_data.get("trust_indenture_date", "[Date of Trust Indenture]")
    
    meeting_type_text = {
        "in_person": f"In person at {template_data.get('meeting_location', '[Location]')}",
        "video_conference": "By telephone/video conference",
        "unanimous_written_consent": "By unanimous written consent without meeting"
    }.get(meeting_type, "By unanimous written consent without meeting")
    
    # Build the document
    doc = f"""TRUST MINUTES
Private Irrevocable Ecclesiastical Trust

Trust Name: {trust_name}
Minute Number: {minute_number}
Date of Meeting: {meeting_date}
Time: {meeting_time}
Location: {meeting_type_text}

═══════════════════════════════════════════════════════════════════════════════

TRUSTEES PRESENT

"""
    
    for trustee in trustees_present:
        doc += f"• {trustee}, Trustee\n"
    
    doc += f"""
Quorum: YES

═══════════════════════════════════════════════════════════════════════════════

OPENING STATEMENT

The Trustees, acting in their fiduciary capacity and not in any personal capacity, convened this meeting to conduct the business of the Trust in accordance with the Declaration and Indenture of Private Irrevocable Trust dated {trust_indenture_date}, and the principles of Natural Law, Common Law, Equity, and Ecclesiastical Jurisdiction declared therein.

All Trustees present affirm they are acting as living men and women in private capacity, and not as surety, representative, or accommodation party for any artificial PERSON or all-capital-letter NAME.

═══════════════════════════════════════════════════════════════════════════════

MATTERS CONSIDERED AND RESOLUTIONS ADOPTED

"""
    
    # Generate template-specific content
    if template_type == "general_meeting":
        doc += generate_general_meeting_content(template_data)
    elif template_type == "distribution_to_beneficiaries":
        doc += generate_distribution_content(template_data)
    elif template_type == "acceptance_of_property":
        doc += generate_property_acceptance_content(template_data)
    elif template_type == "disposition_of_asset":
        doc += generate_disposition_content(template_data)
    elif template_type == "appointment_additional_trustee":
        doc += generate_trustee_appointment_content(template_data, "additional")
    elif template_type == "appointment_successor_trustee":
        doc += generate_trustee_appointment_content(template_data, "successor")
    elif template_type == "designation_of_beneficiaries":
        doc += generate_beneficiary_designation_content(template_data)
    elif template_type == "bank_account_authorization":
        doc += generate_bank_account_content(template_data)
    elif template_type == "change_of_situs":
        doc += generate_change_of_situs_content(template_data)
    elif template_type == "benevolence_approval":
        doc += generate_benevolence_approval_content(template_data)
    # New templates
    elif template_type == "investment_policy":
        doc += generate_investment_policy_content(template_data)
    elif template_type == "loan_authorization":
        doc += generate_loan_authorization_content(template_data)
    elif template_type == "insurance_authorization":
        doc += generate_insurance_authorization_content(template_data)
    elif template_type == "annual_review":
        doc += generate_annual_review_content(template_data)
    elif template_type == "quarterly_review":
        doc += generate_quarterly_review_content(template_data)
    elif template_type == "trustee_compensation":
        doc += generate_trustee_compensation_content(template_data)
    elif template_type == "trustee_resignation":
        doc += generate_trustee_resignation_content(template_data)
    elif template_type == "beneficiary_request_denial":
        doc += generate_beneficiary_denial_content(template_data)
    elif template_type == "hems_distribution":
        doc += generate_hems_distribution_content(template_data)
    elif template_type == "beneficiary_loan":
        doc += generate_beneficiary_loan_content(template_data)
    # Batch 2 templates
    elif template_type == "trust_amendment":
        doc += generate_trust_amendment_content(template_data)
    elif template_type == "power_of_attorney":
        doc += generate_power_of_attorney_content(template_data)
    elif template_type == "trust_termination":
        doc += generate_trust_termination_content(template_data)
    elif template_type == "real_estate_purchase":
        doc += generate_real_estate_purchase_content(template_data)
    elif template_type == "business_interest_acquisition":
        doc += generate_business_interest_content(template_data)
    elif template_type == "real_estate_lease":
        doc += generate_real_estate_lease_content(template_data)
    elif template_type == "fiscal_year_election":
        doc += generate_fiscal_year_content(template_data)
    elif template_type == "tax_filing_authorization":
        doc += generate_tax_filing_content(template_data)
    elif template_type == "emergency_ratification":
        doc += generate_emergency_ratification_content(template_data)
    elif template_type == "conflict_of_interest":
        doc += generate_conflict_of_interest_content(template_data)
    
    # Add adjournment and certification
    doc += f"""
═══════════════════════════════════════════════════════════════════════════════

ADJOURNMENT

There being no further business to come before the Board of Trustees, the meeting was adjourned at {template_data.get('adjournment_time', meeting_time)}.

═══════════════════════════════════════════════════════════════════════════════

CERTIFICATION AND AUTHENTICATION

The undersigned Trustees hereby certify that the foregoing Minutes constitute a true, accurate, and complete record of the meeting and resolutions adopted, and that all decisions recorded herein were made in good faith, in accordance with the Trust Indenture, and for the benefit of the Trust and its Beneficiaries.

These Trust Minutes are executed in the private capacity of the Trustees as living men and women, and not as surety, representative, or accommodation party for any artificial PERSON or all-capital-letter NAME.

All Trust Minutes and records are private and confidential, held under Common Law Copyright, and are not to be disclosed to any third party except as unanimously authorized by the Board of Trustees.

═══════════════════════════════════════════════════════════════════════════════

TRUSTEE SIGNATURES

"""
    
    for trustee in trustees_present:
        doc += f"""
Trustee: {trustee}
Signature: _____________________________________
Date: _________________

"""
    
    doc += f"""
═══════════════════════════════════════════════════════════════════════════════

END OF TRUST MINUTES
{trust_name} – Private Trust Minutes – Common Law Copyright – Not for Public Disclosure
"""
    
    return doc

def generate_general_meeting_content(data: dict) -> str:
    """Generate content for general meeting with multiple resolutions"""
    resolutions = data.get("resolutions", [])
    content = ""
    
    if not resolutions:
        # Default placeholder resolution
        content += """Resolution 1: [Title/Subject]

WHEREAS, [state the background, circumstances, or reason for the resolution];

NOW, THEREFORE, BE IT RESOLVED that the Board of Trustees hereby:
• [State the specific action, decision, or authorization clearly and completely.]

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    else:
        for i, res in enumerate(resolutions, 1):
            content += f"""Resolution {i}: {res.get('title', '[Title]')}

"""
            for whereas in res.get('whereas_clauses', ['[State the background, circumstances, or reason]']):
                content += f"WHEREAS, {whereas};\n\n"
            
            content += "NOW, THEREFORE, BE IT RESOLVED that the Board of Trustees hereby:\n"
            for resolved in res.get('resolved_clauses', ['[State the specific action]']):
                content += f"• {resolved}\n"
            
            content += f"""
Vote: {res.get('vote', 'Unanimous approval')}
Effective Date: {res.get('effective_date', 'Immediately upon adoption')}

"""
    
    return content

def generate_distribution_content(data: dict) -> str:
    """Generate content for distribution to beneficiaries"""
    total = data.get("distribution_total", 0)
    items = data.get("distribution_items", [])
    dist_date = data.get("distribution_date", "[Date]")
    characterization = data.get("distribution_characterization", "income")
    article_ref = data.get("article_ref_distribution", "")
    beneficiary_standard = data.get("beneficiary_standard", "")
    
    article_text = f", pursuant to {article_ref}" if article_ref else ""
    standard_text = f" The distribution standard is: {beneficiary_standard}." if beneficiary_standard else ""
    
    content = f"""Resolution 1: Distribution of Trust Proceeds

WHEREAS, the Trustees, in the exercise of their discretion{article_text}, deem it appropriate to make a distribution to the Beneficiaries;{standard_text}

NOW, THEREFORE, BE IT RESOLVED that:

• A distribution in the total amount of ${total:,.2f} shall be made from the Trust to the Beneficiaries as follows:

"""
    
    if items:
        for item in items:
            name = item.get("beneficiary_name", "[Beneficiary Name]")
            amount = item.get("amount", 0)
            percentage = item.get("percentage", 0)
            content += f"    • {name}: ${amount:,.2f} (representing {percentage}% beneficial interest)\n"
    else:
        content += "    • [Beneficiary Name]: $__________ (representing ____% beneficial interest)\n"
    
    char_text = {"income": "income", "principal": "principal", "return_of_corpus": "return of corpus"}.get(characterization, "income")
    
    content += f"""
• Such distribution shall be made on or before {dist_date}.

• The distribution is characterized as {char_text} for purposes of the Trust's internal accounting.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    
    return content

def generate_property_acceptance_content(data: dict) -> str:
    """Generate content for acceptance of additional property into trust"""
    grantor = data.get("grantor_name", "[Grantor/Creator]")
    description = data.get("property_description", "[Description of property]")
    value = data.get("property_value")
    conveyance_date = data.get("conveyance_date", "[Date]")
    
    value_text = f"${value:,.2f}" if value else "$______________"
    
    content = f"""Resolution 1: Acceptance of Additional Property into Trust

WHEREAS, {grantor} has offered to convey the following property to the Trust:

    Description of property: {description}
    Approximate value: {value_text}

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees accepts the conveyance of the above-described property into the corpus of this Trust.

• The Trustees are authorized to execute any and all documents necessary to accept and perfect title to said property in the name of the Trust.

• Schedule A to the Trust Indenture is hereby amended to include the above-described property, with an effective date of conveyance of {conveyance_date}.

Vote: Unanimous approval
Requires unanimous consent per Indenture: YES
Effective Date: Immediately upon adoption

"""
    
    return content

def generate_disposition_content(data: dict) -> str:
    """Generate content for disposition/sale of an asset"""
    asset_description = data.get("disposition_asset_description", "[Asset Description]")
    disposition_reason = data.get("disposition_reason", "sale")
    disposition_date = data.get("disposition_date", "[Date]")
    disposition_value = data.get("disposition_value")
    disposition_recipient = data.get("disposition_recipient", "")
    disposition_notes = data.get("disposition_notes", "")
    article_ref = data.get("article_ref_asset_disposition", data.get("article_ref_distribution", "Article [X]"))
    
    reason_text = {
        "sale": "the Trustees have determined it is in the best interest of the Trust to sell",
        "transfer": "the Trustees have determined it is appropriate to transfer",
        "donation": "the Trustees have determined to donate",
        "destruction": "the asset has been destroyed or rendered unusable",
        "other": "the Trustees have determined to dispose of"
    }.get(disposition_reason, "the Trustees have determined to dispose of")
    
    value_text = f"${disposition_value:,.2f}" if disposition_value else "[Fair Market Value]"
    
    recipient_text = f" to {disposition_recipient}" if disposition_recipient else ""
    
    content = f"""Resolution: Disposition of Trust Asset

WHEREAS, pursuant to {article_ref} of the Trust Indenture, the Trustees have authority to manage, sell, exchange, or otherwise dispose of Trust property as they deem prudent and in the best interest of the Trust;

WHEREAS, the following property is currently held in the corpus of the Trust and recorded on Schedule A:

    {asset_description}

WHEREAS, {reason_text} this property{recipient_text};

"""
    
    if disposition_reason == "sale":
        content += f"""WHEREAS, the Trustees have negotiated a sale price of {value_text}, which they believe represents fair market value for the property;

"""
    elif disposition_reason == "transfer" and disposition_recipient:
        content += f"""WHEREAS, this transfer to {disposition_recipient} is being made {"in exchange for consideration of " + value_text if disposition_value else "for appropriate consideration as determined by the Trustees"};

"""
    elif disposition_reason == "donation":
        content += f"""WHEREAS, the fair market value of the property at the time of donation is approximately {value_text};

"""
    elif disposition_reason == "destruction":
        content += """WHEREAS, the loss of this property has been documented and any applicable insurance claims have been or will be filed;

"""
    
    if disposition_notes:
        content += f"""WHEREAS, the Trustees note the following additional details: {disposition_notes};

"""
    
    content += f"""NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees approves the {"sale" if disposition_reason == "sale" else "disposition"} of the above-described property.

• The Trustees are authorized to execute any and all documents necessary to complete the {"sale" if disposition_reason == "sale" else disposition_reason} and transfer title to the {"purchaser" if disposition_reason == "sale" else "recipient"}.

• Schedule A to the Trust Indenture is hereby amended to reflect the removal of this property from the Trust corpus, effective {disposition_date}.

• {"Any proceeds from this sale shall be deposited into the Trust's designated accounts and managed in accordance with the Trust Indenture." if disposition_reason == "sale" else "This disposition is recorded as part of the permanent Trust records."}

Vote: Unanimous approval
Requires unanimous consent per Indenture: YES
Effective Date: {disposition_date}

"""
    
    return content

def generate_trustee_appointment_content(data: dict, appointment_type: str) -> str:
    """Generate content for trustee appointment (additional or successor)"""
    new_trustee = data.get("new_trustee_name", "[New Trustee Name]")
    gender = data.get("new_trustee_gender", "man")
    departing_trustee = data.get("departing_trustee_name", "")
    departing_reason = data.get("departing_reason", "resigned")
    signature_req = data.get("signature_requirement", "any_one")
    threshold = data.get("signature_threshold")
    
    if appointment_type == "successor":
        whereas_reason = f"{departing_trustee} has {departing_reason}"
        title = "Appointment of Successor Trustee"
        role_text = "Successor Trustee"
    else:
        whereas_reason = "the existing Trustee(s) deem it prudent and in the best interest of the Trust to appoint an additional Trustee"
        title = "Appointment of Additional Trustee"
        role_text = "an additional Trustee"
    
    sig_text = {
        "any_one": "Any one Trustee may sign individually for all transactions without limit.",
        "any_two": "Any two Trustees must sign jointly for all transactions.",
        "all_trustees": f"All Trustees must sign jointly for transactions exceeding ${threshold:,.2f}." if threshold else "All Trustees must sign jointly for all transactions.",
        "threshold": f"Any one Trustee may sign individually for transactions up to ${threshold:,.2f}, and any two Trustees must sign jointly for transactions exceeding that amount." if threshold else "Any one Trustee may sign individually for transactions up to $[amount]."
    }.get(signature_req, "Any one Trustee may sign individually for all transactions.")
    
    content = f"""Resolution 1: {title}

WHEREAS, the Trust Indenture provides for the appointment of {'successor' if appointment_type == 'successor' else 'additional'} Trustees by decision of the Board of Trustees, or by appointment of the Protector, or by other means as provided in the Indenture;

WHEREAS, {whereas_reason};

WHEREAS, {new_trustee}, a living {gender} acting in private capacity, has been identified as a suitable and qualified person to serve as Trustee of this Trust, and has expressed willingness to accept such appointment;

NOW, THEREFORE, BE IT RESOLVED that:

• {new_trustee} is hereby appointed as {role_text} of this Trust, effective immediately upon acceptance of this appointment.

• Upon acceptance, {new_trustee} shall have all the duties, rights, titles, powers, and discretions of a Trustee as set forth in the Trust Indenture, and shall serve as a member of the Board of Trustees with equal authority to the existing Trustees.

• Legal title to the Trust property shall vest in {new_trustee} collectively with the existing Trustee(s) as the Board of Trustees, without the necessity of any further act or conveyance.

• {new_trustee} shall execute the Trustee Acceptance and Oath attached hereto as Exhibit A.

• The existing Trustees shall take all actions necessary to notify financial institutions, service providers, and other relevant parties of the appointment.

Vote: Unanimous approval
Requires unanimous consent per Indenture: YES
Effective Date: Immediately upon adoption

───────────────────────────────────────────────────────────────────────────────

Resolution 2: Signature Authority and Banking Powers

WHEREAS, the appointment of {'' if appointment_type == 'additional' else 'a successor '}Trustee may affect signature authority on financial accounts and banking relationships;

WHEREAS, the Board of Trustees desires to establish clear signature requirements for the administration of Trust accounts;

NOW, THEREFORE, BE IT RESOLVED that:

• {new_trustee} is authorized to act as a signatory on all financial accounts of the Trust.

• Signature Requirements: {sig_text}

• The Trustees are authorized to update signature cards, resolutions, and certifications with all financial institutions.

• An updated Certification of Trust reflecting the appointment shall be prepared and executed by all Trustees.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    
    # Add Exhibit A - Trustee Acceptance
    content += f"""
═══════════════════════════════════════════════════════════════════════════════

EXHIBIT A – TRUSTEE ACCEPTANCE AND OATH

I, {new_trustee}, a living {gender} acting in private capacity, hereby accept the appointment as {'Successor' if appointment_type == 'successor' else 'Additional'} Trustee of this Trust.

I affirm and declare:

1. I have read the Declaration and Indenture of Private Irrevocable Trust and understand my duties, obligations, and responsibilities as Trustee.

2. I agree to faithfully and diligently perform all duties as Trustee in accordance with the Trust Indenture and applicable principles of Natural Law, Common Law, and Equity.

3. I will act at all times in the best interest of the Trust and its Beneficiaries, with loyalty, prudence, and good faith.

4. I understand that I am accepting this appointment in my private capacity as a living {gender}, and not as surety, representative, or accommodation party for any artificial PERSON or all-capital-letter NAME.

5. I agree to maintain the confidentiality of all Trust matters and records.

Effective Date of Appointment: {data.get('effective_date', '[Date]')}


_____________________________________
{new_trustee}
Date: _________________


WITNESS (optional but recommended):

_____________________________________
Witness Signature
Printed Name: __________________________________
Date: _________________

"""
    
    return content

def generate_beneficiary_designation_content(data: dict) -> str:
    """Generate content for designation of beneficiaries"""
    beneficiaries = data.get("beneficiaries", [])
    designation_type = data.get("designation_type", "initial")  # initial, amendment, restatement
    total_units = data.get("total_units", 100)
    
    type_text = {
        "initial": "establish the initial",
        "amendment": "amend the existing",
        "restatement": "restate in full the"
    }.get(designation_type, "establish the")
    
    content = f"""Resolution 1: Designation of Beneficiaries and Units of Beneficial Interest

WHEREAS, the Trust Indenture provides for the designation of Beneficiaries and the allocation of Units of Beneficial Interest by the Board of Trustees;

WHEREAS, the Trustees desire to {type_text} designation of Beneficiaries and allocation of beneficial interests;

NOW, THEREFORE, BE IT RESOLVED that the Board of Trustees hereby designates the following as Beneficiaries of this Trust and allocates Units of Beneficial Interest as follows:

"""
    
    if beneficiaries:
        for ben in beneficiaries:
            name = ben.get("name", "[Beneficiary Name]")
            units = ben.get("units", 0)
            percentage = ben.get("percentage", 0)
            relationship = ben.get("relationship", "")
            rel_text = f" ({relationship})" if relationship else ""
            content += f"    • {name}{rel_text}: {units} Units ({percentage}% beneficial interest)\n"
    else:
        content += "    • [Beneficiary Name]: _____ Units (_____% beneficial interest)\n"
    
    content += f"""
Total Units of Beneficial Interest: {total_units} Units (100%)

BE IT FURTHER RESOLVED that:

• The above designations shall be effective immediately and shall supersede any prior designation of beneficiaries.

• Each Beneficiary's interest is subject to all terms and conditions of the Trust Indenture, including any spendthrift provisions.

• The Trustees reserve the right to amend, modify, or revoke these designations at any time in accordance with the Trust Indenture.

Vote: Unanimous approval
Requires unanimous consent per Indenture: YES
Effective Date: Immediately upon adoption

"""
    
    return content

def generate_bank_account_content(data: dict) -> str:
    """Generate content for bank account authorization"""
    bank_name = data.get("bank_name", "[Bank Name]")
    account_type = data.get("account_type", "checking")  # checking, savings, brokerage, money_market
    purpose = data.get("purpose", "general trust administration")
    authorized_signers = data.get("authorized_signers", [])
    signature_requirement = data.get("signature_requirement", "any_one")
    initial_deposit = data.get("initial_deposit")
    
    account_type_text = {
        "checking": "checking account",
        "savings": "savings account",
        "brokerage": "brokerage/investment account",
        "money_market": "money market account"
    }.get(account_type, "account")
    
    sig_text = {
        "any_one": "Any one authorized Trustee may sign individually for all transactions.",
        "any_two": "Any two authorized Trustees must sign jointly for all transactions.",
        "threshold": f"Any one Trustee may sign for transactions up to ${data.get('signature_threshold', 10000):,.2f}; two signatures required above that amount."
    }.get(signature_requirement, "Any one authorized Trustee may sign individually.")
    
    deposit_text = f"${initial_deposit:,.2f}" if initial_deposit else "[Amount]"
    
    content = f"""Resolution 1: Authorization to Open Bank Account

WHEREAS, the Trustees deem it necessary and appropriate to establish a {account_type_text} for the purpose of {purpose};

WHEREAS, the Trust Indenture authorizes the Trustees to open and maintain bank accounts in the name of the Trust;

NOW, THEREFORE, BE IT RESOLVED that:

• The Trustees are hereby authorized to open a {account_type_text} at {bank_name} in the name of this Trust.

• The account shall be titled in substantially the following form:
  "[Trust Name], a Private Irrevocable Trust"
  or such similar title as the financial institution may require.

• The following Trustees are designated as authorized signatories on the account:
"""
    
    if authorized_signers:
        for signer in authorized_signers:
            content += f"    • {signer}, Trustee\n"
    else:
        content += "    • [Trustee Names], Trustee\n"
    
    content += f"""
• Signature Authority: {sig_text}

• The Trustees are authorized to deposit an initial amount of {deposit_text} from existing Trust funds or from new contributions to the Trust.

• The Trustees are authorized to execute any and all documents, agreements, signature cards, resolutions, or certifications required by the financial institution to open and maintain the account.

• Online banking and electronic transfer capabilities may be established as deemed appropriate by the Trustees.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    
    return content

def generate_change_of_situs_content(data: dict) -> str:
    """Generate content for change of situs"""
    current_situs = data.get("current_situs", "[Current State/Jurisdiction]")
    new_situs = data.get("new_situs", "[New State/Jurisdiction]")
    effective_date = data.get("effective_date", "[Date]")
    reasons = data.get("reasons", [])
    
    content = f"""Resolution 1: Change of Trust Situs

WHEREAS, the Trust is currently administered and has its principal place of administration (situs) in {current_situs};

WHEREAS, the Trustees have determined that it is in the best interest of the Trust and its Beneficiaries to change the situs of the Trust to {new_situs};

"""
    
    if reasons:
        content += "WHEREAS, the reasons for this change include:\n"
        for reason in reasons:
            content += f"    • {reason}\n"
        content += "\n"
    else:
        content += """WHEREAS, such change is being made for reasons including, but not limited to: favorable trust laws, tax considerations, proximity to Trustees or Beneficiaries, or administrative convenience;

"""
    
    content += f"""WHEREAS, the Trust Indenture permits the Trustees to change the situs of the Trust;

NOW, THEREFORE, BE IT RESOLVED that:

• The situs of this Trust is hereby changed from {current_situs} to {new_situs}, effective {effective_date}.

• Henceforth, the Trust shall be administered under the laws of {new_situs}, to the extent such laws do not conflict with the express terms of the Trust Indenture or the ecclesiastical nature of this Trust.

• The principal place of administration of the Trust shall be located in {new_situs}.

• All references in the Trust Indenture or any prior Trust Minutes to the original situs or governing law shall be deemed amended to reflect the new situs of {new_situs}.

• The Trustees are authorized to:
    • Update the Trust's records to reflect the change of situs
    • Notify all financial institutions, service providers, and relevant parties
    • File any required notices or registrations in {new_situs}
    • Execute any documents necessary to effectuate this change

BE IT FURTHER RESOLVED that this change of situs shall not affect:
    • The validity or continuity of this Trust
    • The interests of any Beneficiary
    • Any existing rights, duties, or obligations under the Trust Indenture
    • The Trust's status as a private, ecclesiastical trust operating under Common Law principles

Vote: Unanimous approval
Requires unanimous consent per Indenture: YES
Effective Date: {effective_date}

"""
    
    return content

def generate_benevolence_approval_content(data: dict) -> str:
    """Generate content for benevolence assistance approval"""
    beneficiary_name = data.get("beneficiary_name", "[Beneficiary Name]")
    beneficiary_type = data.get("beneficiary_type", "individual")
    purpose = data.get("benevolence_purpose", "assistance")
    purpose_description = data.get("purpose_description", "[Description of need]")
    amount = data.get("amount", 0)
    payment_method = data.get("payment_method", "check")
    criteria_met = data.get("criteria_met", [])
    
    type_text = {
        "individual": "an individual",
        "family": "a family",
        "organization": "an organization"
    }.get(beneficiary_type, "an individual")
    
    purpose_text = {
        "medical": "medical expenses and healthcare needs",
        "housing": "housing assistance and shelter",
        "education": "educational expenses and advancement",
        "food_necessities": "food and basic necessities",
        "utilities": "utility payments and essential services",
        "transportation": "transportation needs",
        "emergency": "emergency relief and crisis assistance",
        "spiritual": "spiritual development and ministry support",
        "other": "charitable assistance"
    }.get(purpose, "charitable assistance")
    
    content = f"""Resolution 1: Approval of Benevolence Assistance

WHEREAS, this Trust operates as a private ecclesiastical trust with charitable purposes, consistent with the principles set forth in the Trust Indenture;

WHEREAS, the Board of Trustees has received and reviewed a request for benevolence assistance from {beneficiary_name}, {type_text}, for the purpose of {purpose_text};

WHEREAS, the Trustees have evaluated the request and determined that:
    • The need is genuine and verified
    • The assistance aligns with the charitable purposes of this Trust
    • The recipient meets the criteria established for benevolence assistance
    • Providing this assistance is consistent with sound fiduciary principles

WHEREAS, the following criteria have been confirmed:
"""
    
    if criteria_met:
        for criterion in criteria_met:
            content += f"    • {criterion}\n"
    else:
        content += """    • Need has been verified through appropriate inquiry
    • Assistance is consistent with the Trust's charitable mission
    • Resources are available to provide the requested assistance
    • No conflict of interest exists among the Trustees
"""
    
    content += f"""
WHEREAS, the request is summarized as follows:
    Beneficiary: {beneficiary_name}
    Type: {beneficiary_type.title()}
    Purpose: {purpose_description}
    Amount Requested: ${amount:,.2f}

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby approves benevolence assistance to {beneficiary_name} in the amount of ${amount:,.2f} for the purpose described above.

• The assistance shall be disbursed via {payment_method} within a reasonable time following adoption of this resolution.

• This benevolence grant is made without any obligation of repayment and is intended solely to assist with the stated need.

• The Trustees affirm that this assistance is made in furtherance of the Trust's charitable purposes and is consistent with the Trust Indenture.

• A record of this benevolence grant shall be maintained in the Trust's Benevolence Log for proper documentation and compliance purposes.

BE IT FURTHER RESOLVED that:

• The Trustees have exercised due diligence in evaluating this request and have acted in good faith.

• This grant does not create any ongoing obligation or entitlement to future assistance.

• All standard documentation requirements for benevolence grants shall be completed and maintained.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    
    return content


# ==================== NEW TEMPLATES ====================

def generate_investment_policy_content(data: dict) -> str:
    """Generate content for investment policy approval"""
    policy_type = data.get("policy_type", "adopt")  # adopt, amend, review
    risk_tolerance = data.get("risk_tolerance", "moderate")
    asset_allocation = data.get("asset_allocation", [])
    restrictions = data.get("investment_restrictions", [])
    review_frequency = data.get("review_frequency", "annually")
    
    action_text = {
        "adopt": "adopt a formal Investment Policy Statement",
        "amend": "amend the existing Investment Policy Statement",
        "review": "review and reaffirm the current Investment Policy Statement"
    }.get(policy_type, "adopt a formal Investment Policy Statement")
    
    content = f"""Resolution 1: Investment Policy {policy_type.title()}

WHEREAS, the prudent administration of Trust assets requires a clearly defined investment policy;

WHEREAS, the Board of Trustees has a fiduciary duty to invest Trust assets in accordance with the Prudent Investor Rule and applicable principles of trust administration;

WHEREAS, the Trustees desire to {action_text} governing the investment of Trust assets;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby {'adopts' if policy_type == 'adopt' else 'approves'} the following Investment Policy Statement for this Trust:

INVESTMENT OBJECTIVES:
    Primary Objective: Preservation of capital and purchasing power
    Secondary Objective: Generation of income sufficient for Trust purposes
    Tertiary Objective: Long-term growth consistent with risk tolerance

RISK TOLERANCE: {risk_tolerance.title()}
"""

    if asset_allocation:
        content += "\nTARGET ASSET ALLOCATION:\n"
        for allocation in asset_allocation:
            content += f"    • {allocation.get('asset_class', 'Asset Class')}: {allocation.get('percentage', 0)}%\n"
    else:
        content += """
TARGET ASSET ALLOCATION:
    • Fixed Income Securities: 40-60%
    • Equity Securities: 30-50%
    • Cash and Cash Equivalents: 5-15%
    • Alternative Investments: 0-10%
"""

    if restrictions:
        content += "\nINVESTMENT RESTRICTIONS:\n"
        for restriction in restrictions:
            content += f"    • {restriction}\n"
    else:
        content += """
INVESTMENT RESTRICTIONS:
    • No speculative or margin trading
    • No investments in derivatives except for hedging purposes
    • No single security shall exceed 10% of portfolio value
    • No investments in entities that conflict with Trust purposes
"""

    content += f"""
REVIEW AND MONITORING:
    • Investment performance shall be reviewed {review_frequency}
    • Asset allocation shall be rebalanced when deviation exceeds 5%
    • The Investment Policy shall be reviewed and reaffirmed annually

• The Trustees are authorized to engage qualified investment advisors and managers as needed.

• All investment decisions shall be documented and made in accordance with this policy.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    return content


def generate_loan_authorization_content(data: dict) -> str:
    """Generate content for loan authorization (making or receiving)"""
    loan_direction = data.get("loan_direction", "making")  # making or receiving
    borrower_name = data.get("borrower_name", "[Borrower Name]")
    lender_name = data.get("lender_name", "[Lender Name]")
    loan_amount = float(data.get("loan_amount", 0))
    interest_rate = data.get("interest_rate", "AFR")
    term_months = data.get("term_months", 60)
    purpose = data.get("loan_purpose", "")
    collateral = data.get("collateral_description", "")
    
    if loan_direction == "making":
        content = f"""Resolution 1: Authorization of Loan from Trust

WHEREAS, {borrower_name} has requested a loan from this Trust in the principal amount of ${loan_amount:,.2f};

WHEREAS, the Board of Trustees has evaluated this loan request and determined that:
    • The loan serves a legitimate purpose consistent with Trust administration
    • The terms are fair and reasonable
    • Adequate security exists to protect Trust assets
    • The loan will not impair the Trust's ability to fulfill its obligations

WHEREAS, loans from Trust assets must be documented and administered in accordance with applicable requirements;

NOW, THEREFORE, BE IT RESOLVED that:

• The Trust is hereby authorized to make a loan to {borrower_name} under the following terms:

LOAN TERMS:
    Principal Amount: ${loan_amount:,.2f}
    Interest Rate: {interest_rate}
    Term: {term_months} months
    Purpose: {purpose if purpose else 'As described in loan application'}
    Collateral: {collateral if collateral else 'Promissory note and personal guarantee'}

• A formal Promissory Note shall be executed documenting all loan terms.

• Payment records shall be maintained and interest shall be charged at the stated rate.

• The Trustees are authorized to take all actions necessary to document and administer this loan.

"""
    else:
        content = f"""Resolution 1: Authorization to Obtain Loan for Trust

WHEREAS, the Board of Trustees has determined that obtaining financing would benefit the Trust;

WHEREAS, {lender_name} has offered to provide financing under acceptable terms;

WHEREAS, the Trustees have evaluated the terms and determined they are reasonable and in the Trust's interest;

NOW, THEREFORE, BE IT RESOLVED that:

• The Trust is hereby authorized to obtain a loan from {lender_name} under the following terms:

LOAN TERMS:
    Principal Amount: ${loan_amount:,.2f}
    Interest Rate: {interest_rate}
    Term: {term_months} months
    Purpose: {purpose if purpose else 'Trust administration and investment purposes'}
    Collateral: {collateral if collateral else 'As required by lender'}

• The Trustees are authorized to execute all necessary loan documents.

• Loan payments shall be made from Trust assets in accordance with the repayment schedule.

• A record of this loan shall be maintained in the Trust's financial records.

"""

    content += """Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    return content


def generate_insurance_authorization_content(data: dict) -> str:
    """Generate content for insurance authorization"""
    insurance_type = data.get("insurance_type", "property")
    policy_action = data.get("policy_action", "obtain")  # obtain, renew, cancel, modify
    insurer_name = data.get("insurer_name", "[Insurance Company]")
    coverage_amount = float(data.get("coverage_amount", 0))
    premium_amount = float(data.get("premium_amount", 0))
    coverage_description = data.get("coverage_description", "")
    policy_number = data.get("policy_number", "")
    
    type_descriptions = {
        "property": "property and casualty insurance",
        "liability": "liability insurance",
        "life": "life insurance",
        "health": "health insurance",
        "umbrella": "umbrella/excess liability insurance",
        "professional": "professional liability insurance",
        "other": "insurance coverage"
    }
    type_text = type_descriptions.get(insurance_type, "insurance coverage")
    
    action_text = {
        "obtain": "obtain new",
        "renew": "renew existing",
        "cancel": "cancel",
        "modify": "modify"
    }.get(policy_action, "obtain")
    
    content = f"""Resolution 1: Insurance Policy Authorization

WHEREAS, prudent Trust administration requires appropriate insurance coverage to protect Trust assets and mitigate risks;

WHEREAS, the Board of Trustees has evaluated the need for {type_text};

WHEREAS, the Trustees have reviewed available coverage options and determined the following action is appropriate;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby authorizes the Trust to {action_text} {type_text} as follows:

INSURANCE DETAILS:
    Insurance Type: {insurance_type.replace('_', ' ').title()}
    Insurer: {insurer_name}
    Coverage Amount: ${coverage_amount:,.2f}
    Annual Premium: ${premium_amount:,.2f}
    {f'Policy Number: {policy_number}' if policy_number else ''}
    Coverage Description: {coverage_description if coverage_description else 'Standard coverage for Trust assets and operations'}

• The Trustees are authorized to execute all necessary applications and policy documents.

• Premium payments shall be made from Trust assets as they become due.

• The insurance policy shall name the Trust as the insured party.

• Policy documents shall be maintained with the Trust records.

BE IT FURTHER RESOLVED that:

• The Trustees shall review insurance coverage annually and make adjustments as needed.

• Claims under this policy shall be handled in accordance with policy terms and fiduciary duties.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    return content


def generate_annual_review_content(data: dict) -> str:
    """Generate content for annual review meeting"""
    fiscal_year = data.get("fiscal_year", str(datetime.now().year - 1))
    total_assets = float(data.get("total_assets", 0))
    total_income = float(data.get("total_income", 0))
    total_expenses = float(data.get("total_expenses", 0))
    total_distributions = float(data.get("total_distributions", 0))
    investment_return = data.get("investment_return", "0%")
    key_accomplishments = data.get("key_accomplishments", [])
    upcoming_priorities = data.get("upcoming_priorities", [])
    governance_items = data.get("governance_items", [])
    
    content = f"""Resolution 1: Annual Review and Affirmation

WHEREAS, the Board of Trustees is required to conduct an annual review of Trust operations, finances, and governance;

WHEREAS, the fiscal year {fiscal_year} has concluded and a comprehensive review has been completed;

WHEREAS, the Trustees have examined the financial statements, investment performance, distributions, and administrative matters;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby acknowledges and approves the following Annual Report for fiscal year {fiscal_year}:

═══════════════════════════════════════════════════════════════════════════════

FINANCIAL SUMMARY – FISCAL YEAR {fiscal_year}

    Total Trust Assets (Year End): ${total_assets:,.2f}
    Total Income Received: ${total_income:,.2f}
    Total Expenses Paid: ${total_expenses:,.2f}
    Total Distributions Made: ${total_distributions:,.2f}
    Investment Return: {investment_return}

═══════════════════════════════════════════════════════════════════════════════

KEY ACCOMPLISHMENTS:
"""

    if key_accomplishments:
        for item in key_accomplishments:
            content += f"    • {item}\n"
    else:
        content += """    • Trust assets were prudently managed and preserved
    • All required distributions were made timely
    • Proper records and documentation were maintained
    • Fiduciary duties were fulfilled in good faith
"""

    content += """
═══════════════════════════════════════════════════════════════════════════════

GOVERNANCE REVIEW:
"""

    if governance_items:
        for item in governance_items:
            content += f"    • {item}\n"
    else:
        content += """    • Trust Indenture remains in full force and effect
    • All Trustees continue to serve and fulfill their duties
    • Insurance coverage has been reviewed and is adequate
    • Investment policy has been reviewed and reaffirmed
    • Beneficiary designations have been reviewed
"""

    content += """
═══════════════════════════════════════════════════════════════════════════════

PRIORITIES FOR UPCOMING YEAR:
"""

    if upcoming_priorities:
        for item in upcoming_priorities:
            content += f"    • {item}\n"
    else:
        content += """    • Continue prudent investment management
    • Maintain comprehensive records and documentation
    • Review and update Schedule A as needed
    • Fulfill all distribution obligations
    • Monitor compliance with Trust Indenture
"""

    content += """
═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Trustees affirm that all actions taken during the fiscal year were in accordance with the Trust Indenture and fiduciary duties.

• The financial records accurately reflect the Trust's position and activities.

• The Trust remains in good standing and continues to operate for its intended purposes.

Vote: Unanimous approval
Effective Date: Upon adoption

"""
    return content


def generate_quarterly_review_content(data: dict) -> str:
    """Generate content for quarterly review meeting"""
    quarter = data.get("quarter", "Q1")
    year = data.get("year", str(datetime.now().year))
    beginning_balance = float(data.get("beginning_balance", 0))
    ending_balance = float(data.get("ending_balance", 0))
    income_received = float(data.get("income_received", 0))
    expenses_paid = float(data.get("expenses_paid", 0))
    distributions_made = float(data.get("distributions_made", 0))
    discussion_items = data.get("discussion_items", [])
    action_items = data.get("action_items", [])
    
    content = f"""Resolution 1: Quarterly Review and Report – {quarter} {year}

WHEREAS, the Board of Trustees conducts regular quarterly reviews to monitor Trust operations;

WHEREAS, the {quarter} {year} quarter has concluded and a review has been completed;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby acknowledges and approves the following Quarterly Report:

═══════════════════════════════════════════════════════════════════════════════

QUARTERLY FINANCIAL SUMMARY – {quarter} {year}

    Beginning Balance: ${beginning_balance:,.2f}
    Income Received: ${income_received:,.2f}
    Expenses Paid: ${expenses_paid:,.2f}
    Distributions Made: ${distributions_made:,.2f}
    Ending Balance: ${ending_balance:,.2f}
    Net Change: ${ending_balance - beginning_balance:,.2f}

═══════════════════════════════════════════════════════════════════════════════

MATTERS DISCUSSED:
"""

    if discussion_items:
        for item in discussion_items:
            content += f"    • {item}\n"
    else:
        content += """    • Review of financial statements and account balances
    • Investment performance and asset allocation
    • Pending distribution requests or obligations
    • Administrative matters and compliance items
"""

    content += """
═══════════════════════════════════════════════════════════════════════════════

ACTION ITEMS FOR NEXT QUARTER:
"""

    if action_items:
        for item in action_items:
            content += f"    • {item}\n"
    else:
        content += """    • Continue monitoring investment performance
    • Process any pending distribution requests
    • Review upcoming obligations and deadlines
    • Prepare for annual review (if Q4)
"""

    content += """
═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Trustees have reviewed the quarterly report and find it to be accurate and complete.

• All actions taken during the quarter were in accordance with the Trust Indenture.

• The Trust continues to operate in compliance with its governing documents.

Vote: Unanimous approval
Effective Date: Upon adoption

"""
    return content


def generate_trustee_compensation_content(data: dict) -> str:
    """Generate content for trustee compensation approval"""
    trustee_name = data.get("trustee_name", "[Trustee Name]")
    compensation_type = data.get("compensation_type", "annual")  # annual, hourly, per_meeting, percentage
    compensation_amount = float(data.get("compensation_amount", 0))
    effective_date = data.get("effective_date", "[Effective Date]")
    compensation_basis = data.get("compensation_basis", "")
    duties_description = data.get("duties_description", "")
    all_trustees = data.get("all_trustees", False)
    
    type_text = {
        "annual": f"${compensation_amount:,.2f} per year",
        "hourly": f"${compensation_amount:,.2f} per hour",
        "per_meeting": f"${compensation_amount:,.2f} per meeting attended",
        "percentage": f"{compensation_amount}% of Trust assets annually"
    }.get(compensation_type, f"${compensation_amount:,.2f}")
    
    trustee_text = "all serving Trustees" if all_trustees else trustee_name
    
    content = f"""Resolution 1: Trustee Compensation Approval

WHEREAS, the Trust Indenture authorizes reasonable compensation to Trustees for their services;

WHEREAS, the Board of Trustees has evaluated the duties, responsibilities, and time commitment required of Trustees;

WHEREAS, the proposed compensation is reasonable and consistent with compensation paid to trustees of similar trusts;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby approves compensation for {trustee_text} as follows:

COMPENSATION TERMS:
    Trustee(s): {trustee_text}
    Compensation Amount: {type_text}
    Effective Date: {effective_date}
    Compensation Basis: {compensation_basis if compensation_basis else 'Services rendered as Trustee'}

DUTIES AND RESPONSIBILITIES:
{duties_description if duties_description else '''    • Administration of Trust assets and operations
    • Attendance at regular and special meetings
    • Review and approval of distributions
    • Investment oversight and monitoring
    • Maintenance of Trust records and compliance
    • Communication with beneficiaries as appropriate'''}

• Compensation shall be paid {'monthly' if compensation_type == 'annual' else 'quarterly'} from Trust assets.

• The compensation arrangement shall be reviewed annually and may be adjusted by unanimous Trustee action.

• This compensation is for services rendered in the Trustee's private capacity and does not create an employment relationship.

BE IT FURTHER RESOLVED that:

• The Trustees affirm that this compensation is reasonable and does not constitute self-dealing.

• Proper records of compensation payments shall be maintained.

• Any Trustee receiving compensation shall recuse from voting on their own compensation.

Vote: Unanimous approval (with appropriate recusals)
Effective Date: {effective_date}

"""
    return content


def generate_trustee_resignation_content(data: dict) -> str:
    """Generate content for trustee resignation or removal"""
    departing_trustee = data.get("departing_trustee_name", "[Trustee Name]")
    departure_type = data.get("departure_type", "resignation")  # resignation, removal, death, incapacity
    departure_reason = data.get("departure_reason", "")
    effective_date = data.get("effective_date", "[Effective Date]")
    remaining_trustees = data.get("remaining_trustees", [])
    successor_appointed = data.get("successor_appointed", False)
    successor_name = data.get("successor_name", "")
    
    type_text = {
        "resignation": "has tendered their resignation",
        "removal": "is being removed from office",
        "death": "has passed away",
        "incapacity": "is no longer able to serve due to incapacity"
    }.get(departure_type, "is departing from the position of Trustee")
    
    content = f"""Resolution 1: Acknowledgment of Trustee {departure_type.title()}

WHEREAS, {departing_trustee} currently serves as a Trustee of this Trust;

WHEREAS, {departing_trustee} {type_text}{f' for the following reason: {departure_reason}' if departure_reason else ''};

WHEREAS, the Board of Trustees must take appropriate action to document this change and ensure continuity of Trust administration;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby acknowledges and accepts the {departure_type} of {departing_trustee} as Trustee, effective {effective_date}.

• {departing_trustee} is released from all ongoing duties and obligations as Trustee, effective upon the date specified above.

• The Trust extends its {'gratitude for faithful service' if departure_type in ['resignation', 'death'] else 'acknowledgment'} rendered during the tenure as Trustee.

"""

    if remaining_trustees:
        content += """
CONTINUING TRUSTEES:
The following Trustees shall continue to serve:
"""
        for trustee in remaining_trustees:
            content += f"    • {trustee}\n"
    
    if successor_appointed and successor_name:
        content += f"""
• {successor_name} has been appointed as Successor Trustee pursuant to separate resolution.

"""
    else:
        content += """
• The remaining Trustees shall continue to administer the Trust in accordance with the Trust Indenture.

• A successor Trustee {'will be appointed pursuant to the Trust Indenture' if departure_type != 'removal' else 'may be appointed if deemed necessary'}.

"""

    content += f"""
BE IT FURTHER RESOLVED that:

• All necessary updates shall be made to bank accounts, service providers, and official records.

• An updated Certification of Trust shall be prepared reflecting this change.

• {departing_trustee} {'shall execute any documents necessary to effectuate a smooth transition' if departure_type == 'resignation' else 'or their representative shall cooperate in the transition of duties'}.

• The departing Trustee's signature authority is hereby revoked effective {effective_date}.

Vote: Unanimous approval
Effective Date: {effective_date}

"""
    return content


def generate_beneficiary_denial_content(data: dict) -> str:
    """Generate content for beneficiary request denial"""
    beneficiary_name = data.get("beneficiary_name", "[Beneficiary Name]")
    request_type = data.get("request_type", "distribution")
    request_amount = float(data.get("request_amount", 0))
    request_purpose = data.get("request_purpose", "")
    request_date = data.get("request_date", "[Request Date]")
    denial_reasons = data.get("denial_reasons", [])
    alternative_offered = data.get("alternative_offered", "")
    
    content = f"""Resolution 1: Denial of Beneficiary Request

WHEREAS, {beneficiary_name}, a beneficiary of this Trust, submitted a request dated {request_date};

WHEREAS, the request was for a {request_type} in the amount of ${request_amount:,.2f}{f' for the purpose of: {request_purpose}' if request_purpose else ''};

WHEREAS, the Board of Trustees has carefully reviewed and considered this request in light of the Trust Indenture, the interests of all beneficiaries, and sound fiduciary principles;

WHEREAS, after due deliberation, the Trustees have determined that the request cannot be approved;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby denies the request from {beneficiary_name} for the following reasons:

REASONS FOR DENIAL:
"""

    if denial_reasons:
        for reason in denial_reasons:
            content += f"    • {reason}\n"
    else:
        content += """    • The request does not meet the distribution standards set forth in the Trust Indenture
    • Approval would not be consistent with the Trustees' fiduciary duties
    • The Trust's resources and obligations do not permit approval at this time
"""

    content += """
• This decision was made in good faith, with careful consideration of all relevant factors, and in accordance with the Trustees' fiduciary duties to all beneficiaries.

• The Trustees affirm that they have acted impartially and have not been influenced by improper considerations.

"""

    if alternative_offered:
        content += f"""
ALTERNATIVE OFFERED:
While the specific request cannot be approved, the Trustees offer the following alternative:
    {alternative_offered}

"""

    content += """
BE IT FURTHER RESOLVED that:

• The beneficiary shall be notified of this decision in writing.

• This denial does not preclude the beneficiary from making future requests.

• A record of this request and denial shall be maintained in the Trust's records.

• The Trustees' decision in this matter is final.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    return content


def generate_hems_distribution_content(data: dict) -> str:
    """Generate content for HEMS distribution (Health, Education, Maintenance, Support)"""
    beneficiary_name = data.get("beneficiary_name", "[Beneficiary Name]")
    hems_category = data.get("hems_category", "support")  # health, education, maintenance, support
    distribution_amount = float(data.get("distribution_amount", 0))
    specific_purpose = data.get("specific_purpose", "")
    supporting_documentation = data.get("supporting_documentation", [])
    recurring = data.get("recurring", False)
    recurring_frequency = data.get("recurring_frequency", "monthly")
    
    category_descriptions = {
        "health": "health and medical expenses",
        "education": "educational expenses",
        "maintenance": "maintenance of accustomed standard of living",
        "support": "support and general welfare"
    }
    category_text = category_descriptions.get(hems_category, "support")
    
    category_details = {
        "health": """This distribution qualifies under the Health standard as it is for:
    • Medical treatment, procedures, or care
    • Health insurance premiums or medical expenses
    • Prescription medications or medical supplies
    • Mental health services or therapy
    • Preventive care or wellness services""",
        "education": """This distribution qualifies under the Education standard as it is for:
    • Tuition and academic fees
    • Books, supplies, and educational materials
    • Room and board for educational purposes
    • Tutoring or educational support services
    • Professional development or vocational training""",
        "maintenance": """This distribution qualifies under the Maintenance standard as it is for:
    • Housing costs (mortgage, rent, utilities)
    • Transportation expenses
    • Food and household expenses
    • Clothing and personal necessities
    • Maintaining the beneficiary's accustomed lifestyle""",
        "support": """This distribution qualifies under the Support standard as it is for:
    • General living expenses and welfare
    • Emergency assistance or unexpected needs
    • Quality of life enhancement
    • Other needs consistent with the beneficiary's wellbeing"""
    }
    
    content = f"""Resolution 1: HEMS Distribution Approval

WHEREAS, this Trust is authorized to make distributions for the Health, Education, Maintenance, and Support (HEMS) of beneficiaries;

WHEREAS, {beneficiary_name}, a beneficiary of this Trust, has a qualifying need for {category_text};

WHEREAS, the Board of Trustees has evaluated this need and determined it falls within the HEMS distribution standard;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby approves a {'recurring ' if recurring else ''}distribution to {beneficiary_name} under the {hems_category.upper()} standard:

DISTRIBUTION DETAILS:
    Beneficiary: {beneficiary_name}
    HEMS Category: {hems_category.title()}
    Amount: ${distribution_amount:,.2f}{f' {recurring_frequency}' if recurring else ''}
    Purpose: {specific_purpose if specific_purpose else category_text}

═══════════════════════════════════════════════════════════════════════════════

HEMS STANDARD COMPLIANCE:

{category_details.get(hems_category, category_details['support'])}

═══════════════════════════════════════════════════════════════════════════════

"""

    if supporting_documentation:
        content += "SUPPORTING DOCUMENTATION REVIEWED:\n"
        for doc in supporting_documentation:
            content += f"    • {doc}\n"
        content += "\n"

    if recurring:
        content += f"""
RECURRING DISTRIBUTION TERMS:
    • This distribution shall recur {recurring_frequency} until modified or terminated by the Trustees.
    • The beneficiary shall provide updated documentation as requested.
    • The Trustees reserve the right to modify or terminate this arrangement.

"""

    content += """
BE IT FURTHER RESOLVED that:

• The Trustees have determined this distribution is consistent with the HEMS standard and the Trust Indenture.

• The distribution shall be made within a reasonable time following adoption.

• Appropriate records shall be maintained documenting this distribution.

• The Solvency Declaration requirements have been satisfied.

Vote: Unanimous approval
Effective Date: Immediately upon adoption

"""
    return content


def generate_beneficiary_loan_content(data: dict) -> str:
    """Generate content for loan to beneficiary"""
    beneficiary_name = data.get("beneficiary_name", "[Beneficiary Name]")
    loan_amount = float(data.get("loan_amount", 0))
    interest_rate = data.get("interest_rate", "AFR (Applicable Federal Rate)")
    term_months = data.get("term_months", 60)
    loan_purpose = data.get("loan_purpose", "")
    collateral = data.get("collateral_description", "")
    repayment_terms = data.get("repayment_terms", "monthly installments")
    
    content = f"""Resolution 1: Authorization of Intra-Family Loan to Beneficiary

WHEREAS, {beneficiary_name}, a beneficiary of this Trust, has requested a loan from Trust assets;

WHEREAS, the Trust Indenture permits loans to beneficiaries under appropriate terms and conditions;

WHEREAS, the Board of Trustees has evaluated this request and determined that:
    • The loan serves a legitimate purpose
    • The terms are fair and comply with applicable requirements
    • The beneficiary has the ability to repay the loan
    • The loan will not impair the Trust's ability to fulfill its obligations;

WHEREAS, intra-family loans must be properly documented and administered to maintain their tax treatment;

NOW, THEREFORE, BE IT RESOLVED that:

• The Board of Trustees hereby authorizes a loan to {beneficiary_name} under the following terms:

═══════════════════════════════════════════════════════════════════════════════

LOAN TERMS AND CONDITIONS

    Borrower: {beneficiary_name}
    Principal Amount: ${loan_amount:,.2f}
    Interest Rate: {interest_rate}
    Term: {term_months} months
    Purpose: {loan_purpose if loan_purpose else 'Personal use'}
    Collateral: {collateral if collateral else 'Unsecured; beneficiary interest may serve as informal security'}
    Repayment: {repayment_terms}

═══════════════════════════════════════════════════════════════════════════════

REQUIRED DOCUMENTATION:

• A formal Promissory Note shall be executed containing all material terms.

• The Note shall include:
    - Fixed repayment schedule
    - Interest rate at or above AFR
    - Default provisions
    - Prepayment terms

═══════════════════════════════════════════════════════════════════════════════

ADMINISTRATION REQUIREMENTS:

• Interest shall be charged at the stated rate and must be paid at least annually.

• All payments shall be recorded and receipts provided.

• Late payments shall be documented and addressed per the Note terms.

• The loan shall be treated as a Trust asset on the books and records.

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• This loan is made on arm's-length terms and is not a disguised gift.

• Failure to repay may result in offset against future distributions to the borrower.

• The Trustees shall monitor repayment and take appropriate action if the loan becomes delinquent.

• If the borrower's interest in the Trust is less than the outstanding loan balance at any time, additional security may be required.

Vote: Unanimous approval
Effective Date: Upon execution of Promissory Note

"""
    return content


# ============= BATCH 2 CONTENT GENERATORS =============

def generate_trust_amendment_content(data: dict) -> str:
    """Generate content for trust amendment"""
    amendment_type = data.get("amendment_type", "modification")
    article_section = data.get("article_section", "Article [X], Section [Y]")
    current_provision = data.get("current_provision", "[Current language]")
    amended_provision = data.get("amended_provision", "[New language]")
    effective_date = data.get("effective_date", "immediately upon execution")
    reason = data.get("reason", "the Settlor and Trustees have determined this amendment is in the best interest of the Trust and its beneficiaries")
    
    content = f"""
TRUST AMENDMENT

Amendment Type: {amendment_type.replace('_', ' ').title()}
Article/Section: {article_section}
Effective Date: {effective_date}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS the Trust Indenture grants the power to amend certain provisions of the Trust; and

WHEREAS {reason}; and

WHEREAS this amendment is consistent with the purposes and intent of the Trust as originally established; and

WHEREAS proper notice (if required) has been provided to all interested parties;

NOW, THEREFORE, BE IT RESOLVED that {article_section} of the Trust Indenture is hereby amended as follows:

───────────────────────────────────────────────────────────────────────────────

CURRENT PROVISION:

{current_provision}

───────────────────────────────────────────────────────────────────────────────

AMENDED PROVISION (Effective {effective_date}):

{amended_provision}

───────────────────────────────────────────────────────────────────────────────

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• This amendment shall be effective {effective_date}.

• All other provisions of the Trust Indenture not specifically amended hereby shall remain in full force and effect.

• This amendment shall be attached to and become part of the original Trust Indenture.

• The Trustees are authorized to execute any documents necessary to effectuate this amendment.

• Copies of this amendment shall be provided to all Trustees and may be provided to beneficiaries as appropriate.

Vote: Unanimous approval
Effective: {effective_date}

"""
    return content


def generate_power_of_attorney_content(data: dict) -> str:
    """Generate content for power of attorney authorization"""
    agent_name = data.get("agent_name", "[Agent Name]")
    scope = data.get("scope", "limited")
    powers_granted = data.get("powers_granted", ["Execute documents", "Access accounts"])
    expiration = data.get("expiration", "upon completion of specified purpose")
    purpose = data.get("purpose", "act on behalf of the Trust in specified matters")
    
    powers_list = "\n".join([f"    • {power}" for power in powers_granted]) if isinstance(powers_granted, list) else f"    • {powers_granted}"
    
    content = f"""
POWER OF ATTORNEY AUTHORIZATION

Agent Appointed: {agent_name}
Scope of Authority: {scope.title()}
Expiration: {expiration}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS the Trustees require assistance in conducting certain Trust business; and

WHEREAS {agent_name} is a competent and trustworthy individual capable of acting in the Trust's best interest; and

WHEREAS the Trust Indenture authorizes the Trustees to appoint agents to assist in Trust administration;

NOW, THEREFORE, BE IT RESOLVED that {agent_name} is hereby appointed as Agent with {scope} power of attorney to {purpose}.

═══════════════════════════════════════════════════════════════════════════════

POWERS GRANTED:

{powers_list}

═══════════════════════════════════════════════════════════════════════════════

LIMITATIONS AND CONDITIONS:

• This Power of Attorney is {scope} in scope and applies only to the specific powers enumerated above.

• The Agent shall act in good faith and in the best interest of the Trust at all times.

• The Agent shall keep accurate records of all actions taken and provide reports to the Trustees upon request.

• The Agent may not delegate these powers without express written consent of the Trustees.

• This Power of Attorney shall expire {expiration}.

• The Trustees reserve the right to revoke this Power of Attorney at any time with or without cause.

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Agent is authorized to execute documents and take actions within the scope of authority granted herein.

• Third parties may rely on this Power of Attorney until notified of its revocation.

• A certified copy of these Minutes shall serve as evidence of the Agent's authority.

Vote: Unanimous approval
Effective: Immediately

"""
    return content


def generate_trust_termination_content(data: dict) -> str:
    """Generate content for trust termination/dissolution"""
    termination_reason = data.get("termination_reason", "the Trust has accomplished its purposes")
    termination_date = data.get("termination_date", "[Date]")
    distribution_plan = data.get("distribution_plan", "pro rata to beneficiaries according to their interests")
    final_accounting = data.get("final_accounting_date", "within 60 days")
    outstanding_obligations = data.get("outstanding_obligations", "None known at this time")
    
    content = f"""
TRUST TERMINATION AND DISSOLUTION

Termination Date: {termination_date}
Reason: {termination_reason}
Final Distribution: {distribution_plan}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS {termination_reason}; and

WHEREAS all conditions precedent to termination have been satisfied; and

WHEREAS the Trustees have determined that termination is appropriate and in accordance with the Trust Indenture; and

WHEREAS proper notice has been provided to all beneficiaries and interested parties;

NOW, THEREFORE, BE IT RESOLVED that the Trust shall be terminated effective {termination_date}.

═══════════════════════════════════════════════════════════════════════════════

FINAL ACCOUNTING:

• A final accounting shall be prepared {final_accounting}.
• The accounting shall include all assets, liabilities, income, and expenses.
• Copies shall be provided to all beneficiaries prior to final distribution.

═══════════════════════════════════════════════════════════════════════════════

OUTSTANDING OBLIGATIONS:

{outstanding_obligations}

═══════════════════════════════════════════════════════════════════════════════

DISTRIBUTION PLAN:

{distribution_plan}

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• All outstanding debts and obligations shall be paid prior to any distribution to beneficiaries.

• The Trustees shall liquidate assets as necessary to make final distributions.

• Each beneficiary shall execute a receipt and release upon receiving their final distribution.

• The Trustees shall file all required final tax returns and obtain tax clearance.

• Upon completion of distributions and administrative tasks, the Trustees shall be discharged from further duty.

• All Trust records shall be retained for the period required by applicable law.

Vote: Unanimous approval
Effective: {termination_date}

"""
    return content


def generate_real_estate_purchase_content(data: dict) -> str:
    """Generate content for real estate purchase authorization"""
    property_address = data.get("property_address", "[Property Address]")
    property_type = data.get("property_type", "residential")
    purchase_price = data.get("purchase_price", "$[Amount]")
    financing = data.get("financing", "all cash")
    purpose = data.get("purpose", "investment and income production")
    inspection_period = data.get("inspection_period", "standard due diligence period")
    
    content = f"""
REAL ESTATE PURCHASE AUTHORIZATION

Property: {property_address}
Property Type: {property_type.title()}
Purchase Price: {purchase_price}
Financing: {financing}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS the Trustees have identified real property suitable for acquisition by the Trust; and

WHEREAS the acquisition of this property is consistent with the Trust's investment objectives; and

WHEREAS the purchase is expected to benefit the Trust through {purpose}; and

WHEREAS adequate funds are available for this acquisition;

NOW, THEREFORE, BE IT RESOLVED that the Trustees are authorized to acquire the following real property:

PROPERTY DESCRIPTION:
Address: {property_address}
Type: {property_type.title()}

═══════════════════════════════════════════════════════════════════════════════

PURCHASE TERMS:

• Purchase Price: {purchase_price}
• Financing: {financing}
• Due Diligence: {inspection_period}
• Purpose: {purpose}

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Trustees are authorized to negotiate terms and execute all documents necessary to complete the purchase.

• Title shall be taken in the name of the Trust.

• The Trustees shall obtain title insurance, surveys, and inspections as appropriate.

• The property shall be added to Schedule A upon closing.

• The Trustees are authorized to take all actions necessary for property management following acquisition.

• If financing is required, the Trustees are authorized to execute mortgages or deeds of trust as needed.

Vote: Unanimous approval
Authorization: Valid for 180 days

"""
    return content


def generate_business_interest_content(data: dict) -> str:
    """Generate content for business interest acquisition"""
    entity_name = data.get("entity_name", "[Entity Name]")
    entity_type = data.get("entity_type", "LLC")
    ownership_percentage = data.get("ownership_percentage", "[X]%")
    purchase_price = data.get("purchase_price", "$[Amount]")
    purpose = data.get("purpose", "investment diversification")
    due_diligence = data.get("due_diligence", "financial review completed")
    
    content = f"""
BUSINESS INTEREST ACQUISITION

Entity: {entity_name}
Entity Type: {entity_type}
Interest: {ownership_percentage} ownership
Price: {purchase_price}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS the Trustees have identified an opportunity to acquire an interest in {entity_name}; and

WHEREAS this acquisition is consistent with the Trust's investment strategy and objectives; and

WHEREAS {due_diligence}; and

WHEREAS the investment is expected to provide {purpose};

NOW, THEREFORE, BE IT RESOLVED that the Trust is authorized to acquire {ownership_percentage} ownership interest in {entity_name}, a {entity_type}, for {purchase_price}.

═══════════════════════════════════════════════════════════════════════════════

ACQUISITION DETAILS:

• Entity Name: {entity_name}
• Entity Type: {entity_type}
• Ownership Percentage: {ownership_percentage}
• Purchase Price: {purchase_price}
• Purpose: {purpose}

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Trustees are authorized to negotiate and execute subscription agreements, operating agreements, or other documents necessary to complete the acquisition.

• The Trustees shall obtain and review all entity governing documents prior to closing.

• The interest shall be recorded on Schedule A upon acquisition.

• The Trustees are authorized to exercise all rights of ownership including voting, receiving distributions, and participating in management as permitted.

• The Trustees shall monitor the investment and report on its performance periodically.

Vote: Unanimous approval
Authorization: Valid for 120 days

"""
    return content


def generate_real_estate_lease_content(data: dict) -> str:
    """Generate content for real estate lease authorization"""
    property_address = data.get("property_address", "[Property Address]")
    tenant_name = data.get("tenant_name", "[Tenant Name]")
    lease_term = data.get("lease_term", "[X] years")
    monthly_rent = data.get("monthly_rent", "$[Amount]")
    security_deposit = data.get("security_deposit", "equivalent to one month's rent")
    permitted_use = data.get("permitted_use", "residential occupancy")
    
    content = f"""
REAL ESTATE LEASE AUTHORIZATION

Property: {property_address}
Tenant: {tenant_name}
Term: {lease_term}
Monthly Rent: {monthly_rent}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS the Trust owns real property located at {property_address}; and

WHEREAS leasing said property will provide income for the Trust; and

WHEREAS the proposed tenant has been vetted and approved by the Trustees; and

WHEREAS the lease terms are fair and reasonable;

NOW, THEREFORE, BE IT RESOLVED that the Trustees are authorized to enter into a lease agreement for the property.

═══════════════════════════════════════════════════════════════════════════════

LEASE TERMS:

• Property: {property_address}
• Tenant: {tenant_name}
• Term: {lease_term}
• Monthly Rent: {monthly_rent}
• Security Deposit: {security_deposit}
• Permitted Use: {permitted_use}

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Trustees are authorized to execute the lease agreement and all related documents.

• The lease shall contain standard provisions protecting the Trust's interests.

• The Trustees shall collect and hold security deposits in compliance with applicable law.

• The Trustees are authorized to enforce the lease terms and take appropriate action for any default.

• Rent collected shall be deposited into the Trust operating account.

• The Trustees shall maintain appropriate property insurance.

Vote: Unanimous approval
Effective: Upon lease execution

"""
    return content


def generate_fiscal_year_content(data: dict) -> str:
    """Generate content for fiscal year election"""
    fiscal_year_end = data.get("fiscal_year_end", "December 31")
    election_type = data.get("election_type", "initial")
    effective_year = data.get("effective_year", "[Year]")
    reason = data.get("reason", "administrative convenience and alignment with beneficiary tax years")
    
    content = f"""
FISCAL YEAR ELECTION

Fiscal Year End: {fiscal_year_end}
Election Type: {election_type.replace('_', ' ').title()}
Effective: Tax Year {effective_year}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS the Trust is required to select a fiscal year for tax reporting purposes; and

WHEREAS the Trustees have considered the advantages of various fiscal year endings; and

WHEREAS a {fiscal_year_end} fiscal year end is appropriate for {reason};

NOW, THEREFORE, BE IT RESOLVED that the Trust adopts a fiscal year ending {fiscal_year_end}, effective for the {effective_year} tax year and all subsequent years until changed.

═══════════════════════════════════════════════════════════════════════════════

ELECTION DETAILS:

• Fiscal Year End: {fiscal_year_end}
• Election Type: {election_type.replace('_', ' ').title()}
• First Applicable Year: {effective_year}
• Reason: {reason}

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Trust's tax preparer is authorized to make any required filings with the IRS to effectuate this election.

• The Trust's books and records shall be maintained on a fiscal year basis consistent with this election.

• All required estimated tax payments shall be made based on this fiscal year.

• This election shall remain in effect until formally changed by resolution of the Trustees.

Vote: Unanimous approval
Effective: Tax Year {effective_year}

"""
    return content


def generate_tax_filing_content(data: dict) -> str:
    """Generate content for tax filing authorization"""
    tax_year = data.get("tax_year", "[Year]")
    preparer_name = data.get("preparer_name", "[Tax Preparer/CPA]")
    returns_to_file = data.get("returns_to_file", ["Form 1041 - U.S. Income Tax Return for Estates and Trusts"])
    filing_deadline = data.get("filing_deadline", "April 15")
    extension_authorized = data.get("extension_authorized", True)
    
    returns_list = "\n".join([f"    • {ret}" for ret in returns_to_file]) if isinstance(returns_to_file, list) else f"    • {returns_to_file}"
    
    content = f"""
TAX FILING AUTHORIZATION

Tax Year: {tax_year}
Tax Preparer: {preparer_name}
Filing Deadline: {filing_deadline}
Extension Authorized: {"Yes" if extension_authorized else "No"}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS the Trust is required to file income tax returns for the {tax_year} tax year; and

WHEREAS {preparer_name} has been engaged to prepare the Trust's tax returns; and

WHEREAS the Trustees have reviewed and approved the information to be used in the returns;

NOW, THEREFORE, BE IT RESOLVED that the Trustees authorize the preparation and filing of the following tax returns:

{returns_list}

═══════════════════════════════════════════════════════════════════════════════

AUTHORIZATIONS:

• {preparer_name} is authorized to prepare all required federal, state, and local tax returns for the Trust.

• The Trustees authorize electronic filing of all returns where permitted.

• {"An automatic extension may be filed if additional time is needed to complete the returns." if extension_authorized else "No extension is authorized; returns must be filed by the original deadline."}

• The Trustees authorize payment of any taxes due from Trust funds.

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The Trustees shall review and approve the returns prior to filing.

• Copies of all filed returns shall be maintained in the Trust records.

• K-1 schedules shall be provided to beneficiaries as required.

• The tax preparer is authorized to respond to routine IRS inquiries regarding the returns.

Vote: Unanimous approval
Tax Year: {tax_year}

"""
    return content


def generate_emergency_ratification_content(data: dict) -> str:
    """Generate content for emergency action ratification"""
    action_date = data.get("action_date", "[Date]")
    emergency_type = data.get("emergency_type", "[Type of Emergency]")
    actions_taken = data.get("actions_taken", ["Action 1", "Action 2"])
    trustee_acting = data.get("trustee_acting", "[Trustee Name]")
    cost_incurred = data.get("cost_incurred", "$[Amount]")
    outcome = data.get("outcome", "the emergency was successfully addressed")
    
    actions_list = "\n".join([f"    • {action}" for action in actions_taken]) if isinstance(actions_taken, list) else f"    • {actions_taken}"
    
    content = f"""
EMERGENCY ACTION RATIFICATION

Emergency Date: {action_date}
Emergency Type: {emergency_type}
Trustee Acting: {trustee_acting}
Cost Incurred: {cost_incurred}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS on {action_date}, an emergency situation arose involving {emergency_type}; and

WHEREAS immediate action was required to protect Trust assets and/or beneficiaries; and

WHEREAS {trustee_acting} took prompt action to address the emergency; and

WHEREAS {outcome}; and

WHEREAS it was not possible to convene a formal Trustee meeting prior to taking action;

NOW, THEREFORE, BE IT RESOLVED that the following emergency actions taken on {action_date} are hereby ratified and confirmed:

{actions_list}

═══════════════════════════════════════════════════════════════════════════════

EMERGENCY DETAILS:

• Date of Emergency: {action_date}
• Type: {emergency_type}
• Trustee Acting: {trustee_acting}
• Cost Incurred: {cost_incurred}
• Outcome: {outcome}

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• The actions taken were reasonable and necessary under the circumstances.

• The Trustee acted in good faith and in the best interest of the Trust.

• All costs incurred ({cost_incurred}) are approved as proper Trust expenses.

• The Trustee is indemnified for all actions taken in connection with this emergency.

• This ratification shall serve as full authorization for the actions taken.

• Documentation of the emergency and actions taken shall be maintained in Trust records.

Vote: Unanimous approval
Effective: Retroactive to {action_date}

"""
    return content


def generate_conflict_of_interest_content(data: dict) -> str:
    """Generate content for conflict of interest disclosure"""
    trustee_name = data.get("trustee_name", "[Trustee Name]")
    conflict_type = data.get("conflict_type", "financial interest")
    description = data.get("description", "[Description of the conflict]")
    related_transaction = data.get("related_transaction", "[Related transaction or matter]")
    disclosure_date = data.get("disclosure_date", "[Date]")
    waiver_granted = data.get("waiver_granted", True)
    conditions = data.get("conditions", "None")
    
    content = f"""
CONFLICT OF INTEREST DISCLOSURE AND WAIVER

Trustee: {trustee_name}
Conflict Type: {conflict_type.replace('_', ' ').title()}
Related Matter: {related_transaction}
Waiver: {"Granted" if waiver_granted else "Denied"}

═══════════════════════════════════════════════════════════════════════════════

WHEREAS {trustee_name} has disclosed a potential conflict of interest regarding {related_transaction}; and

WHEREAS the nature of the conflict is {conflict_type}: {description}; and

WHEREAS the disclosure was made on {disclosure_date} in compliance with the Trustee's fiduciary duties; and

WHEREAS the remaining Trustees have considered the disclosure and its implications;

═══════════════════════════════════════════════════════════════════════════════

DISCLOSURE DETAILS:

• Trustee with Conflict: {trustee_name}
• Type of Conflict: {conflict_type.replace('_', ' ').title()}
• Description: {description}
• Related Transaction: {related_transaction}
• Date of Disclosure: {disclosure_date}

═══════════════════════════════════════════════════════════════════════════════

NOW, THEREFORE, BE IT RESOLVED that:

• The disclosure by {trustee_name} is hereby acknowledged and accepted.

• {"The conflict is hereby WAIVED, and the Trustee is authorized to participate in deliberations and voting on the related matter." if waiver_granted else "The conflict is NOT waived, and the Trustee shall RECUSE from all deliberations and voting on the related matter."}

{"• Conditions of waiver: " + conditions if waiver_granted and conditions != "None" else ""}

═══════════════════════════════════════════════════════════════════════════════

BE IT FURTHER RESOLVED that:

• This disclosure and resolution shall be documented in the Trust records.

• {trustee_name} shall provide additional disclosures if circumstances change.

• Future similar conflicts shall require separate disclosure and consideration.

• The remaining Trustees have determined that {"proceeding with waiver" if waiver_granted else "requiring recusal"} is in the best interest of the Trust.

Vote: {"Unanimous approval (excluding conflicted Trustee)" if not waiver_granted else "Unanimous approval"}
Effective: Immediately

"""
    return content


@router.post("/minutes-templates")
async def create_minutes_from_template(template: MinutesTemplateCreate, user: dict = Depends(require_write_access)):
    """Create minutes from a template"""
    trust = await db.trusts.find_one({"trust_id": template.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    minutes_id = f"min_{uuid.uuid4().hex[:12]}"
    
    # Generate the document
    generated_doc = generate_template_document(trust, template.template_type.value, template.template_data)
    
    # Extract meeting date from template data
    meeting_date = template.template_data.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": template.trust_id,
        "user_id": user["user_id"],
        "template_type": template.template_type.value,
        "template_data": template.template_data,
        "generated_document": generated_doc,
        "original_document": generated_doc,  # Store original for audit
        "meeting_date": meeting_date,
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "updated_by": None
    }
    
    await db.minutes_templates.insert_one(minutes_doc)
    
    # If accepting property and add_to_schedule_a is true, add to Schedule A
    if template.template_type.value == "acceptance_of_property" and template.template_data.get("add_to_schedule_a"):
        category = template.template_data.get("schedule_a_category", "other_property")
        asset_doc = {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}",
            "trust_id": template.trust_id,
            "user_id": user["user_id"],
            "category": category,
            "description": template.template_data.get("property_description", ""),
            "identifier": template.template_data.get("property_identifier", ""),
            "location": template.template_data.get("property_location", ""),
            "approximate_value": template.template_data.get("property_value"),
            "date_conveyed": template.template_data.get("conveyance_date", meeting_date),
            "notes": template.template_data.get("property_notes", ""),
            "status": "active",
            "minutes_ref": minutes_id,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None
        }
        await db.schedule_a_items.insert_one(asset_doc)
    
    # If disposing of an asset and update_schedule_a is true, mark asset as disposed
    if template.template_type.value == "disposition_of_asset" and template.template_data.get("update_schedule_a"):
        asset_id = template.template_data.get("disposition_asset_id")
        if asset_id:
            # Update the Schedule A item to mark as disposed
            disposition_update = {
                "status": "disposed",
                "disposition_minutes_ref": minutes_id,
                "disposition_date": template.template_data.get("disposition_date", meeting_date),
                "disposition_notes": f"Reason: {template.template_data.get('disposition_reason', 'sale')}. " +
                    (f"Recipient: {template.template_data.get('disposition_recipient', '')}. " if template.template_data.get('disposition_recipient') else "") +
                    (f"Value: ${template.template_data.get('disposition_value', 0):,.2f}. " if template.template_data.get('disposition_value') else "") +
                    (template.template_data.get('disposition_notes', '')),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            await db.schedule_a_items.update_one(
                {"item_id": asset_id, "user_id": user["user_id"]},
                {"$set": disposition_update}
            )
    
    return {
        "minutes_id": minutes_id,
        "trust_id": template.trust_id,
        "template_type": template.template_type.value,
        "template_data": template.template_data,
        "generated_document": generated_doc,
        "original_document": generated_doc,
        "meeting_date": meeting_date,
        "status": "draft",
        "created_at": minutes_doc["created_at"],
        "updated_at": None,
        "updated_by": None
    }

@router.get("/minutes-templates")
async def get_minutes_templates(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Get all template-based minutes"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    
    minutes = await db.minutes_templates.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return minutes

@router.get("/minutes-templates/{minutes_id}")
async def get_minutes_template(minutes_id: str, user: dict = Depends(get_current_user)):
    """Get a single template-based minutes"""
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return minutes

class MinutesTemplateUpdate(BaseModel):
    generated_document: Optional[str] = None
    status: Optional[str] = None
    template_data: Optional[dict] = None

@router.put("/minutes-templates/{minutes_id}")
async def update_minutes_template(minutes_id: str, update_data: MinutesTemplateUpdate, user: dict = Depends(require_write_access)):
    """Update a template-based minutes (with audit trail)"""
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    # Track the update
    update_fields = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user["user_id"]
    }
    
    # Allow updating the generated document and status
    if update_data.generated_document is not None:
        update_fields["generated_document"] = update_data.generated_document
    if update_data.status is not None:
        update_fields["status"] = update_data.status
    if update_data.template_data is not None:
        update_fields["template_data"] = update_data.template_data
    
    await db.minutes_templates.update_one(
        {"minutes_id": minutes_id},
        {"$set": update_fields}
    )
    
    updated = await db.minutes_templates.find_one({"minutes_id": minutes_id}, {"_id": 0})
    return updated

@router.delete("/minutes-templates/{minutes_id}")
async def delete_minutes_template(minutes_id: str, user: dict = Depends(require_write_access)):
    """Delete a template-based minutes"""
    result = await db.minutes_templates.delete_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return {"message": "Minutes deleted"}

@router.get("/minutes-templates/{minutes_id}/pdf")
async def get_minutes_template_pdf(minutes_id: str, user: dict = Depends(get_current_user)):
    """Generate PDF for template-based minutes"""
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found")
    
    # Generate PDF from the document text
    buffer = io.BytesIO()
    pdf_doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TrustTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=6,
        textColor=colors.HexColor('#010079'),
        alignment=1  # Center
    )
    body_style = ParagraphStyle(
        'TrustBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        spaceAfter=6
    )
    
    story = []
    
    # Convert text document to PDF paragraphs
    doc_text = minutes.get("generated_document", "")
    lines = doc_text.split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 6))
        elif line.startswith("═") or line.startswith("─"):
            story.append(Spacer(1, 12))
        elif line == "TRUST MINUTES":
            story.append(Paragraph(line, title_style))
        elif line.startswith("Resolution") or line.isupper():
            story.append(Paragraph(f"<b>{line}</b>", body_style))
        elif line.startswith("WHEREAS") or line.startswith("NOW, THEREFORE"):
            story.append(Paragraph(f"<i>{line}</i>", body_style))
        elif line.startswith("•"):
            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{line}", body_style))
        else:
            # Escape special characters for reportlab
            line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(line, body_style))
    
    # Check if watermark should be shown (soft gating based on subscription)
    show_watermark = await should_show_watermark(user["user_id"])
    
    # Add watermark footer
    if show_watermark:
        story.append(Spacer(1, 30))
        watermark_style = ParagraphStyle(
            'Watermark',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#888888'),
            alignment=1  # Center
        )
        story.append(Paragraph("Generated by TrustOffice • Subscribe to remove watermark", watermark_style))
    
    pdf_doc.build(story)
    pdf_bytes = buffer.getvalue()
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    return {
        "pdf_base64": pdf_base64,
        "filename": f"minutes_{minutes_id}.pdf"
    }

@router.get("/template-options")
async def get_template_options(trust_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Get available minutes template options with descriptions"""
    templates = [
        {
            "type": "blank",
            "name": "Blank Minutes",
            "description": "Start with a blank minutes document",
            "icon": "file-text",
            "category": "basic"
        },
        {
            "type": "general_meeting",
            "name": "General Meeting",
            "description": "Record a general trustee meeting with multiple resolutions",
            "icon": "users",
            "category": "basic"
        },
        {
            "type": "distribution_to_beneficiaries",
            "name": "Distribution to Beneficiaries",
            "description": "Document a distribution of trust proceeds to beneficiaries",
            "icon": "dollar-sign",
            "category": "distributions"
        },
        {
            "type": "hems_distribution",
            "name": "HEMS Distribution",
            "description": "Health, Education, Maintenance, Support distribution with standard compliance",
            "icon": "heart-pulse",
            "category": "distributions"
        },
        {
            "type": "acceptance_of_property",
            "name": "Accept Property into Trust",
            "description": "Accept additional property into the trust corpus and update Schedule A",
            "icon": "plus-circle",
            "category": "assets"
        },
        {
            "type": "disposition_of_asset",
            "name": "Dispose / Sell Asset",
            "description": "Record the sale, transfer, or removal of an asset from Schedule A",
            "icon": "minus-circle",
            "category": "assets"
        },
        {
            "type": "appointment_additional_trustee",
            "name": "Appoint Additional Trustee",
            "description": "Appoint a new trustee to serve alongside existing trustees",
            "icon": "user-plus",
            "category": "governance"
        },
        {
            "type": "appointment_successor_trustee",
            "name": "Appoint Successor Trustee",
            "description": "Appoint a replacement trustee due to resignation, death, or removal",
            "icon": "user-check",
            "category": "governance"
        },
        {
            "type": "trustee_resignation",
            "name": "Trustee Resignation/Removal",
            "description": "Document a trustee's departure from office",
            "icon": "user-minus",
            "category": "governance"
        },
        {
            "type": "trustee_compensation",
            "name": "Trustee Compensation",
            "description": "Approve trustee fee arrangements and compensation",
            "icon": "wallet",
            "category": "governance"
        },
        {
            "type": "designation_of_beneficiaries",
            "name": "Designate Beneficiaries",
            "description": "Establish or amend beneficiary designations and units of beneficial interest",
            "icon": "users-round",
            "category": "beneficiaries"
        },
        {
            "type": "beneficiary_request_denial",
            "name": "Beneficiary Request Denial",
            "description": "Document denial of a beneficiary request with proper reasoning",
            "icon": "x-circle",
            "category": "beneficiaries"
        },
        {
            "type": "beneficiary_loan",
            "name": "Loan to Beneficiary",
            "description": "Authorize an intra-family loan to a beneficiary",
            "icon": "hand-coins",
            "category": "beneficiaries"
        },
        {
            "type": "bank_account_authorization",
            "name": "Open Bank Account",
            "description": "Authorize opening a bank or investment account for the trust",
            "icon": "landmark",
            "category": "financial"
        },
        {
            "type": "investment_policy",
            "name": "Investment Policy",
            "description": "Adopt, amend, or review the trust's investment policy statement",
            "icon": "trending-up",
            "category": "financial"
        },
        {
            "type": "loan_authorization",
            "name": "Loan Authorization",
            "description": "Authorize the trust to make or receive a loan",
            "icon": "banknote",
            "category": "financial"
        },
        {
            "type": "insurance_authorization",
            "name": "Insurance Authorization",
            "description": "Approve trust insurance policies and coverage",
            "icon": "shield-check",
            "category": "financial"
        },
        {
            "type": "annual_review",
            "name": "Annual Review Meeting",
            "description": "Year-end financial and governance review with comprehensive report",
            "icon": "calendar-check",
            "category": "reviews"
        },
        {
            "type": "quarterly_review",
            "name": "Quarterly Review Meeting",
            "description": "Routine quarterly trustee meeting and financial review",
            "icon": "calendar-days",
            "category": "reviews"
        },
        {
            "type": "change_of_situs",
            "name": "Change Trust Situs",
            "description": "Change the jurisdiction and principal place of administration",
            "icon": "map-pin",
            "category": "administrative"
        },
        {
            "type": "benevolence_approval",
            "name": "Benevolence Assistance",
            "description": "Approve and document a benevolence grant for charitable assistance",
            "icon": "heart-handshake",
            "category": "benevolence",
            "requires_benevolence": True
        },
        # Legal/Amendment templates
        {
            "type": "trust_amendment",
            "name": "Trust Amendment",
            "description": "Modify specific provisions of the trust instrument",
            "icon": "file-edit",
            "category": "legal"
        },
        {
            "type": "power_of_attorney",
            "name": "Power of Attorney",
            "description": "Grant limited power of attorney to a trustee or agent",
            "icon": "stamp",
            "category": "legal"
        },
        {
            "type": "trust_termination",
            "name": "Trust Termination",
            "description": "Document trust dissolution and final distribution",
            "icon": "file-x",
            "category": "legal"
        },
        # Asset Management templates
        {
            "type": "real_estate_purchase",
            "name": "Real Estate Purchase",
            "description": "Authorize acquisition of real property for the trust",
            "icon": "home",
            "category": "assets"
        },
        {
            "type": "business_interest_acquisition",
            "name": "Business Interest Acquisition",
            "description": "Authorize purchase of LLC, partnership, or corporate interest",
            "icon": "building-2",
            "category": "assets"
        },
        {
            "type": "real_estate_lease",
            "name": "Real Estate Lease",
            "description": "Authorize leasing of trust real property to third parties",
            "icon": "key",
            "category": "assets"
        },
        # Tax & Compliance templates
        {
            "type": "fiscal_year_election",
            "name": "Fiscal Year Election",
            "description": "Document the trust's fiscal year choice for tax purposes",
            "icon": "calendar-range",
            "category": "administrative"
        },
        {
            "type": "tax_filing_authorization",
            "name": "Tax Filing Authorization",
            "description": "Authorize preparation and filing of trust tax returns",
            "icon": "receipt",
            "category": "administrative"
        },
        # Special Situation templates
        {
            "type": "emergency_ratification",
            "name": "Emergency Action Ratification",
            "description": "Ratify trustee actions taken during an emergency",
            "icon": "alert-triangle",
            "category": "governance"
        },
        {
            "type": "conflict_of_interest",
            "name": "Conflict of Interest Disclosure",
            "description": "Document trustee's disclosure and waiver of conflict",
            "icon": "scale",
            "category": "governance"
        }
    ]
    
    # Filter benevolence template based on trust settings
    if trust_id:
        trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
        if trust and trust.get("benevolence_enabled"):
            return templates
        else:
            return [t for t in templates if not t.get("requires_benevolence")]
    
    return templates
