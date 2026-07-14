"""
In-app error logging router.

POST /api/error-log
    Public endpoint (no JWT required) for frontend error reports.
    Rate limited: max 10 reports per minute per IP.
    Stores in MongoDB (error_logs collection) with full context for later
    querying by Kit via the admin endpoint.

GET /api/admin-api/error-log
    Admin-only (X-Admin-API-Key header). Returns recent errors sorted by
    timestamp desc. Supports ?limit, ?since, ?resolved query params.
"""
from __future__ import annotations

import os
import time
import secrets
import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from database import db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

# Public router — POST /api/error-log (no prefix; mounted under /api in server.py)
router = APIRouter(tags=["error-log"])

# Admin router — GET /api/admin-api/error-log (mounted under /api in server.py)
admin_router = APIRouter(prefix="/admin-api", tags=["error-log-admin"])

# ---------------------------------------------------------------------------
# Admin API key auth (same pattern as admin_api.py)
# ---------------------------------------------------------------------------

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
_api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


async def _verify_admin_key(api_key: Optional[str]) -> None:
    """Verify the X-Admin-API-Key header. Raises 401 if missing/invalid."""
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="Admin API not configured")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Use X-Admin-API-Key header.")
    if not secrets.compare_digest(api_key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Per-IP rate limiting (max 10 reports per minute per IP)
# ---------------------------------------------------------------------------

_RATE_LIMIT_WINDOW = 60  # 1 minute
_RATE_LIMIT_MAX = 10
_ip_buckets: Dict[str, deque] = defaultdict(deque)


def _is_rate_limited(ip: str) -> bool:
    """Return True if the IP has exceeded the per-IP rate limit."""
    now = time.time()
    bucket = _ip_buckets[ip]
    cutoff = now - _RATE_LIMIT_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT_MAX:
        return True
    bucket.append(now)
    return False


def _get_client_ip(request: Request) -> str:
    """Extract client IP, honouring X-Forwarded-For (rightmost = closest proxy)."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ErrorLogPayload(BaseModel):
    """Payload the frontend sends when capturing an error."""

    error_type: str = Field("uncaught_exception", max_length=200)
    error_message: str = Field("", max_length=4000)
    stack_trace: Optional[str] = Field(None, max_length=8000)
    url: Optional[str] = Field(None, max_length=1000)
    user_agent: Optional[str] = Field(None, max_length=500)
    component_stack: Optional[str] = Field(None, max_length=8000)
    boundary: Optional[bool] = False
    metadata: Optional[Dict[str, Any]] = Field(None)


# ---------------------------------------------------------------------------
# POST /api/error-log — public, rate-limited, stores in MongoDB
# ---------------------------------------------------------------------------


@router.post("/error-log", status_code=200)
async def log_frontend_error(payload: ErrorLogPayload, request: Request):
    """Receive and store a frontend error report.

    No JWT required — errors can happen before auth completes.
    User ID is extracted best-effort from the Authorization header or
    session_token cookie (no DB hit, just JWT decode).
    """
    client_ip = _get_client_ip(request)

    # Per-IP rate limit
    if _is_rate_limited(client_ip):
        return {"status": "rate_limited"}

    # Best-effort user_id extraction from JWT (no DB hit)
    user_id: Optional[str] = None
    try:
        import jwt as _jwt

        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        else:
            token = request.cookies.get("session_token")

        if token:
            jwt_secret = os.environ.get("JWT_SECRET")
            if jwt_secret:
                decoded = _jwt.decode(token, jwt_secret, algorithms=["HS256"])
                user_id = decoded.get("user_id")
    except Exception:
        pass  # No token or invalid — still log anonymously

    # Store in MongoDB
    now = datetime.now(timezone.utc)
    doc = {
        "error_id": f"err_{uuid.uuid4().hex[:12]}",
        "timestamp": now.isoformat(),
        "user_id": user_id,
        "error_type": payload.error_type[:200] if payload.error_type else "unknown",
        "error_message": payload.error_message[:4000] if payload.error_message else "",
        "stack_trace": payload.stack_trace[:8000] if payload.stack_trace else None,
        "url": payload.url[:1000] if payload.url else None,
        "user_agent": payload.user_agent[:500] if payload.user_agent else None,
        "component_stack": payload.component_stack[:8000] if payload.component_stack else None,
        "boundary": bool(payload.boundary),
        "metadata": payload.metadata if isinstance(payload.metadata, dict) else {},
        "resolved": False,
        "ip_address": client_ip,
    }

    try:
        await db.error_logs.insert_one(doc)
    except Exception as e:
        logger.error(f"Failed to store error log: {e}")
        # Return 200 anyway — error reporting must never cause issues for the frontend
        return {"status": "stored_failed"}

    return {"status": "logged"}


# ---------------------------------------------------------------------------
# PATCH /api/admin-api/error-log/{error_id}/resolve — mark as resolved
# ---------------------------------------------------------------------------


@router.post("/error-log/{error_id}/resolve", status_code=200)
async def resolve_error_log(error_id: str, request: Request):
    """Mark an error log entry as resolved (admin-only)."""
    api_key = request.headers.get("X-Admin-API-Key")
    await _verify_admin_key(api_key)

    result = await db.error_logs.update_one(
        {"error_id": error_id},
        {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Error log not found")
    return {"status": "resolved", "error_id": error_id}


# ---------------------------------------------------------------------------
# GET /api/admin-api/error-log — admin-only, returns recent errors
# ---------------------------------------------------------------------------


@admin_router.get("/error-log")
async def get_error_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    since: Optional[str] = Query(None, description="ISO timestamp — only return errors after this time"),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
):
    """Return recent error logs, sorted by timestamp desc. Admin-only."""
    api_key = request.headers.get("X-Admin-API-Key")
    await _verify_admin_key(api_key)

    query: Dict[str, Any] = {}
    if since:
        query["timestamp"] = {"$gte": since}
    if resolved is not None:
        query["resolved"] = resolved

    cursor = db.error_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    errors: List[Dict[str, Any]] = await cursor.to_list(length=limit)

    total = await db.error_logs.count_documents(query)
    unresolved = await db.error_logs.count_documents({"resolved": False})

    return {
        "errors": errors,
        "total": total,
        "unresolved_count": unresolved,
        "limit": limit,
    }