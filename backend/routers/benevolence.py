# Benevolence router - handles charitable assistance tracking
from fastapi import APIRouter, HTTPException, Depends, Response
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from database import db
from dependencies import get_current_user, require_write_access, should_show_watermark
from models import (
    BenevolenceRecordCreate, BenevolenceRecordUpdate, BenevolenceRecordResponse
)
from pdf_utils import NAVY, GRAY, separator_line, create_doc_template

router = APIRouter(tags=["benevolence"])


# ==================== BENEVOLENCE CRUD ENDPOINTS ====================

@router.post("/benevolence", response_model=BenevolenceRecordResponse)
async def create_benevolence_record(record: BenevolenceRecordCreate, user: dict = Depends(require_write_access)):
    """Create a new benevolence record"""
    trust = await db.trusts.find_one({"trust_id": record.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    if not trust.get("benevolence_enabled"):
        raise HTTPException(status_code=400, detail="Benevolence mode is not enabled for this trust. Enable it in the trust settings or upgrade your plan at trustoffice.app/settings/billing.")
    
    record_id = f"ben_{uuid.uuid4().hex[:12]}"
    record_doc = {
        "record_id": record_id,
        "trust_id": record.trust_id,
        "user_id": user["user_id"],
        "beneficiary_name": record.beneficiary_name,
        "beneficiary_type": record.beneficiary_type,
        "purpose": record.purpose.value,
        "purpose_description": record.purpose_description,
        "amount": record.amount,
        "date": record.date,
        "approved_by": record.approved_by,
        "approval_method": record.approval_method,
        "minutes_id": record.minutes_id,
        "notes": record.notes,
        "status": record.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None
    }
    
    await db.benevolence_records.insert_one(record_doc)
    return BenevolenceRecordResponse(**record_doc)


@router.get("/benevolence", response_model=List[BenevolenceRecordResponse])
async def get_benevolence_records(
    trust_id: str,
    purpose: Optional[str] = None,
    status: Optional[str] = None,
    approver: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Get benevolence records with optional filters"""
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    
    if purpose:
        query["purpose"] = purpose
    if status:
        query["status"] = status
    if approver:
        query["approved_by"] = {"$in": [approver]}
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        if "date" in query:
            query["date"]["$lte"] = end_date
        else:
            query["date"] = {"$lte": end_date}
    
    records = await db.benevolence_records.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    return [BenevolenceRecordResponse(**r) for r in records]


@router.get("/benevolence/{record_id}", response_model=BenevolenceRecordResponse)
async def get_benevolence_record(record_id: str, user: dict = Depends(get_current_user)):
    """Get a single benevolence record"""
    record = await db.benevolence_records.find_one(
        {"record_id": record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Benevolence record not found. It may have been deleted. Please refresh the page and try again.")
    return BenevolenceRecordResponse(**record)


@router.put("/benevolence/{record_id}", response_model=BenevolenceRecordResponse)
async def update_benevolence_record(record_id: str, update: BenevolenceRecordUpdate, user: dict = Depends(require_write_access)):
    """Update a benevolence record"""
    record = await db.benevolence_records.find_one(
        {"record_id": record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Benevolence record not found. It may have been deleted. Please refresh the page and try again.")
    
    update_data = {k: v for k, v in update.dict().items() if v is not None}
    if "purpose" in update_data and hasattr(update_data["purpose"], "value"):
        update_data["purpose"] = update_data["purpose"].value
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.benevolence_records.update_one(
        {"record_id": record_id},
        {"$set": update_data}
    )
    
    updated = await db.benevolence_records.find_one({"record_id": record_id}, {"_id": 0})
    return BenevolenceRecordResponse(**updated)


@router.patch("/benevolence/{record_id}/attach-minutes", response_model=BenevolenceRecordResponse)
async def attach_minutes_to_benevolence(
    record_id: str,
    request: dict,
    user: dict = Depends(require_write_access)
):
    """
    Attach existing minutes to a benevolence record.
    
    This is the "Money → Minutes" flow where the trustee links an existing
    benevolence record to a minutes record that documented the approval decision.
    Does NOT modify the minutes text - only creates the reference link.
    """
    record = await db.benevolence_records.find_one(
        {"record_id": record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Benevolence record not found. It may have been deleted. Please refresh the page and try again.")
    
    minutes_record_id = request.get("minutes_record_id")
    if not minutes_record_id:
        raise HTTPException(status_code=400, detail="minutes_record_id is required. Please select a minutes record to link this benevolence record to.")
    
    # Verify the minutes record exists and belongs to the user
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_record_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes record not found. It may have been deleted. Please refresh the page and try again.")
    
    await db.benevolence_records.update_one(
        {"record_id": record_id},
        {"$set": {
            "minutes_id": minutes_record_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    updated = await db.benevolence_records.find_one({"record_id": record_id}, {"_id": 0})
    return BenevolenceRecordResponse(**updated)


@router.delete("/benevolence/{record_id}")
async def delete_benevolence_record(record_id: str, user: dict = Depends(require_write_access)):
    """Delete a benevolence record"""
    result = await db.benevolence_records.delete_one(
        {"record_id": record_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Benevolence record not found. It may have been already deleted. Please refresh the page and try again.")
    return {"message": "Benevolence record deleted"}


# ==================== BENEVOLENCE SUMMARY & REPORTING ====================

@router.get("/benevolence/summary/{trust_id}")
async def get_benevolence_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """Get benevolence summary with totals by period and purpose"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    records = await db.benevolence_records.find(
        {"trust_id": trust_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    
    # Calculate totals
    total_amount = sum(r.get("amount", 0) for r in records)
    total_count = len(records)
    
    # Group by purpose
    by_purpose = {}
    for r in records:
        purpose = r.get("purpose", "other")
        if purpose not in by_purpose:
            by_purpose[purpose] = {"count": 0, "total": 0}
        by_purpose[purpose]["count"] += 1
        by_purpose[purpose]["total"] += r.get("amount", 0)
    
    # Group by month/quarter/year
    by_month = {}
    by_quarter = {}
    by_year = {}
    
    for r in records:
        date_str = r.get("date", "")
        amount = r.get("amount", 0)
        
        try:
            if "T" in date_str:
                date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                date = datetime.strptime(date_str[:10], "%Y-%m-%d")
            
            # Month key (YYYY-MM)
            month_key = date.strftime("%Y-%m")
            if month_key not in by_month:
                by_month[month_key] = {"count": 0, "total": 0}
            by_month[month_key]["count"] += 1
            by_month[month_key]["total"] += amount
            
            # Quarter key (YYYY-Q#)
            quarter = (date.month - 1) // 3 + 1
            quarter_key = f"{date.year}-Q{quarter}"
            if quarter_key not in by_quarter:
                by_quarter[quarter_key] = {"count": 0, "total": 0}
            by_quarter[quarter_key]["count"] += 1
            by_quarter[quarter_key]["total"] += amount
            
            # Year key
            year_key = str(date.year)
            if year_key not in by_year:
                by_year[year_key] = {"count": 0, "total": 0}
            by_year[year_key]["count"] += 1
            by_year[year_key]["total"] += amount
        except (ValueError, AttributeError):
            pass
    
    # Get list of unique approvers
    all_approvers = set()
    for r in records:
        for approver in r.get("approved_by", []):
            all_approvers.add(approver)
    
    return {
        "trust_id": trust_id,
        "trust_name": trust.get("name", ""),
        "total_amount": total_amount,
        "total_count": total_count,
        "by_purpose": by_purpose,
        "by_month": dict(sorted(by_month.items(), reverse=True)),
        "by_quarter": dict(sorted(by_quarter.items(), reverse=True)),
        "by_year": dict(sorted(by_year.items(), reverse=True)),
        "approvers": list(all_approvers)
    }


# ==================== BENEVOLENCE PDF EXPORT ====================

@router.get("/benevolence/export/{trust_id}/pdf")
async def export_benevolence_pdf(
    trust_id: str, 
    year: Optional[int] = None,
    user: dict = Depends(get_current_user)
):
    """Generate a styled PDF export of Benevolence Report"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    if not trust.get("benevolence_enabled"):
        raise HTTPException(status_code=400, detail="Benevolence mode is not enabled for this trust. Enable it in the trust settings or upgrade your plan at trustoffice.app/settings/billing.")
    
    # Check if watermark should be shown (soft gating based on subscription)
    show_watermark = await should_show_watermark(user["user_id"])
    hide_watermark = not show_watermark
    
    # Get records, optionally filtered by year
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    records = await db.benevolence_records.find(query, {"_id": 0}).sort("date", -1).to_list(1000)
    
    # Filter by year if specified
    if year:
        filtered_records = []
        for r in records:
            try:
                date_str = r.get("date", "")
                if "T" in date_str:
                    record_year = int(date_str[:4])
                elif "-" in date_str:
                    record_year = int(date_str[:4])
                else:
                    continue
                if record_year == year:
                    filtered_records.append(r)
            except (ValueError, TypeError):
                pass
        records = filtered_records
    
    # Purpose category display names
    PURPOSE_LABELS = {
        "medical": "Medical Expenses",
        "housing": "Housing Assistance",
        "education": "Education",
        "food_necessities": "Food & Necessities",
        "utilities": "Utilities",
        "transportation": "Transportation",
        "emergency": "Emergency Relief",
        "spiritual": "Spiritual/Ministry",
        "assistance": "General Assistance",
        "other": "Other"
    }
    
    # Group by purpose
    grouped_by_purpose = {}
    for r in records:
        purpose = r.get("purpose", "other")
        if purpose not in grouped_by_purpose:
            grouped_by_purpose[purpose] = []
        grouped_by_purpose[purpose].append(r)
    
    # Calculate totals
    total_amount = sum(r.get("amount", 0) for r in records)
    total_grants = len(records)
    unique_beneficiaries = len(set(r.get("beneficiary_name", "") for r in records))
    
    # Generate PDF
    doc, buffer = create_doc_template()
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'BenevolenceTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=6,
        textColor=NAVY,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'BenevolenceSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=12,
        textColor=GRAY,
        alignment=1,
        fontName='Helvetica'
    )
    
    category_style = ParagraphStyle(
        'CategoryTitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceBefore=18,
        spaceAfter=6,
        textColor=NAVY,
        fontName='Helvetica-Bold'
    )
    
    story = []
    
    # Header
    story.append(Paragraph("BENEVOLENCE REPORT", title_style))
    year_text = f"Year {year}" if year else "All Time"
    story.append(Paragraph(f"Charitable Assistance Record • {year_text}", subtitle_style))
    story.append(Spacer(1, 6))
    
    # Trust & Report info
    trust_name = trust.get("name", "Private Trust")
    tax_status = trust.get("tax_status", "private")
    tax_label = {"501c3": "501(c)(3) Organization", "508": "508 Church/Religious Org", "private": "Private Foundation"}.get(tax_status, tax_status)
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    info_data = [
        ["Trust Name:", trust_name],
        ["Tax Status:", tax_label],
        ["Report Generated:", current_date],
        ["Period:", f"January 1 - December 31, {year}" if year else "All Records"],
    ]
    
    info_table = Table(info_data, colWidths=[1.5*inch, 4.5*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), NAVY),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))
    
    # Separator line
    story.append(separator_line())
    story.append(Spacer(1, 16))
    
    # Summary Statistics
    story.append(Paragraph("SUMMARY", category_style))
    
    summary_data = [
        ["Total Grants:", str(total_grants)],
        ["Total Disbursed:", f"${total_amount:,.2f}"],
        ["Unique Beneficiaries:", str(unique_beneficiaries)],
        ["Categories Used:", str(len(grouped_by_purpose))],
    ]
    
    summary_table = Table(summary_data, colWidths=[1.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (1, 0), (1, -1), NAVY),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 16))
    
    # Breakdown by Purpose
    story.append(Paragraph("GRANTS BY PURPOSE CATEGORY", category_style))
    
    purpose_order = ["medical", "housing", "education", "food_necessities", "utilities", 
                     "transportation", "emergency", "spiritual", "assistance", "other"]
    
    for purpose_key in purpose_order:
        purpose_records = grouped_by_purpose.get(purpose_key, [])
        if not purpose_records:
            continue
        
        purpose_label = PURPOSE_LABELS.get(purpose_key, purpose_key.title())
        purpose_total = sum(r.get("amount", 0) for r in purpose_records)
        
        # Category sub-header
        cat_header = ParagraphStyle(
            'PurposeHeader',
            parent=styles['Normal'],
            fontSize=11,
            spaceBefore=12,
            spaceAfter=4,
            textColor=colors.HexColor('#333333'),
            fontName='Helvetica-Bold'
        )
        story.append(Paragraph(f"{purpose_label} ({len(purpose_records)} grants • ${purpose_total:,.2f})", cat_header))
        
        # Table of grants in this category
        table_data = [["Date", "Beneficiary", "Description", "Amount"]]
        
        for r in purpose_records:
            date_str = r.get("date", "N/A")
            try:
                if "T" in date_str:
                    date_str = datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%m/%d/%Y")
                elif "-" in date_str and len(date_str) >= 10:
                    date_str = datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%m/%d/%Y")
            except (ValueError, AttributeError):
                pass
            
            beneficiary = r.get("beneficiary_name", "N/A")[:25]
            if len(r.get("beneficiary_name", "")) > 25:
                beneficiary += "..."
            
            desc = r.get("purpose_description", "")[:35]
            if len(r.get("purpose_description", "")) > 35:
                desc += "..."
            
            amount = f"${r.get('amount', 0):,.2f}"
            
            table_data.append([date_str, beneficiary, desc, amount])
        
        col_widths = [0.9*inch, 1.5*inch, 2.8*inch, 1*inch]
        grant_table = Table(table_data, colWidths=col_widths)
        grant_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F8F8')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(grant_table)
    
    # Footer
    story.append(Spacer(1, 24))
    story.append(Table([[""]], colWidths=[6.5*inch], rowHeights=[1]))
    story[-1].setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, NAVY),
    ]))
    story.append(Spacer(1, 8))
    
    footer_style = ParagraphStyle(
        'ReportFooter',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#888888'),
        alignment=1,
        fontName='Helvetica'
    )
    if not hide_watermark:
        story.append(Paragraph(
            f"This report was generated by {trust_name} on {current_date}. "
            "Maintain this record for tax reporting and audit purposes.",
            footer_style
        ))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Return PDF
    year_suffix = f"_{year}" if year else ""
    filename = f"benevolence_report{year_suffix}_{trust_id}.pdf"
    
    return Response(
        content=buffer.read(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
