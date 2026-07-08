# Minutes router - handles minutes records and templates
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import base64
import re
import logging

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from database import db
from dependencies import get_current_user, require_write_access, should_show_watermark, auto_update_onboarding
from trustee_utils import parse_trustees
from models import (
    MinutesCreate, MinutesResponse, MinutesTemplateCreate, MinutesTemplateResponse,
    MinutesDraftRequest, MinutesDraftResponse, MinutesAutosaveRequest,
    GuidedMinutesContext
)
from email_service import email_service
from ai_service import draft_minutes_from_structured_input, MinutesDraftRequest as AiMinutesDraftRequest
from routers.template_registry import get_template_registry, get_template_definition, build_ai_prompt
from pdf_utils import NAVY, GRAY, create_doc_template

router = APIRouter(tags=["minutes"])
logger = logging.getLogger(__name__)


@router.post("/minutes", response_model=MinutesResponse)
async def create_minutes(minutes: MinutesCreate, background_tasks: BackgroundTasks, user: dict = Depends(require_write_access)):
    trust = await db.trusts.find_one({"trust_id": minutes.trust_id, "user_id": user["user_id"]}, {"_id": 0})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": minutes.trust_id,
        "user_id": user["user_id"],
        "minutes_type": minutes.minutes_type.value,
        "meeting_date": minutes.meeting_date,
        "participants_text": minutes.participants_text,
        "decisions_text": minutes.decisions_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        # New fields for minutes redesign
        "template_type": minutes.template_type,
        "sections": minutes.sections or [],
        "template_data": minutes.template_data or {},
        "status": minutes.status,
        "is_retroactive": minutes.is_retroactive,
        "retroactive_reason": minutes.retroactive_reason,
        "retroactive_trustees_aware": minutes.retroactive_trustees_aware,
        "retroactive_type": minutes.retroactive_type,
        "manually_edited": minutes.manually_edited,
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
    
    # Only update onboarding when finalized (not drafts)
    if minutes.status == "finalized":
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
    template_type: Optional[str] = None,
    status: Optional[str] = None,
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
    if template_type:
        query["template_type"] = template_type
    if status:
        query["status"] = status
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


# ==================== STATIC-PATH MINUTES ENDPOINTS (must be before /minutes/{minutes_id}) ====================

