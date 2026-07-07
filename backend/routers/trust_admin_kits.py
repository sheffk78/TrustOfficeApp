"""
Trust Administration Kit router.

Auto-gathers trust data from MongoDB and uses AI to generate state-specific
paperwork packets for common trust administration tasks: vehicle retitling,
bank/brokerage account setup, real estate deed transfer, tax prep, insurance
scheduling, and professional onboarding.

The kit generator reads trust / entity / vault data the system already has so
the user only supplies information the system doesn't possess (e.g. vehicle
details for a vehicle retitle kit).  AI (ai_sonnet) produces the state-specific
instructions, form pre-fill data, fees, and checklist.
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import logging
import time
import uuid

from database import db
from dependencies import get_current_user, require_write_access
from ai_client import ai_sonnet, AIClientError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["trust_admin_kits"])


# ==================== KIT TYPE DEFINITIONS ====================

KIT_TYPES: Dict[str, Dict[str, Any]] = {
    "vehicle_retitle": {
        "label": "Vehicle Retitling",
        "description": "Transfer a vehicle title into the trust's name",
        "icon": "Car",
        "user_fields": [
            {"key": "vehicle_year", "label": "Vehicle Year", "type": "text", "required": True},
            {"key": "vehicle_make", "label": "Vehicle Make", "type": "text", "required": True},
            {"key": "vehicle_model", "label": "Vehicle Model", "type": "text", "required": True},
            {"key": "vehicle_vin", "label": "VIN", "type": "text", "required": False},
            {"key": "current_title_state", "label": "Current Title State", "type": "text", "required": False, "default_from": "state_code"},
            {"key": "registration_renewal_month", "label": "Registration Renewal Month (if known)", "type": "text", "required": False},
        ],
    },
    "bank_account": {
        "label": "Bank/Brokerage Account",
        "description": "Open a bank or brokerage account in the trust's name",
        "icon": "Building",
        "user_fields": [
            {"key": "institution_name", "label": "Institution Name", "type": "text", "required": False, "placeholder": "e.g., Police Credit Union"},
            {"key": "account_type", "label": "Account Type", "type": "select", "options": ["Checking", "Savings", "Brokerage", "CD"], "required": False},
        ],
    },
    "real_estate_transfer": {
        "label": "Real Estate Transfer",
        "description": "Transfer real estate into the trust via deed",
        "icon": "Home",
        "user_fields": [
            {"key": "property_address", "label": "Property Address", "type": "text", "required": True},
            {"key": "current_deed_state", "label": "State where property is located", "type": "text", "required": True, "default_from": "state_code"},
            {"key": "county", "label": "County", "type": "text", "required": True},
            {"key": "current_ownership", "label": "Current Ownership (how title is held now)", "type": "text", "required": False},
        ],
    },
    "tax_prep_packet": {
        "label": "Tax Prep Packet",
        "description": "Assemble trust financial data for your CPA",
        "icon": "FileText",
        "user_fields": [
            {"key": "tax_year", "label": "Tax Year", "type": "text", "required": True},
            {"key": "cpa_name", "label": "CPA/Firm Name", "type": "text", "required": False},
            {"key": "cpa_email", "label": "CPA Email", "type": "text", "required": False},
        ],
    },
    "insurance_schedule": {
        "label": "Insurance Scheduling",
        "description": "Schedule trust assets on insurance policies",
        "icon": "Shield",
        "user_fields": [
            {"key": "insurer_name", "label": "Insurance Company", "type": "text", "required": False},
            {"key": "policy_type", "label": "Policy Type", "type": "select", "options": ["Homeowners", "Auto", "Umbrella", "Jewelry/Art Rider", "Other"], "required": True},
        ],
    },
    "professional_engagement": {
        "label": "Professional Engagement",
        "description": "Onboard a CPA, attorney, or financial advisor with trust documentation",
        "icon": "Briefcase",
        "user_fields": [
            {"key": "professional_type", "label": "Professional Type", "type": "select", "options": ["CPA/Accountant", "Attorney", "Financial Advisor", "Insurance Agent"], "required": True},
            {"key": "firm_name", "label": "Firm Name", "type": "text", "required": False},
            {"key": "contact_email", "label": "Contact Email", "type": "text", "required": False},
        ],
    },
}


# ==================== RATE LIMITING ====================
# In-memory per-user generation counter.  Resets after the window elapses.
# Key: user_id  Value: (count, window_start_ts)
_MAX_KITS_PER_HOUR = 10
_RATE_WINDOW_SECONDS = 3600
_rate_limit_store: Dict[str, tuple] = {}


def _check_rate_limit(user_id: str) -> None:
    """Raise 429 if user has exceeded the kit generation rate limit."""
    now = time.time()
    entry = _rate_limit_store.get(user_id)
    if entry is None or (now - entry[1]) > _RATE_WINDOW_SECONDS:
        _rate_limit_store[user_id] = (1, now)
        return
    count, window_start = entry
    if count >= _MAX_KITS_PER_HOUR:
        retry_in = int(_RATE_WINDOW_SECONDS - (now - window_start))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: maximum {_MAX_KITS_PER_HOUR} kits per hour. Try again in {max(retry_in, 1)} seconds.",
        )
    _rate_limit_store[user_id] = (count + 1, window_start)


# ==================== DATA AUTO-GATHERING ====================

async def _gather_trust_data(trust_id: str, user_id: str) -> Dict[str, Any]:
    """
    Gather trust profile, entity record, and vault documents from MongoDB.

    Returns a dict with:
        trust_name, trustee_name, ein, formation_date, state_code,
        jurisdiction, trust_type, vault_docs
    """
    # 1. Trust profile
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "file_content": 0},
    )
    if not trust:
        raise HTTPException(
            status_code=404,
            detail="Trust not found. Please refresh the page or check your trust selection.",
        )

    # 2. Entity record (optional — may not exist)
    entity = await db.entities.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "file_content": 0},
    )

    # 3. Vault documents — exclude file_content (large BSON binary)
    vault_docs: List[Dict[str, Any]] = []
    async for doc in db.vault_documents.find(
        {"user_id": user_id},
        {"_id": 0, "file_content": 0},
    ):
        vault_docs.append({
            "doc_id": doc.get("doc_id"),
            "title": doc.get("title"),
            "category": doc.get("category"),
            "file_name": doc.get("file_name"),
        })

    # Merge trust + entity into a single auto_gathered snapshot
    gathered: Dict[str, Any] = {
        "trust_name": trust.get("name"),
        "trustee_name": trust.get("trustee_name"),
        "ein": trust.get("ein"),
        "formation_date": trust.get("start_date") or (entity or {}).get("formation_date"),
        "state_code": trust.get("state_code"),
        "jurisdiction": trust.get("jurisdiction"),
        "trust_type": trust.get("trust_type") or (entity or {}).get("entity_type"),
        "governing_law": (entity or {}).get("governing_law"),
        "trustee_names": (entity or {}).get("trustee_names"),
        "legal_name": (entity or {}).get("legal_name"),
        "beneficiary_standard": (entity or {}).get("beneficiary_standard"),
        "article_ref_distribution": (entity or {}).get("article_ref_distribution"),
        "article_ref_compensation": (entity or {}).get("article_ref_compensation"),
        "article_ref_amendment": (entity or {}).get("article_ref_amendment"),
        "vault_docs": vault_docs,
    }
    return gathered


def _build_user_needs_to_provide(kit_type: str, gathered: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the ``user_needs_to_provide`` mapping for the preview endpoint.

    Fields that carry ``default_from`` are pre-filled from the auto-gathered
    trust data so the frontend can show a sensible default.
    """
    kit_def = KIT_TYPES[kit_type]
    result: Dict[str, Any] = {}
    for field in kit_def["user_fields"]:
        key = field["key"]
        entry: Dict[str, Any] = {
            "label": field["label"],
            "type": field["type"],
            "required": field.get("required", False),
        }
        if "options" in field:
            entry["options"] = field["options"]
        if "placeholder" in field:
            entry["placeholder"] = field["placeholder"]
        # Pre-fill default from auto-gathered data where possible
        default_from = field.get("default_from")
        if default_from and gathered.get(default_from):
            entry["default"] = gathered[default_from]
        result[key] = entry
    return result


