"""
TrustOffice Security Module
Implements OWASP best practices for API security

Features:
- Rate limiting middleware
- Input sanitization utilities
- Security headers middleware
- Request validation
"""
import re
import html
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps
from typing import Optional, Callable, Dict, Any
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
import logging

logger = logging.getLogger(__name__)


# ============= RATE LIMITING =============

class RateLimitConfig:
    """Rate limit configuration per endpoint pattern"""
    
    # Default limits: requests per minute
    DEFAULT_LIMITS = {
        # Auth endpoints - stricter limits to prevent brute force
        "/api/auth/login": (5, 60),           # 5 requests per minute
        "/api/auth/register": (3, 60),         # 3 requests per minute
        "/api/auth/forgot-password": (3, 300), # 3 requests per 5 minutes
        "/api/auth/reset-password": (3, 300),  # 3 requests per 5 minutes
        
        # AI endpoints - expensive operations
        "/api/minutes-draft": (10, 60),        # 10 requests per minute
        "/api/governance-suggestions": (10, 60),
        "/api/guided-minutes/draft": (10, 60),
        
        # Chat endpoint (Trust Assistant)
        "/api/ai/chat": (30, 60),               # 30 requests per minute
        
        # File generation - resource intensive
        "/api/minutes-templates": (20, 60),    # 20 requests per minute
        "/api/trust-units/certificates": (20, 60),
        "/api/exports": (10, 60),

        # Trust Admin Kit generation — AI-powered, expensive
        "/api/trust-admin-kits/generate": (10, 3600),  # 10 kits per hour
        
        # Standard CRUD operations
        "default": (100, 60),                  # 100 requests per minute
    }


class InMemoryRateLimiter:
    """
    In-memory rate limiter using sliding window algorithm.
    For production, consider Redis-backed implementation.
    """
    
    def __init__(self):
        self._store: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_rate_limited(
        self, 
        key: str, 
        limit: int, 
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check if request should be rate limited.
        Returns (is_limited, remaining_requests)
        """
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - window_seconds
        
        async with self._lock:
            # Clean old entries
            self._store[key] = [
                ts for ts in self._store[key]
                if ts > window_start
            ]
            
            current_count = len(self._store[key])
            
            if current_count >= limit:
                return True, 0
            
            # Record this request
            self._store[key].append(now)
            return False, limit - current_count - 1
    
    async def cleanup(self):
        """Periodic cleanup of old entries"""
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - 3600  # Clean entries older than 1 hour
        
        async with self._lock:
            for key in list(self._store.keys()):
                self._store[key] = [
                    ts for ts in self._store[key]
                    if ts > cutoff
                ]
                if not self._store[key]:
                    del self._store[key]


# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for FastAPI.
    Applies different limits based on endpoint patterns.
    """
    
    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
    
    def _get_client_key(self, request: Request) -> str:
        """Get unique identifier for the client"""
        # Try to get user ID from JWT if authenticated
        user_id = getattr(request.state, 'user_id', None)
        if user_id:
            return f"user:{user_id}"
        
        # Fall back to IP address
        # Security: Use the rightmost IP in X-Forwarded-For, which is set by
        # the closest trusted proxy and harder to spoof than the leftmost IP.
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Rightmost IP is the one added by the most recent (trusted) proxy
            ip = forwarded.split(",")[-1].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        return f"ip:{ip}"
    
    def _get_limit_for_path(self, path: str) -> tuple[int, int]:
        """Get rate limit config for the given path"""
        # Check for exact match first
        if path in self.config.DEFAULT_LIMITS:
            return self.config.DEFAULT_LIMITS[path]
        
        # Check for prefix matches
        for pattern, limits in self.config.DEFAULT_LIMITS.items():
            if pattern != "default" and path.startswith(pattern):
                return limits
        
        return self.config.DEFAULT_LIMITS["default"]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks and file uploads
        # (BaseHTTPMiddleware buffers request body, which breaks file uploads)
        if request.url.path in ["/health", "/api/health"] or "/vault/upload" in request.url.path:
            return await call_next(request)
        
        # Skip for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Get client identifier and rate limit config
        client_key = self._get_client_key(request)
        limit, window = self._get_limit_for_path(request.url.path)
        
        # Create composite key for this client + endpoint
        rate_key = f"{client_key}:{request.url.path}"
        
        # Check rate limit
        is_limited, remaining = await rate_limiter.is_rate_limited(
            rate_key, limit, window
        )
        
        if is_limited:
            logger.warning(f"Rate limit exceeded for {client_key} on {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Too many requests. Please try again later.",
                    "retry_after": window
                },
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(window)
                }
            )
        
        # Process request and add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(window)
        
        return response


