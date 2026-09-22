"""
HTTP surface for the TrustOffice shared action layer.

Exposes every registered action as:

  GET  /api/actions                     → manifest (agent + UI discovery)
  GET  /api/actions/{name}              → one action's manifest
  POST /api/actions/{name}              → call an action

Agent tools read the manifest; the React UI calls POST through the
callAction() helper. The same handlers power the chat approval pipeline —
one action, many surfaces, no duplicate logic.

Param validation, trust-ownership checks, and the write gate all live in
action_layer.call_action() so every surface gets identical enforcement;
this router adds HTTP-specific error mapping only.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from action_layer import ACTIONS, ActionError, call_action, list_actions
from dependencies import get_current_user

router = APIRouter(prefix="/actions", tags=["actions"])
logger = logging.getLogger(__name__)


class ActionCallRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    trust_id: Optional[str] = Field(None, description="Trust scope; defaults to the caller's active trust")
    conversation_id: Optional[str] = Field(None, description="Chat conversation context, when the caller is the Trust Assistant")


@router.get("")
async def list_all_actions(user: dict = Depends(get_current_user)):
    """Manifest of every registered action — the discovery surface."""
    return {"actions": list_actions()}


@router.get("/{name}")
async def get_action_manifest(name: str, user: dict = Depends(get_current_user)):
    act = ACTIONS.get(name)
    if not act:
        raise HTTPException(status_code=404, detail=f"Unknown action: {name}")
    return act.to_manifest()


@router.post("/{name}")
async def call_action_endpoint(
    name: str,
    body: ActionCallRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Execute a registered action.

    Validation, trust ownership, and the subscription write gate are enforced
    inside action_layer.call_action(); failures come back as ok=false with a
    machine-readable error code (the layer never raises past this point).
    """
    if name not in ACTIONS:
        raise HTTPException(status_code=404, detail=f"Unknown action: {name}")

    outcome = await call_action(
        name,
        body.params or {},
        user_id=user["user_id"],
        trust_id=body.trust_id,
        user=user,
        surface="ui",
    )

    # Uniform envelope, plain 200 — machines read ok/error.code, UIs read
    # result. Validation errors surface as action_params_invalid here.
    return outcome