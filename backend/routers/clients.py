# Clients router — Phase 2 Multi-Trust Client View
from fastapi import APIRouter, HTTPException, Depends
from typing import List

from dependencies import get_current_user, require_write_access
from models import (
    ClientCreate, ClientUpdate, ClientResponse,
    ClientDetailResponse, ClientHealthSummary,
    DeadlineResponse, MeetingResponse,
)
from services import client_service

router = APIRouter(tags=["clients"])


# ==================== HELPERS ====================

async def _require_owned_client(client_id: str, user: dict) -> dict:
    client = await client_service.get_client(client_id, user["user_id"])
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    return client


# ==================== CLIENT CRUD ====================

@router.post("/clients", response_model=ClientResponse, status_code=201)
async def create_client(
    payload: ClientCreate,
    user: dict = Depends(require_write_access),
):
    """Create a new client profile."""
    client = await client_service.create_client(payload, user["user_id"])
    return ClientResponse(**client)


@router.get("/clients", response_model=List[ClientResponse])
async def list_clients(user: dict = Depends(get_current_user)):
    """List all clients for the current user."""
    clients = await client_service.list_clients(user["user_id"])
    return [ClientResponse(**c) for c in clients]


@router.get("/clients/{client_id}", response_model=ClientDetailResponse)
async def get_client_detail(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    """Get detailed client view with all linked trusts."""
    detail = await client_service.get_client_detail(client_id, user["user_id"])
    if not detail:
        raise HTTPException(status_code=404, detail="Client not found.")
    return ClientDetailResponse(**detail)


@router.put("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str,
    payload: ClientUpdate,
    user: dict = Depends(require_write_access),
):
    """Update client profile."""
    updated = await client_service.update_client(client_id, payload, user["user_id"])
    if not updated:
        raise HTTPException(status_code=404, detail="Client not found.")
    return ClientResponse(**updated)


@router.delete("/clients/{client_id}", status_code=204)
async def delete_client(
    client_id: str,
    user: dict = Depends(require_write_access),
):
    """Delete a client profile. Trusts are unlinked, not deleted."""
    deleted = await client_service.delete_client(client_id, user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Client not found.")


# ==================== TRUST LINKING ====================

@router.post("/clients/{client_id}/trusts/{trust_id}")
async def link_trust(
    client_id: str,
    trust_id: str,
    user: dict = Depends(require_write_access),
):
    """Link a trust to a client."""
    result = await client_service.link_trust(client_id, trust_id, user["user_id"])
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Client or trust not found.",
        )
    return {"status": "linked", "client_id": client_id, "trust_id": trust_id}


@router.delete("/clients/{client_id}/trusts/{trust_id}")
async def unlink_trust(
    client_id: str,
    trust_id: str,
    user: dict = Depends(require_write_access),
):
    """Unlink a trust from a client."""
    result = await client_service.unlink_trust(client_id, trust_id, user["user_id"])
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Client or linked trust not found.",
        )
    return {"status": "unlinked", "client_id": client_id, "trust_id": trust_id}


# ==================== AGGREGATION ====================

@router.get("/clients/{client_id}/health", response_model=ClientHealthSummary)
async def get_client_health(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    """Get aggregated health summary across all linked trusts."""
    health = await client_service.get_client_health(client_id, user["user_id"])
    if not health:
        raise HTTPException(status_code=404, detail="Client not found.")
    return ClientHealthSummary(**health)


@router.get("/clients/{client_id}/deadlines", response_model=List[DeadlineResponse])
async def get_client_deadlines(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    """Get all deadlines across all trusts for this client."""
    await _require_owned_client(client_id, user)
    deadlines = await client_service.get_client_deadlines(client_id, user["user_id"])
    return [DeadlineResponse(**d) for d in deadlines]


@router.get("/clients/{client_id}/meetings", response_model=List[MeetingResponse])
async def get_client_meetings(
    client_id: str,
    user: dict = Depends(get_current_user),
):
    """Get all meetings across all trusts for this client."""
    await _require_owned_client(client_id, user)
    meetings = await client_service.get_client_meetings(client_id, user["user_id"])
    return [MeetingResponse(**m) for m in meetings]
