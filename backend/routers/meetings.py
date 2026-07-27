# Meetings router — Phase 1 Core Governance (agendas, minutes, approval workflow)
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from dependencies import get_current_user, require_write_access
from models import (
    MeetingAgendaCreate, MeetingAgendaUpdate, MeetingAgendaResponse,
    MeetingCreate, MeetingResponse,
    MinutesApprovalStatusResponse, ApprovalWorkflowSummary,
    ApprovalStatus,
)
from services import meeting_service

router = APIRouter(tags=["meetings"])


# ==================== REQUEST BODIES ====================

class MinutesCreateBody(BaseModel):
    """Create minutes record (workflow-backed)."""
    meeting_id: Optional[str] = None
    agenda_id: Optional[str] = None
    minutes_type: Optional[str] = None
    meeting_date: Optional[str] = None
    participants_text: Optional[str] = ""
    decisions_text: Optional[str] = ""
    sections: Optional[List[dict]] = []
    template_data: Optional[dict] = {}
    notes: Optional[str] = None
    approval_due_date: Optional[str] = None


class MinutesUpdateBody(BaseModel):
    meeting_id: Optional[str] = None
    agenda_id: Optional[str] = None
    minutes_type: Optional[str] = None
    meeting_date: Optional[str] = None
    participants_text: Optional[str] = None
    decisions_text: Optional[str] = None
    sections: Optional[List[dict]] = None
    template_data: Optional[dict] = None
    notes: Optional[str] = None


class WorkflowActionBody(BaseModel):
    note: Optional[str] = None


# ==================== HELPERS ====================

async def _require_owned_trust(trust_id: str, user: dict) -> dict:
    trust = await meeting_service.get_owned_trust(trust_id, user["user_id"])
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return trust


# ==================== AGENDAS ====================

@router.post("/meetings/{trust_id}/agendas", response_model=MeetingAgendaResponse)
async def generate_agenda(
    trust_id: str,
    payload: MeetingAgendaCreate,
    user: dict = Depends(require_write_access),
):
    """Generate a meeting agenda. If agenda_items is empty, smart defaults are
    built from meeting type, open deadlines, and incomplete prior agenda items."""
    await _require_owned_trust(trust_id, user)
    if payload.trust_id != trust_id:
        raise HTTPException(status_code=400, detail="trust_id in path and body must match.")
    agenda = await meeting_service.generate_agenda(trust_id, payload, user)
    return MeetingAgendaResponse(**agenda)


@router.get("/meetings/agendas/{agenda_id}", response_model=MeetingAgendaResponse)
async def get_agenda(agenda_id: str, user: dict = Depends(get_current_user)):
    agenda = await meeting_service.get_agenda(agenda_id, user["user_id"])
    if not agenda:
        raise HTTPException(status_code=404, detail="Agenda not found.")
    return MeetingAgendaResponse(**agenda)