# ==================== AI PROMPT ====================

def _build_kit_system_prompt(kit_type: str, state_code: str) -> str:
    """Build the AI system prompt for a kit generation call."""
    kit_label = KIT_TYPES[kit_type]["label"]
    return (
        "You are a trust administration assistant. "
        f"Generate a detailed, state-specific kit for {kit_label} in the state with code '{state_code}'.\n\n"
        "Use the provided trust data to pre-fill form fields. "
        "Research the specific forms, fees, and procedures for the user's state. "
        "If the state has special provisions (e.g. Montana's permanent registration for vehicles 11+ years old), include them.\n\n"
        "Output valid JSON only — no markdown, no commentary, no code fences. "
        "The JSON must conform to this schema:\n"
        "{\n"
        '  "kit_title": "string — descriptive title including the state name",\n'
        '  "summary": "string — one paragraph summary of what this kit contains and what the trustee needs to do",\n'
        '  "instructions": {\n'
        '    "overview": "string — step-by-step overview of the process",\n'
        '    "steps": [\n'
        '      {"step": 1, "title": "string", "description": "string", "documents_needed": ["string"]}\n'
        '    ]\n'
        '  },\n'
        '  "forms": [\n'
        '    {\n'
        '      "form_name": "string",\n'
        '      "form_purpose": "string",\n'
        '      "pre_fill_data": {"field": "value"},\n'
        '      "where_to_get": "string",\n'
        '      "download_url": "string or null"\n'
        '    }\n'
        '  ],\n'
        '  "documents_to_bring": [\n'
        '    {"document": "string", "source": "string", "vault_doc_id": "string or null"}\n'
        '  ],\n'
        '  "fees": [\n'
        '    {"fee_name": "string", "amount": "string"}\n'
        '  ],\n'
        '  "special_notes": ["string"],\n'
        '  "where_to_submit": "string",\n'
        '  "estimated_time": "string"\n'
        "}\n"
        "For documents that already exist in the vault, set source to 'Already in your vault' "
        "and include the matching vault_doc_id. "
        "Include realistic, accurate, current information for the user's jurisdiction."
    )


