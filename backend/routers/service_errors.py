"""TrustOffice "errors service" lane (2026-11-17 false-alarm fix).

Scoped, service-to-service endpoint for Kit's command center to sweep the
benign Starlette BaseHTTPMiddleware client-disconnect noise (bot probes
aborting mid-response -> RuntimeError("No response returned.")) out of the
unresolved-error feed. Authenticated with the same X-Service-Key header
pattern as the leads service lane — NOT a user JWT. The key itself is the
shared service key (TRUSTOFFICE_LEADS_SERVICE_KEY); the header/dependency
helpers are imported from leads_service.py to avoid duplication.

Endpoints (mounted under /api/service/errors):
  POST /resolve-disconnects -> mark matching stale disconnect errors
                               resolved + return every remaining
                               unresolved error for Jeff's feed
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from database import db
from routers.leads_service import SERVICE_KEY_HEADER, require_leads_service

logger = logging.getLogger(__name__)

# Only disconnect errors at least this old are swept — a live probe storm is
# still writing rows, and recent rows may be part of an active investigation.
SWEEP_MIN_AGE = timedelta(hours=1)

# Match the exact Starlette message fragment; case-insensitive regex like the
# rest of the error store queries. Never matches a user-facing error string.
DISCONNECT_PATTERN = {"$regex": "No response returned", "$options": "i"}

# Fixed note recorded on every swept row (verified: all probed paths 404).
SWEEP_NOTE = (
    "Auto-resolved: benign BaseHTTPMiddleware client-disconnect (bot probe) "
    "— verified no exposure 2026-11-18."
)

# Cap on the remaining_unresolved view returned to the caller.
REMAINING_LIMIT = 20

# Message truncation for the feed view.
MESSAGE_LIMIT = 120


router = APIRouter(
    prefix="/service/errors",
    tags=["service-errors"],
    dependencies=[Depends(require_leads_service)],
)


@router.post("/resolve-disconnects")
async def resolve_disconnects():
    """Sweep stale benign client-disconnect errors out of the unresolved feed.

    Matches db.error_logs rows where resolved==False AND error_message
    contains "No response returned" (case-insensitive) AND timestamp is
    older than SWEEP_MIN_AGE. Sets resolved=True, resolved_at=now (iso),
    resolved_note=SWEEP_NOTE. Read-only afterwards: no other mutations.

    Returns every remaining unresolved error (up to 20, newest first) so
    the caller can reconcile Jeff's feed in one round trip.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - SWEEP_MIN_AGE).isoformat()

    sweep_query = {
        "resolved": False,
        "error_message": DISCONNECT_PATTERN,
        "timestamp": {"$lt": cutoff},
    }
    result = await db.error_logs.update_many(
        sweep_query,
        {
            "$set": {
                "resolved": True,
                "resolved_at": now.isoformat(),
                "resolved_note": SWEEP_NOTE,
            }
        },
    )
    resolved_count = result.modified_count
    logger.info(
        "service-errors sweep: resolved %d stale BaseHTTPMiddleware "
        "client-disconnect rows (cutoff=%s)",
        resolved_count,
        cutoff,
    )

    remaining_unresolved: list = []
    cursor = (
        db.error_logs.find({"resolved": False})
        .sort("timestamp", -1)
        .limit(REMAINING_LIMIT)
    )
    async for doc in cursor:
        message = doc.get("error_message") or ""
        remaining_unresolved.append(
            {
                "error_id": doc.get("error_id"),
                "url": doc.get("url"),
                "error_type": doc.get("error_type"),
                "timestamp": doc.get("timestamp"),
                "truncated_message": message[:MESSAGE_LIMIT],
            }
        )

    return {
        "success": True,
        "resolved_count": resolved_count,
        "updated": result.modified_count,
        "remaining_unresolved": remaining_unresolved,
    }
