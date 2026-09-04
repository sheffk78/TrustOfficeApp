"""
Authentication and rate limiting for the MCP server.

Reuses the existing X-Admin-API-Key mechanism from routers/admin_api.py.
Uses constant-time comparison (secrets.compare_digest) and an in-memory
sliding window rate limiter matching the existing Admin API pattern.
"""

import os
import secrets
import time
from collections import defaultdict
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# API Key configuration — same env var as the existing Admin API
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")

# Rate limiting — 60 req/min for MCP (slightly more conservative than Admin API's 100)
rate_limit_store: defaultdict = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX = 60     # 60 requests per minute


def validate_api_key(api_key: Optional[str]) -> Tuple[bool, str]:
    """
    Validate the admin API key using constant-time comparison.

    Returns (is_valid, error_message).
    """
    if not ADMIN_API_KEY:
        logger.error("ADMIN_API_KEY not configured for MCP server")
        return False, "Admin API not configured"

    if not api_key:
        return False, "Missing API key. Provide X-Admin-API-Key header or ADMIN_API_KEY env var."

    if not secrets.compare_digest(api_key, ADMIN_API_KEY):
        return False, "Invalid API key"

    return True, ""


def check_rate_limit(identifier: str = "mcp_session") -> Tuple[bool, int]:
    """
    Check if rate limit is exceeded.

    Returns (is_exceeded, retry_after_seconds).
    Matches the sliding-window pattern from admin_api.py.
    """
    now = time.time()
    rate_limit_store[identifier] = [
        t for t in rate_limit_store[identifier] if now - t < RATE_LIMIT_WINDOW
    ]

    if len(rate_limit_store[identifier]) >= RATE_LIMIT_MAX:
        # Calculate retry-after: time until the oldest request in the window expires
        oldest = rate_limit_store[identifier][0]
        retry_after = int(RATE_LIMIT_WINDOW - (now - oldest)) + 1
        return True, max(retry_after, 1)

    rate_limit_store[identifier].append(now)
    return False, 0


def reset_rate_limits():
    """Reset rate limit store — used in tests."""
    rate_limit_store.clear()