# ============= SSN / EIN GUARDS (NOW-phase security package) =============
#
# TrustOffice never stores Social Security numbers. User-supplied text fields
# must reject SSN-shaped input. EINs are a legitimate 9-digit identifier stored
# normalized as "XX-XXXXXXX" (see models.py EIN validators); EIN fields must
# still accept that format and bare 9-digit EINs (which models.py normalizes).
#
# LLM redaction: before any document content / document-derived text is sent to
# the third-party LLM, SSN and EIN digit patterns are stripped and replaced with
# explicit placeholders so the model can still reason about structure but never
# sees the raw identifiers.

import logging as _logging

_ssn_logger = _logging.getLogger("trustoffice.security.ssn")

# Dashed SSN: 123-45-6789 â always rejected (all fields) and redacted for LLM.
SSN_DASHED_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Dashed EIN: 12-3456789 â legitimate, accepted on EIN fields; redacted for LLM.
EIN_DASHED_RE = re.compile(r"\b\d{2}-\d{7}\b")
# Bare 9-digit sequence: ambiguous; rejected on generic fields, accepted on EIN
# fields (models.py normalizes to XX-XXXXXXX); redacted as SSN for LLM outbound.
BARE_9_RE = re.compile(r"\b\d{9}\b")

# Keys that carry EINs â these must NOT be rejected for bare 9-digit input.
EIN_FIELD_KEYS = ("ein",)


def is_ein_field(field_name: str) -> bool:
    """Return True if a field name is (or contains) an EIN field."""
    if not field_name:
        return False
    name = field_name.lower()
    return any(key in name for key in EIN_FIELD_KEYS)


def contains_ssn(value: str, allow_ein_field: bool = False) -> bool:
    """
    Detect SSN-shaped input in a single string.

    - Dashed SSN (\\d{3}-\\d{2}-\\d{4}) is ALWAYS detected.
    - Bare 9-digit sequences are detected UNLESS allow_ein_field is True
      (EIN fields legitimately accept bare 9-digit EINs that models.py
      normalizes to XX-XXXXXXX).
    - Dashed EIN (\\d{2}-\\d{7}) is NEVER treated as an SSN.
    """
    if not isinstance(value, str) or not value:
        return False
    if SSN_DASHED_RE.search(value):
        return True
    if not allow_ein_field and BARE_9_RE.search(value):
        return True
    return False


def check_ssn_or_raise(value: str, field_name: str = "") -> None:
    """
    Raise HTTPException(422) if `value` contains SSN-shaped input.

    EIN fields (detected by field name) are exempt from the bare-9-digit
    rejection so legitimate EINs still flow through. Dashed SSNs are rejected
    on every field including EIN fields.
    """
    allow_ein = is_ein_field(field_name)
    if contains_ssn(value, allow_ein_field=allow_ein):
        _ssn_logger.warning(
            "SSN-shaped input rejected on field %r", field_name or "<unnamed>"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="SSNs are not accepted â TrustOffice never stores Social Security numbers.",
        )


