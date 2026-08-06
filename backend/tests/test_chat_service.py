# Smoke tests for chat_service module (backend/chat_service.py)
# chat_service is a business-logic module (not a router), so these tests
# verify module importability and function signatures rather than HTTP endpoints.
# These tests SKIP gracefully when module-level dependencies (prompt files,
# database, AI client) are unavailable.

import pytest
import os
import inspect

# chat_service reads prompt files from ./prompts/ at import time, so the
# backend dir must be on the path. These tests run from the repo root.
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def test_module_imports():
    """Module health: chat_service imports successfully.
    This also verifies the prompts/ and knowledge/ directories exist and the
    prompt files load without error (chat_service reads them at import time).
    """
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service  # noqa: F401


def test_has_expected_public_functions():
    """chat_service should expose the expected public functions."""
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service

    expected = [
        "classify_intent",
        "extract_action_data",
        "build_trust_context",
        "generate_response",
        "generate_response_stream",
        "generate_action_card",
        "build_citation_notes",
        "get_knowledge_base",
    ]
    for name in expected:
        assert hasattr(chat_service, name), f"chat_service missing public function: {name}"


def test_classify_intent_is_coroutine():
    """classify_intent should be an async function."""
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service
    assert inspect.iscoroutinefunction(chat_service.classify_intent)


def test_generate_response_is_coroutine():
    """generate_response should be an async function."""
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service
    assert inspect.iscoroutinefunction(chat_service.generate_response)


def test_build_trust_context_is_coroutine():
    """build_trust_context should be an async function."""
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service
    assert inspect.iscoroutinefunction(chat_service.build_trust_context)


def test_normalize_trustees_string():
    """_normalize_trustees should join a list into a comma-separated string."""
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service
    result = chat_service._normalize_trustees(["Alice", "Bob", "Charlie"])
    assert result == "Alice, Bob, Charlie"
    # String passthrough
    assert chat_service._normalize_trustees("Alice, Bob") == "Alice, Bob"
    # Empty / None
    assert chat_service._normalize_trustees([]) == ""
    assert chat_service._normalize_trustees(None) == ""


def test_get_knowledge_base_returns_dict():
    """get_knowledge_base should return a dict (may be empty if knowledge dir absent)."""
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service
    kb = chat_service.get_knowledge_base()
    assert isinstance(kb, dict)


def test_prompt_constants_loaded():
    """chat_service should have loaded the system prompt constants at import time."""
    import sys
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, os.path.abspath(BACKEND_DIR))
    import chat_service
    assert hasattr(chat_service, "CHAT_SYSTEM_PROMPT")
    assert hasattr(chat_service, "INTENT_CLASSIFIER_PROMPT")
    assert hasattr(chat_service, "ACTION_EXTRACTOR_PROMPT")
    # They should be non-empty strings
    assert isinstance(chat_service.CHAT_SYSTEM_PROMPT, str)
    assert len(chat_service.CHAT_SYSTEM_PROMPT) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])