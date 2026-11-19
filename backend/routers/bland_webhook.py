"""Bland.ai call-completed webhook receiver (batch-mode lane).

POST /api/service/bland/webhook — public route under the standard /api prefix;
NO service-key JWT, NO user session. Auth: header `X-Webhook-Secret` must
equal env BLAND_WEBHOOK_SECRET (constant-time compare). While
BLAND_WEBHOOK_SECRET is unset the route returns 503 — an unauthenticated open
endpoint never exists; set the env to unlock.

Payload shape per Bland's docs (fields not invented — quoted sources):
- https://docs.bland.ai/tutorials/post-call-webhooks — "Standard Post-Call
  Webhook": call_id, call_length (MINUTES — the doc example shows
  0.183333 min for an ~11s call, matching corrected_duration "11"),
  completed, queue_status, status, error_message, answered_by, variables{},
  metadata{}, summary, concatenated_transcript, transcripts[], disposition_tag
  (V1 pathways), agent_dispositions[] (agent calls; empty when every
  disposition uses Follow-up event delivery).
- https://docs.bland.ai/api-v1/post/calls-agent — Send Call accepts `webhook`,
  `request_data` {}, `metadata` {} and `external_id` "string": our dispatcher
  echoes the CRM lead_id there, so the webhook carries it back in those spots
  (checked at top level too).
- https://docs.bland.ai/agents/dispositions#read-the-results — agent
  disposition results arrive under agent_dispositions: [{disposition_key,
  name, status, payload{}, values[{key,state,value}], evidence[], ...}],
  either held on the call webhook (Hold original) or as follow-up events with
  event_type "dispositions" on the same URL.

Retries: the docs warn events can arrive more than once and to deduplicate on
the X-Webhook-Idempotency-Key header. When that header is present and an
event with the same key already had its outcome applied, we answer 2xx and
skip re-applying (ai_call_attempts must not double-count).

Behavior: persist the FULL raw payload (+ received_at, header-truncated UA)
into the bland_webhook_events collection FIRST, then attempt deterministic
mapping: a recognizable disposition + a lead_id/external_id that resolves to
a CRM lead rides _apply_call_outcome (the exact /{lead_id}/call-outcome logic,
including the cooldown stamp). Anything unmappable is stored only and
answered 202 {"status": "stored_unmapped"}. Malformed payloads never 500:
202/400 max; garbage bodies are still persisted for debugging.
"""
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from database import db
from routers.leads_service import (
    WEBHOOK_DISPOSITIONS,
    _apply_call_outcome,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/service/bland", tags=["bland-webhook"])

WEBHOOK_SECRET_HEADER = "x-webhook-secret"
IDEMPOTENCY_HEADER = "x-webhook-idempotency-key"
USER_AGENT_MAX = 120
SUMMARY_MAX = 300
# Transcript tail fallback length for the activity summary.
TRANSCRIPT_TAIL_CHARS = 160


def _normalize_disposition(raw) -> str:
    """'Not Interested' / 'NO-ANSWER' -> not_interested; non-strings pass."""
    if not isinstance(raw, str):
        return ""
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized.replace("__", "_")


def _entry_pairs(entry: dict):
    """(key, value) pairs an agent_dispositions entry produced.

    Per the dispositions doc: `payload` carries every produced value keyed by
    its key; `values` is the raw list with per-value state.
    """
    pairs = []
    payload = entry.get("payload")
    if isinstance(payload, dict):
        pairs.extend(payload.items())
    values = entry.get("values")
    if isinstance(values, list):
        for v in values:
            if not isinstance(v, dict):
                continue
            if v.get("state") not in (None, "produced"):
                continue
            key = v.get("key")
            if isinstance(key, str) and key:
                pairs.append((key, v.get("value")))
    return pairs


def _extract_disposition(payload: dict) -> Tuple[Optional[str], str]:
    """Deterministic disposition lookup. Returns (mapped, raw_candidate).

    Order (all doc-quoted surfaces):
      1. agent_dispositions entries — truthy boolean on a key that names a
         disposition ('booked': true), or a produced string value that IS one.
      2. top-level `disposition` / `disposition_tag` (V1 pathways).
      3. metadata / request_data `disposition` keys (dispatcher echo).
    Anything not in our disposition vocabulary stays unmapped — we never
    invent a mapping.
    """
    raw_candidate = ""

    def _consider(raw) -> Optional[str]:
        nonlocal raw_candidate
        if not isinstance(raw, str) or not raw.strip():
            return None
        candidate = raw.strip()
        if not raw_candidate:
            raw_candidate = candidate
        normalized = _normalize_disposition(candidate)
        if normalized in WEBHOOK_DISPOSITIONS:
            return normalized
        return None

    entries = payload.get("agent_dispositions")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for key, value in _entry_pairs(entry):
                # String VALUE that names a disposition ('interested').
                mapped = _consider(value)
                if mapped:
                    return mapped, raw_candidate
                # Boolean on a key that names one ('booked', 'opt_out').
                if isinstance(value, bool) and value:
                    mapped = _consider(key)
                    if mapped:
                        return mapped, raw_candidate

    for container in (
        payload,
        payload.get("metadata"),
        payload.get("request_data"),
    ):
        if not isinstance(container, dict):
            continue
        for key in ("disposition", "outcome", "disposition_tag"):
            mapped = _consider(container.get(key))
            if mapped:
                return mapped, raw_candidate

    return None, raw_candidate


def _extract_lead_ref(payload: dict) -> Optional[str]:
    """lead_id / external_id echoed by the dispatcher.

    Dispatch surfaces (docs.bland.ai/api-v1/post/calls-agent): request_data{},
    metadata{}, external_id. Top-level checked first in case the agent config
    bubbles the ref up.
    """
    for container in (
        payload,
        payload.get("request_data"),
        payload.get("metadata"),
        payload.get("variables"),
    ):
        if not isinstance(container, dict):
            continue
        for key in ("lead_id", "external_id"):
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _summary_from_payload(payload: dict) -> str:
    """summary field, else transcript tail for the activity line."""
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()[:SUMMARY_MAX]
    tail = ""
    concatenated = payload.get("concatenated_transcript")
    if isinstance(concatenated, str) and concatenated.strip():
        tail = concatenated.strip()[-TRANSCRIPT_TAIL_CHARS:]
    else:
        transcripts = payload.get("transcripts")
        if isinstance(transcripts, list):
            texts = [
                t.get("text")
                for t in transcripts
                if isinstance(t, dict) and isinstance(t.get("text"), str) and t.get("text")
            ]
            if texts:
                tail = " ".join(texts)[-TRANSCRIPT_TAIL_CHARS:]
    if tail:
        return ("Transcript tail: " + tail)[:SUMMARY_MAX]
    return ""


def _call_duration_sec(payload: dict) -> Optional[int]:
    """call_length is MINUTES per the post-call webhook doc example
    (0.183333 min == 11s == corrected_duration "11"); seconds fallback."""
    call_length = payload.get("call_length")
    if isinstance(call_length, (int, float)) and not isinstance(call_length, bool):
        if call_length >= 0:
            return int(round(call_length * 60))
    corrected = payload.get("corrected_duration")
    if isinstance(corrected, str) and corrected.strip():
        try:
            value = float(corrected.strip())
            if value >= 0:
                return int(round(value))
        except ValueError:
            return None
    return None


def _user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:USER_AGENT_MAX]