@router.post("/minutes/draft", response_model=MinutesDraftResponse)
async def create_minutes_draft(
    request: MinutesDraftRequest,
    user: dict = Depends(require_write_access)
):
    """
    Unified AI draft generation for minutes.
    
    Supports two modes:
    1. Quick minutes (bullet-point input): agenda_items + key_decisions
    2. Template mode (structured fields): template_type + template_data
    
    Both modes include trust context (jurisdiction, trustee names, trust name).
    """
    user_id = user["user_id"]
    
    # Get trust context for AI
    trust = await db.trusts.find_one(
        {"trust_id": request.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    # Get entity-level details for beneficiary standard
    entity = await db.entities.find_one(
        {"trust_id": request.trust_id, "entity_type": "Trust", "user_id": user_id},
        {"_id": 0}
    )
    beneficiary_standard = entity.get("beneficiary_standard") if entity else None
    
    trust_name = trust.get("name", "")
    jurisdiction = trust.get("jurisdiction", "")
    participants_str = ", ".join(request.participants) if request.participants else ""
    
    # Determine minutes_type for backward compat
    minutes_type = request.minutes_type or "general"
    
    # Build AI prompt based on mode
    if request.template_type:
        # ── Template mode: use template-specific prompt ──
        template_def = get_template_definition(request.template_type)
        if not template_def:
            raise HTTPException(status_code=400, detail=f"Unknown template type '{request.template_type}'. Please select a valid template from the minutes wizard.")
        ai_context = {
            "trust_name": trust_name,
            "meeting_date": request.meeting_date,
            "participants": participants_str,
            "jurisdiction": jurisdiction,
            "beneficiary_standard": beneficiary_standard or "Not specified",
            "additional_context": request.additional_context or "",
        }
        
        # Add template_data fields to the context
        if request.template_data:
            ai_context.update(request.template_data)
            # Ensure additional_context remains a string after template_data update
            # (template_data may contain None values that would crash += operations)
            if ai_context.get("additional_context") is None:
                ai_context["additional_context"] = ""
        
        # Add bullet-point context if also provided
        if request.agenda_items:
            ai_context["agenda_items"] = "; ".join(request.agenda_items)
        if request.key_decisions:
            ai_context["key_decisions"] = "; ".join(request.key_decisions)
        
        # Add other attendees
        if request.other_attendees:
            ai_context.setdefault("additional_context", "")
            ai_context["additional_context"] += f"\nOther attendees: {', '.join(request.other_attendees)}"
        
        # Add retroactive context
        if request.is_retroactive:
            retro_note = f"\nRETROACTIVE: These minutes document a past event. Reason: {request.retroactive_reason or 'Not specified'}"
            ai_context["additional_context"] += retro_note
        
        # Add section context
        if request.section_context:
            ai_context["additional_context"] += f"\n{request.section_context}"
        
        ai_prompt_text = build_ai_prompt(request.template_type, ai_context)
        
        # Use the AI service with the constructed prompt
        try:
            ai_request = AiMinutesDraftRequest(
                minutes_type=minutes_type,
                meeting_date=request.meeting_date,
                participants=request.participants or parse_trustees(trust.get("trustees") or "") or [trust.get("role", "Trustee")],
                decisions_outline=[ai_prompt_text],
                trust_name=trust_name,
                jurisdiction=jurisdiction,
                beneficiary_standard=beneficiary_standard,
                additional_context=ai_context.get("additional_context", "")
            )
            ai_response = await draft_minutes_from_structured_input(ai_request)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating template minutes draft: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate minutes draft. Please try again. If this continues, contact support@trustoffice.app.")
    else:
        # ── Quick minutes / bullet-point mode ──
        decisions_outline = []
        
        if request.agenda_items:
            decisions_outline.append("AGENDA ITEMS DISCUSSED:")
            decisions_outline.extend([f"  - {item}" for item in request.agenda_items])
        
        if request.key_decisions:
            decisions_outline.append("KEY DECISIONS MADE:")
            decisions_outline.extend([f"  - {decision}" for decision in request.key_decisions])
        
        # Build additional context
        additional_context_parts = []
        if request.additional_context:
            additional_context_parts.append(f"Additional notes: {request.additional_context}")
        
        if request.other_attendees:
            additional_context_parts.append(
                f"Other attendees present (not trustees): {', '.join(request.other_attendees)}"
            )
        
        if request.is_retroactive:
            additional_context_parts.append(
                f"RETROACTIVE: These minutes document a past event. Reason: {request.retroactive_reason or 'Not specified'}"
            )
        
        if request.section_context:
            additional_context_parts.append(request.section_context)
        
        additional_context_parts.append(
            "WIZARD INPUT: This is from a guided wizard where the user provided brief bullet points. "
            "Please expand these into proper formal minutes language with WHEREAS clauses for context "
            "and RESOLVED clauses for each decision. Make the document complete and professional."
        )
        
        # Map minutes_type for AI service
        minutes_type_map = {
            "annual": "annual",
            "quarterly": "quarterly",
            "general": "quarterly"
        }
        ai_minutes_type = minutes_type_map.get(minutes_type, "quarterly")
        
        try:
            ai_request = AiMinutesDraftRequest(
                minutes_type=ai_minutes_type,
                meeting_date=request.meeting_date,
                participants=request.participants or parse_trustees(trust.get("trustees") or "") or [trust.get("role", "Trustee")],
                decisions_outline=decisions_outline if decisions_outline else ["No specific decisions recorded"],
                trust_name=trust_name,
                jurisdiction=jurisdiction,
                beneficiary_standard=beneficiary_standard,
                additional_context="\n".join(additional_context_parts)
            )
            ai_response = await draft_minutes_from_structured_input(ai_request)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating minutes draft: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate minutes draft. Please try again. If this continues, contact support@trustoffice.app.")
    
    return MinutesDraftResponse(
        suggested_title=ai_response.suggested_title,
        draft_body=ai_response.draft_body,
        cautions=ai_response.cautions + [
            "AI-generated content. Review all dates, amounts, and decisions before finalizing.",
            "You are responsible for accuracy and legal sufficiency of these minutes."
        ],
        minutes_type=minutes_type,
        meeting_date=request.meeting_date,
        participants_text=participants_str,
        template_type=request.template_type
    )


@router.post("/minutes/autosave", response_model=MinutesResponse)
async def autosave_minutes(
    request: MinutesAutosaveRequest,
    user: dict = Depends(require_write_access)
):
    """
    Save or update a draft minutes record.
    
    If minutes_id is provided, updates existing draft.
    If no minutes_id, creates a new draft record.
    Always forces status="draft".
    """
    user_id = user["user_id"]
    
    # Verify trust exists
    trust = await db.trusts.find_one(
        {"trust_id": request.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if request.minutes_id:
        # Update existing draft
        existing = await db.minutes_records.find_one(
            {"minutes_id": request.minutes_id, "user_id": user_id},
            {"_id": 0}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Draft minutes not found. It may have been deleted. Please start a new draft.")
        
        update_doc = {
            "minutes_type": request.minutes_type,
            "template_type": request.template_type,
            "meeting_date": request.meeting_date,
            "participants_text": request.participants_text,
            "decisions_text": request.decisions_text,
            "sections": request.sections or [],
            "template_data": request.template_data or {},
            "status": "draft",  # Force draft status
            "is_retroactive": request.is_retroactive,
            "retroactive_reason": request.retroactive_reason,
            "retroactive_trustees_aware": request.retroactive_trustees_aware,
            "retroactive_type": request.retroactive_type,
            "updated_at": now,
        }
        
        await db.minutes_records.update_one(
            {"minutes_id": request.minutes_id, "user_id": user_id},
            {"$set": update_doc}
        )
        
        # Fetch updated doc for response
        updated = await db.minutes_records.find_one(
            {"minutes_id": request.minutes_id},
            {"_id": 0}
        )
        logger.info(f"Autosave updated draft: {request.minutes_id}")
        return MinutesResponse(**updated)
    else:
        # Create new draft
        minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
        minutes_doc = {
            "minutes_id": minutes_id,
            "trust_id": request.trust_id,
            "user_id": user_id,
            "minutes_type": request.minutes_type,
            "template_type": request.template_type,
            "meeting_date": request.meeting_date,
            "participants_text": request.participants_text,
            "decisions_text": request.decisions_text,
            "sections": request.sections or [],
            "template_data": request.template_data or {},
            "status": "draft",
            "is_retroactive": request.is_retroactive,
            "retroactive_reason": request.retroactive_reason,
            "retroactive_trustees_aware": request.retroactive_trustees_aware,
            "retroactive_type": request.retroactive_type,
            "manually_edited": False,
            "created_at": now,
            "source": "wizard",
        }
        
        await db.minutes_records.insert_one(minutes_doc)
        logger.info(f"Autosave created new draft: {minutes_id}")
        return MinutesResponse(**minutes_doc)


@router.get("/minutes/drafts", response_model=List[MinutesResponse])
async def get_draft_minutes(
    trust_id: str,
    user: dict = Depends(get_current_user)
):
    """
    List draft minutes for current trust.
    
    Returns only records with status="draft", sorted by most recently updated.
    """
    query = {
        "user_id": user["user_id"],
        "trust_id": trust_id,
        "status": "draft"
    }
    
    minutes = await db.minutes_records.find(query, {"_id": 0}).sort("updated_at", -1).to_list(100)
    return [MinutesResponse(**m) for m in minutes]


@router.get("/minutes/context", response_model=GuidedMinutesContext)
async def get_minutes_context(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Get trust context for the unified minutes wizard.
    
    Returns trust information including name, jurisdiction, trustees list,
    and beneficiary standard to prefill the wizard and provide AI context.
    Same data as /guided-minutes/context but at /minutes/context.
    """
    user_id = user["user_id"]
    
    # If trust_id not provided, get the first/default trust
    if not trust_id:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0}
        )
    else:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
    
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
    # Get trustees from trust document or from entities
    # trustees is stored as comma-separated string in MongoDB, must parse it
    trustees_raw = trust.get("trustees", "")
    trustees = parse_trustees(trustees_raw) if isinstance(trustees_raw, str) else (trustees_raw if isinstance(trustees_raw, list) else [])

    # Always query entity for beneficiary standard (not just when trustees is empty)
    entity = await db.entities.find_one(
        {"trust_id": trust["trust_id"], "entity_type": "Trust", "user_id": user_id},
        {"_id": 0}
    )

    # If no trustees from trust doc, try entity trustee_names
    if not trustees and entity and entity.get("trustee_names"):
        trustees = parse_trustees(entity.get("trustee_names", ""))
    
    # Get beneficiary standard from entity if available
    beneficiary_standard = entity.get("beneficiary_standard") if entity else None
    article_ref_distribution = entity.get("article_ref_distribution") if entity else None
    article_ref_compensation = entity.get("article_ref_compensation") if entity else None
    
    return GuidedMinutesContext(
        trust_id=trust["trust_id"],
        trust_name=trust.get("name", ""),
        jurisdiction=trust.get("jurisdiction"),
        trustees=trustees,
        beneficiary_standard=beneficiary_standard,
        article_ref_distribution=article_ref_distribution,
        article_ref_compensation=article_ref_compensation,
        tax_status=trust.get("tax_status"),
        start_date=trust.get("start_date")
    )


@router.get("/minutes/{minutes_id}", response_model=MinutesResponse)
async def get_minutes_by_id(minutes_id: str, user: dict = Depends(get_current_user)):
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
    return MinutesResponse(**minutes)


@router.put("/minutes/{minutes_id}")
async def update_minutes(minutes_id: str, request: Request, user: dict = Depends(require_write_access)):
    """Update minutes content, participants, or other attendees"""
    data = await request.json()
    
    # Check if minutes are finalized
    existing = await db.minutes_records.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
    
    if existing.get("status") == "finalized":
        # Only allow unfinalizing (status -> draft) with a documented reason
        if "status" not in data or data["status"] != "draft":
            raise HTTPException(
                status_code=403,
                detail="Finalized minutes cannot be edited. To make changes, unfinalize with a documented reason."
            )
        # Record the unfinalize event in version history
        await db.minutes_version_history.insert_one({
            "minutes_id": minutes_id,
            "trust_id": existing.get("trust_id"),
            "action": "unfinalized",
            "previous_content": existing.get("generated_content", ""),
            "reason": data.get("unfinalize_reason", "No reason provided"),
            "user_id": user["user_id"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        # When unfinalizing, ONLY allow status change — no content edits in the same request
        update_data = {"status": "draft"}
        update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        result = await db.minutes_records.update_one(
            {"minutes_id": minutes_id, "user_id": user["user_id"]},
            {"$set": update_data}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
        return {"message": "Minutes unfinalized", "updated_fields": list(update_data.keys())}
    
    # Only allow updating specific fields
    allowed_fields = [
        'decisions_text', 'participants_text', 'other_attendees_text',
        'template_type', 'sections', 'template_data', 'status',
        'is_retroactive', 'retroactive_reason', 'retroactive_trustees_aware',
        'retroactive_type', 'manually_edited', 'meeting_date'
    ]
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update. Please provide at least one field to update (e.g., decisions_text, participants_text, meeting_date).")
    
    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    result = await db.minutes_records.update_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
    
    return {"message": "Minutes updated", "updated_fields": list(update_data.keys())}


@router.delete("/minutes/{minutes_id}")
async def delete_minutes(minutes_id: str, user: dict = Depends(require_write_access)):
    # Get the minutes record before deleting (for cascade)
    minutes = await db.minutes_records.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been already deleted. Please refresh the page and try again.")
    
    if minutes.get("status") == "finalized":
        raise HTTPException(
            status_code=403,
            detail="Finalized minutes cannot be deleted. This protects the legal record chain."
        )
    
    result = await db.minutes_records.delete_one({"minutes_id": minutes_id, "user_id": user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been already deleted. Please refresh the page and try again.")
    
    # Cascade: unlink any transactions that referenced these minutes
    if minutes:
        await db.transactions.update_many(
            {"linked_minutes_id": minutes_id, "user_id": user["user_id"]},
            {"$set": {"linked_minutes_id": None}}
        )
        # Re-activate spending threshold alerts for unlinked transactions
        from alert_detection import check_transaction_alerts
        affected_txns = await db.transactions.find(
            {"trust_id": minutes.get("trust_id"), "user_id": user["user_id"], "linked_minutes_id": None},
            {"_id": 0}
        ).to_list(100)
        for txn in affected_txns:
            # Re-run alert checks (will re-create threshold alert if applicable)
            await check_transaction_alerts(txn)
    
    return {"message": "Minutes deleted"}

def generate_minutes_pdf(minutes: dict, trust: dict, hide_watermark: bool = False) -> bytes:
    """Generate a professional legal-style PDF for minutes record with proper formatting"""
    import re
    
    doc, buffer = create_doc_template(margins={
        'topMargin': 0.75 * inch,
        'bottomMargin': 0.75 * inch,
        'leftMargin': 1 * inch,
        'rightMargin': 1 * inch,
    })
    
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
        textColor=NAVY
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
        textColor=NAVY,
        borderWidth=0,
        borderPadding=0,
        borderColor=NAVY,
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
        textColor=GRAY
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
    
    # ==== RETROACTIVE HEADER (only when is_retroactive is true) ====
    if minutes.get('is_retroactive'):
        retroactive_data = [
            ['RETROACTIVE MINUTES', ''],
            ['Date of Original Event:', minutes.get('meeting_date', 'N/A')],
            ['Reason for Retroactive Documentation:', minutes.get('retroactive_reason', 'Not specified')],
            ['Retroactive Type:', minutes.get('retroactive_type', 'Not specified')],
            ['Trustees Aware at Time:', 'Yes' if minutes.get('retroactive_trustees_aware') else 'No'],
        ]
        retroactive_table = Table(retroactive_data, colWidths=[2.5 * inch, 3.5 * inch])
        retroactive_table.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),  # Merge top row for label
            ('FONTNAME', (0, 0), (1, 0), 'Times-Bold'),
            ('FONTSIZE', (0, 0), (1, 0), 13),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.HexColor('#990000')),
            ('ALIGN', (0, 0), (1, 0), 'CENTER'),
            ('FONTNAME', (0, 1), (0, -1), 'Times-Bold'),
            ('FONTNAME', (1, 1), (1, -1), 'Times-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#333333')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff3e0')),
            ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#990000')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cc9966')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(retroactive_table)
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
        ParagraphStyle('FooterNote', parent=styles['Normal'], fontName='Times-Italic', fontSize=8, alignment=1, textColor=GRAY)
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
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
    
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
    trustees_raw = trust.get("trustees") or trust.get("trustee_names") or ""
    trustees = parse_trustees(trustees_raw) if isinstance(trustees_raw, str) else (trustees_raw if isinstance(trustees_raw, list) else [])
    trustee_names = trustees if trustees else [trust.get("role", "Trustee")]

    # Get data from template_data with defaults
    minute_number = template_data.get("minute_number", f"{datetime.now().year}-001")
    meeting_date = template_data.get("meeting_date", datetime.now().strftime("%B %d, %Y"))
    meeting_time = template_data.get("meeting_time", "10:00 AM")
    meeting_type = template_data.get("meeting_type", "unanimous_written_consent")
    trustees_present = template_data.get("trustees_present", trustee_names)
    trust_formation_date = template_data.get("trust_formation_date") or template_data.get("trust_indenture_date", "[Date of Trust Formation]")
    
    # Format ISO dates (yyyy-MM-dd) to human-readable for the document
    def _fmt_date(d):
        if not d or d == "[Date of Trust Formation]":
            return d
        try:
            from datetime import datetime as _dt
            return _dt.strptime(d[:10], "%Y-%m-%d").strftime("%B %d, %Y")
        except (ValueError, TypeError):
            return d
    
    meeting_date = _fmt_date(meeting_date)
    trust_formation_date = _fmt_date(trust_formation_date)
    
    # Format time from 24h (HH:MM) to 12h with AM/PM
    def _fmt_time(t):
        if not t:
            return t
        try:
            h, m = t.split(":")
            h = int(h)
            suffix = "AM" if h < 12 else "PM"
            h12 = h if h <= 12 else h - 12
            if h12 == 0:
                h12 = 12
            return f"{h12}:{m} {suffix}"
        except (ValueError, TypeError):
            return t
    
    meeting_time = _fmt_time(meeting_time)
    
    meeting_type_text = {
        "in_person": f"In person at {template_data.get('meeting_location', '[Location]')}",
        "video_conference": "By telephone/video conference",
        "unanimous_written_consent": "By unanimous written consent without meeting"
    }.get(meeting_type, "By unanimous written consent without meeting")
    
    # Build the document
    doc = f"""TRUST MINUTES
Private Irrevocable Trust

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

The Trustees, acting in their fiduciary capacity, convened this meeting to conduct the business of the Trust in accordance with the Declaration of Trust dated {trust_formation_date}, and applicable state law.

All Trustees present affirm they are acting in their fiduciary capacity as trustees of the Trust.

═══════════════════════════════════════════════════════════════════════════════

MATTERS CONSIDERED AND RESOLUTIONS ADOPTED

"""
    
    # Enrich template_data with trust context for conveyance templates
    # (bill_of_sale, assignment, general_assignment need trust_name, trustee_name, ein, state_code)
    if template_type in ("bill_of_sale", "assignment_of_personal_property", "general_assignment"):
        template_data.setdefault("trust_name", trust_name)
        template_data.setdefault("trustee_name", ", ".join(trustee_names))
        template_data.setdefault("ein", trust.get("ein", ""))
        template_data.setdefault("state_code", trust.get("jurisdiction", "") or trust.get("state_code", ""))
    
    # Generate template-specific content
    if template_type == "general_meeting":
        doc += generate_general_meeting_content(template_data)
    elif template_type == "initial_trustee_meeting":
        doc += generate_initial_trustee_meeting_content(trust, template_data)
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
    elif template_type == "bill_of_sale":
        doc += generate_bill_of_sale_content(template_data)
    elif template_type == "assignment_of_personal_property":
        doc += generate_assignment_of_personal_property_content(template_data)
    elif template_type == "general_assignment":
        doc += generate_general_assignment_content(template_data)
    
    # Add adjournment and certification
    doc += f"""
═══════════════════════════════════════════════════════════════════════════════

ADJOURNMENT

There being no further business to come before the Board of Trustees, the meeting was adjourned at {_fmt_time(template_data.get('adjournment_time', meeting_time))}.

═══════════════════════════════════════════════════════════════════════════════

CERTIFICATION AND AUTHENTICATION

The undersigned Trustees hereby certify that the foregoing Minutes constitute a true, accurate, and complete record of the meeting and resolutions adopted, and that all decisions recorded herein were made in good faith, in accordance with the Trust Indenture, and for the benefit of the Trust and its Beneficiaries.

These Trust Minutes are executed by the Trustees in their official capacity as fiduciaries of the Trust.

All Trust Minutes and records are confidential and maintained as fiduciary records of the Trust. They are not to be disclosed to any third party except as authorized by the Board of Trustees.

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
{trust_name} – Private Trust Minutes – Confidential
"""
    
    return doc

def generate_initial_trustee_meeting_content(trust: dict, data: dict) -> str:
    """Generate content for the initial organizational trustee meeting.
    
    This is the first meeting of the trust. It covers one-time organizational 
    actions based on standard first-meeting minutes for private trusts.
    """
    trust_name = trust.get("name", "[Trust Name]")
    trustees_raw = trust.get("trustees") or trust.get("trustee_names") or ""
    trustees = parse_trustees(trustees_raw) if isinstance(trustees_raw, str) else (trustees_raw if isinstance(trustees_raw, list) else [])
    trustee_names = trustees if trustees else [trust.get("role", "Trustee")]
    jurisdiction = trust.get("jurisdiction") or trust.get("state_code") or "[State]"
    # Use the trust_formation_date from the form data (which comes from the entity's
    # formation_date, the same source Settings uses) instead of trust.start_date
    # which may be stale or different. Falls back to trust.start_date if form data is empty.
    start_date = data.get("trust_formation_date") or trust.get("start_date", "[Date of Trust Formation]")
    ein = trust.get("ein", "")
    trust_address = ""
    if trust.get("address_line1"):
        trust_address = trust.get("address_line1", "")
        if trust.get("address_line2"):
            trust_address += f"\n{trust['address_line2']}"
        trust_address += f"\n{trust.get('address_city', '[City]')}, {trust.get('address_state', '[State]')} {trust.get('address_zip', '[Zip]')}"
    
    # Data from template form
    meeting_location = data.get("meeting_location", "[City, State]")
    meeting_time = data.get("meeting_time", "")
    principal_place = data.get("principal_place", meeting_location)
    bank_name = data.get("bank_name", "[Bank Name]")
    initial_deposit = data.get("initial_deposit", "")
    fiscal_year_end = data.get("fiscal_year_end", "December 31")
    compensation_type = data.get("compensation_type", "none")
    compensation_amount = data.get("compensation_amount", "")
    accept_trusteeship = data.get("accept_trusteeship", True)
    authorize_ein = data.get("authorize_ein", True)
    accept_initial_property = data.get("accept_initial_property", True)
    authorize_insurance = data.get("authorize_insurance", True)
    designate_record_keeper = data.get("designate_record_keeper", True)
    acknowledge_fiduciary_duties = data.get("acknowledge_fiduciary_duties", True)
    adopt_governance_standards = data.get("adopt_governance_standards", True)
    authorize_professional_services = data.get("authorize_professional_services", True)
    ratify_prior_actions = data.get("ratify_prior_actions", True)
    
    meeting_date = data.get("meeting_date", "[Date]")
    
    # Format ISO dates to human-readable
    def _fmt_date_iso(d):
        if not d or d.startswith("["):
            return d
        try:
            from datetime import datetime as _dt
            return _dt.strptime(d[:10], "%Y-%m-%d").strftime("%B %d, %Y")
        except (ValueError, TypeError):
            return d
    
    start_date = _fmt_date_iso(start_date)
    meeting_date = _fmt_date_iso(meeting_date)
    
    # Format time from 24h to 12h with AM/PM
    def _fmt_time_12h(t):
        if not t:
            return t
        try:
            h, m = t.split(":")
            h = int(h)
            suffix = "AM" if h < 12 else "PM"
            h12 = h if h <= 12 else h - 12
            if h12 == 0:
                h12 = 12
            return f"{h12}:{m} {suffix}"
        except (ValueError, TypeError):
            return t
    
    meeting_time = _fmt_time_12h(meeting_time)
    
    content = f"""FIRST ORGANIZATIONAL MEETING MINUTES
{trust_name}

Trust Formation Date: {start_date}
Date: {meeting_date}"""
    if meeting_time:
        content += f"\nTime: {meeting_time}"
    content += f"\nLocation: {meeting_location}"

    content += f"""

═══════════════════════════════════════════════════════════════════════════════

TRUSTEES PRESENT

"""
    for trustee in trustee_names:
        content += f"{trustee}, Trustee\n"

    content += f"""
═══════════════════════════════════════════════════════════════════════════════

CALL TO ORDER

{trustee_names[0]}, acting as presiding Trustee, called the organizational 
meeting of {trust_name} to order.

The presiding Trustee confirmed that this meeting constitutes the first formal 
meeting of the Board of Trustees following the execution of the Declaration of 
Trust on {start_date}.

═══════════════════════════════════════════════════════════════════════════════

QUORUM

The presiding Trustee confirmed that all appointed Trustees are present, and a 
quorum exists for the transaction of business.

"""

    # RESOLUTION 1: Acceptance of Trusteeship + Adoption of Declaration
    if accept_trusteeship:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 1: ADOPTION OF DECLARATION OF TRUST AND ACCEPTANCE OF TRUSTEESHIP

WHEREAS, the Declaration of Trust for {trust_name} was duly executed on 
{start_date} by {"; ".join(trustee_names)} as Trustee(s);

BE IT RESOLVED, that the Trustees hereby acknowledge receipt of the Declaration 
of Trust, accept their appointment as Trustees, and agree to hold and administer 
the Trust estate in accordance with the terms, conditions, and fiduciary duties 
set forth in said Declaration.

"""
        for trustee in trustee_names:
            content += f"BE IT FURTHER RESOLVED, that {trustee} hereby accepts the appointment as Trustee of the {trust_name} and agrees to serve in such capacity subject to the terms and conditions set forth in the Trust Instrument.\n\n"
        content += "VOTE: Unanimous approval.\n\n"

    # RESOLUTION 2: Fiduciary Duties Acknowledgment
    if acknowledge_fiduciary_duties:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 2: ACKNOWLEDGMENT OF FIDUCIARY DUTIES

WHEREAS, the Trustees understand that they hold the Trust property in a 
fiduciary capacity and not in any personal capacity;

BE IT RESOLVED, that the Trustees acknowledge and accept the following fiduciary 
duties as binding upon them:

  Duty of Loyalty — To act solely in the interest of the Trust and its 
  Beneficiaries, avoiding all conflicts of interest and self-dealing.

  Duty of Prudence — To manage Trust assets with the care, skill, and caution 
  that a reasonable person would exercise, seeking professional guidance when 
  necessary.

  Duty of Impartiality — To balance the interests of all Beneficiaries fairly 
  and in accordance with the Trust instrument.

  Duty of Obedience — To follow the written terms of the Declaration of Trust 
  and act only within the powers granted therein.

  Duty of Recordkeeping — To maintain complete, accurate, and organized records 
  of all Trust meetings, decisions, transactions, and assets.

  Duty of Confidentiality — To preserve the privacy of all Trust records, 
  minutes, and internal deliberations, disclosing information only when required 
  by law or authorized by the Board.

VOTE: Unanimous acknowledgment.

"""

    # RESOLUTION 3: Principal Place of Administration
    content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 3: ESTABLISHMENT OF PRINCIPAL PLACE OF ADMINISTRATION

WHEREAS, the Declaration of Trust designates the principal place of 
administration and elected situs of this Trust;

BE IT RESOLVED, that the Trustees confirm the principal place of administration 
of {trust_name} to be:
{principal_place}"""

    if trust_address:
        content += f"\n{trust_address}"

    content += f"""

All official Trust records, minutes, resolutions, and correspondence shall be 
maintained at this location or in such secure location as the Trustees may 
designate by subsequent resolution.

VOTE: Unanimous approval.

═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 4: AUTHORIZATION TO OPEN BANK ACCOUNTS

WHEREAS, the Trustees determine that it is necessary and prudent to establish 
one or more financial accounts in the name of the Trust for the proper 
administration of Trust assets;

BE IT RESOLVED, that the Trustees are hereby authorized to open and maintain 
bank accounts, brokerage accounts, or other financial accounts in the name of 
{trust_name}, and to execute all documents, agreements, and certifications 
required by financial institutions for such purpose.

BE IT FURTHER RESOLVED, that the Trustee(s) are authorized and directed to 
open one or more bank accounts"""

    if bank_name and bank_name != "[Bank Name]":
        content += f" at {bank_name}"
    else:
        content += " at such financial institution(s) as the Trustee(s) may deem appropriate"

    content += f" in the name of the {trust_name};\n\n"

    if initial_deposit:
        content += f"BE IT FURTHER RESOLVED, that the Trustee(s) shall deposit the initial trust corpus of {initial_deposit} into the trust bank account.\n\n"
    
    content += f"""BE IT FURTHER RESOLVED, that {trustee_names[0]}, as Trustee, is authorized to sign 
on behalf of the Trust, and to present this resolution, the Declaration of 
Trust, a Certification of Trust, and the Trust's EIN documentation to any bank 
or financial institution as proof of authority.

BE IT FURTHER RESOLVED, that any Trustee acting alone is authorized to:
  (a) Execute any and all documents necessary to open and maintain such accounts;
  (b) Make deposits to and withdrawals from such accounts;
  (c) Endorse checks and other negotiable instruments payable to the Trust;
  (d) Apply for and obtain debit cards, checks, and other banking instruments.

VOTE: Unanimous approval.

═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 5: EMPLOYER IDENTIFICATION NUMBER

"""
    
    if ein:
        content += f"""WHEREAS, the Trustees have obtained an Employer Identification Number (EIN) 
from the Internal Revenue Service for the purpose of opening bank accounts and 
conducting Trust business;

BE IT RESOLVED, that the Trustees accept and adopt the following EIN for 
{trust_name}:

  EIN: {ein}

This EIN shall be used for all Trust banking, financial, and reporting purposes 
as deemed necessary by the Trustees.

VOTE: Unanimous approval.

"""
    else:
        content += f"""WHEREAS, the Trust requires an Employer Identification Number (EIN) for 
tax filing and banking purposes;

BE IT RESOLVED, that the Trustee(s) are authorized and directed to apply for 
and obtain an EIN from the Internal Revenue Service for the {trust_name};

FURTHER RESOLVED, that once obtained, the EIN shall be used for all tax filing 
and banking purposes related to the Trust.

VOTE: Unanimous approval.

"""

    # RESOLUTION 6: Acceptance of Initial Trust Property
    if accept_initial_property:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 6: ACCEPTANCE OF INITIAL TRUST PROPERTY

WHEREAS, the Settlor has conveyed or will convey property to the Trustee(s) as 
the initial trust corpus; and

WHEREAS, the Trustee(s) are willing to accept such property in accordance with 
the terms of the Trust Instrument;

BE IT RESOLVED, that the Trustees acknowledge their authority to accept real 
property, personal property, financial assets, business interests, and any other 
lawful property conveyed to the Trust by the Settlor, provided such acceptance 
is consistent with the Trust's stated purpose and in the best interest of the 
Beneficiaries.

BE IT FURTHER RESOLVED, that any property accepted into the Trust shall be 
recorded on Schedule A or in a separate Trust ledger, and acceptance shall be 
memorialized by resolution at the time of conveyance.

VOTE: Unanimous approval.

"""

    # RESOLUTION 7: Fiscal Year
    content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 7: ESTABLISHMENT OF FISCAL YEAR

WHEREAS, the Trustees desire to establish a fiscal year for accounting and 
record-keeping purposes;

BE IT RESOLVED, that the fiscal year of {trust_name} shall """

    if fiscal_year_end == "December 31":
        content += f"be the calendar year, beginning January 1 and ending December 31."
    else:
        content += f"end on {fiscal_year_end}."

    content += f"""

The Trustees may, by subsequent resolution, change the fiscal year if deemed 
prudent for tax or administrative purposes.

VOTE: Unanimous approval.

"""

    # RESOLUTION 8: Trustee Compensation
    content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 8: TRUSTEE COMPENSATION

"""
    
    if compensation_type == "none":
        content += f"""WHEREAS, the Trust Instrument addresses the matter of Trustee compensation;

BE IT RESOLVED, that the initial Trustee(s) shall serve without compensation at 
this time, reserving the right to establish reasonable compensation in the 
future as permitted by the Trust Instrument.

VOTE: Unanimous approval.

"""
    elif compensation_type == "fixed":
        content += f"""WHEREAS, the Trust Instrument permits reasonable compensation for Trustee services;

BE IT RESOLVED, that the initial Trustee(s) shall receive annual compensation 
of {compensation_amount or "[Amount]"} for services rendered to the Trust, 
payable in accordance with the terms of the Trust Instrument.

VOTE: Unanimous approval.

"""
    elif compensation_type == "percentage":
        content += f"""WHEREAS, the Trust Instrument permits reasonable compensation for Trustee services;

BE IT RESOLVED, that the initial Trustee(s) shall receive compensation equal to 
{compensation_amount or "[Percentage]"}% of the trust corpus value, computed 
annually in accordance with the terms of the Trust Instrument.

VOTE: Unanimous approval.

"""

    # RESOLUTION 9: Governance Standards
    if adopt_governance_standards:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 9: ADOPTION OF GOVERNANCE STANDARDS

WHEREAS, the Trustees desire to establish clear governance standards and 
practices for the ongoing administration of the Trust;

BE IT RESOLVED, that the Trustees adopt the following governance practices:

  Regular Meetings — The Trustees shall meet not less than two (2) times per 
  year, and preferably quarterly, to review Trust finances, approve expenditures, 
  accept new assets, and address Trust business.

  Meeting Minutes — All meetings of the Trustees shall be memorialized in 
  written minutes, which shall include the date, location, Trustees present, 
  agenda items, resolutions passed, and votes recorded. Minutes shall be signed 
  by all Trustees present.

  Resolutions — All significant decisions, including the acceptance of property, 
  approval of expenditures, authorization of contracts, and appointment of 
  agents, shall be documented by formal written resolution and filed in the 
  Trust's compliance records.

  Annual Review — The Trustees shall conduct an annual review of Trust 
  operations, compliance with fiduciary duties, financial condition, and any 
  required tax or regulatory filings.

VOTE: Unanimous approval.

"""

    # RESOLUTION 10: Insurance
    if authorize_insurance:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 10: AUTHORIZATION OF INSURANCE

WHEREAS, it is prudent and in the best interest of the Trust to maintain 
appropriate insurance coverage;

BE IT RESOLVED, that the Trustee(s) are authorized to obtain and maintain the 
following insurance on behalf of {trust_name}:
  (a) Trustee liability (errors and omissions) insurance;
  (b) Property insurance for trust real and personal property; and
  (c) Such other insurance as the Trustee(s) may deem appropriate.

VOTE: Unanimous approval.

"""

    # RESOLUTION 11: Professional Services
    if authorize_professional_services:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 11: AUTHORIZATION FOR LEGAL AND PROFESSIONAL SERVICES

WHEREAS, the Trustees may from time to time require the assistance of attorneys, 
accountants, tax advisors, or other professional service providers for the proper 
administration of the Trust;

BE IT RESOLVED, that the Trustees are authorized to retain and compensate 
qualified professionals as deemed necessary for the protection, administration, 
and tax compliance of the Trust, and to execute engagement agreements and pay 
reasonable fees for such services from Trust assets.

All professional fees shall be reviewed and approved by the Trustees and 
recorded in the Trust's financial ledgers.

VOTE: Unanimous approval.

"""

    # RESOLUTION 12: Designation of Record Keeper
    if designate_record_keeper:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 12: DESIGNATION OF RECORD KEEPER

WHEREAS, the Trust Instrument requires that adequate records be kept of all 
trust proceedings;

BE IT RESOLVED, that {trustee_names[0] if trustee_names else "[Trustee Name]"} 
is hereby designated as the Record Keeper of {trust_name}, responsible for 
maintaining all trust records, minutes, and documents at the principal place of 
administration.

FURTHER RESOLVED, that all trust records shall be kept in a secure and accessible 
manner, and shall be available for review by any Trustee or beneficiary as 
required by law.

VOTE: Unanimous approval.

"""

    # RESOLUTION 13: Certification of Trust Authority
    content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 13: EXECUTION OF CERTIFICATIONS AND TRUST DOCUMENTS

WHEREAS, banks, financial institutions, title companies, and government agencies 
may require evidence of the Trust's existence and the Trustees' authority to act 
on behalf of the Trust;

BE IT RESOLVED, that the Trustees are authorized to execute, deliver, and present 
Certifications of Trust, affidavits, and other summary documents evidencing the 
Trust's existence, the identity of the Trustees, and the authority of the 
Trustees to transact business, open accounts, hold title to property, and 
otherwise administer the Trust.

The Trustees may execute such certifications in the name of the Trust without 
disclosing the full text of the Declaration of Trust, in order to preserve the 
privacy of the Trust's internal provisions.

VOTE: Unanimous approval.

"""

    # RESOLUTION 14: Ratification
    if ratify_prior_actions:
        content += f"""═══════════════════════════════════════════════════════════════════════════════

RESOLUTION 14: RATIFICATION OF PRIOR ACTIONS

BE IT RESOLVED, that all actions taken by the Settlor and the Trustees in 
connection with the formation, execution, and initial administration of 
{trust_name} are hereby ratified, confirmed, and approved as valid and binding 
acts of the Trust.

VOTE: Unanimous approval.

"""

    # ADJOURNMENT AND ATTESTATION
    content += f"""═══════════════════════════════════════════════════════════════════════════════

ADJOURNMENT

There being no further business to come before the meeting, the presiding 
Trustee declared the meeting adjourned.

═══════════════════════════════════════════════════════════════════════════════

ATTESTATION

The undersigned Trustees certify that the foregoing minutes constitute a true 
and accurate record of the organizational meeting of {trust_name} held on 
{meeting_date}.

"""

    for trustee in trustee_names:
        content += f"""
________________________________________
{trustee}, Trustee
Date: {meeting_date}"""

    content += "\n"
    return content

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

def generate_bill_of_sale_content(data: dict) -> str:
    """Generate bill of sale content for tangible personal property transfer."""
    grantor = data.get("grantor_name", "[Grantor]")
    trust_name = data.get("trust_name", "[Trust Name]")
    trustee = data.get("trustee_name", "[Trustee]")
    description = data.get("property_description", "[Description]")
    identifier = data.get("property_identifier", "N/A")
    location = data.get("property_location", "N/A")
    value = data.get("property_value")
    conveyance_date = data.get("conveyance_date", "[Date]")
    ein = data.get("ein", "[EIN]")
    state_code = data.get("state_code", "[State]")

    value_text = f"${value:,.2f}" if value else "$1.00 (One Dollar) and other good and valuable consideration"
    ein_text = f" (EIN: {ein})" if ein and ein != "[EIN]" else ""

    content = f"""BILL OF SALE

WHEREAS, {grantor} ("Grantor") is the lawful owner of the following described personal property:

    Description: {description}
    Identifier: {identifier}
    Location: {location}

NOW, THEREFORE, for and in consideration of {value_text}, the receipt and sufficiency of which is hereby acknowledged, Grantor does hereby BARGAIN, SELL, GRANT, ASSIGN, TRANSFER, and CONVEY unto {trust_name}{ein_text} ("Trust"), the following described personal property:

    {description}
    Identifier: {identifier}

TO HAVE AND TO HOLD said property unto the Trust, its successors and assigns, forever.

Grantor warrants that Grantor is the lawful owner of said property, that the same is free from all encumbrances and liens, and that Grantor has full right and authority to convey the same.

This Bill of Sale is executed in conjunction with the trust's acceptance resolution dated {conveyance_date}.

AS-IS: Said property is conveyed "as-is" and "where-is" without any warranty, express or implied, except as expressly stated herein.

GRANTOR:

___________________________________________
{grantor}, Grantor

Date: {conveyance_date}

TRUSTEE ACKNOWLEDGMENT OF RECEIPT:

___________________________________________
{trustee}, Trustee of {trust_name}

Date: {conveyance_date}

NOTARY ACKNOWLEDGMENT:

State of {state_code}
County of _________________

On this _____ day of ____________, 20___, before me personally appeared {grantor}, known to me to be the person whose name is subscribed to the foregoing instrument, and acknowledged that he/she executed the same for the purposes therein contained.

___________________________________________
Notary Public
My Commission Expires: _________________

"""
    return content

def generate_assignment_of_personal_property_content(data: dict) -> str:
    """Generate assignment of personal property content for artwork, jewelry, collectibles."""
    grantor = data.get("grantor_name", "[Grantor]")
    trust_name = data.get("trust_name", "[Trust Name]")
    trustee = data.get("trustee_name", "[Trustee]")
    description = data.get("property_description", "[Description]")
    identifier = data.get("property_identifier", "N/A")
    location = data.get("property_location", "N/A")
    value = data.get("property_value")
    appraiser_name = data.get("appraiser_name", "")
    conveyance_date = data.get("conveyance_date", "[Date]")
    ein = data.get("ein", "[EIN]")
    state_code = data.get("state_code", "[State]")

    value_text = f"${value:,.2f}" if value else "$1.00 (One Dollar) and other good and valuable consideration"
    appraiser_text = f"\n    Appraised by: {appraiser_name}" if appraiser_name else ""
    ein_text = f" (EIN: {ein})" if ein and ein != "[EIN]" else ""

    content = f"""ASSIGNMENT AND CONVEYANCE OF PERSONAL PROPERTY

WHEREAS, {grantor} ("Assignor") is the lawful owner of the following described personal property:

    Description: {description}
    Identifier: {identifier}
    Location: {location}
    Appraised value: {value_text}{appraiser_text}

NOW, THEREFORE, for and in consideration of {value_text}, the receipt and sufficiency of which is hereby acknowledged, Assignor does hereby ASSIGN, TRANSFER, CONVEY, and DELIVER unto {trust_name}{ein_text} ("Trust"), all of Assignor's right, title, and interest in and to the following described personal property:

    {description}
    Identifier: {identifier}

TO HAVE AND TO HOLD said property unto the Trust, its successors and assigns, forever.

Assignor warrants that Assignor is the lawful owner of said property, that the same is free from all encumbrances and liens, and that Assignor has full right and authority to assign and convey the same.

This Assignment is executed in conjunction with the trust's acceptance resolution dated {conveyance_date}.

ASSIGNOR:

___________________________________________
{grantor}, Assignor

Date: {conveyance_date}

TRUSTEE ACKNOWLEDGMENT OF RECEIPT:

___________________________________________
{trustee}, Trustee of {trust_name}

Date: {conveyance_date}

NOTARY ACKNOWLEDGMENT:

State of {state_code}
County of _________________

On this _____ day of ____________, 20___, before me personally appeared {grantor}, known to me to be the person whose name is subscribed to the foregoing instrument, and acknowledged that he/she executed the same for the purposes therein contained.

___________________________________________
Notary Public
My Commission Expires: _________________

"""
    return content

def generate_general_assignment_content(data: dict) -> str:
    """Generate general assignment content for intangible assets."""
    grantor = data.get("grantor_name", "[Grantor]")
    trust_name = data.get("trust_name", "[Trust Name]")
    trustee = data.get("trustee_name", "[Trustee]")
    description = data.get("property_description", "[Description]")
    identifier = data.get("property_identifier", "N/A")
    value = data.get("property_value")
    conveyance_date = data.get("conveyance_date", "[Date]")
    ein = data.get("ein", "[EIN]")
    state_code = data.get("state_code", "[State]")

    value_text = f"${value:,.2f}" if value else "$1.00 (One Dollar) and other good and valuable consideration"
    ein_text = f" (EIN: {ein})" if ein and ein != "[EIN]" else ""

    content = f"""GENERAL ASSIGNMENT OF ASSETS

WHEREAS, {grantor} ("Assignor") is the lawful owner of the following described assets:

    Description: {description}
    Identifier: {identifier}

NOW, THEREFORE, for and in consideration of {value_text}, the receipt and sufficiency of which is hereby acknowledged, Assignor does hereby ASSIGN, TRANSFER, and CONVEY unto {trust_name}{ein_text} ("Trust"), all of Assignor's right, title, and interest in and to the following described assets:

    {description}
    Identifier: {identifier}

TO HAVE AND TO HOLD said assets unto the Trust, its successors and assigns, forever.

Assignor warrants that Assignor is the lawful owner of said assets, that the same is free from all encumbrances and liens, and that Assignor has full right and authority to assign and convey the same.

This General Assignment is executed in conjunction with the trust's acceptance resolution dated {conveyance_date}.

ASSIGNOR:

___________________________________________
{grantor}, Assignor

Date: {conveyance_date}

TRUSTEE ACKNOWLEDGMENT OF RECEIPT:

___________________________________________
{trustee}, Trustee of {trust_name}

Date: {conveyance_date}

NOTARY ACKNOWLEDGMENT:

State of {state_code}
County of _________________

On this _____ day of ____________, 20___, before me personally appeared {grantor}, known to me to be the person whose name is subscribed to the foregoing instrument, and acknowledged that he/she executed the same for the purposes therein contained.

___________________________________________
Notary Public
My Commission Expires: _________________

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

WHEREAS, {new_trustee}, acting in a fiduciary capacity, has been identified as a suitable and qualified person to serve as Trustee of this Trust, and has expressed willingness to accept such appointment;

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

I, {new_trustee}, acting in my fiduciary capacity, hereby accept the appointment as {'Successor' if appointment_type == 'successor' else 'Additional'} Trustee of this Trust.

I affirm and declare:

1. I have read the Declaration and Indenture of Private Irrevocable Trust and understand my duties, obligations, and responsibilities as Trustee.

2. I agree to faithfully and diligently perform all duties as Trustee in accordance with the Trust Indenture and applicable law.

3. I will act at all times in the best interest of the Trust and its Beneficiaries, with loyalty, prudence, and good faith.

4. I understand that I am accepting this appointment in my fiduciary capacity as Trustee of the Trust.

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

• Henceforth, the Trust shall be administered under the laws of {new_situs}, to the extent such laws do not conflict with the express terms of the Trust Indenture.

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
    • The Trust's status as a private trust operating in accordance with applicable law

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

WHEREAS, this Trust operates with charitable purposes, consistent with the principles set forth in the Trust Indenture;

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
        raise HTTPException(status_code=404, detail="Trust not found. Please refresh the page or check your trust selection.")
    
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
    
    # Update onboarding checklist — minutes were generated
    try:
        await auto_update_onboarding(user["user_id"], template.trust_id)
    except Exception:
        pass
    
    # If accepting property or conveying property and add_to_schedule_a is true, add to Schedule A
    CONVEYANCE_TEMPLATES = {"acceptance_of_property", "bill_of_sale", "assignment_of_personal_property", "general_assignment"}
    if template.template_type.value in CONVEYANCE_TEMPLATES and template.template_data.get("add_to_schedule_a"):
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
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
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
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
    
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
    
    # Update onboarding checklist if minutes are finalized
    if update_data.status == "final":
        try:
            await auto_update_onboarding(user["user_id"], minutes["trust_id"])
        except Exception:
            pass
    
    updated = await db.minutes_templates.find_one({"minutes_id": minutes_id}, {"_id": 0})
    return updated

@router.delete("/minutes-templates/{minutes_id}")
async def delete_minutes_template(minutes_id: str, user: dict = Depends(require_write_access)):
    """Delete a template-based minutes"""
    result = await db.minutes_templates.delete_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been already deleted. Please refresh the page and try again.")
    return {"message": "Minutes deleted"}

@router.get("/minutes-templates/{minutes_id}/pdf")
async def get_minutes_template_pdf(minutes_id: str, user: dict = Depends(get_current_user)):
    """Generate PDF for template-based minutes"""
    minutes = await db.minutes_templates.find_one(
        {"minutes_id": minutes_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found. It may have been deleted. Please refresh the page and try again.")
    
    # Generate PDF from the document text
    pdf_doc, buffer = create_doc_template(margins={
        'topMargin': 0.75 * inch,
        'bottomMargin': 0.75 * inch,
        'leftMargin': 1 * inch,
        'rightMargin': 1 * inch,
    })
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TrustTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=6,
        textColor=NAVY,
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
    """Get available minutes template options with descriptions and fields"""
    # Determine benevolence status
    benevolence_enabled = False
    if trust_id:
        trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]}, {"_id": 0, "benevolence_enabled": 1})
        if trust and trust.get("benevolence_enabled"):
            benevolence_enabled = True
    
    return get_template_registry(trust_id=trust_id, benevolence_enabled=benevolence_enabled)
