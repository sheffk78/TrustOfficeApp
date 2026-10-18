#!/usr/bin/env python3
"""
AI budget enforcement at the service boundary (2026-10-17 deep-audit C1).

Every AI-spending path routes through these wrappers:
  - ai_service.draft_minutes_from_structured_input  (routers/ai.py, routers/minutes.py, routers/guided_minutes.py)
  - chat LLM response generation                    (routers/chat.py /chat + /chat/stream)

Before this module, caps lived ONLY in routers/ai.py; the alternate paths
(minutes.py, guided_minutes.py, chat) inherited no hourly/daily/monthly cap
and no usage recording — a subscriber could bypass the 10/hour + 30/day caps
by choosing a different door, and chat spend was never tracked at all.

Enforcement order per call (mirrors routers/ai.py semantics):
  1. hourly rate limit (429)
  2. daily cap (429)
  3. monthly budget kill-switch (503)
  4. usage recording after success

The wrappers import the cap helpers from routers.ai (single source of truth,
no duplicated constants) with a lazy import to avoid router-package import
cycles at module load.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CHAT_ENDPOINT = "chat"


async def enforce_ai_budget(user_id: str, endpoint: str):
    """
    Hourly + daily + monthly budget gates for ANY AI-spending call.
    Raises the same HTTPException shapes routers/ai.py produces (429/503).
    Import-lazy: routers.ai imports ai_service, so we cannot import it at
    module level here.
    """
    from routers.ai import check_rate_limit, check_daily_cap, check_monthly_budget

    await check_rate_limit(user_id, endpoint)
    await check_daily_cap(user_id, endpoint)
    await check_monthly_budget()


async def record_ai_usage(user_id: str, endpoint: str):
    """Record one successful AI call against daily usage + cost tracking."""
    from routers.ai import record_daily_usage, COST_PER_CALL_CENTS

    cost = COST_PER_CALL_CENTS.get(endpoint, 0.5)
    await record_daily_usage(user_id, endpoint, cost)


async def guard_chat_ai_call(user_id: str) -> bool:
    """
    Chat path: 120 calls/hour + 200/day cap + monthly budget.
    Distinct endpoint key so chat pacing is independent of minutes-draft caps.
    """
    await enforce_ai_budget(user_id, _CHAT_ENDPOINT)
    return True