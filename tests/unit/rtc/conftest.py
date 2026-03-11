"""Reusable fixtures for YAML configuration model tests."""

from __future__ import annotations

from typing import Any

import pytest

##### AGENT #####


@pytest.fixture
def agent_assistant_raw() -> dict[str, Any]:
    """Config matching config/agents/assistant.yaml."""
    return {
        "name": "assistant",
        "instructions": "You are a helpful personal assistant.",
        "tools": ["web_search"],
        "handoffs": ["web_scraper"],
    }


@pytest.fixture
def agent_web_scraper_raw() -> dict[str, Any]:
    """Config matching config/agents/web_scraper.yaml."""
    return {
        "name": "web_scraper",
        "instructions": "You are a web search specialist.",
        "tools": ["web_search"],
    }


@pytest.fixture
def agent_full_raw() -> dict[str, Any]:
    """Agent with every optional field populated."""
    return {
        "name": "full_agent",
        "instructions": "Full agent prompt.",
        "tools": ["tool_a", "tool_b"],
        "mcp_servers": ["context7", "filesystem"],
        "handoffs": ["other_agent"],
        "stt": "whisperlive",
        "llm": {"provider": "google", "model": "gemini-2.0-flash"},
        "tts": "kokoro",
        "vad": "silero",
        "turn_detection": "server_vad",
        "allow_interruptions": True,
        "min_endpointing_delay": 0.3,
        "max_endpointing_delay": 2.0,
        "min_consecutive_speech_delay": 0.5,
        "use_tts_aligned_transcript": True,
    }


##### SESSION #####


@pytest.fixture
def session_web_raw() -> dict[str, Any]:
    """Config matching config/sessions/web.yaml."""
    return {
        "name": "web",
        "stt": "whisperlive",
        "tts": "kokoro",
        "vad": "silero",
        "llm": {"provider": "google", "model": "gemini-2.0-flash"},
        "max_tool_steps": 10,
        "allow_interruptions": True,
        "min_endpointing_delay": 0.5,
        "max_endpointing_delay": 3.0,
        "dispatcher": "assistant",
        "agents": ["assistant", "web_scraper"],
    }


@pytest.fixture
def session_minimal_raw() -> dict[str, Any]:
    """Minimal valid session config."""
    return {"name": "minimal"}


@pytest.fixture
def session_full_raw() -> dict[str, Any]:
    """Session with every optional field populated."""
    return {
        "name": "full_session",
        "stt": "whisperlive",
        "tts": "kokoro",
        "vad": "silero",
        "llm": {"provider": "openai", "model": "gpt-4o"},
        "turn_detection": "server_vad",
        "min_endpointing_delay": 0.3,
        "max_endpointing_delay": 5.0,
        "allow_interruptions": False,
        "min_interruption_words": 3,
        "min_interruption_duration": 1.0,
        "discard_audio_if_uninterruptible": False,
        "false_interruption_timeout": 3.0,
        "resume_false_interruption": False,
        "tools": ["web_search", "calculator"],
        "mcp_servers": ["context7"],
        "max_tool_steps": 20,
        "min_consecutive_speech_delay": 1.0,
        "user_away_timeout": 30.0,
        "tts_text_transforms": ["filter_markdown"],
        "use_tts_aligned_transcript": True,
        "preemptive_generation": True,
        "ivr_detection": True,
        "dispatcher": "main_agent",
        "agents": ["main_agent", "helper"],
    }


##### MCP TRANSPORT #####


@pytest.fixture
def stdio_servers() -> dict[str, dict[str, Any]]:
    """Real-world stdio MCP server configs."""
    return {
        "context7": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp"],
            "env": {"CONTEXT7_API_KEY": "ctx7sk-test-key"},
        },
        "filesystem": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        },
        "docker": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-docker"],
        },
        "memory": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
        },
        "postgres": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres"],
            "env": {"PG_CONNECTION_STRING": "postgresql://user:pass@localhost:5432/db"},
        },
        "playwright": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-playwright"],
        },
        "git": {
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-server-git", "--repository", "/tmp/repo"],
        },
    }


@pytest.fixture
def sse_servers() -> dict[str, dict[str, Any]]:
    """Real-world SSE MCP server configs."""
    return {
        "n8n-local": {
            "transport": "sse",
            "url": "http://localhost:5678/mcp/sse",
            "headers": {"Authorization": "Bearer test-token"},
        },
        "custom-sse": {
            "transport": "sse",
            "url": "http://mcp.internal:3001/sse",
        },
    }


@pytest.fixture
def streamable_http_servers() -> dict[str, dict[str, Any]]:
    """Real-world streamable-http MCP server configs."""
    return {
        "cloud-api": {
            "transport": "streamable-http",
            "url": "https://api.example.com/mcp",
            "headers": {"Authorization": "Bearer api-key", "X-Project-Id": "proj-1"},
        },
        "internal-service": {
            "transport": "streamable-http",
            "url": "http://localhost:8080/mcp/stream",
        },
    }


@pytest.fixture
def all_mcp_servers(
    stdio_servers: dict[str, dict[str, Any]],
    sse_servers: dict[str, dict[str, Any]],
    streamable_http_servers: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Combined registry of all MCP server types."""
    return {**stdio_servers, **sse_servers, **streamable_http_servers}
