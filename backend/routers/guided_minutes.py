# Guided Minutes router - AI-assisted wizard for creating minutes
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from datetime import datetime, timezone
from typing import Optional, List
import re
import uuid
import logging

from database import db
from dependencies import get_current_user, require_write_access, auto_update_onboarding
from models import (
    GuidedMinutesContext,
    GuidedMinutesDraftRequest,
    GuidedMinutesDraftResponse,
    GuidedMinutesSaveRequest,
    GuidedMinutesSaveWithRecordsRequest,
    GuidedMinutesSaveWithRecordsResponse,
    MinutesResponse,
    MinutesType,
    MinutesSearchResult,
    AttachMinutesRequest
)
from ai_service import MinutesDraftRequest, draft_minutes_from_structured_input
from email_service import email_service

router = APIRouter(prefix="/guided-minutes", tags=["guided-minutes"])
logger = logging.getLogger(__name__)


@router.get("/context", response_model=GuidedMinutesContext)
async def get_guided_minutes_context(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Get context for the guided minutes wizard.
    
    Returns trust information including name, jurisdiction, trustees list,
    and beneficiary standard to prefill the wizard and provide AI context.
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
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Get trustees from trust document or from entities
    trustees = trust.get("trustees", [])
    
    # If no trustees in trust doc, try to get from entities
    if not trustees:
        # Look for the main trust entity
        entity = await db.entities.find_one(
            {"trust_id": trust["trust_id"], "entity_type": "Trust", "user_id": user_id},
            {"_id": 0}
        )
        if entity and entity.get("trustee_names"):
            # Parse comma-separated trustee names
            trustees = [t.strip() for t in entity.get("trustee_names", "").split(",") if t.strip()]
        
        # Also check beneficiary standard from entity
        beneficiary_standard = entity.get("beneficiary_standard") if entity else None
        article_ref_distribution = entity.get("article_ref_distribution") if entity else None
        article_ref_compensation = entity.get("article_ref_compensation") if entity else None
    else:
        beneficiary_standard = None
        article_ref_distribution = None
        article_ref_compensation = None
    
    return GuidedMinutesContext(
        trust_id=trust["trust_id"],
        trust_name=trust.get("name", ""),
        jurisdiction=trust.get("jurisdiction"),
        trustees=trustees,
        beneficiary_standard=beneficiary_standard,
        article_ref_distribution=article_ref_distribution,
        article_ref_compensation=article_ref_compensation,
        tax_status=trust.get("tax_status")
    )


@router.post("/draft", response_model=GuidedMinutesDraftResponse)
async def create_guided_minutes_draft(
    request: GuidedMinutesDraftRequest,
    user: dict = Depends(require_write_access)
):
    """
    Generate an AI draft from guided minutes wizard input.
    
    Uses the existing AI minutes drafting service (Claude Sonnet) to create
    a professional WHEREAS/RESOLVED style document from the wizard's
    structured input (agenda items + key decisions).
    """
    user_id = user["user_id"]
    
    # Get trust context for AI
    trust = await db.trusts.find_one(
        {"trust_id": request.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Try to get entity-level details
    entity = await db.entities.find_one(
        {"trust_id": request.trust_id, "entity_type": "Trust", "user_id": user_id},
        {"_id": 0}
    )
    
    beneficiary_standard = entity.get("beneficiary_standard") if entity else None
    
    # Build the decisions outline from agenda + key decisions
    decisions_outline = []
    
    if request.agenda_items:
        decisions_outline.append("AGENDA ITEMS DISCUSSED:")
        decisions_outline.extend([f"  - {item}" for item in request.agenda_items])
    
    if request.key_decisions:
        decisions_outline.append("KEY DECISIONS MADE:")
        decisions_outline.extend([f"  - {decision}" for decision in request.key_decisions])
    
    # Build additional context with wizard-specific instructions
    additional_context_parts = []
    
    if request.additional_context:
        additional_context_parts.append(f"Additional notes: {request.additional_context}")
    
    # Include other attendees in the context if present
    if request.other_attendees:
        additional_context_parts.append(
            f"Other attendees present (not trustees): {', '.join(request.other_attendees)}"
        )
    
    additional_context_parts.append(
        "WIZARD INPUT: This is from a guided wizard where the user provided brief bullet points. "
        "Please expand these into proper formal minutes language with WHEREAS clauses for context "
        "and RESOLVED clauses for each decision. Make the document complete and professional."
    )
    
    # Map guided minutes type to existing MinutesType
    minutes_type_map = {
        "annual": "annual",
        "quarterly": "quarterly", 
        "general": "quarterly"  # Use quarterly format for general meetings
    }
    
    # Call the existing AI drafting service
    ai_request = MinutesDraftRequest(
        minutes_type=minutes_type_map.get(request.minutes_type, "quarterly"),
        meeting_date=request.meeting_date,
        participants=request.participants,
        decisions_outline=decisions_outline if decisions_outline else ["No specific decisions recorded"],
        trust_name=trust.get("name", ""),
        jurisdiction=trust.get("jurisdiction"),
        beneficiary_standard=beneficiary_standard,
        additional_context="\n".join(additional_context_parts)
    )
    
    try:
        ai_response = await draft_minutes_from_structured_input(ai_request)
        
        # Format participants for display/storage
        participants_text = ", ".join(request.participants) if request.participants else ""
        
        return GuidedMinutesDraftResponse(
            suggested_title=ai_response.suggested_title,
            draft_body=ai_response.draft_body,
            cautions=ai_response.cautions + [
                "AI-generated content. Review all dates, amounts, and decisions before finalizing.",
                "You are responsible for accuracy and legal sufficiency of these minutes."
            ],
            minutes_type=request.minutes_type,
            meeting_date=request.meeting_date,
            participants_text=participants_text
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating guided minutes draft: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate minutes draft. Please try again."
        )


@router.post("/save", response_model=MinutesResponse)
async def save_guided_minutes(
    request: GuidedMinutesSaveRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_write_access)
):
    """
    Save the guided minutes as a normal minutes_records entry.
    
    Takes the final edited draft and creates a standard minutes record
    that integrates with the existing Minutes page and PDF generation.
    """
    user_id = user["user_id"]
    
    # Verify trust exists
    trust = await db.trusts.find_one(
        {"trust_id": request.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Map guided minutes type to MinutesType enum
    minutes_type_map = {
        "annual": "annual",
        "quarterly": "quarterly",
        "general": "quarterly"  # Store as quarterly in DB
    }
    
    minutes_type = minutes_type_map.get(request.minutes_type, "quarterly")
    
    # Create the minutes record
    minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": request.trust_id,
        "user_id": user_id,
        "minutes_type": minutes_type,
        "meeting_date": request.meeting_date,
        "participants_text": request.participants_text,
        "other_attendees_text": request.other_attendees_text or "",
        "decisions_text": request.decisions_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "guided_wizard"  # Track that this came from guided flow
    }
    
    await db.minutes_records.insert_one(minutes_doc)
    
    # Update onboarding progress
    await auto_update_onboarding(user_id, request.trust_id)
    
    # Send notification email
    background_tasks.add_task(
        email_service.send_minutes_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", ""),
        minutes_type=minutes_type,
        meeting_date=request.meeting_date,
        participants=request.participants_text,
        decisions=request.decisions_text[:500] + "..." if len(request.decisions_text) > 500 else request.decisions_text
    )
    
    logger.info(f"Guided minutes saved: {minutes_id} for user {user_id}")
    
    return MinutesResponse(**{k: v for k, v in minutes_doc.items() if k != "source"})



# ==================== MINUTES SEARCH & ATTACH ENDPOINTS ====================

@router.get("/search", response_model=List[MinutesSearchResult])
async def search_minutes(
    trust_id: str,
    query: Optional[str] = None,
    minutes_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 20,
    user: dict = Depends(get_current_user)
):
    """
    Search minutes records for attachment to money records.
    
    Supports filtering by type, date range, and text search.
    Returns minimal fields needed for the attachment dialog.
    """
    user_id = user["user_id"]
    
    search_query = {"trust_id": trust_id, "user_id": user_id}
    
    if minutes_type:
        search_query["minutes_type"] = minutes_type
    
    if start_date:
        if "meeting_date" not in search_query:
            search_query["meeting_date"] = {}
        search_query["meeting_date"]["$gte"] = start_date
    
    if end_date:
        if "meeting_date" not in search_query:
            search_query["meeting_date"] = {}
        search_query["meeting_date"]["$lte"] = end_date
    
    if query:
        escaped_query = re.escape(query)
        search_query["$or"] = [
            {"decisions_text": {"$regex": escaped_query, "$options": "i"}},
            {"participants_text": {"$regex": escaped_query, "$options": "i"}}
        ]
    
    minutes_docs = await db.minutes_records.find(
        search_query,
        {"_id": 0}
    ).sort("meeting_date", -1).limit(limit).to_list(limit)
    
    results = []
    for doc in minutes_docs:
        decisions = doc.get("decisions_text", "")
        preview = decisions[:100] + "..." if len(decisions) > 100 else decisions
        
        results.append(MinutesSearchResult(
            minutes_id=doc.get("minutes_id"),
            minutes_type=doc.get("minutes_type"),
            meeting_date=doc.get("meeting_date"),
            participants_text=doc.get("participants_text"),
            preview=preview,
            created_at=doc.get("created_at", "")
        ))
    
    return results


@router.post("/save-with-records", response_model=GuidedMinutesSaveWithRecordsResponse)
async def save_guided_minutes_with_records(
    request: GuidedMinutesSaveWithRecordsRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_write_access)
):
    """
    Save guided minutes and create linked money records in one transaction.
    
    This is the "Minutes → Money" flow where the trustee approves actions
    in minutes first, then creates the corresponding payment/distribution records.
    All created records will have their minutes_record_id set to the new minutes.
    """
    user_id = user["user_id"]
    
    # Verify trust exists
    trust = await db.trusts.find_one(
        {"trust_id": request.trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")
    
    # Map guided minutes type
    minutes_type_map = {
        "annual": "annual",
        "quarterly": "quarterly",
        "general": "quarterly"
    }
    minutes_type = minutes_type_map.get(request.minutes_type, "quarterly")
    
    # Create the minutes record first
    minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    minutes_doc = {
        "minutes_id": minutes_id,
        "trust_id": request.trust_id,
        "user_id": user_id,
        "minutes_type": minutes_type,
        "meeting_date": request.meeting_date,
        "participants_text": request.participants_text,
        "other_attendees_text": request.other_attendees_text or "",
        "decisions_text": request.decisions_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "guided_wizard"
    }
    
    await db.minutes_records.insert_one(minutes_doc)
    logger.info(f"Guided minutes saved: {minutes_id} for user {user_id}")
    
    # Create linked money records
    created_counts = {"compensation": 0, "distribution": 0, "benevolence": 0}
    
    for record in request.records_to_create:
        try:
            if record.record_type == "compensation":
                payment_id = f"payment_{uuid.uuid4().hex[:12]}"
                payment_doc = {
                    "payment_id": payment_id,
                    "trust_id": request.trust_id,
                    "user_id": user_id,
                    "amount": record.amount,
                    "date": record.date,
                    "classification_text": record.description or f"Compensation for {record.recipient}",
                    "exceeds_plan_flag": False,
                    "plan_id": None,
                    "minutes_record_id": minutes_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": "guided_minutes"
                }
                await db.compensation_payments.insert_one(payment_doc)
                created_counts["compensation"] += 1
                logger.info(f"Created compensation payment {payment_id} linked to {minutes_id}")
                
            elif record.record_type == "distribution":
                dist_id = f"dist_{uuid.uuid4().hex[:12]}"
                dist_doc = {
                    "distribution_id": dist_id,
                    "trust_id": request.trust_id,
                    "user_id": user_id,
                    "beneficiary_name": record.recipient,
                    "amount": record.amount,
                    "date": record.date,
                    "purpose_classification": record.purpose_classification or "hems_support",
                    "authority_clause_ref": "",
                    "notes": record.description or "",
                    "solvency_confirmed": False,
                    "recusal_acknowledged": False,
                    "approved_by": None,
                    "approved_at": None,
                    "minutes_record_id": minutes_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "is_benevolence": False,
                    "source": "guided_minutes"
                }
                await db.distribution_records.insert_one(dist_doc)
                created_counts["distribution"] += 1
                logger.info(f"Created distribution {dist_id} linked to {minutes_id}")
                
            elif record.record_type == "benevolence":
                # Check if benevolence is enabled
                if not trust.get("benevolence_enabled"):
                    logger.warning(f"Benevolence not enabled for trust {request.trust_id}, skipping record")
                    continue
                    
                ben_id = f"ben_{uuid.uuid4().hex[:12]}"
                ben_doc = {
                    "record_id": ben_id,
                    "trust_id": request.trust_id,
                    "user_id": user_id,
                    "beneficiary_name": record.recipient,
                    "beneficiary_type": "individual",
                    "purpose": "assistance",
                    "purpose_description": record.benevolence_need or record.description or "",
                    "amount": record.amount,
                    "date": record.date,
                    "approved_by": [],
                    "approval_method": "minutes",
                    "minutes_id": minutes_id,
                    "notes": record.description or "",
                    "status": "approved",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": "guided_minutes"
                }
                await db.benevolence_records.insert_one(ben_doc)
                created_counts["benevolence"] += 1
                logger.info(f"Created benevolence record {ben_id} linked to {minutes_id}")
                
        except Exception as e:
            logger.error(f"Error creating {record.record_type} record: {e}")
            # Continue with other records even if one fails
    
    # Update onboarding progress
    await auto_update_onboarding(user_id, request.trust_id)
    
    # Send notification email
    background_tasks.add_task(
        email_service.send_minutes_notification,
        to_email=user["email"],
        user_name=user.get("name", ""),
        trust_name=trust.get("name", ""),
        minutes_type=minutes_type,
        meeting_date=request.meeting_date,
        participants=request.participants_text,
        decisions=request.decisions_text[:500] + "..." if len(request.decisions_text) > 500 else request.decisions_text
    )
    
    return GuidedMinutesSaveWithRecordsResponse(
        minutes_id=minutes_id,
        minutes_type=minutes_type,
        meeting_date=request.meeting_date,
        created_records=created_counts
    )
