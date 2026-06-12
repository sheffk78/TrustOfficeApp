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
