"""
Ollama Client - Wrapper for Ollama API calls
Replaces Claude API as the primary AI backbone for TrustOffice.
Uses Ollama's HTTP API for completions and chat.

Models:
- Primary drafting: gemma4:e4b or qwen3.5:9b (local) OR kimi-k2.6:cloud (Ollama Max)
- Quick suggestions: qwen3.5:9b or openclaw-qwen35-quick
- Fallback to Claude if Ollama is unreachable or fails

Environment:
- OLLAMA_HOST (default: http://localhost:11434) - points to the Ollama server
- OLLAMA_MODEL_DRAFT (default: qwen3.5:9b) - model for minutes drafting
- OLLAMA_MODEL_QUICK (default: qwen3.5:9b) - model for governance suggestions
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL_DRAFT = os.environ.get('OLLAMA_MODEL_DRAFT', 'qwen3.5:9b')
OLLAMA_MODEL_QUICK = os.environ.get('OLLAMA_MODEL_QUICK', 'qwen3.5:9b')

class OllamaClientError(Exception):
    """Custom exception for Ollama API errors"""
    pass


class OllamaUnavailableError(OllamaClientError):
    """Ollama server is unreachable"""
    pass


def _call_ollama_generate(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1000,
    temperature: float = 0.3
) -> str:
    """
    Call Ollama generate API (non-streaming).
    
    Args:
        model: Ollama model name
        system_prompt: System message
        user_content: User message
        max_tokens: Maximum tokens
        temperature: Temperature (0-1)
    
    Returns:
        str: The assistant's response text
    
    Raises:
        OllamaUnavailableError: If Ollama server is unreachable
        OllamaClientError: If the API call fails
    """
    url = f"{OLLAMA_HOST}/api/generate"
    
    payload = {
        "model": model,
        "prompt": f"{system_prompt}\n\n{user_content}",
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('response', '')
    
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):
            logger.error(f"Ollama server unreachable at {OLLAMA_HOST}: {e}")
            raise OllamaUnavailableError(f"Ollama server unreachable at {OLLAMA_HOST}")
        logger.error(f"Ollama API error: {e}")
        raise OllamaClientError(f"Ollama API error: {str(e)}")
    except urllib.error.HTTPError as e:
        # Read error body
        try:
            err_body = e.read().decode('utf-8')[:500]
        except:
            err_body = str(e)
        logger.error(f"Ollama HTTP error ({e.code}): {err_body}")
        raise OllamaClientError(f"Ollama HTTP error: {err_body}")
    except json.JSONDecodeError as e:
        logger.error(f"Ollama returned invalid JSON: {e}")
        raise OllamaClientError(f"Invalid JSON from Ollama: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error calling Ollama: {e}")
        raise OllamaClientError(f"Unexpected error: {str(e)}")


def _call_ollama_chat(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1000,
    temperature: float = 0.3
) -> str:
    """
    Call Ollama chat API (non-streaming).
    Preferred over generate for chat-tuned models.
    """
    url = f"{OLLAMA_HOST}/api/chat"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('message', {}).get('content', '')
    
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):
            logger.error(f"Ollama server unreachable at {OLLAMA_HOST}: {e}")
            raise OllamaUnavailableError(f"Ollama server unreachable at {OLLAMA_HOST}")
        logger.error(f"Ollama API error: {e}")
        raise OllamaClientError(f"Ollama API error: {str(e)}")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8')[:500]
        except:
            err_body = str(e)
        logger.error(f"Ollama HTTP error ({e.code}): {err_body}")
        raise OllamaClientError(f"Ollama HTTP error: {err_body}")
    except json.JSONDecodeError as e:
        logger.error(f"Ollama returned invalid JSON: {e}")
        raise OllamaClientError(f"Invalid JSON from Ollama: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error calling Ollama: {e}")
        raise OllamaClientError(f"Unexpected error: {str(e)}")


def _is_chat_tuned(model: str) -> bool:
    """Determine if model is chat-tuned (prefers /api/chat)"""
    # Most modern instruction models work better with chat API
    chat_tuned_prefixes = (
        'qwen', 'kimi', 'gemma', 'glm', 'llama', 'mistral', 'deepseek',
        'openclaw', 'openhermes', 'dolphin', 'chat'
    )
    return any(p in model.lower() for p in chat_tuned_prefixes)


async def call_ollama(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1000,
    temperature: float = 0.3
) -> str:
    """
    Unified Ollama caller - auto-selects generate vs chat API.
    
    Args:
        model: Ollama model name
        system_prompt: System message
        user_content: User message
        max_tokens: Maximum tokens
        temperature: Temperature
    
    Returns:
        str: AI response text
    
    Raises:
        OllamaUnavailableError: Server unreachable
        OllamaClientError: API call failed
    """
    if _is_chat_tuned(model):
        return _call_ollama_chat(model, system_prompt, user_content, max_tokens, temperature)
    else:
        return _call_ollama_generate(model, system_prompt, user_content, max_tokens, temperature)


async def call_ollama_sonnet(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1200,
    temperature: float = 0.2
) -> str:
    """Convenience method - maps to Claude Sonnet replacement model"""
    return await call_ollama(OLLAMA_MODEL_DRAFT, system_prompt, user_content, max_tokens, temperature)


async def call_ollama_haiku(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 400,
    temperature: float = 0.3
) -> str:
    """Convenience method - maps to Claude Haiku replacement model"""
    return await call_ollama(OLLAMA_MODEL_QUICK, system_prompt, user_content, max_tokens, temperature)


async def ping_ollama() -> bool:
    """Check if Ollama server is accessible"""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            models = [m.get('name', '') for m in data.get('models', [])]
            logger.info(f"Ollama reachable. Available models: {models}")
            return True
    except Exception as e:
        logger.error(f"Ollama ping failed: {e}")
        return False


def list_available_models() -> list:
    """Return list of available Ollama model names"""
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags", method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return [m.get('name', '') for m in data.get('models', [])]
    except Exception as e:
        logger.error(f"Cannot list Ollama models: {e}")
        return []
