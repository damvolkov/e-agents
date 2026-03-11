"""Tests for AgentConfig YAML configuration model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from e_agents.rtc.models.config import AgentConfig
from e_agents.rtc.core.settings import STTBackend, TTSBackend, TurnDetection, VADBackend
from e_agents.shared.models import LLMConfig

##### VALIDATION #####


_AGENT_CASES = [
    pytest.param(
        {"name": "assistant", "instructions": "Help the user.", "tools": ["web_search"]},
        id="assistant-with-tools",
    ),
    pytest.param(
        {"name": "scraper", "instructions": "Search the web.", "tools": ["s1", "s2", "s3", "s4"]},
        id="scraper-multi-tools",
    ),
    pytest.param(
        {"name": "router", "handoffs": ["agent_a", "agent_b"]},
        id="router-handoffs-only",
    ),
    pytest.param(
        {"name": "mcp_agent", "mcp_servers": ["context7", "filesystem"]},
        id="mcp-servers-only",
    ),
]


@pytest.mark.parametrize("data", _AGENT_CASES)
async def test_agent_config_validates(data: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(data)
    assert cfg.name == data["name"]
    assert cfg.tools == data.get("tools", [])
    assert cfg.handoffs == data.get("handoffs", [])
    assert cfg.mcp_servers == data.get("mcp_servers", [])


##### DEFAULTS #####


async def test_agent_config_defaults() -> None:
    cfg = AgentConfig(name="minimal")
    assert cfg.instructions == ""
    assert cfg.tools == []
    assert cfg.mcp_servers == []
    assert cfg.handoffs == []
    assert cfg.stt is None
    assert cfg.llm is None
    assert cfg.tts is None
    assert cfg.vad is None
    assert cfg.turn_detection is None
    assert cfg.allow_interruptions is None
    assert cfg.min_endpointing_delay is None
    assert cfg.max_endpointing_delay is None
    assert cfg.min_consecutive_speech_delay is None
    assert cfg.use_tts_aligned_transcript is None


##### FULL FIELDS #####


async def test_agent_config_full_fields(agent_full_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_full_raw)
    assert cfg.name == "full_agent"
    assert cfg.instructions == "Full agent prompt."
    assert cfg.tools == ["tool_a", "tool_b"]
    assert cfg.mcp_servers == ["context7", "filesystem"]
    assert cfg.handoffs == ["other_agent"]
    assert cfg.stt == STTBackend.WHISPERLIVE
    assert cfg.tts == TTSBackend.KOKORO
    assert cfg.vad == VADBackend.SILERO
    assert cfg.turn_detection == TurnDetection.SERVER_VAD
    assert cfg.allow_interruptions is True
    assert cfg.min_endpointing_delay == 0.3
    assert cfg.max_endpointing_delay == 2.0
    assert cfg.min_consecutive_speech_delay == 0.5
    assert cfg.use_tts_aligned_transcript is True


##### INSTRUCTIONS ALIAS #####


async def test_agent_config_instructions_alias_from_prompt() -> None:
    cfg = AgentConfig.model_validate({"name": "aliased", "prompt": "Use prompt key."})
    assert cfg.instructions == "Use prompt key."


async def test_agent_config_instructions_preferred_over_prompt() -> None:
    cfg = AgentConfig.model_validate({"name": "both", "instructions": "Wins."})
    assert cfg.instructions == "Wins."


##### LLM FIELD VARIANTS #####


async def test_agent_config_llm_as_string() -> None:
    cfg = AgentConfig.model_validate({"name": "str_llm", "llm": "gpt-4o"})
    assert cfg.llm == "gpt-4o"


async def test_agent_config_llm_as_object() -> None:
    cfg = AgentConfig.model_validate({
        "name": "obj_llm",
        "llm": {"provider": "google", "model": "gemini-2.0-flash"},
    })
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.llm.provider == "google"
    assert cfg.llm.model == "gemini-2.0-flash"


async def test_agent_config_llm_none_by_default() -> None:
    cfg = AgentConfig(name="no_llm")
    assert cfg.llm is None


##### ENUM VALIDATION #####


async def test_agent_config_rejects_invalid_stt_backend() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"name": "bad_stt", "stt": "nonexistent"})


async def test_agent_config_rejects_invalid_tts_backend() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"name": "bad_tts", "tts": "nonexistent"})


async def test_agent_config_rejects_invalid_vad_backend() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"name": "bad_vad", "vad": "nonexistent"})


async def test_agent_config_rejects_invalid_turn_detection() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"name": "bad_td", "turn_detection": "nonexistent"})


##### YAML ROUNDTRIP #####


async def test_agent_config_roundtrip_yaml(agent_assistant_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_assistant_raw)
    dumped = cfg.model_dump_yaml()
    restored = AgentConfig.model_validate_yaml(dumped)
    assert restored.name == cfg.name
    assert restored.instructions == cfg.instructions
    assert restored.tools == cfg.tools


async def test_agent_config_full_roundtrip_yaml(agent_full_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_full_raw)
    dumped = cfg.model_dump_yaml()
    restored = AgentConfig.model_validate_yaml(dumped)
    assert restored == cfg


##### FROM YAML FILE #####


async def test_agent_config_from_yaml_file(tmp_path: Path) -> None:
    yaml_file = tmp_path / "test_agent.yaml"
    yaml_file.write_text(
        "name: file_agent\n"
        "instructions: Loaded from file.\n"
        "tools:\n"
        "  - web_search\n"
        "handoffs:\n"
        "  - other\n",
    )
    cfg = AgentConfig.from_yaml(yaml_file)
    assert cfg.name == "file_agent"
    assert cfg.instructions == "Loaded from file."
    assert cfg.tools == ["web_search"]
    assert cfg.handoffs == ["other"]


async def test_agent_config_from_yaml_file_prompt_alias(tmp_path: Path) -> None:
    yaml_file = tmp_path / "prompt_agent.yaml"
    yaml_file.write_text("name: prompt_agent\nprompt: Via prompt key.\n")
    cfg = AgentConfig.from_yaml(yaml_file)
    assert cfg.instructions == "Via prompt key."


##### FIXTURE CONFIGS #####


async def test_agent_assistant_fixture(agent_assistant_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_assistant_raw)
    assert cfg.name == "assistant"
    assert "web_search" in cfg.tools
    assert "web_scraper" in cfg.handoffs


async def test_agent_web_scraper_fixture(agent_web_scraper_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_web_scraper_raw)
    assert cfg.name == "web_scraper"
    assert len(cfg.tools) == 1


##### VALIDATION ERRORS #####


async def test_agent_config_rejects_missing_name() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"instructions": "No name."})