def scan_dict_for_ssn(data, _path: str = "") -> None:
    """
    Recursively scan a dict/list structure of user input and raise HTTP 422 on
    the first SSN-shaped string found. EIN-typed keys are exempt from the
    bare-9-digit rule. Used by the SSN intake guard middleware.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            field_name = f"{_path}.{key}" if _path else str(key)
            if isinstance(value, str):
                check_ssn_or_raise(value, field_name=field_name)
            elif isinstance(value, (dict, list)):
                scan_dict_for_ssn(value, field_name)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            scan_dict_for_ssn(item, f"{_path}[{idx}]")


def redact_pii_for_llm(text: str):
    """
    Strip SSN and EIN digit patterns from text before it is sent to the
    third-party LLM. Replacement is explicit ([REDACTED-SSN] / [REDACTED-EIN])
    so the model can still reason about document structure.

    Returns a tuple (redacted_text, counts) where counts is a dict with keys
    'ssn' and 'ein' (number of distinct matches redacted of each type).

    Order matters: dashed SSNs (3-2-4) are redacted first so the remaining
    dashed EINs (2-7) are not mis-classified. Bare 9-digit sequences are
    redacted as SSN (the more sensitive identifier).
    """
    if not isinstance(text, str) or not text:
        return text, {"ssn": 0, "ein": 0}

    redacted = text
    ssn_count = 0
    ein_count = 0

    # 1) Dashed SSN (123-45-6789)
    redacted, n_ssn_dashed = SSN_DASHED_RE.subn("[REDACTED-SSN]", redacted)
    ssn_count += n_ssn_dashed

    # 2) Dashed EIN (12-3456789) â must run after SSN so 3-2-4 never matches 2-7
    redacted, n_ein = EIN_DASHED_RE.subn("[REDACTED-EIN]", redacted)
    ein_count += n_ein

    # 3) Bare 9-digit sequences â treat as SSN (most sensitive interpretation)
    redacted, n_bare = BARE_9_RE.subn("[REDACTED-SSN]", redacted)
    ssn_count += n_bare

    return redacted, {"ssn": ssn_count, "ein": ein_count}


class SSNGuardMiddleware(BaseHTTPMiddleware):
    """
    Reject SSN-shaped input in all JSON user-supplied request bodies with HTTP 422.

    Applied globally; recursively scans string values. EIN-typed fields are
    exempt from the bare-9-digit rule (they still reject dashed SSNs). File
    upload / multipart endpoints are skipped because BaseHTTPMiddleware buffers
    the body and would break them (consistent with the other middlewares).
    """

    # Paths that should never be SSN-scanned (binary / multipart uploads).
    SKIP_PATH_FRAGMENTS = ("/vault/upload",)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in ("GET", "OPTIONS", "DELETE", "HEAD"):
            return await call_next(request)
        if any(frag in request.url.path for frag in self.SKIP_PATH_FRAGMENTS):
            return await call_next(request)
        if request.headers.get("Content-Type", "").startswith("multipart/"):
            return await call_next(request)

        # Only scan JSON bodies; read+evaluate without consuming the stream for
        # downstream handlers by re-injecting the body.
        content_type = request.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return await call_next(request)

        try:
            body_bytes = await request.body()
            if not body_bytes:
                return await call_next(request)
            import json as _json
            payload = _json.loads(body_bytes)
        except Exception:
            # Not valid JSON â let downstream validation handle it.
            return await call_next(request)

        try:
            scan_dict_for_ssn(payload)
        except HTTPException as exc:
            # Return a proper 422 response (don't re-raise â the middleware is
            # the boundary that enforces the intake ban).
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        except Exception:
            # Never let the guard itself crash a request.
            return await call_next(request)

        # Re-inject the (unchanged) body so downstream handlers still see it.
        async def _receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = _receive
        return await call_next(request)


# ============= INPUT SANITIZATION =============

class InputSanitizer:
    """
    Utility class for sanitizing user inputs.
    Implements OWASP input validation recommendations.
    """
    
    # Patterns for common dangerous inputs
    XSS_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe[^>]*>',
        r'<object[^>]*>',
        r'<embed[^>]*>',
    ]
    
    SQL_INJECTION_PATTERNS = [
        r"('\s*OR\s*'1'\s*=\s*'1)",
        r"(;\s*DROP\s+TABLE)",
        r"(;\s*DELETE\s+FROM)",
        r"(UNION\s+SELECT)",
        r"(--\s*$)",
    ]
    
    NOSQL_INJECTION_PATTERNS = [
        r'\$where',
        r'\$gt',
        r'\$lt',
        r'\$ne',
        r'\$regex',
        r'\$or',
        r'\$and',
    ]
    
    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 10000) -> str:
        """
        Sanitize a string input.
        - HTML encode special characters
        - Truncate to max length
        - Remove null bytes
        """
        if not isinstance(value, str):
            return value
        
        # Remove null bytes
        value = value.replace('\x00', '')
        
        # Truncate to max length
        value = value[:max_length]
        
        # HTML encode to prevent XSS
        value = html.escape(value)
        
        return value
    
    @classmethod
    def sanitize_html(cls, value: str) -> str:
        """
        Sanitize HTML input - strip all tags.
        Use when HTML is not expected.
        """
        if not isinstance(value, str):
            return value
        
        # Remove all HTML tags
        clean = re.sub(r'<[^>]+>', '', value)
        return html.escape(clean)
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @classmethod
    def validate_mongo_id(cls, id_value: str) -> bool:
        """Validate MongoDB ObjectId or custom ID format"""
        # Allow custom IDs like trust_xxxxx, user_xxxxx, etc.
        custom_pattern = r'^[a-z]+_[a-f0-9]{12}$'
        # Standard ObjectId (24 hex chars)
        objectid_pattern = r'^[a-f0-9]{24}$'
        
        return bool(
            re.match(custom_pattern, id_value) or 
            re.match(objectid_pattern, id_value)
        )
    
    @classmethod
    def check_nosql_injection(cls, value: str) -> bool:
        """
        Check if value contains NoSQL injection patterns.
        Returns True if suspicious patterns found.
        """
        if not isinstance(value, str):
            return False
        
        for pattern in cls.NOSQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"Potential NoSQL injection detected: {pattern}")
                return True
        
        return False
    
    @classmethod
    def sanitize_dict(cls, data: dict, max_depth: int = 10) -> dict:
        """
        Recursively sanitize all string values in a dictionary.
        """
        if max_depth <= 0:
            return data
        
        sanitized = {}
        for key, value in data.items():
            # Sanitize the key
            safe_key = cls.sanitize_string(str(key), max_length=100)
            
            if isinstance(value, str):
                sanitized[safe_key] = cls.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[safe_key] = cls.sanitize_dict(value, max_depth - 1)
            elif isinstance(value, list):
                sanitized[safe_key] = [
                    cls.sanitize_string(v) if isinstance(v, str)
                    else cls.sanitize_dict(v, max_depth - 1) if isinstance(v, dict)
                    else v
                    for v in value
                ]
            else:
                sanitized[safe_key] = value
        
        return sanitized


# ============= SECURITY HEADERS MIDDLEWARE =============

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    Implements OWASP security headers recommendations.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip security headers + body buffering for file uploads
        # BaseHTTPMiddleware buffers the request body, breaking multipart uploads
        if "/vault/upload" in request.url.path:
            return await call_next(request)
        
        response = await call_next(request)
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Enable XSS filter in browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Strict Transport Security (HTTPS only)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' https:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none';"
        )
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        
        return response


# ============= UTILITY FUNCTIONS =============

def sanitize_request_body(func: Callable) -> Callable:
    """
    Decorator to sanitize request body before processing.
    Use on route handlers that accept user input.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Find the request body in kwargs
        for key, value in kwargs.items():
            if isinstance(value, dict):
                kwargs[key] = InputSanitizer.sanitize_dict(value)
        
        return await func(*args, **kwargs)
    
    return wrapper


def validate_content_type(allowed_types: list[str]):
    """
    Decorator to validate Content-Type header.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            content_type = request.headers.get("Content-Type", "")
            
            if not any(ct in content_type for ct in allowed_types):
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Content-Type must be one of: {', '.join(allowed_types)}"
                )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    
    return decorator
