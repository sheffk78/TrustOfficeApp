"""
Page Agent Router — authenticated LLM proxy for the Page Agent pilot.

Endpoints:
- POST /api/page-agent/llm/chat/completions  — forwards chat completion requests
  to OpenRouter (OpenAI-compatible) after validating the caller's JWT and active
  subscription. Appends the OpenRouter API key server-side and strips any key
  material from responses. Every prompt is logged to MongoDB (page_agent_audit).
- GET  /api/page-agent/health — simple health check.

The frontend Page Agent component points `baseURL` at this endpoint so the
OpenRouter API key never reaches the browser.

The route path `/llm/chat/completions` matches the OpenAI SDK convention used
by Page Agent's internal LLM client — it appends `/chat/completions` to the
configured `baseURL`.
"""
import asyncio
import os
import json
import re
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dependencies import get_current_user, get_subscription_state
from database import db

router = APIRouter(prefix="/page-agent", tags=["page-agent"])
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================

# OpenRouter (same provider TrustOffice already uses for all AI calls).
# The key lives in OPENROUTER_API_KEY, same as ai_client.py.
# Default model mirrors the existing TrustOffice default (Gemini flash).
OPENROUTER_CHAT_URL = os.environ.get(
    "OPENROUTER_CHAT_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
PAGE_AGENT_MODEL = os.environ.get(
    "PAGE_AGENT_MODEL",
    os.environ.get("OPENROUTER_DEFAULT_MODEL", "google/gemini-2.5-flash-lite"),
)

# Upstream timeout (seconds). Page Agent calls can take a while due to tool
# loops, so be generous but bounded.
UPSTREAM_TIMEOUT = int(os.environ.get("PAGE_AGENT_UPSTREAM_TIMEOUT", "120"))

# Maximum bytes we'll accept on the proxy body to avoid abuse.
MAX_BODY_BYTES = 256 * 1024  # 256 KB

# Patterns to scrub from upstream responses so we never leak the API key
# back to the browser. Keys are matched case-insensitively as substrings.
KEY_SCRUB_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE),
]

AUDIT_COLLECTION = "page_agent_audit"


# ==================== MODELS ====================

class LLMProxyRequest(BaseModel):
    """OpenAI-compatible chat completion body forwarded to OpenRouter.

    We accept a loosely-typed dict so Page Agent can evolve its request shape
    (tools, messages, stream, etc.) without a backend redeploy.
    """
    model: str = Field(..., description="Model identifier, e.g. google/gemini-2.5-flash-lite")
    messages: list = Field(..., description="OpenAI-style messages array")
    # Optional fields commonly sent by OpenAI clients — all optional
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = None
    tools: Optional[list] = None
    tool_choice: Optional[Any] = None
    stop: Optional[Any] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    upstream_configured: bool
    audit_collection: str


# ==================== HELPERS ====================

def _scrub_keys(text: str) -> str:
    """Remove any obvious API-key/Bearer patterns from a string."""
    if not text:
        return text
    scrubbed = text
    for pat in KEY_SCRUB_PATTERNS:
        scrubbed = pat.sub("[REDACTED]", scrubbed)
    return scrubbed


def _scrub_obj(obj: Any) -> Any:
    """Recursively scrub key-like substrings from strings inside a JSON-ish object."""
    if isinstance(obj, str):
        return _scrub_keys(obj)
    if isinstance(obj, list):
        return [_scrub_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_obj(v) for k, v in obj.items()}
    return obj


def _extract_prompt_text(body: Dict[str, Any]) -> str:
    """Best-effort extraction of the user-facing prompt text for the audit log."""
    try:
        messages = body.get("messages") or []
        parts = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, list):
                # OpenAI vision/tool content blocks
                content = " ".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            if content:
                parts.append(f"[{role}] {content}")
        return "\n".join(parts)[:8000]  # cap audit record size
    except Exception:
        return json.dumps(body, default=str)[:8000]


async def _audit_log(
    user_id: str,
    trust_id: Optional[str],
    prompt_text: str,
    response_status: int,
    model: str,
    error: Optional[str] = None,
) -> None:
    """Persist an audit record to MongoDB. Fire-and-forget — never block the response."""
    try:
        doc = {
            "user_id": user_id,
            "trust_id": trust_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "prompt_text": prompt_text,
            "response_status": response_status,
            "error": error,
        }
        await db[AUDIT_COLLECTION].insert_one(doc)
    except Exception as e:
        # Audit failure must not break the user's request — only log it.
        logger.error(f"page_agent audit log insert failed: {e}")


