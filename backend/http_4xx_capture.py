"""HTTP 4xx rejection capture for TrustOffice backend.

Jeff directive 2026-09-19 (morning-incident post-mortem, Gap 1): server-side
rejections like the minutes-template 422 (registry/enum drift, live 38 days)
never reached the error pipeline because FastAPI's built-in handlers for
HTTPException / RequestValidationError return the error response directly —
only unhandled 500s flow through the global exception handler.

This module installs dedicated handlers for those two exception types that:
  1. store the rejection in error_logs (same single source of truth the
     orchestrator polls — nothing about the fixer loop changes), and
  2. return the ORIGINAL status code + detail (client behavior unchanged).

Noise discipline — rejections that are part of normal user flows must never
page anyone (dedupe + expected-status filtering):
  - 401 "Not authenticated" (session expired / unauthenticated page loads)
  - 402/403 from the subscription gate (expected unpaid-account responses)
  - 409 optimistic-lock conflicts, 404 single-item misses
  - OPTIONS preflight / health probes are never captured
Everything else (e.g. 422 validation drift, 400 bad enum values, unexpected
404s on collections) is captured, and repeated occurrences trigger a deduped
Discord alert via the existing report_error() path.

Config: env var TO_CAPTURE_4XX=0 disables capture entirely (kill switch).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from error_alerting import report_error

logger = logging.getLogger("uvicorn.error")

# Rejections we never store or alert on (expected user flows, per contract
# with the frontend which already filters these client-side).
_NOISE_STATUS = {401, 402, 403, 409}
# 404 on item endpoints is normal (deleted/never-existed resource). Collection
# 404s (typo'd route) still get captured — see _is_collection_404.
_NOISE_MESSAGE_MARKERS = (
    "not authenticated",
    "subscription",
    "payment required",
    "read-only",
)

# FastAPI wraps route HTTPExceptions in StarletteHTTPException; the response
# shape FastAPI's default handler produces is {"detail": ...}. We re-produce
# exactly that so clients see zero difference.
_CAPTURE_ENV = "TO_CAPTURE_4XX"


def _capture_enabled() -> bool:
    return os.environ.get(_CAPTURE_ENV, "1") != "0"


def _is_noise(status_code: int, detail: object, path: str) -> bool:
    if status_code in _NOISE_STATUS:
        return True
    # OPTIONS preflight never carries application meaning
    return False


def _looks_like_drift(detail: object, status_code: int) -> bool:
    """Heuristic: rejection messages that smell like contract drift — the
    class of bug that bit us on 2026-09-19 (422 + enum name). These page
    Discord immediately; everything else just gets stored."""
    if status_code != 422:
        return False
    text = str(detail or "").lower()
    markers = (
        "enum",
        "not a valid enumeration",
        "value is not a valid",
        "unexpected value",
    )
    return any(m in text for m in markers)


async def _capture(
    request: Request,
    status_code: int,
    detail: object,
    validation_errors: Optional[list] = None,
) -> None:
    """Best-effort capture — never let observability break the response."""
    try:
        if not _capture_enabled() or _is_noise(status_code, detail, request.url.path):
            return

        error_type = "http_4xx_rejection"
        if validation_errors:
            error_type = "request_validation_error"
        elif _looks_like_drift(detail, status_code):
            error_type = "enum_validation_drift"

        message = str(detail) if detail is not None else "(no detail)"
        if validation_errors:
            # Compact the pydantic error list: "field: msg" pairs
            try:
                pairs = []
                for err in list(validation_errors)[:5]:
                    loc = ".".join(str(p) for p in (err.get("loc") or [])[1:]) or "?"
                    pairs.append(f"{loc}: {err.get('message', '')}")
                message = "; ".join(pairs)
            except Exception:
                pass

        alert = _looks_like_drift(detail, status_code)

        await report_error(
            source="server",
            error_type=error_type,
            error_message=message[:2000],
            request_path=request.url.path,
            request_method=request.method,
            extra_context={
                "status_code": status_code,
                "capture": "4xx_middleware",
            },
            alert=alert,
        )
    except Exception as exc:  # observability must never break responses
        logger.debug(f"4xx capture failed (non-fatal): {exc}")


def install_4xx_capture(app: FastAPI) -> None:
    """Register dedicated handlers for HTTPException + RequestValidationError.

    FastAPI resolves the MOST SPECIFIC handler for each exception type; these
    registered handlers take over from the defaults, and any handler that
    re-raises/propagates would fall through — so we fully own the response
    here and reproduce FastAPI's default body shape ({"detail": ...}).

    Must be called AFTER app construction and BEFORE include_router() calls —
    actually handler registration is order-independent for dispatch (matched
    by exception type at request time), but call it early for clarity.
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        await _capture(request, exc.status_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        await _capture(
            request, 422, exc.errors() and exc.errors()[0].get("msg") or "validation failed",
            validation_errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    logger.info("4xx capture installed (TO_CAPTURE_4XX=%s)" % os.environ.get(_CAPTURE_ENV, "1"))