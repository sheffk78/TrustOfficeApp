# Deadlines router — Phase 3 Health Score & Deadline Tracking (deadline CRUD + monitoring)
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from dependencies import get_current_user, require_write_access
from models import (
    DeadlineCreate, DeadlineUpdate, DeadlineResponse, DeadlineSummary,
)
from services import deadline_service

router = APIRouter(tags=["deadlines"])


# ==================== REQUEST BODIES ====================

class WaiveDeadlineBody(BaseModel):
    note: str


class SnoozeDeadlineBody(BaseModel):
    days: int


# ==================== HELPERS ====================

async def _require_owned_trust(trust_id: str, user: dict) -> dict:
    trust = await deadline_service.get_owned_trust(trust_id, user["user_id"])
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return trust


# ==================== CROSS-TRUST MONITORING ====================
# NOTE: static paths must be declared before /deadlines/{trust_id} so FastAPI
# doesn't swallow them as path parameters.

@router.get("/deadlines/upcoming", response_model=List[DeadlineResponse])
async def get_upcoming_deadlines(
    days: int = 30,
    user: dict = Depends(get_current_user),
):
    """Upcoming deadlines across ALL trusts (next N days)."""
    days = max(1, min(days, 365))
    deadlines = await deadline_service.get_upcoming_deadlines(user["user_id"], days=days)
    return [DeadlineResponse(**d) for d in deadlines]


@router.get("/deadlines/overdue", response_model=List[DeadlineResponse])
async def get_overdue_deadlines(user: dict = Depends(get_current_user)):
    """Overdue deadlines across ALL trusts."""
    deadlines = await deadline_service.get_overdue_deadlines(user["user_id"])
    return [DeadlineResponse(**d) for d in deadlines]


# ==================== CRUD ====================

@router.post("/deadlines", response_model=DeadlineResponse, status_code=201)
async def create_deadline(
    payload: DeadlineCreate,
    user: dict = Depends(require_write_access),
):
    """Create a compliance deadline for a trust."""
    deadline = await deadline_service.create_deadline(payload, user["user_id"])
    if not deadline:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return DeadlineResponse(**deadline)


@router.get("/deadlines/{trust_id}", response_model=List[DeadlineResponse])
async def get_trust_deadlines(trust_id: str, user: dict = Depends(get_current_user)):
    """All deadlines for a trust, with computed days_remaining / is_overdue."""
    await _require_owned_trust(trust_id, user)
    deadlines = await deadline_service.get_trust_deadlines(trust_id, user["user_id"])
    return [DeadlineResponse(**d) for d in deadlines]


@router.get("/deadlines/{trust_id}/summary", response_model=DeadlineSummary)
async def get_deadline_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """Aggregated deadline summary for a trust."""
    await _require_owned_trust(trust_id, user)
    summary = await deadline_service.get_deadline_summary(trust_id, user["user_id"])
    if not summary:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return DeadlineSummary(**summary)


@router.put("/deadlines/{deadline_id}", response_model=DeadlineResponse)
async def update_deadline(
    deadline_id: str,
    payload: DeadlineUpdate,
    user: dict = Depends(require_write_access),
):
    """Update a deadline."""
    deadline = await deadline_service.update_deadline(deadline_id, user["user_id"], payload)
    if not deadline:
        raise HTTPException(status_code=404, detail="Deadline not found.")
    return DeadlineResponse(**deadline)


@router.delete("/deadlines/{deadline_id}", status_code=204)
async def delete_deadline(deadline_id: str, user: dict = Depends(require_write_access)):
    """Delete a deadline."""
    deleted = await deadline_service.delete_deadline(deadline_id, user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Deadline not found.")
    return None


# ==================== AUTO-GENERATION ====================

@router.post("/deadlines/{trust_id}/auto-generate", response_model=List[DeadlineResponse], status_code=201)
async def auto_generate_deadlines(
    trust_id: str,
    user: dict = Depends(require_write_access),
):
    """Auto-generate standard compliance deadlines (tax filings, quarterly
    reviews, annual review, etc.) for the current tax year. Skips titles that
    already exist for the trust."""
    await _require_owned_trust(trust_id, user)
    created = await deadline_service.auto_generate_deadlines(trust_id, user["user_id"])
    return [DeadlineResponse(**d) for d in created]


# ==================== STATE TRANSITIONS ====================

@router.post("/deadlines/{deadline_id}/complete", response_model=DeadlineResponse)
async def complete_deadline(deadline_id: str, user: dict = Depends(require_write_access)):
    """Mark a deadline completed."""
    deadline = await deadline_service.complete_deadline(deadline_id, user["user_id"])
    if not deadline:
        raise HTTPException(status_code=404, detail="Deadline not found.")
    return DeadlineResponse(**deadline)


@router.post("/deadlines/{deadline_id}/waive", response_model=DeadlineResponse)
async def waive_deadline(
    deadline_id: str,
    payload: WaiveDeadlineBody,
    user: dict = Depends(require_write_access),
):
    """Waive a deadline (note required)."""
    if not payload.note or not payload.note.strip():
        raise HTTPException(status_code=400, detail="A waiver note is required.")
    deadline = await deadline_service.waive_deadline(deadline_id, user["user_id"], payload.note.strip())
    if not deadline:
        raise HTTPException(status_code=404, detail="Deadline not found.")
    return DeadlineResponse(**deadline)


@router.post("/deadlines/{deadline_id}/snooze", response_model=DeadlineResponse)
async def snooze_deadline(
    deadline_id: str,
    payload: SnoozeDeadlineBody,
    user: dict = Depends(require_write_access),
):
    """Snooze a deadline by extending its due_date N days."""
    if payload.days < 1 or payload.days > 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365.")
    deadline = await deadline_service.snooze_deadline(deadline_id, user["user_id"], payload.days)
    if not deadline:
        raise HTTPException(status_code=404, detail="Deadline not found.")
    return DeadlineResponse(**deadline)
