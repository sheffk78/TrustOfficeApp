"""Kit-owned Bland.ai call dispatch controller (dormant by design).

Scheduler: FastAPI startup-launched asyncio loop, fully env-gated.
  BLAND_DISPATCH_ENABLED unset/false  -> fully idle, one startup log line.
  enabled, but BLAND_API_KEY missing  -> idle, one startup log (never dials).
  enabled + key present               -> fresh poll every BLAND_FRESH_POLL_MINUTES
                                         (default 5); aged poll once per calendar
                                         day at/after 09:00 America/Denver
                                         (BLAND_AGED_DISPATCH_HOUR_MT, default 9).

Per-lead dispatch: claim via the EXISTING claim logic
(routers.leads_service.claim_lead_for_call / ClaimRequest, called directly ---
no HTTP self-call), then POST https://api.bland.ai/v1/calls (Bland Send Call
docs: https://docs.bland.ai/api-v1/post/calls-agent):
  authorization: Bearer <BLAND_API_KEY>
  agent_id      = BLAND_AGENT_ID (default fe709e36-fc79-4eab-a199-d984fbe36e52)
  phone_number  = lead phone (already normalized E.164 on the lead)
  request_data  = {lead_id, name, email, timezone: "America/Denver"}
  metadata      = {lead_id, tier}
  external_id   = lead_id            (echoed back on Bland's call-completed webhook
                                      for idempotency)
  webhook       = https://api.trustoffice.app/api/service/bland/webhook?secret=<BLAND_WEBHOOK_SECRET>

On Bland 4xx (or any non-2xx / transport failure): log + record in
bland_call_log {lead_id, tier, claim_id, ts, ok:false, error_code, http} and
SKIP that lead this cycle; failures never crash the loop.

Guardrails:
  * call window BLAND_CALL_WINDOW_MT (default "09:00-19:30" America/Denver)
    --- outside window: defer, no error, no call.
  * fresh batch max BLAND_FRESH_BATCH_MAX (default 2) per poll cycle.
  * kill switches: BLAND_DISPATCH_ENABLED (all tiers), BLAND_FRESH_ENABLED
    (default false), BLAND_AGED_ENABLED (default false --- aged calls OFF
    until Jeff flips).
  * aged tier inherits the server-side daily cap enforced by the queue's
    tier=aged selection (the concurrent tier lane adds bland_aged_budget);
    before that lane merges, the aged poll logs and skips --- no duplicate
    tier logic or cap ledger lives here.

Every dispatch decision (claim attempt + submit) writes bland_call_log
{lead_id, tier, claim_id, ts, submitted ok/fail} for the audit trail.
"""

import asyncio
import inspect
import logging
import os
from typing import Any
from datetime import datetime, time, timedelta, timezone, date
from zoneinfo import ZoneInfo
from urllib.parse import quote

import httpx
from fastapi.responses import JSONResponse

from database import db
from routers.leads_service import (
    ClaimRequest,
    _iso_utc_now,
    claim_lead_for_call,
    get_calling_queue as _queue_fn,
)

logger = logging.getLogger(__name__)

DENVER = ZoneInfo("America/Denver")
BLAND_API_URL = "https://api.bland.ai/v1/calls"
WEBHOOK_BASE = "https://api.trustoffice.app/api/service/bland/webhook"
DEFAULT_AGENT_ID = "fe709e36-fc79-4eab-a199-d984fbe36e52"
CLAIMED_BY = "bland-dispatcher"
CALL_LOG_COLLECTION = "bland_call_log"
AGED_PAGE_LIMIT = 25

# The concurrent tier lane (deleg_2f77f2ab) adds tier=fresh|aged to the queue
# plus the bland_aged_budget daily-cap ledger. It has not merged onto
# origin/main yet; probe the queue signature so this module imports cleanly
# today and opts into tier selection once the lane lands (rebase at deploy).
# This module never implements tier selection or the cap ledger itself.
_HAS_TIER = "tier" in inspect.signature(_queue_fn).parameters

