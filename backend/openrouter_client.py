"""
OpenRouter Client - Wrapper for OpenRouter API calls
Uses Google Gemini via OpenRouter as the primary AI backbone for TrustOffice.

Models available via OpenRouter:
- google/gemini-2.5-flash   (recommended primary)
- google/gemini-2.5-pro     (complex tasks)
- moonshotai/kimi-k2.6      (coding-intensive)
- z-ai/glm-5.1             (long-context)

All models use the same OpenAI-compatible /v1/chat/completions endpoint.

Environment:
- OPENROUTER_API_KEY (required): Your OpenRouter API key
- OPENROUTER_DEFAULT_MODEL (default: google/gemini-2.5-flash)
- OPENROUTER_FALLBACK_MODEL (default: google/gemini-2.5-pro)
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_DEFAULT_MODEL = os.environ.get(
    'OPENROUTER_DEFAULT_MODEL',
    'google/gemini-2.5-flash'
)
OPENROUTER_FALLBACK_MODEL = os.environ.get(
    'OPENROUTER_FALLBACK_MODEL',
    'google/gemini-2.5-pro'
)
OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1/chat/completions'
OPENROUTER_REFERRER = 'https://trustoffice.app'


class OpenRouterClientError(Exception):
    """Custom exception for OpenRouter API errors"""
    pass


class OpenRouterUnavailableError(OpenRouterClientError):
    """OpenRouter is unreachable or rate-limited"""
    pass


def _call_openrouter(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1000,
    temperature: float = 0.3
) -> str:
    """
    Call OpenRouter chat completions API (non-streaming).

    Args:
        model: Model ID (e.g., 'google/gemini-2.5-flash-preview-05-20')
        system_prompt: System message
        user_content: User message
        max_tokens: Maximum tokens in response
        temperature: Temperature (0-1)

    Returns:
        str: The assistant's response text

    Raises:
        OpenRouterUnavailableError: If OpenRouter is unreachable or returns 5xx
        OpenRouterClientError: For 4xx errors or malformed responses
    """
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set - cannot make AI API calls")
        raise OpenRouterClientError("OPENROUTER_API_KEY not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    data = json.dumps(payload).encode('utf-8')

    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': OPENROUTER_REFERRER,
        'X-Title': 'TrustOffice',
        'Accept': 'application/json',
    }

    req = urllib.request.Request(
        OPENROUTER_BASE_URL,
        data=data,
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_data = json.loads(resp.read().decode('utf-8'))

        if 'error' in response_data:
            err = response_data['error']
            msg = err.get('message', str(err))
            code = err.get('code', '')
            logger.error(f"OpenRouter API error: {code} — {msg}")
            raise OpenRouterClientError(f"OpenRouter error: {msg}")

        choices = response_data.get('choices', [])
        if not choices:
            raise OpenRouterClientError("OpenRouter returned no choices")

        content = choices[0].get('message', {}).get('content', '')
        if not content:
            raise OpenRouterClientError("OpenRouter returned empty content")

        return content.strip()

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error(f"OpenRouter HTTP error {e.code}: {body}")
        if e.code >= 500:
            raise OpenRouterUnavailableError(f"OpenRouter server error: {e.code}")
        raise OpenRouterClientError(f"OpenRouter error {e.code}: {body}")

    except urllib.error.URLError as e:
        logger.error(f"OpenRouter connection error: {e.reason}")
        raise OpenRouterUnavailableError(f"Cannot reach OpenRouter: {e.reason}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenRouter response: {e}")
        raise OpenRouterClientError("Invalid JSON from OpenRouter")

    except Exception as e:
        logger.error(f"Unexpected OpenRouter error: {e}")
        raise OpenRouterClientError(f"Unexpected error: {str(e)}")


def _call_openrouter_stream(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
):
    """
    Call OpenRouter chat completions API with streaming enabled.
    Yields content deltas (text chunks) as they arrive.

    Args:
        model: Model ID (e.g., 'google/gemini-2.5-flash')
        system_prompt: System message
        user_content: User message
        max_tokens: Maximum tokens in response
        temperature: Temperature (0-1)

    Yields:
        str: Content text chunks as they arrive from the API

    Raises:
        OpenRouterUnavailableError: If OpenRouter is unreachable or returns 5xx
        OpenRouterClientError: For 4xx errors or malformed responses
    """
    if not OPENROUTER_API_KEY:
        raise OpenRouterClientError("OPENROUTER_API_KEY not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    data = json.dumps(payload).encode('utf-8')

    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': OPENROUTER_REFERRER,
        'X-Title': 'TrustOffice',
        'Accept': 'text/event-stream',
    }

    req = urllib.request.Request(
        OPENROUTER_BASE_URL,
        data=data,
        headers=headers,
        method='POST'
    )

    try:
        resp = urllib.request.urlopen(req, timeout=60)

        for line in iter(resp.readline, b''):
            if not line:
                continue
            line_str = line.decode('utf-8', errors='ignore').strip()

            if line_str.startswith('data: '):
                data_str = line_str[6:]
                if data_str == '[DONE]':
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get('choices', [])
                    if choices:
                        delta = choices[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                except json.JSONDecodeError:
                    # Skip malformed chunks
                    continue
        resp.close()

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        logger.error(f"OpenRouter streaming HTTP error {e.code}: {body}")
        if e.code >= 500:
            raise OpenRouterUnavailableError(f"OpenRouter server error: {e.code}")
        raise OpenRouterClientError(f"OpenRouter error {e.code}: {body}")

    except urllib.error.URLError as e:
        logger.error(f"OpenRouter streaming connection error: {e.reason}")
        raise OpenRouterUnavailableError(f"Cannot reach OpenRouter: {e.reason}")

    except Exception as e:
        logger.error(f"Unexpected OpenRouter streaming error: {e}")
        raise OpenRouterClientError(f"Unexpected error: {str(e)}")


def _fallback_call(
    system_prompt: str,
    user_content: str,
    max_tokens: int,
    temperature: float
) -> str:
    """Try fallback model if primary fails"""
    if OPENROUTER_FALLBACK_MODEL == OPENROUTER_DEFAULT_MODEL:
        raise OpenRouterClientError("Primary and fallback models are the same")

    logger.info(f"Falling back to OpenRouter model: {OPENROUTER_FALLBACK_MODEL}")
    return _call_openrouter(
        model=OPENROUTER_FALLBACK_MODEL,
        system_prompt=system_prompt,
        user_content=user_content,
        max_tokens=max_tokens,
        temperature=temperature
    )


async def call_openrouter_sonnet_stream(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
):
    """
    Streaming version of call_openrouter_sonnet.
    Yields content text chunks as they arrive.
    Falls back to fallback model if primary is unavailable.

    Uses iterate_in_threadpool to run the sync urllib generator in a thread,
    preventing event loop blocking during the streaming duration.
    """
    from starlette.concurrency import iterate_in_threadpool

    try:
        sync_gen = _call_openrouter_stream(
            model=OPENROUTER_DEFAULT_MODEL,
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        async for chunk in iterate_in_threadpool(sync_gen):
            yield chunk
    except OpenRouterUnavailableError:
        logger.info("Primary model unavailable for streaming, trying fallback")
        sync_gen = _call_openrouter_stream(
            model=OPENROUTER_FALLBACK_MODEL,
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        async for chunk in iterate_in_threadpool(sync_gen):
            yield chunk


async def call_openrouter_sonnet(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1200,
    temperature: float = 0.2
) -> str:
    """Convenience wrapper for complex drafting tasks (Sonnet-equivalent)."""
    try:
        return _call_openrouter(
            model=OPENROUTER_DEFAULT_MODEL,
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=max_tokens,
            temperature=temperature
        )
    except OpenRouterUnavailableError:
        return _fallback_call(system_prompt, user_content, max_tokens, temperature)


async def call_openrouter_haiku(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 400,
    temperature: float = 0.3
) -> str:
    """Convenience wrapper for quick suggestion tasks (Haiku-equivalent)."""
    try:
        return _call_openrouter(
            model=OPENROUTER_DEFAULT_MODEL,
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=max_tokens,
            temperature=temperature
        )
    except OpenRouterUnavailableError:
        return _fallback_call(system_prompt, user_content, max_tokens, temperature)


async def ping_openrouter() -> bool:
    """Quick health check for OpenRouter"""
    if not OPENROUTER_API_KEY:
        return False
    try:
        _call_openrouter(
            model=OPENROUTER_DEFAULT_MODEL,
            system_prompt="You are a helpful assistant.",
            user_content="Say 'pong' only.",
            max_tokens=5,
            temperature=0
        )
        return True
    except Exception as e:
        logger.warning(f"OpenRouter ping failed: {e}")
        return False


async def list_openrouter_models() -> list:
    """List available models from OpenRouter"""
    if not OPENROUTER_API_KEY:
        return []
    try:
        req = urllib.request.Request(
            'https://openrouter.ai/api/v1/models',
            headers={
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'Accept': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return [m.get('id') for m in data.get('data', [])]
    except Exception as e:
        logger.warning(f"Failed to list OpenRouter models: {e}")
        return []