@router.post("/webhook")
async def bland_call_completed(request: Request, background_tasks: BackgroundTasks):
    """Bland call-completed receiver — see module docstring for the contract.

    Mapped outcomes run the exact /{lead_id}/call-outcome logic (_apply_call_outcome),
    which now includes the founder fallback email trigger queued on background_tasks.
    """
    expected = os.environ.get("BLAND_WEBHOOK_SECRET")
    if not expected:
        logger.warning(
            "BLAND_WEBHOOK_SECRET is not set — /api/service/bland/webhook "
            "returns 503 (endpoint present but locked). Set the env to unlock."
        )
        return JSONResponse(
            status_code=503, content={"detail": "webhook not configured"}
        )
    provided = request.headers.get(WEBHOOK_SECRET_HEADER, "")
    if not provided:
        # Bland's webhook URL carries the secret as a query param; accept it
        # with the same constant-time compare so no custom header is needed.
        provided = request.query_params.get("secret", "")
    if not provided or not secrets.compare_digest(provided, expected):
        logger.warning("Bland webhook rejected: missing/invalid webhook secret "
                       "(header %s or ?secret=)", WEBHOOK_SECRET_HEADER)
        return JSONResponse(
            status_code=401, content={"detail": "invalid webhook secret"}
        )

    raw = await request.body()
    received_at = datetime.now(timezone.utc).isoformat()
    user_agent = _user_agent(request)
    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        payload = None

    if not isinstance(payload, dict):
        # Garbage (unparseable or non-object JSON): persist for debugging,
        # answer 400. Never 500 — webhook receivers swallow noise.
        await db.bland_webhook_events.insert_one(
            {
                "received_at": received_at,
                "user_agent": user_agent,
                "raw_body": raw.decode("utf-8", errors="replace"),
                "parse_error": True,
                "idempotency_key": idempotency_key,
            }
        )
        return JSONResponse(
            status_code=400,
            content={"received": True, "status": "invalid_payload"},
        )

    # Retry guard: an already-applied event under the same idempotency key
    # must not re-increment ai_call_attempts. Store the duplicate, answer 200.
    if idempotency_key:
        prior = await db.bland_webhook_events.find_one(
            {"idempotency_key": idempotency_key, "mapping.applied": True}
        )
        if prior:
            await db.bland_webhook_events.insert_one(
                {
                    "payload": payload,
                    "received_at": received_at,
                    "user_agent": user_agent,
                    "parse_error": False,
                    "idempotency_key": idempotency_key,
                    "mapping": {"applied": True, "duplicate": True},
                }
            )
            return JSONResponse(
                status_code=200,
                content={"received": True, "status": "already_applied"},
            )

    # Persist the FULL raw payload first — mapping never loses the event.
    inserted = await db.bland_webhook_events.insert_one(
        {
            "payload": payload,
            "received_at": received_at,
            "user_agent": user_agent,
            "parse_error": False,
            "idempotency_key": idempotency_key,
        }
    )
    event_id = inserted.inserted_id

    lead_ref = _extract_lead_ref(payload)
    mapped, disposition_raw = _extract_disposition(payload)

    def _unmapped(reason: str):
        return {"received": True, "status": "stored_unmapped", "reason": reason,
                "lead_id": lead_ref, "disposition_raw": disposition_raw}

    try:
        if not mapped:
            logger.info("Bland webhook stored unmapped: raw=%r lead=%r",
                        disposition_raw, lead_ref)
            await db.bland_webhook_events.update_one(
                {"_id": event_id},
                {"$set": {"mapping": {
                    "applied": False,
                    "disposition_raw": disposition_raw,
                    "lead_ref": lead_ref,
                    "reason": (
                        "no_disposition" if not disposition_raw
                        else "disposition_unmapped"
                    ),
                }}},
            )
            return JSONResponse(status_code=202, content=_unmapped(
                "no_disposition" if not disposition_raw
                else "disposition_unmapped"
            ))

        if not lead_ref:
            await db.bland_webhook_events.update_one(
                {"_id": event_id},
                {"$set": {"mapping": {
                    "applied": False,
                    "disposition_raw": disposition_raw,
                    "disposition": mapped,
                    "lead_ref": None,
                    "reason": "no_lead_ref",
                }}},
            )
            return JSONResponse(status_code=202, content=_unmapped("no_lead_ref"))

        lead = await db.leads.find_one({"lead_id": lead_ref})
        if not lead:
            await db.bland_webhook_events.update_one(
                {"_id": event_id},
                {"$set": {"mapping": {
                    "applied": False,
                    "disposition_raw": disposition_raw,
                    "disposition": mapped,
                    "lead_ref": lead_ref,
                    "reason": "lead_not_found",
                }}},
            )
            return JSONResponse(
                status_code=202,
                content=_unmapped("lead_not_found"),
            )

        stage = await _apply_call_outcome(
            lead_ref,
            disposition=mapped,
            summary=_summary_from_payload(payload),
            call_duration_sec=_call_duration_sec(payload),
            current_stage=lead.get("stage"),
            background_tasks=background_tasks,
        )
        await db.bland_webhook_events.update_one(
            {"_id": event_id},
            {"$set": {"mapping": {
                "applied": True,
                "disposition_raw": disposition_raw,
                "disposition": mapped,
                "lead_id": lead_ref,
                "stage": stage,
                "reason": "applied",
            }}},
        )
        return JSONResponse(
            status_code=200,
            content={
                "received": True,
                "lead_id": lead_ref,
                "disposition": mapped,
                "stage": stage,
            },
        )
    except Exception:  # noqa: BLE001 — receiver must never 500 on payload noise
        logger.exception("Bland webhook mapping failed (event stored as-is)")
        await db.bland_webhook_events.update_one(
            {"_id": event_id},
            {"$set": {"mapping": {"applied": False, "reason": "mapping_error"}}},
        )
        return JSONResponse(status_code=202, content=_unmapped("mapping_error"))
