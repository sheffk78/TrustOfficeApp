# Schedule A router - handles trust asset ledger (Schedule A)
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import base64

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from database import db
from dependencies import get_current_user, require_write_access, should_show_watermark
from models import ScheduleAItemCreate, ScheduleAItemUpdate, ScheduleAItemResponse
from pdf_utils import NAVY, GRAY, LIGHT_GRAY, separator_line, create_doc_template

router = APIRouter(tags=["schedule-a"])

# ==================== SCHEDULE A ENDPOINTS ====================

@router.post("/schedule-a", response_model=ScheduleAItemResponse)
async def create_schedule_a_item(item: ScheduleAItemCreate, user: dict = Depends(require_write_access)):
    """Add an asset to Schedule A"""
    trust = await db.trusts.find_one({"trust_id": item.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    item_id = f"asset_{uuid.uuid4().hex[:12]}"
    item_doc = {
        "item_id": item_id,
        "trust_id": item.trust_id,
        "user_id": user["user_id"],
        "category": item.category.value,
        "description": item.description,
        "identifier": item.identifier,
        "location": item.location,
        "approximate_value": item.approximate_value,
        "date_conveyed": item.date_conveyed,
        "notes": item.notes,
        "status": "active",
        "minutes_ref": item.minutes_ref,
        "disposition_minutes_ref": None,
        "disposition_date": None,
        "disposition_notes": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None
    }
    
    await db.schedule_a_items.insert_one(item_doc)
    return ScheduleAItemResponse(**item_doc)

@router.get("/schedule-a")
async def get_schedule_a_items(
    trust_id: str, 
    category: Optional[str] = None, 
    status: Optional[str] = "active",  # Default to active only, use "all" for all assets
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user)
):
    """Get all Schedule A items for a trust. Use status='all' to include disposed assets (paginated)."""
    query = {"trust_id": trust_id, "user_id": user["user_id"]}
    if category:
        query["category"] = category
    
    # Handle status filtering with backward compatibility
    # Items without status field are treated as 'active'
    if status and status != "all":
        if status == "active":
            # Match either explicit 'active' OR no status field (legacy items)
            query["$or"] = [{"status": "active"}, {"status": {"$exists": False}}]
        else:
            query["status"] = status
    
    total = await db.schedule_a_items.count_documents(query)
    items = await db.schedule_a_items.find(query, {"_id": 0}).sort("category", 1).skip(skip).limit(limit).to_list(limit)
    # Ensure backward compatibility - set defaults for items without status field
    for item in items:
        if "status" not in item:
            item["status"] = "active"
        if "minutes_ref" not in item:
            item["minutes_ref"] = None
        if "disposition_minutes_ref" not in item:
            item["disposition_minutes_ref"] = None
        if "disposition_date" not in item:
            item["disposition_date"] = None
        if "disposition_notes" not in item:
            item["disposition_notes"] = None
    return {
        "items": [ScheduleAItemResponse(**item) for item in items],
        "total": total,
        "skip": skip,
        "limit": limit
    }

@router.get("/schedule-a/{item_id}", response_model=ScheduleAItemResponse)
async def get_schedule_a_item(item_id: str, user: dict = Depends(get_current_user)):
    """Get a single Schedule A item"""
    item = await db.schedule_a_items.find_one({"item_id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Asset not found")
    # Ensure backward compatibility
    if "status" not in item:
        item["status"] = "active"
    if "minutes_ref" not in item:
        item["minutes_ref"] = None
    if "disposition_minutes_ref" not in item:
        item["disposition_minutes_ref"] = None
    if "disposition_date" not in item:
        item["disposition_date"] = None
    if "disposition_notes" not in item:
        item["disposition_notes"] = None
    return ScheduleAItemResponse(**item)

@router.put("/schedule-a/{item_id}", response_model=ScheduleAItemResponse)
async def update_schedule_a_item(item_id: str, update: ScheduleAItemUpdate, user: dict = Depends(require_write_access)):
    """Update a Schedule A item"""
    item = await db.schedule_a_items.find_one({"item_id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.schedule_a_items.update_one(
        {"item_id": item_id},
        {"$set": update_data}
    )
    
    updated_item = await db.schedule_a_items.find_one({"item_id": item_id}, {"_id": 0})
    return ScheduleAItemResponse(**updated_item)

@router.delete("/schedule-a/{item_id}")
async def delete_schedule_a_item(item_id: str, user: dict = Depends(require_write_access)):
    """Delete a Schedule A item"""
    result = await db.schedule_a_items.delete_one({"item_id": item_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"message": "Asset deleted"}


class DisposeAssetRequest(BaseModel):
    """Request model for disposing an asset without minutes"""
    disposition_date: str
    disposition_reason: str = "sale"  # sale, transfer, donation, destruction
    disposition_value: Optional[float] = Field(None, ge=0)
    disposition_recipient: Optional[str] = None
    disposition_notes: Optional[str] = None


@router.post("/schedule-a/{item_id}/dispose")
async def dispose_schedule_a_item(
    item_id: str, 
    request: DisposeAssetRequest,
    user: dict = Depends(require_write_access)
):
    """
    Mark a Schedule A item as disposed (without creating minutes).
    This is for quick dispositions; for formal documentation, use the disposition_of_asset minutes template.
    """
    item = await db.schedule_a_items.find_one(
        {"item_id": item_id, "user_id": user["user_id"]}, 
        {"_id": 0}
    )
    if not item:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if item.get("status") == "disposed":
        raise HTTPException(status_code=400, detail="Asset is already disposed")
    
    # Build disposition notes
    notes_parts = [f"Reason: {request.disposition_reason}"]
    if request.disposition_recipient:
        notes_parts.append(f"Recipient: {request.disposition_recipient}")
    if request.disposition_value:
        notes_parts.append(f"Value: ${request.disposition_value:,.2f}")
    if request.disposition_notes:
        notes_parts.append(request.disposition_notes)
    
    update_data = {
        "status": "disposed",
        "disposition_date": request.disposition_date,
        "disposition_notes": ". ".join(notes_parts),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.schedule_a_items.update_one(
        {"item_id": item_id},
        {"$set": update_data}
    )
    
    return {"message": "Asset marked as disposed", "item_id": item_id}

@router.get("/schedule-a/summary/{trust_id}")
async def get_schedule_a_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """Get Schedule A summary with totals by category"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    items = await db.schedule_a_items.find({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0}).to_list(1000)
    
    # Group by category
    categories = {}
    total_value = 0
    
    for item in items:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = {"items": [], "total_value": 0, "count": 0}
        categories[cat]["items"].append(item)
        categories[cat]["count"] += 1
        if item.get("approximate_value"):
            categories[cat]["total_value"] += item["approximate_value"]
            total_value += item["approximate_value"]
    
    return {
        "trust_id": trust_id,
        "trust_name": trust.get("name", ""),
        "categories": categories,
        "total_items": len(items),
        "total_value": total_value
    }

@router.get("/schedule-a/export/{trust_id}/pdf")
async def export_schedule_a_pdf(trust_id: str, user: dict = Depends(get_current_user)):
    """Generate a styled PDF export of Schedule A"""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Check if watermark should be shown (soft gating based on subscription)
    show_watermark = await should_show_watermark(user["user_id"])
    hide_watermark = not show_watermark
    
    items = await db.schedule_a_items.find(
        {"trust_id": trust_id, "user_id": user["user_id"]}, 
        {"_id": 0}
    ).sort("category", 1).to_list(1000)
    
    # Category display names and order
    CATEGORY_ORDER = [
        ("real_property", "REAL PROPERTY", "Land, buildings, residences, and other real estate"),
        ("personal_property", "PERSONAL PROPERTY (TANGIBLE)", "Vehicles, furnishings, equipment, and other tangible items"),
        ("financial_accounts", "FINANCIAL ACCOUNTS", "Bank accounts, investment accounts, and brokerage accounts"),
        ("business_interests", "BUSINESS INTERESTS", "Ownership interests in LLCs, partnerships, corporations"),
        ("digital_assets", "DIGITAL ASSETS", "Cryptocurrency, NFTs, and other digital holdings"),
        ("intellectual_property", "INTELLECTUAL PROPERTY", "Trademarks, copyrights, patents, and trade secrets"),
        ("notes_receivable", "NOTES RECEIVABLE / DEBTS OWED TO GRANTOR", "Promissory notes and debts owed to the grantor"),
        ("other_property", "OTHER PROPERTY", "Precious metals, art, collectibles, and other assets"),
    ]
    
    # Group items by category
    grouped = {}
    for item in items:
        cat = item.get("category", "other_property")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item)
    
    # Calculate totals
    total_value = sum(item.get("approximate_value", 0) or 0 for item in items)
    
    # Generate PDF
    doc, buffer = create_doc_template()
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'ScheduleTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=6,
        textColor=NAVY,
        alignment=1,  # Center
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'ScheduleSubtitle',
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
    
    category_desc_style = ParagraphStyle(
        'CategoryDesc',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=8,
        textColor=colors.HexColor('#888888'),
        fontName='Helvetica-Oblique'
    )
    
    footer_style = ParagraphStyle(
        'ScheduleFooter',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#888888'),
        alignment=1,
        fontName='Helvetica'
    )
    
    story = []
    
    # Header
    story.append(Paragraph("SCHEDULE A", title_style))
    story.append(Paragraph("Initial Corpus of the Trust", subtitle_style))
    story.append(Spacer(1, 6))
    
    # Trust info
    trust_name = trust.get("name", "Private Trust")
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    info_data = [
        ["Trust Name:", trust_name],
        ["Date Prepared:", current_date],
        ["Total Assets:", str(len(items))],
        ["Total Estimated Value:", f"${total_value:,.2f}" if total_value else "Not disclosed"],
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
    story.append(Spacer(1, 12))
    
    # Categories
    for cat_key, cat_name, cat_desc in CATEGORY_ORDER:
        cat_items = grouped.get(cat_key, [])
        if not cat_items:
            continue
        
        # Category header
        story.append(Paragraph(cat_name, category_style))
        story.append(Paragraph(cat_desc, category_desc_style))
        
        # Category total
        cat_total = sum(item.get("approximate_value", 0) or 0 for item in cat_items)
        
        # Table header
        table_data = [["Description", "Identifier", "Location", "Value", "Date"]]
        
        for item in cat_items:
            desc = item.get("description", "")[:50]
            if len(item.get("description", "")) > 50:
                desc += "..."
            identifier = item.get("identifier", "—") or "—"
            location = item.get("location", "—") or "—"
            if len(location) > 30:
                location = location[:30] + "..."
            value = f"${item.get('approximate_value', 0):,.2f}" if item.get("approximate_value") else "N/D"
            date_conveyed = item.get("date_conveyed", "—") or "—"
            if date_conveyed and date_conveyed != "—":
                try:
                    # Try to format the date
                    from datetime import datetime as dt
                    if "T" in date_conveyed:
                        date_conveyed = dt.fromisoformat(date_conveyed.replace("Z", "+00:00")).strftime("%m/%d/%Y")
                    elif "-" in date_conveyed and len(date_conveyed) == 10:
                        date_conveyed = dt.strptime(date_conveyed, "%Y-%m-%d").strftime("%m/%d/%Y")
                except (ValueError, AttributeError):
                    pass
            
            table_data.append([desc, identifier, location, value, date_conveyed])
        
        # Add subtotal row
        table_data.append(["", "", f"Subtotal ({len(cat_items)} items):", f"${cat_total:,.2f}", ""])
        
        # Create table
        col_widths = [2*inch, 1.2*inch, 1.5*inch, 0.9*inch, 0.9*inch]
        asset_table = Table(table_data, colWidths=col_widths)
        asset_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Data rows
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -2), 8),
            ('ALIGN', (3, 1), (3, -1), 'RIGHT'),  # Value column
            ('ALIGN', (4, 1), (4, -1), 'CENTER'),  # Date column
            
            # Subtotal row
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 8),
            ('BACKGROUND', (0, -1), (-1, -1), LIGHT_GRAY),
            ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
            ('BOX', (0, 0), (-1, -1), 1, NAVY),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(asset_table)
        story.append(Spacer(1, 12))
    
    # Grand Total
    story.append(Spacer(1, 12))
    story.append(separator_line(thickness=2))
    story.append(Spacer(1, 8))
    
    total_data = [
        ["GRAND TOTAL", f"{len(items)} Assets", f"${total_value:,.2f}"]
    ]
    total_table = Table(total_data, colWidths=[3.5*inch, 1.5*inch, 1.5*inch])
    total_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, 0), NAVY),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
    ]))
    story.append(total_table)
    
    # Footer
    story.append(Spacer(1, 24))
    if not hide_watermark:
        story.append(Paragraph(
            f"{trust_name} – Schedule A – Private Trust Document – Confidential",
            footer_style
        ))
        story.append(Paragraph(
            "This document is private and confidential. Not for public disclosure.",
            footer_style
        ))
    
    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    
    return {
        "pdf_base64": pdf_base64,
        "filename": f"schedule_a_{trust_id}.pdf"
    }


