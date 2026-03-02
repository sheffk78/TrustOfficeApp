# Minutes router - handles minutes records and templates
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import io
import base64

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
    user: dict = Depends(get_current_user)
):
    """Get minutes with optional search and filters"""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id
    if minutes_type:
        query["minutes_type"] = minutes_type
    
    # Add text search across participants and decisions
    if search:
        search_term = search.strip()
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

@router.delete("/minutes/{minutes_id}")
async def delete_minutes(minutes_id: str, user: dict = Depends(require_write_access)):
    result = await db.minutes_records.delete_one({"minutes_id": minutes_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found")
    return {"message": "Minutes deleted"}

def generate_minutes_pdf(minutes: dict, trust: dict, hide_watermark: bool = False) -> bytes:
    """Generate a professional PDF for minutes record"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    # Custom styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TrustTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=6,
        textColor=colors.HexColor('#010079')
    )
    heading_style = ParagraphStyle(
        'TrustHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor('#010079')
    )
    body_style = ParagraphStyle(
        'TrustBody',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        spaceAfter=8
    )
    label_style = ParagraphStyle(
        'TrustLabel',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666')
    )
    
    story = []
    
    # Header
    story.append(Paragraph(trust.get('name', 'Trust'), title_style))
    story.append(Paragraph(f"Meeting Minutes - {minutes.get('minutes_type', 'General').replace('_', ' ').title()}", heading_style))
    story.append(Spacer(1, 12))
    
    # Meeting details table
    meeting_date = minutes.get('meeting_date', 'N/A')
    if 'T' in meeting_date:
        meeting_date = meeting_date.split('T')[0]
    
    details_data = [
        ['Meeting Date:', meeting_date],
        ['Minutes Type:', minutes.get('minutes_type', 'General').replace('_', ' ').title()],
        ['Trust:', trust.get('name', 'N/A')],
        ['Jurisdiction:', trust.get('jurisdiction', 'N/A')]
    ]
    
    details_table = Table(details_data, colWidths=[1.5*inch, 4.5*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 20))
    
    # Participants
    if minutes.get('participants_text'):
        story.append(Paragraph('Participants Present', heading_style))
        participants = minutes.get('participants_text', '').split(',')
        for p in participants:
            if p.strip():
                story.append(Paragraph(f"• {p.strip()}", body_style))
        story.append(Spacer(1, 12))
    
    # Decisions/Discussion
    if minutes.get('decisions_text'):
        story.append(Paragraph('Decisions & Discussion', heading_style))
        story.append(Paragraph(minutes.get('decisions_text', ''), body_style))
        story.append(Spacer(1, 12))
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph('_' * 50, body_style))
    story.append(Paragraph('Trustee Signature', label_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph('_' * 50, body_style))
    story.append(Paragraph('Date', label_style))
    
    # Generated timestamp (watermark)
    story.append(Spacer(1, 30))
    if not hide_watermark:
        story.append(Paragraph(
            f"Generated by TrustOffice on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}",
            ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#999999'))
        ))
    
    doc.build(story)
    return buffer.getvalue()

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
            "icon": "file-text"
        },
        {
            "type": "general_meeting",
            "name": "General Meeting",
            "description": "Record a general trustee meeting with multiple resolutions",
            "icon": "users"
        },
        {
            "type": "distribution_to_beneficiaries",
            "name": "Distribution to Beneficiaries",
            "description": "Document a distribution of trust proceeds to beneficiaries",
            "icon": "dollar-sign"
        },
        {
            "type": "acceptance_of_property",
            "name": "Accept Property into Trust",
            "description": "Accept additional property into the trust corpus and update Schedule A",
            "icon": "plus-circle"
        },
        {
            "type": "disposition_of_asset",
            "name": "Dispose / Sell Asset",
            "description": "Record the sale, transfer, or removal of an asset from Schedule A",
            "icon": "minus-circle"
        },
        {
            "type": "appointment_additional_trustee",
            "name": "Appoint Additional Trustee",
            "description": "Appoint a new trustee to serve alongside existing trustees",
            "icon": "user-plus"
        },
        {
            "type": "appointment_successor_trustee",
            "name": "Appoint Successor Trustee",
            "description": "Appoint a replacement trustee due to resignation, death, or removal",
            "icon": "user-check"
        },
        {
            "type": "designation_of_beneficiaries",
            "name": "Designate Beneficiaries",
            "description": "Establish or amend beneficiary designations and units of beneficial interest",
            "icon": "users-round"
        },
        {
            "type": "bank_account_authorization",
            "name": "Open Bank Account",
            "description": "Authorize opening a bank or investment account for the trust",
            "icon": "landmark"
        },
        {
            "type": "change_of_situs",
            "name": "Change Trust Situs",
            "description": "Change the jurisdiction and principal place of administration",
            "icon": "map-pin"
        },
        {
            "type": "benevolence_approval",
            "name": "Benevolence Assistance",
            "description": "Approve and document a benevolence grant for charitable assistance",
            "icon": "heart-handshake",
            "requires_benevolence": True
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
