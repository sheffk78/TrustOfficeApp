"""
Unified AI Client - OpenRouter (Gemini) primary, Claude fallback

This module provides a unified interface for AI calls in TrustOffice.
It uses OpenRouter for access to Google Gemini and other models,
with automatic fallback to Claude if OpenRouter fails.

Primary model via OpenRouter: google/gemini-2.5-flash-preview-05-20
Fallback model via OpenRouter: google/gemini-2.5-pro-preview-05-20
Emergency fallback: Claude (via claude_client)

Environment variables:
- OPENROUTER_API_KEY: Required for primary provider
- CLAUDE_API_KEY or EMERGENT_LLM_KEY: Required for fallback
- OPENROUTER_DEFAULT_MODEL (default: google/gemini-2.5-flash-preview-05-20)
- OPENROUTER_FALLBACK_MODEL (default: google/gemini-2.5-pro-preview-05-20)
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Primary: OpenRouter
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_DEFAULT_MODEL = os.environ.get(
    'OPENROUTER_DEFAULT_MODEL',
    'google/gemini-2.5-flash-preview-05-20'
)
OPENROUTER_FALLBACK_MODEL = os.environ.get(
    'OPENROUTER_FALLBACK_MODEL',
    'google/gemini-2.5-pro-preview-05-20'
)

# Fallback: Claude
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY') or os.environ.get('EMERGENT_LLM_KEY')

AI_PRIMARY_MODEL = OPENROUTER_DEFAULT_MODEL
AI_FALLBACK_MODEL = OPENROUTER_FALLBACK_MODEL
AI_ENABLED = bool(OPENROUTER_API_KEY) or bool(CLAUDE_API_KEY)

# Import clients
try:
    from openrouter_client import (
        call_openrouter_sonnet, call_openrouter_haiku,
        OpenRouterClientError, OpenRouterUnavailableError,
        ping_openrouter, list_openrouter_models
    )
    OPENROUTER_AVAILABLE = True
except ImportError as e:
    logger.error(f"OpenRouter client not available: {e}")
    OPENROUTER_AVAILABLE = False

try:
    from claude_client import (
        call_claude_sonnet, call_claude_haiku,
        ClaudeClientError
    )
    CLAUDE_AVAILABLE = True
except ImportError as e:
    logger.error(f"Claude client not available: {e}")
    CLAUDE_AVAILABLE = False


class AIClientError(Exception):
    """Unified error for AI client failures"""
    pass


def _is_garbled_response(text: str) -> bool:
    """Check if response is empty/garbled"""
    if not text or not text.strip():
        return True
    if text.strip() in ('o', '```', '<|endoftext|>', '</s>', '[DONE]', ''):
        return True
    if len(set(text.split())) < 10 and len(text) > 200:
        return True
    return False


async def _try_openrouter(
    call_fn,
    system_prompt: str,
    user_content: str,
    max_tokens: int,
    temperature: float,
    errors: list
) -> Optional[str]:
    """Try OpenRouter with fallback model if primary fails"""
    if not OPENROUTER_AVAILABLE or not OPENROUTER_API_KEY:
        errors.append("OpenRouter not configured or not available")
        return None

    try:
        # Try primary model first
        response = await call_fn(system_prompt, user_content, max_tokens, temperature)
        if not _is_garbled_response(response):
            logger.info("OpenRouter succeeded")
            return response
        else:
            logger.warning("OpenRouter returned garbled output, trying fallback")
            errors.append("OpenRouter garbled output")

            # Try fallback model
            from openrouter_client import _call_openrouter
            logger.info(f"Trying fallback model: {OPENROUTER_FALLBACK_MODEL}")
            fallback_response = _call_openrouter(
                OPENROUTER_FALLBACK_MODEL,
                system_prompt, user_content, max_tokens, temperature
            )
            if not _is_garbled_response(fallback_response):
                logger.info("OpenRouter fallback model succeeded")
                return fallback_response
            else:
                errors.append("OpenRouter fallback model also garbled")

    except OpenRouterUnavailableError as e:
        logger.warning(f"OpenRouter unavailable: {e}")
        errors.append(f"OpenRouter unavailable: {e}")
    except OpenRouterClientError as e:
        logger.warning(f"OpenRouter call failed: {e}")
        errors.append(f"OpenRouter error: {e}")
    except Exception as e:
        logger.warning(f"Unexpected OpenRouter error: {e}")
        errors.append(f"Unexpected OpenRouter error: {e}")

    return None


async def _try_claude(
    call_fn,
    system_prompt: str,
    user_content: str,
    max_tokens: int,
    temperature: float,
    errors: list
) -> Optional[str]:
    """Try Claude as final fallback"""
    if not CLAUDE_AVAILABLE or not CLAUDE_API_KEY:
        errors.append("Claude not configured or not available")
        return None

    try:
        logger.info("Falling back to Claude")
        response = await call_fn(system_prompt, user_content, max_tokens, temperature)
        logger.info("Claude succeeded")
        return response
    except ClaudeClientError as e:
        logger.error(f"Claude fallback failed: {e}")
        errors.append(f"Claude error: {e}")
    except Exception as e:
        logger.error(f"Unexpected Claude error: {e}")
        errors.append(f"Unexpected Claude error: {e}")

    return None


async def ai_sonnet(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1200,
    temperature: float = 0.2
) -> str:
    """
    Unified AI call for complex drafting tasks.
    Tries OpenRouter (Gemini) first, falls back to Claude.
    """
    errors = []

    # Try OpenRouter primary
    result = await _try_openrouter(
        call_openrouter_sonnet,
        system_prompt, user_content, max_tokens, temperature,
        errors
    )
    if result is not None:
        return result

    # Fallback to Claude
    result = await _try_claude(
        call_claude_sonnet,
        system_prompt, user_content, max_tokens, temperature,
        errors
    )
    if result is not None:
        return result

    raise AIClientError(f"All AI providers failed. Errors: {'; '.join(errors)}")


async def ai_haiku(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 400,
    temperature: float = 0.3
) -> str:
    """
    Unified AI call for quick suggestion tasks.
    Tries OpenRouter (Gemini) first, falls back to Claude.
    """
    errors = []

    result = await _try_openrouter(
        call_openrouter_haiku,
        system_prompt, user_content, max_tokens, temperature,
        errors
    )
    if result is not None:
        return result

    result = await _try_claude(
        call_claude_haiku,
        system_prompt, user_content, max_tokens, temperature,
        errors
    )
    if result is not None:
        return result

    raise AIClientError(f"All AI providers failed. Errors: {'; '.join(errors)}")


# Aliases for ai_service.py
async def ai_draft(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1200,
    temperature: float = 0.2
) -> str:
    """Alias for ai_sonnet - drafting tasks"""
    return await ai_sonnet(system_prompt, user_content, max_tokens, temperature)


async def ai_suggest(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 400,
    temperature: float = 0.3
) -> str:
    """Alias for ai_haiku - quick suggestions"""
    return await ai_haiku(system_prompt, user_content, max_tokens, temperature)


async def ai_health_check() -> dict:
    """
    Health check for all AI providers.
    Returns status dict for monitoring.
    """
    result = {
        "openrouter": {
            "available": False,
            "configured": bool(OPENROUTER_API_KEY),
            "default_model": OPENROUTER_DEFAULT_MODEL,
            "fallback_model": OPENROUTER_FALLBACK_MODEL,
            "error": None
        },
        "claude": {
            "available": False,
            "configured": bool(CLAUDE_API_KEY),
            "error": None
        },
        "primary": "openrouter"
    }

    # Check OpenRouter
    if OPENROUTER_AVAILABLE and OPENROUTER_API_KEY:
        try:
            if await ping_openrouter():
                result["openrouter"]["available"] = True
            else:
                result["openrouter"]["error"] = "Ping failed"
        except Exception as e:
            result["openrouter"]["error"] = str(e)
    elif not OPENROUTER_API_KEY:
        result["openrouter"]["error"] = "OPENROUTER_API_KEY not set"
    else:
        result["openrouter"]["error"] = "openrouter_client module not importable"

    # Check Claude
    if CLAUDE_AVAILABLE and CLAUDE_API_KEY:
        try:
            from claude_client import ping_claude
            if await ping_claude():
                result["claude"]["available"] = True
            else:
                result["claude"]["error"] = "Ping failed"
        except Exception as e:
            result["claude"]["error"] = str(e)
    elif not CLAUDE_API_KEY:
        result["claude"]["error"] = "CLAUDE_API_KEY not set"
    else:
        result["claude"]["error"] = "claude_client module not importable"

    return result