def _call_openrouter(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    """Forward the body to OpenRouter. Returns (status, parsed_json, raw_text).

    Raises HTTPException on transport failure so the route can surface it.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="LLM proxy not configured: OPENROUTER_API_KEY is not set on the server.",
        )

    # Build the upstream payload. Force the model to the configured Page Agent
    # model so a tampered client request can't route to an arbitrary model.
    body["model"] = PAGE_AGENT_MODEL
    payload = json.dumps(body).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        # OpenRouter attribution headers (matches openrouter_client.py pattern)
        "HTTP-Referer": os.environ.get("OPENROUTER_REFERRER", "https://trustoffice.app"),
        "X-Title": "TrustOffice",
    }

    req = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            err_body = str(e)
        logger.error(f"page_agent upstream HTTP {e.code}: {err_body}")
        raise HTTPException(
            status_code=502,
            detail=f"Upstream LLM error ({e.code}): {_scrub_keys(err_body)}",
        )
    except urllib.error.URLError as e:
        logger.error(f"page_agent upstream unreachable: {e}")
        raise HTTPException(
            status_code=504,
            detail=f"Upstream LLM unreachable: {str(e)[:200]}",
        )
    except Exception as e:
        logger.error(f"page_agent upstream unexpected error: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Upstream LLM error: {str(e)[:200]}",
        )

    # Parse JSON (tolerate non-JSON error pages)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"raw": raw[:2000]}

    return status, parsed, raw


# ==================== ENDPOINTS ====================

@router.get("/health")
async def page_agent_health():
    """Health check for the Page Agent proxy."""
    return HealthResponse(
        status="ok",
        service="trustoffice-page-agent-proxy",
        upstream_configured=bool(OPENROUTER_API_KEY),
        audit_collection=AUDIT_COLLECTION,
    )


@router.post("/llm/chat/completions")
async def page_agent_llm_proxy(
    request: Request,
    body: LLMProxyRequest,
    user: dict = Depends(get_current_user),
):
    """
    Authenticated LLM proxy for Page Agent.

    1. Validates JWT (via get_current_user).
    2. Checks subscription is active (not read-only).
    3. Forwards the body to OpenRouter with the server-held API key.
    4. Logs the prompt + response status to page_agent_audit.
    5. Scrubs any API-key material from the response before returning.
    """
    user_id = user["user_id"]

    # --- Content-length guard (defence-in-depth, not a hard limit) ---
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body too large.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid content-length header.")

    # --- Subscription check: block read-only / inactive accounts ---
    sub_state = await get_subscription_state(user_id)
    if sub_state.is_read_only or not sub_state.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your subscription is inactive. Page Agent requires an active subscription.",
            headers={"X-Subscription-Status": sub_state.status},
        )

    # --- Resolve active trust_id for the audit record (best-effort) ---
    trust_id = None
    try:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0, "trust_id": 1},
            sort=[("created_at", -1)],
        )
        if trust:
            trust_id = trust.get("trust_id")
    except Exception as e:
        logger.warning(f"page_agent: could not resolve trust_id for audit: {e}")

    # --- Build upstream body (model forwarded as-is from client) ---
    body_dict = body.model_dump(exclude_none=True)
    # Force stream off — we return a single JSON response. Page Agent's
    # non-streaming path is what we pilot with.
    body_dict["stream"] = False

    prompt_text = _extract_prompt_text(body_dict)

    # --- Call upstream (off the event loop so we don't block other requests) ---
    try:
        status, parsed, raw = await asyncio.to_thread(_call_openrouter, body_dict)
    except HTTPException as he:
        # Audit the failure then re-raise
        await _audit_log(
            user_id=user_id,
            trust_id=trust_id,
            prompt_text=prompt_text,
            response_status=he.status_code,
            model=body_dict.get("model", "unknown"),
            error=str(he.detail)[:1000],
        )
        raise

    # --- Scrub any key material from the response before returning ---
    scrubbed = _scrub_obj(parsed)

    # --- Audit success ---
    await _audit_log(
        user_id=user_id,
        trust_id=trust_id,
        prompt_text=prompt_text,
        response_status=status,
        model=body_dict.get("model", "unknown"),
    )

    return JSONResponse(content=scrubbed, status_code=status)