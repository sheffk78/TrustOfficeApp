"""
Claude Client - Wrapper for Anthropic Claude API calls
Uses emergentintegrations library for Claude API integration
"""
import os
import logging
from typing import Optional
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

# Get Claude API key from environment
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY') or os.environ.get('EMERGENT_LLM_KEY')

# Model mappings
CLAUDE_SONNET = "claude-sonnet-4-5-20250929"
CLAUDE_HAIKU = "claude-3-5-haiku-20241022"


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
    Call Claude API using emergentintegrations library.
    
    Args:
        model: Claude model name (e.g., 'claude-sonnet-4-5-20250929')
        system_prompt: System message for Claude
        user_content: User message content
        max_tokens: Maximum tokens in response
        temperature: Temperature for response generation
        session_id: Optional session ID for conversation tracking
    
    Returns:
        str: The assistant's response text
    
    Raises:
        ClaudeClientError: If the API call fails
    """
    if not CLAUDE_API_KEY:
        logger.error("Claude API key not configured")
        raise ClaudeClientError("AI service not configured. Please contact support.")
    
    try:
        # Generate a unique session ID if not provided
        if not session_id:
            import uuid
            session_id = f"trustoffice_{uuid.uuid4().hex[:12]}"
        
        # Initialize the chat with Claude
        chat = LlmChat(
            api_key=CLAUDE_API_KEY,
            session_id=session_id,
            system_message=system_prompt
        ).with_model("anthropic", model)
        
        # Create user message
        user_message = UserMessage(text=user_content)
        
        # Send message and get response
        response = await chat.send_message(user_message)
        
        if not response:
            raise ClaudeClientError("Empty response from AI service")
        
        logger.info(f"Claude API call successful - model: {model}, tokens: ~{len(response.split())}")
        return response
        
    except ClaudeClientError:
        raise
    except Exception as e:
        logger.error(f"Claude API error: {str(e)}")
        raise ClaudeClientError("AI service temporarily unavailable. Please try again later.")


async def call_claude_sonnet(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 1000,
    temperature: float = 0.2
) -> str:
    """
    Convenience function to call Claude Sonnet model.
    Best for complex reasoning, drafting, and detailed outputs.
    """
    return await call_claude(
        model=CLAUDE_SONNET,
        system_prompt=system_prompt,
        user_content=user_content,
        max_tokens=max_tokens,
        temperature=temperature
    )


async def call_claude_haiku(
    system_prompt: str,
    user_content: str,
    max_tokens: int = 500,
    temperature: float = 0.3
) -> str:
    """
    Convenience function to call Claude Haiku model.
    Best for quick, efficient responses and simpler tasks.
    """
    return await call_claude(
        model=CLAUDE_HAIKU,
        system_prompt=system_prompt,
        user_content=user_content,
        max_tokens=max_tokens,
        temperature=temperature
    )