def _build_kit_user_content(
    kit_type: str,
    gathered: Dict[str, Any],
    user_inputs: Dict[str, Any],
) -> str:
    """Build the user-content payload sent to the AI for kit generation."""
    payload = {
        "kit_type": kit_type,
        "kit_label": KIT_TYPES[kit_type]["label"],
        "trust_data": gathered,
        "user_inputs": user_inputs,
        "instructions": (
            "Using the trust data and user inputs above, produce the kit JSON object described in the system prompt. "
            "Pre-fill form fields using the trust data. Reference vault documents where relevant. "
            "Be specific to the trust's state/jurisdiction. Output JSON only."
        ),
    }
    return json.dumps(payload, indent=2, default=str)


def _parse_ai_kit_response(raw: str) -> Dict[str, Any]:
    """
    Parse the AI's JSON response.

    Tolerates the occasional models that wrap JSON in markdown fences.
    """
    text = raw.strip()
    if text.startswith("```"):
        # strip markdown fences
        text = text.split("```json", 1)[-1].split("```", 1)[0]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("AI kit response was not valid JSON: %s", text[:500])
        raise HTTPException(
            status_code=502,
            detail="AI returned malformed JSON. Please try generating the kit again.",
        ) from e


# ==================== ENDPOINTS ====================

@router.get("/trust-admin-kits/types")
async def list_kit_types(user: dict = Depends(get_current_user)):
    """Return the list of supported kit types with descriptions and field specs."""
    types = []
    for key, defn in KIT_TYPES.items():
        types.append({
            "kit_type": key,
            "label": defn["label"],
            "description": defn["description"],
            "icon": defn["icon"],
            "user_fields": defn["user_fields"],
        })
    return {"kit_types": types, "count": len(types)}