@router.patch("/meetings/agendas/{agenda_id}", response_model=MeetingAgendaResponse)
async def update_agenda(
    agenda_id: str,
    payload: MeetingAgendaUpdate,
    user: dict = Depends(require_write_access),
):
    try:
        agenda = await meeting_service.update_agenda(agenda_id, payload, user["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not agenda:
        raise HTTPException(status_code=404, detail="Agenda not found.")
    return MeetingAgendaResponse(**agenda)


# ==================== MEETINGS (agenda ↔ minutes link) ====================

@router.post("/meetings/{trust_id}/records", response_model=MeetingResponse)
async def create_meeting_record(
    trust_id: str,
    payload: MeetingCreate,
    user: dict = Depends(require_write_access),
):
    """Record that a meeting actually took place (links an agenda to minutes)."""
    await _require_owned_trust(trust_id, user)
    if payload.trust_id != trust_id:
        raise HTTPException(status_code=400, detail="trust_id in path and body must match.")
    agenda = await meeting_service.get_agenda(payload.agenda_id, user["user_id"])
    if not agenda:
        raise HTTPException(status_code=404, detail="Agenda not found.")
    meeting = await meeting_service.create_meeting(trust_id, payload, user)
    return MeetingResponse(**meeting)


# ==================== MINUTES ====================

@router.post("/meetings/{trust_id}/minutes", status_code=201)
async def create_minutes(
    trust_id: str,
    payload: MinutesCreateBody,
    user: dict = Depends(require_write_access),
):
    """Create a minutes record and open its approval workflow (status: draft)."""
    await _require_owned_trust(trust_id, user)
    minutes = await meeting_service.create_minutes_record(
        trust_id, payload.model_dump(exclude_unset=True), user
    )
    return minutes


@router.get("/meetings/minutes/{minutes_id}")
async def get_minutes(minutes_id: str, user: dict = Depends(get_current_user)):
    minutes = await meeting_service.get_minutes_record(minutes_id, user["user_id"])
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found.")
    return minutes


@router.patch("/meetings/minutes/{minutes_id}")
async def update_minutes(
    minutes_id: str,
    payload: MinutesUpdateBody,
    user: dict = Depends(require_write_access),
):
    try:
        minutes = await meeting_service.update_minutes_record(
            minutes_id, payload.model_dump(exclude_unset=True), user["user_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not minutes:
        raise HTTPException(status_code=404, detail="Minutes not found.")
    return minutes


# ==================== APPROVAL WORKFLOW ====================

@router.post(
    "/meetings/minutes/{minutes_id}/approve",
    response_model=MinutesApprovalStatusResponse,
)
async def approve_minutes(
    minutes_id: str,
    payload: WorkflowActionBody,
    user: dict = Depends(require_write_access),
):
    """Approve minutes. Valid from under_review; advances the workflow toward finalized."""
    updated, err = await meeting_service.transition_minutes(
        minutes_id, ApprovalStatus.approved, user, note=payload.note
    )
    if err or updated is None:
        raise HTTPException(status_code=409 if err and "Invalid transition" in err else 404, detail=err or "Transition failed.")
    return MinutesApprovalStatusResponse(**updated)


@router.post(
    "/meetings/minutes/{minutes_id}/request-changes",
    response_model=MinutesApprovalStatusResponse,
)
async def request_changes(
    minutes_id: str,
    payload: WorkflowActionBody,
    user: dict = Depends(require_write_access),
):
    """Request changes on minutes under review."""
    updated, err = await meeting_service.transition_minutes(
        minutes_id, ApprovalStatus.changes_requested, user, note=payload.note
    )
    if err or updated is None:
        raise HTTPException(status_code=409 if err and "Invalid transition" in err else 404, detail=err or "Transition failed.")
    return MinutesApprovalStatusResponse(**updated)


@router.post(
    "/meetings/minutes/{minutes_id}/submit",
    response_model=MinutesApprovalStatusResponse,
)
async def submit_for_review(
    minutes_id: str,
    payload: WorkflowActionBody,
    user: dict = Depends(require_write_access),
):
    """Submit draft minutes for review (draft → pending_review)."""
    updated, err = await meeting_service.transition_minutes(
        minutes_id, ApprovalStatus.pending_review, user, note=payload.note
    )
    if err or updated is None:
        raise HTTPException(status_code=409 if err and "Invalid transition" in err else 404, detail=err or "Transition failed.")
    return MinutesApprovalStatusResponse(**updated)


@router.post(
    "/meetings/minutes/{minutes_id}/start-review",
    response_model=MinutesApprovalStatusResponse,
)
async def start_review(
    minutes_id: str,
    payload: WorkflowActionBody,
    user: dict = Depends(require_write_access),
):
    """Start reviewing pending minutes (pending_review → under_review)."""
    updated, err = await meeting_service.transition_minutes(
        minutes_id, ApprovalStatus.under_review, user, note=payload.note
    )
    if err or updated is None:
        raise HTTPException(status_code=409 if err and "Invalid transition" in err else 404, detail=err or "Transition failed.")
    return MinutesApprovalStatusResponse(**updated)


@router.post(
    "/meetings/minutes/{minutes_id}/finalize",
    response_model=MinutesApprovalStatusResponse,
)
async def finalize_minutes(
    minutes_id: str,
    payload: WorkflowActionBody,
    user: dict = Depends(require_write_access),
):
    """Finalize approved minutes (approved → finalized, terminal)."""
    updated, err = await meeting_service.transition_minutes(
        minutes_id, ApprovalStatus.finalized, user, note=payload.note
    )
    if err or updated is None:
        raise HTTPException(status_code=409 if err and "Invalid transition" in err else 404, detail=err or "Transition failed.")
    return MinutesApprovalStatusResponse(**updated)


@router.post(
    "/meetings/minutes/{minutes_id}/reject",
    response_model=MinutesApprovalStatusResponse,
)
async def reject_minutes(
    minutes_id: str,
    payload: WorkflowActionBody,
    user: dict = Depends(require_write_access),
):
    """Reject minutes (terminal)."""
    updated, err = await meeting_service.transition_minutes(
        minutes_id, ApprovalStatus.rejected, user, note=payload.note
    )
    if err or updated is None:
        raise HTTPException(status_code=409 if err and "Invalid transition" in err else 404, detail=err or "Transition failed.")
    return MinutesApprovalStatusResponse(**updated)


@router.get(
    "/meetings/minutes/{minutes_id}/approval",
    response_model=MinutesApprovalStatusResponse,
)
async def get_approval_status(minutes_id: str, user: dict = Depends(get_current_user)):
    approval = await meeting_service.get_approval_status(minutes_id, user["user_id"])
    if not approval:
        raise HTTPException(status_code=404, detail="Approval record not found.")
    return MinutesApprovalStatusResponse(**approval)


# ==================== TRUST-LEVEL STATUS & HISTORY ====================

@router.get(
    "/meetings/{trust_id}/workflow-status",
    response_model=ApprovalWorkflowSummary,
)
async def get_workflow_status(trust_id: str, user: dict = Depends(get_current_user)):
    """Full approval workflow status for a trust: pending, overdue, recently completed."""
    await _require_owned_trust(trust_id, user)
    summary = await meeting_service.get_workflow_summary(trust_id, user["user_id"])
    return ApprovalWorkflowSummary(**summary)


@router.get("/meetings/{trust_id}/history")
async def get_meeting_history(trust_id: str, user: dict = Depends(get_current_user)):
    """List past agendas, meetings, and minutes for a trust."""
    await _require_owned_trust(trust_id, user)
    return await meeting_service.get_meeting_history(trust_id, user["user_id"])
