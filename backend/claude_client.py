"""
Claude Client - Wrapper for Anthropic Claude API calls
Uses the official Anthropic Python SDK for Claude API integration

IMPORTANT: The Claude API key must be provided via environment variable.
CLAUDE_API_KEY is preferred, fallback to EMERGENT_LLM_KEY.
If neither is set, AI features will be unavailable.

Model names:
- claude-sonnet-4-5 (or claude-sonnet-4-5-20250929) for complex drafting
- claude-haiku-4-5 for quick suggestions
"""
import os
import logging
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None

logger = logging.getLogger(__name__)

# Get Claude API key from environment
# CLAUDE_API_KEY is preferred, fallback to EMERGENT_LLM_KEY
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY') or os.environ.get('EMERGENT_LLM_KEY')

if not CLAUDE_API_KEY:
    logger.error("Neither CLAUDE_API_KEY nor EMERGENT_LLM_KEY environment variable is set. AI features will be unavailable.")

# Model IDs
CLAUDE_SONNET = "claude-sonnet-4-5"
CLAUDE_HAIKU = "claude-haiku-4-5"


class ClaudeClientError(Exception):
    """Custom exception for Claude API errors"""
    pass


async def call_claude(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1000,
    temperature: float = 0.3,
    session_id: Optional[str] = None
) -> str:
    """
    Call Claude API using the official Anthropic Python SDK.

    Args:
        model: Claude model name (e.g., 'claude-sonnet-4-5-20250929')
        system_prompt: System message for Claude
        user_content: User message content
        max_tokens: Maximum tokens in response
        temperature: Temperature for response generation
        session_id: Optional session ID (not used with direct SDK, kept for compatibility)

    Returns:
        str: The assistant's response text

    Raises:
        ClaudeClientError: If the API call fails
    """
    if not CLAUDE_API_KEY:
        logger.error("Neither CLAUDE_API_KEY nor EMERGENT_LLM_KEY environment variable is set - cannot make AI API calls")
        raise ClaudeClientError("AI service not configured")

    if anthropic is None:
        raise ClaudeClientError("anthropic package not installed")

    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_content}
            ]
        )

        return response.content[0].text

    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        raise ClaudeClientError(f"Claude API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error calling Claude: {e}")
        raise ClaudeClientError(f"Unexpected error: {str(e)}")


async def call_claude_sonnet(system_prompt: str, user_content: str, max_tokens: int = 1000, temperature: float = 0.3) -> str:
    """Convenience method for calling Claude Sonnet"""
    return await call_claude(CLAUDE_SONNET, system_prompt, user_content, max_tokens, temperature)


async def call_claude_haiku(system_prompt: str, user_content: str, max_tokens: int = 1000, temperature: float = 0.3) -> str:
    """Convenience method for calling Claude Haiku"""
    return await call_claude(CLAUDE_HAIKU, system_prompt, user_content, max_tokens, temperature)


async def ping_claude() -> bool:
    """Check if Claude API is accessible"""
    if not CLAUDE_API_KEY:
        return False
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model=CLAUDE_HAIKU,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}]
        )
        return True
    except Exception:
        return False
