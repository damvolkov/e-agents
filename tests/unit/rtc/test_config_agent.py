"""Tests for AgentConfig YAML configuration model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from e_agents.rtc.core.settings import STTBackend, TTSBackend, TurnDetection, VADBackend
from e_agents.rtc.models.config import (
    AgentConfig,
    CancellationConfig,
    ExecutionConfig,
    HandoffConfig,
    OnCompleteConfig,
    PreResponseConfig,
    ToolRef,
)
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
    assert cfg.tool_names == data.get("tools", [])
    assert cfg.handoff_targets == data.get("handoffs", [])
    assert cfg.mcp_servers == data.get("mcp_servers", [])


##### NORMALIZATION #####


async def test_agent_config_normalizes_tools_to_tool_ref() -> None:
    cfg = AgentConfig.model_validate({"name": "n", "tools": ["web_search", "calc"]})
    assert all(isinstance(t, ToolRef) for t in cfg.tools)
    assert cfg.tools[0].name == "web_search"
    assert cfg.tools[1].name == "calc"


async def test_agent_config_normalizes_handoffs_to_handoff_config() -> None:
    cfg = AgentConfig.model_validate({"name": "n", "handoffs": ["agent_a"]})
    assert all(isinstance(h, HandoffConfig) for h in cfg.handoffs)
    assert cfg.handoffs[0].target == "agent_a"
    assert cfg.handoffs[0].context == "carry"


async def test_agent_config_preserves_detailed_tool_ref() -> None:
    cfg = AgentConfig.model_validate({
        "name": "n",
        "tools": [{"name": "search", "priority": 2, "cancellable": False}],
    })
    ref = cfg.tools[0]
    assert isinstance(ref, ToolRef)
    assert ref.name == "search"
    assert ref.priority == 2
    assert ref.cancellable is False


async def test_agent_config_preserves_detailed_handoff_config() -> None:
    cfg = AgentConfig.model_validate({
        "name": "n",
        "handoffs": [{"target": "helper", "context": "fresh", "description": "Go to helper."}],
    })
    h = cfg.handoffs[0]
    assert isinstance(h, HandoffConfig)
    assert h.target == "helper"
    assert h.context == "fresh"
    assert h.description == "Go to helper."


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
    assert cfg.execution.mode == "blocking"
    assert cfg.execution.cancellation.enabled is False


##### FULL FIELDS #####


async def test_agent_config_full_fields(agent_full_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_full_raw)
    assert cfg.name == "full_agent"
    assert cfg.instructions == "Full agent prompt."
    assert cfg.tool_names == ["tool_a", "tool_b"]
    assert cfg.mcp_servers == ["context7", "filesystem"]
    assert cfg.handoff_targets == ["other_agent"]
    assert cfg.stt == STTBackend.WHISPERLIVE
    assert cfg.tts == TTSBackend.KOKORO
    assert cfg.vad == VADBackend.SILERO
    assert cfg.turn_detection == TurnDetection.SERVER_VAD
    assert cfg.allow_interruptions is True
    assert cfg.min_endpointing_delay == 0.3
    assert cfg.max_endpointing_delay == 2.0
    assert cfg.min_consecutive_speech_delay == 0.5
    assert cfg.use_tts_aligned_transcript is True


##### EXECUTION CONFIG #####


async def test_agent_config_background_execution(agent_background_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_background_raw)
    assert cfg.execution.mode == "background"
    assert cfg.execution.cancellation.enabled is True
    assert "cancel_task" in cfg.execution.cancellation.auto_tools
    assert "list_tasks" in cfg.execution.cancellation.auto_tools

    bg_tool = cfg.tools[0]
    assert isinstance(bg_tool, ToolRef)
    assert bg_tool.execution is not None
    assert bg_tool.execution.mode == "background"
    assert bg_tool.execution.pre_response.enabled is True
    assert bg_tool.execution.pre_response.message == "Searching..."
    assert bg_tool.priority == 3

    plain_tool = cfg.tools[1]
    assert isinstance(plain_tool, ToolRef)
    assert plain_tool.execution is None
    assert plain_tool.priority == 5


##### HANDOFF CONFIG #####


async def test_agent_config_mixed_handoffs(agent_handoff_config_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_handoff_config_raw)
    assert len(cfg.handoffs) == 3
    assert cfg.handoffs[0].target == "specialist_a"
    assert cfg.handoffs[0].context == "truncated"
    assert cfg.handoffs[0].truncate_items == 4
    assert cfg.handoffs[1].target == "specialist_b"
    assert cfg.handoffs[1].context == "fresh"
    assert cfg.handoffs[1].description == "Send to B for analysis."
    assert cfg.handoffs[2].target == "specialist_c"
    assert cfg.handoffs[2].context == "carry"


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
    assert restored.tool_names == cfg.tool_names


async def test_agent_config_full_roundtrip_yaml(agent_full_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_full_raw)
    dumped = cfg.model_dump_yaml()
    restored = AgentConfig.model_validate_yaml(dumped)
    assert restored.name == cfg.name
    assert restored.tool_names == cfg.tool_names
    assert restored.handoff_targets == cfg.handoff_targets
    assert restored.stt == cfg.stt


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
    assert cfg.tool_names == ["web_search"]
    assert cfg.handoff_targets == ["other"]


async def test_agent_config_from_yaml_file_prompt_alias(tmp_path: Path) -> None:
    yaml_file = tmp_path / "prompt_agent.yaml"
    yaml_file.write_text("name: prompt_agent\nprompt: Via prompt key.\n")
    cfg = AgentConfig.from_yaml(yaml_file)
    assert cfg.instructions == "Via prompt key."


##### FIXTURE CONFIGS #####


async def test_agent_assistant_fixture(agent_assistant_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_assistant_raw)
    assert cfg.name == "assistant"
    assert "web_search" in cfg.tool_names
    assert "scraper" in cfg.handoff_targets


async def test_agent_scraper_fixture(agent_scraper_raw: dict[str, Any]) -> None:
    cfg = AgentConfig.model_validate(agent_scraper_raw)
    assert cfg.name == "scraper"
    assert len(cfg.tools) == 1


##### SUB-MODEL DEFAULTS #####


async def test_pre_response_config_defaults() -> None:
    cfg = PreResponseConfig()
    assert cfg.enabled is False
    assert cfg.message is None
    assert cfg.model is None


async def test_on_complete_config_defaults() -> None:
    cfg = OnCompleteConfig()
    assert cfg.notify is True
    assert "completed" in cfg.instructions.lower()


async def test_cancellation_config_defaults() -> None:
    cfg = CancellationConfig()
    assert cfg.enabled is False
    assert len(cfg.auto_tools) == 3


async def test_execution_config_defaults() -> None:
    cfg = ExecutionConfig()
    assert cfg.mode == "blocking"
    assert cfg.pre_response.enabled is False
    assert cfg.cancellation.enabled is False


async def test_tool_ref_defaults() -> None:
    ref = ToolRef(name="test_tool")
    assert ref.priority == 5
    assert ref.cancellable is True
    assert ref.interruptible is True
    assert ref.execution is None


async def test_handoff_config_defaults() -> None:
    h = HandoffConfig(target="other")
    assert h.context == "carry"
    assert h.truncate_items == 6
    assert h.description is None


##### VALIDATION ERRORS #####


async def test_agent_config_rejects_missing_name() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"instructions": "No name."})
