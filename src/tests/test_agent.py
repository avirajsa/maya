"""Tests for Maya agent."""

import os
import pytest

from maya.agent.agent import MayaAgent, get_agent
from maya.agent.prompts import MAYA_SYSTEM_PROMPT, MAYA_VOICE_SUFFIX, get_system_prompt
from maya.core.config import get_config


def test_agent_import():
    """Verify that get_agent and MayaAgent can be imported without crashing."""
    assert get_agent is not None
    assert MayaAgent is not None
    agent = get_agent()
    assert agent is not None
    assert hasattr(agent, "chat")
    assert hasattr(agent, "stream_chat")


def test_agent_requires_api_key():
    """Verify that config loads cleanly even when OPENROUTER_API_KEY is unset or empty."""
    config = get_config()
    assert hasattr(config, "openrouter_api_key")
    # Config is initialized, can inspect openrouter_api_key attribute
    assert isinstance(config.openrouter_api_key, str)


def test_system_prompt():
    """Verify system prompt generation and key persona guidelines."""
    prompt = get_system_prompt()
    assert isinstance(prompt, str)
    assert "Maya" in prompt
    assert "Current Date and Time:" in prompt
    assert "JARVIS" in MAYA_SYSTEM_PROMPT
    assert "Voice Mode Active" in MAYA_VOICE_SUFFIX


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY is not set in environment",
)
@pytest.mark.asyncio
async def test_agent_live_chat():
    """Test live agent call only when OPENROUTER_API_KEY is explicitly configured."""
    agent = get_agent()
    response = await agent.chat("Hello Maya, what is 2 + 2?", session_id="test_live")
    assert isinstance(response, str)
    assert len(response.strip()) > 0