@router.get("/trust-admin-kits/preview/{kit_type}")
async def preview_kit(
    kit_type: str,
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Preview what data the system already has and what the user needs to provide.

    This is the 'smart recognition' step — it reads MongoDB only and does NOT
    call the AI.
    """
    if kit_type not in KIT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown kit type '{kit_type}'. Valid types: {', '.join(KIT_TYPES.keys())}",
        )
    if not trust_id:
        raise HTTPException(status_code=400, detail="trust_id query parameter is required")

    gathered = await _gather_trust_data(trust_id, user["user_id"])

    if not gathered.get("state_code"):
        raise HTTPException(
            status_code=400,
            detail="This trust has no state_code set. Update the trust profile in Settings to include the trust's jurisdiction before generating a kit.",
        )

    return {
        "kit_type": kit_type,
        "kit_label": KIT_TYPES[kit_type]["label"],
        "auto_gathered": gathered,
        "user_needs_to_provide": _build_user_needs_to_provide(kit_type, gathered),
    }


@router.post("/trust-admin-kits/generate")
async def generate_kit(
    body: Dict[str, Any],
    user: dict = Depends(require_write_access),
):
    """
    Generate a Trust Administration Kit.

    Re-gathers trust data from MongoDB, merges with user-supplied inputs,
    calls AI (ai_sonnet) to produce state-specific instructions, persists the
    kit to the ``trust_admin_kits`` collection, and returns the full kit.
    """
    kit_type = body.get("kit_type")
    trust_id = body.get("trust_id")
    user_inputs = body.get("user_inputs", {}) or {}

    if not kit_type:
        raise HTTPException(status_code=400, detail="kit_type is required")
    if kit_type not in KIT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown kit type '{kit_type}'. Valid types: {', '.join(KIT_TYPES.keys())}",
        )
    if not trust_id:
        raise HTTPException(status_code=400, detail="trust_id is required")

    # Validate required user inputs
    kit_def = KIT_TYPES[kit_type]
    missing = []
    for field in kit_def["user_fields"]:
        if field.get("required") and not user_inputs.get(field["key"]):
            # Field may have a default_from that we can auto-fill
            default_from = field.get("default_from")
            if default_from:
                gathered_preview = await _gather_trust_data(trust_id, user["user_id"])
                if gathered_preview.get(default_from):
                    user_inputs.setdefault(field["key"], gathered_preview[default_from])
                    continue
            missing.append(field["label"])
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required inputs: {', '.join(missing)}",
        )

    # Rate limit
    _check_rate_limit(user["user_id"])

    # Gather fresh trust data
    gathered = await _gather_trust_data(trust_id, user["user_id"])

    state_code = gathered.get("state_code")
    if not state_code:
        raise HTTPException(
            status_code=400,
            detail="This trust has no state_code set. Update the trust profile in Settings to include the trust's jurisdiction before generating a kit.",
        )

    # Build AI prompt and call
    system_prompt = _build_kit_system_prompt(kit_type, state_code)
    user_content = _build_kit_user_content(kit_type, gathered, user_inputs)

    try:
        raw_response = await ai_sonnet(
            system_prompt,
            user_content,
            max_tokens=4000,
            temperature=0.3,
        )
    except AIClientError as e:
        logger.error("AI kit generation failed for user=%s kit=%s: %s", user["user_id"], kit_type, e)
        raise HTTPException(
            status_code=503,
            detail="AI service unavailable. The kit could not be generated right now. Please try again in a moment.",
        ) from e
    except Exception as e:
        logger.error("Unexpected AI error for user=%s kit=%s: %s", user["user_id"], kit_type, e)
        raise HTTPException(
            status_code=503,
            detail="Unexpected error generating kit. Please try again.",
        ) from e

    generated_content = _parse_ai_kit_response(raw_response)

    # Compose kit document
    now = datetime.now(timezone.utc).isoformat()
    kit_id = f"kit_{uuid.uuid4().hex[:12]}"
    kit_doc = {
        "kit_id": kit_id,
        "trust_id": trust_id,
        "user_id": user["user_id"],
        "kit_type": kit_type,
        "kit_title": generated_content.get("kit_title", KIT_TYPES[kit_type]["label"]),
        "status": "generated",
        "auto_gathered": gathered,
        "user_inputs": user_inputs,
        "generated_content": generated_content,
        "created_at": now,
        "updated_at": now,
        "viewed_at": None,
        "downloaded_at": None,
    }

    try:
        await db.trust_admin_kits.insert_one(kit_doc)
    except Exception as e:
        logger.error("Failed to persist kit %s: %s", kit_id, e)
        raise HTTPException(status_code=500, detail="Failed to save kit. Please try again.") from e

    # Strip _id for response
    kit_doc.pop("_id", None)
    return kit_doc


@router.get("/trust-admin-kits")
async def list_kits(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List all kits for the current user, optionally filtered by trust_id."""
    query: Dict[str, Any] = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id

    kits = await db.trust_admin_kits.find(
        query,
        {"_id": 0, "auto_gathered.vault_docs": 0},
    ).sort("created_at", -1).to_list(200)

    return {"kits": kits, "count": len(kits)}


@router.get("/trust-admin-kits/{kit_id}")
async def get_kit(kit_id: str, user: dict = Depends(get_current_user)):
    """Get a single kit by ID and mark it as viewed."""
    kit = await db.trust_admin_kits.find_one(
        {"kit_id": kit_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not kit:
        raise HTTPException(
            status_code=404,
            detail="Kit not found. It may have been deleted. Please refresh the page and try again.",
        )

    # Update viewed status + timestamp (fire-and-forget)
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.trust_admin_kits.update_one(
            {"kit_id": kit_id, "user_id": user["user_id"]},
            {"$set": {"status": "viewed", "viewed_at": now, "updated_at": now}},
        )
    except Exception as e:
        logger.warning("Failed to mark kit %s as viewed: %s", kit_id, e)

    kit["status"] = "viewed"
    kit["viewed_at"] = now
    return kit


@router.delete("/trust-admin-kits/{kit_id}")
async def delete_kit(kit_id: str, user: dict = Depends(require_write_access)):
    """Delete a kit."""
    result = await db.trust_admin_kits.delete_one(
        {"kit_id": kit_id, "user_id": user["user_id"]},
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Kit not found. It may have already been deleted. Please refresh the page and try again.",
        )
    return {"message": "Kit deleted", "kit_id": kit_id}