# ---------------------------------------------------------------------------
# env knobs (read at request time so tests can monkeypatch them)
# ---------------------------------------------------------------------------


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def dispatch_enabled() -> bool:
    return _env("BLAND_DISPATCH_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def fresh_enabled() -> bool:
    return _env("BLAND_FRESH_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def aged_enabled() -> bool:
    return _env("BLAND_AGED_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def fresh_poll_minutes() -> int:
    try:
        return max(1, int(_env("BLAND_FRESH_POLL_MINUTES", "5")))
    except ValueError:
        return 5


def fresh_batch_max() -> int:
    try:
        return max(1, int(_env("BLAND_FRESH_BATCH_MAX", "2")))
    except ValueError:
        return 2


def aged_hour_mt() -> int:
    """BLAND_AGED_DISPATCH_HOUR_MT --- hour (America/Denver local time) after
    which the once-per-day aged poll may run. Default 09:00 Denver."""
    try:
        return max(0, min(23, int(_env("BLAND_AGED_DISPATCH_HOUR_MT", "9"))))
    except ValueError:
        return 9


def call_window_mt() -> str:
    return _env("BLAND_CALL_WINDOW_MT", "09:00-19:30")


def agent_id() -> str:
    return _env("BLAND_AGENT_ID", DEFAULT_AGENT_ID)


def api_key() -> str:
    return _env("BLAND_API_KEY", "")


def webhook_secret() -> str:
    return _env("BLAND_WEBHOOK_SECRET", "")


# ---------------------------------------------------------------------------
# Bland Send Call client (injectable session for tests)
# ---------------------------------------------------------------------------


class BlandCaller:
    """Thin wrapper around Bland's Send Call endpoint.

    `session` is injectable (tests pass a fake with an async `post`); production
    uses a lazily created httpx.AsyncClient.
    """

    def __init__(self, session: Any = None) -> None:
        self.session = session

    async def _client(self) -> Any:
        if self.session is None:
            self.session = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0)
            )
        return self.session

    async def submit(self, payload: dict):
        """Returns (ok: bool, http: int|None, error_code: str|None)."""
        client = await self._client()
        try:
            resp = await client.post(
                BLAND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:  # noqa: BLE001 --- transport failure
            return False, None, f"httpx_{type(exc).__name__}"
        if resp.status_code >= 400:
            code = None
            try:
                body = resp.json()
                code = body.get("error") or body.get("error_code")
            except Exception:  # noqa: BLE001 --- non-JSON error body
                code = None
            return False, resp.status_code, str(code) if code else f"http_{resp.status_code}"
        return True, resp.status_code, None


# ---------------------------------------------------------------------------
# time / window helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_window(raw: str):
    """BLAND_CALL_WINDOW_MT 'HH:MM-HH:MM' -> (start, end) in Denver local time."""
    try:
        start_s, end_s = raw.split("-")
        return time.fromisoformat(start_s.strip()), time.fromisoformat(end_s.strip())
    except Exception:  # noqa: BLE001 --- fall back to the default window
        return time(9, 0), time(19, 30)


def _call_window_open(now_denver: datetime) -> bool:
    start, end = _parse_window(call_window_mt())
    now = now_denver.timetz()
    return start <= now < end


# ---------------------------------------------------------------------------
# claim + audit log
# ---------------------------------------------------------------------------


def _claim_conflict(result) -> bool:
    return isinstance(result, JSONResponse) and result.status_code == 409


async def _claim_lead(lead_id: str):
    """Claim via the existing claim logic (direct function call, not HTTP).

    Returns (claimed: bool, claim_id: str|None).
    """
    try:
        result = await claim_lead_for_call(lead_id, ClaimRequest(claimed_by=CLAIMED_BY))
    except Exception:  # noqa: BLE001 --- lead vanished mid-cycle; skip it
        logger.warning("Claim failed (lead unavailable): %s", lead_id)
        return False, None
    if _claim_conflict(result):
        return False, None
    claim_id = None
    if isinstance(result, dict):
        claim_id = result.get("claimed_until")
    return True, claim_id


async def _log_call(lead_id: str, tier: str, claim_id, ok: bool, http,
                    error_code: str | None, reason: str | None = None) -> None:
    doc = {
        "lead_id": lead_id,
        "tier": tier,
        "claim_id": claim_id,
        "ts": _iso_utc_now(),
        "ok": bool(ok),
        "http": http,
        "error_code": error_code,
    }
    if reason:
        doc["reason"] = reason
    await db[CALL_LOG_COLLECTION].insert_one(doc)


# ---------------------------------------------------------------------------
# Bland payload (exact Send Call param names per docs)
# ---------------------------------------------------------------------------


def _bland_payload(lead: dict, tier: str) -> dict:
    secret = webhook_secret()
    return {
        "agent_id": agent_id(),
        "phone_number": lead.get("phone"),
        "request_data": {
            "lead_id": lead.get("lead_id"),
            "name": lead.get("name"),
            "email": lead.get("email"),
            "timezone": "America/Denver",
        },
        "metadata": {"lead_id": lead.get("lead_id"), "tier": tier},
        "external_id": lead.get("lead_id"),
        "webhook": f"{WEBHOOK_BASE}?secret={quote(secret, safe='')}",
    }


# ---------------------------------------------------------------------------
# poll cycles
# ---------------------------------------------------------------------------


async def _dispatch_lead(caller: BlandCaller, lead: dict, tier: str) -> bool:
    """Claim + submit one lead. Returns True when the call was submitted."""
    lead_id = lead.get("lead_id")
    if not lead_id:
        return False
    if not _call_window_open(_now().astimezone(DENVER)):
        return False  # defer, no error, no call_log row
    claimed, claim_id = await _claim_lead(lead_id)
    if not claimed:
        await _log_call(lead_id, tier, None, False, None, "already_claimed",
                        reason="lead already claimed by another dispatcher")
        return False
    ok, http, code = await caller.submit(_bland_payload(lead, tier))
    await _log_call(lead_id, tier, claim_id, ok, http, code)
    if not ok:
        logger.warning("Bland Send Call rejected lead %s tier=%s: http=%s code=%s",
                       lead_id, tier, http, code)
    return ok


async def _poll_fresh(caller: BlandCaller) -> dict:
    called = skipped_window = 0
    if _HAS_TIER:
        page = await _queue_fn(limit=fresh_batch_max(), offset=0, tier="fresh")  # type: ignore[call-arg]
    else:
        page = await _queue_fn(limit=fresh_batch_max(), offset=0)
    for lead in (page or {}).get("leads") or []:
        if not _call_window_open(_now().astimezone(DENVER)):
            skipped_window += 1
            continue
        if await _dispatch_lead(caller, lead, "fresh"):
            called += 1
    return {"fresh_called": called, "fresh_skipped_window": skipped_window}


_AGED_LAST_RUN: date | None = None


def _aged_due(now_denver: datetime) -> bool:
    """True once per calendar day at/after BLAND_AGED_DISPATCH_HOUR_MT Denver."""
    global _AGED_LAST_RUN
    today = now_denver.date()
    if _AGED_LAST_RUN == today:
        return False
    if now_denver.time() < time(hour=aged_hour_mt()):
        return False
    _AGED_LAST_RUN = today
    return True


async def _poll_aged(caller: BlandCaller) -> dict:
    if not _HAS_TIER:
        logger.info(
            "Aged poll skipped: queue tier= aged selection not yet merged "
            "(concurrent lane deleg_2f77f2ab + bland_aged_budget cap ledger) "
            "--- aged dispatches stay at zero"
        )
        return {"aged_called": 0, "aged_skipped_window": 0}
    # The server-side daily cap lives in the queue's tier=aged selection
    # (+ bland_aged_budget post-merge); the dispatcher dispatches what the
    # queue returns --- no cap logic duplicated here.
    called = skipped_window = 0
    if _HAS_TIER:
        page = await _queue_fn(limit=AGED_PAGE_LIMIT, offset=0, tier="aged")  # type: ignore[call-arg]
    else:
        page = await _queue_fn(limit=AGED_PAGE_LIMIT, offset=0)
    for lead in (page or {}).get("leads") or []:
        if not _call_window_open(_now().astimezone(DENVER)):
            skipped_window += 1
            continue
        if await _dispatch_lead(caller, lead, "aged"):
            called += 1
    return {"aged_called": called, "aged_skipped_window": skipped_window}


# ---------------------------------------------------------------------------
# tick / loop / lifecycle
# ---------------------------------------------------------------------------


async def tick(caller: BlandCaller | None = None) -> dict:
    """One poll cycle. Safe to call directly from tests."""
    caller = caller or BlandCaller()
    summary = {
        "fresh_called": 0, "fresh_skipped_window": 0,
        "aged_called": 0, "aged_skipped_window": 0,
    }
    if not dispatch_enabled():
        logger.debug("Dispatcher idle: BLAND_DISPATCH_ENABLED not set")
        return summary
    if not api_key():
        logger.debug("Dispatcher idle: BLAND_API_KEY not provisioned")
        return summary
    now_denver = _now().astimezone(DENVER)
    if fresh_enabled() and _call_window_open(now_denver):
        try:
            summary.update(await _poll_fresh(caller))
        except Exception:  # noqa: BLE001 --- one cycle never kills the loop
            logger.exception("Fresh poll cycle failed")
    if aged_enabled() and _aged_due(now_denver):
        try:
            summary.update(await _poll_aged(caller))
        except Exception:  # noqa: BLE001
            logger.exception("Aged poll cycle failed")
    return summary


_LOOP_TASKS: list = []


async def _loop(caller: BlandCaller):
    while True:
        try:
            await tick(caller)
        except Exception:  # noqa: BLE001
            logger.exception("Dispatch loop tick failed")
        await asyncio.sleep(fresh_poll_minutes() * 60)


async def maybe_start_dispatcher() -> bool:
    """Start the dispatch loop only when enabled AND keyed.

    Idle (logged once) otherwise --- this is the correct shipped state until
    BLAND_API_KEY is provisioned in Railway and Jeff flips the tier flags.
    """
    if _LOOP_TASKS:
        return True
    if not dispatch_enabled():
        logger.info("Bland dispatch controller idle: BLAND_DISPATCH_ENABLED not "
                    "set (dormant; no calls will be placed)")
        return False
    if not api_key():
        logger.info("Bland dispatch controller idle: BLAND_API_KEY not "
                    "provisioned (dormant until the key is set in Railway; "
                    "then flip BLAND_FRESH_ENABLED / BLAND_AGED_ENABLED)")
        return False
    caller = BlandCaller()
    task = asyncio.create_task(_loop(caller), name="bland-dispatch-loop")
    _LOOP_TASKS.append(task)
    logger.info("Bland dispatch controller started: fresh poll every %d min, "
                "batch max %d, call window %s MT",
                fresh_poll_minutes(), fresh_batch_max(), call_window_mt())
    return True


async def stop_dispatcher() -> None:
    for task in _LOOP_TASKS:
        task.cancel()
    _LOOP_TASKS.clear()
