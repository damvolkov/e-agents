"""Tests for SessionConfig YAML configuration model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from e_agents.rtc.core.settings import STTBackend, TTSBackend, TurnDetection, VADBackend
from e_agents.rtc.models.config import SessionConfig, TaskQueueConfig
from e_agents.shared.models import LLMConfig, LLMProvider

##### VALIDATION #####


_SESSION_CASES = [
    pytest.param(
        {"name": "web", "stt": "whisperlive", "tts": "kokoro", "dispatcher": "a", "agents": ["a"]},
        id="web-like",
    ),
    pytest.param(
        {"name": "voice", "stt": "whisperlive", "llm": {"provider": "openai", "model": "gpt-4o"}},
        id="voice-with-llm-object",
    ),
    pytest.param(
        {"name": "simple", "llm": "gpt-4o-mini"},
        id="llm-as-string",
    ),
]


@pytest.mark.parametrize("data", _SESSION_CASES)
async def test_session_config_validates(data: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(data)
    assert cfg.name == data["name"]


##### DEFAULTS #####


async def test_session_config_defaults() -> None:
    cfg = SessionConfig(name="defaults")
    assert cfg.stt == STTBackend.WHISPERLIVE
    assert cfg.tts == TTSBackend.KOKORO
    assert cfg.vad == VADBackend.SILERO
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.llm.provider == LLMProvider.OPENAI
    assert cfg.llm.model == "gpt-4o-mini"
    assert cfg.turn_detection is None
    assert cfg.min_endpointing_delay == 0.5
    assert cfg.max_endpointing_delay == 3.0
    assert cfg.allow_interruptions is True
    assert cfg.min_interruption_words == 0
    assert cfg.min_interruption_duration == 0.5
    assert cfg.discard_audio_if_uninterruptible is True
    assert cfg.false_interruption_timeout == 2.0
    assert cfg.resume_false_interruption is True
    assert cfg.tools == []
    assert cfg.mcp_servers == []
    assert cfg.max_tool_steps == 3
    assert cfg.min_consecutive_speech_delay == 0.0
    assert cfg.user_away_timeout == 15.0
    assert cfg.tts_text_transforms == ["filter_markdown", "filter_emoji"]
    assert cfg.use_tts_aligned_transcript is False
    assert cfg.preemptive_generation is False
    assert cfg.ivr_detection is False
    assert cfg.dispatcher == ""
    assert cfg.agents == []
    assert cfg.task_queue.enabled is False
    assert cfg.task_queue.max_concurrent == 3


##### LLM_FAST DEFAULTS #####


async def test_session_config_llm_fast_defaults_to_llm() -> None:
    cfg = SessionConfig.model_validate({"name": "t", "llm": "gpt-4o"})
    assert cfg.llm_fast == "gpt-4o"


async def test_session_config_llm_fast_explicit() -> None:
    cfg = SessionConfig.model_validate({
        "name": "t",
        "llm": {"provider": "openai", "model": "gpt-4o"},
        "llm_fast": {"provider": "openai", "model": "gpt-4o-mini"},
    })
    assert isinstance(cfg.llm_fast, LLMConfig)
    assert cfg.llm_fast.model == "gpt-4o-mini"


async def test_session_config_llm_fast_as_string() -> None:
    cfg = SessionConfig.model_validate({
        "name": "t",
        "llm": "gpt-4o",
        "llm_fast": "gpt-4o-mini",
    })
    assert cfg.llm_fast == "gpt-4o-mini"


##### TASK QUEUE #####


async def test_session_config_task_queue_defaults() -> None:
    cfg = SessionConfig(name="no_queue")
    assert cfg.task_queue.enabled is False
    assert cfg.task_queue.max_concurrent == 3
    assert cfg.task_queue.default_priority == 5


async def test_session_config_task_queue_enabled(session_with_queue_raw: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(session_with_queue_raw)
    assert cfg.task_queue.enabled is True
    assert cfg.task_queue.max_concurrent == 2


async def test_session_config_task_queue_full(session_full_raw: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(session_full_raw)
    assert cfg.task_queue.enabled is True
    assert cfg.task_queue.max_concurrent == 5
    assert cfg.task_queue.default_priority == 3


##### FULL FIELDS #####


async def test_session_config_full_fields(session_full_raw: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(session_full_raw)
    assert cfg.name == "full_session"
    assert cfg.stt == STTBackend.WHISPERLIVE
    assert cfg.tts == TTSBackend.KOKORO
    assert cfg.vad == VADBackend.SILERO
    assert cfg.turn_detection == TurnDetection.SERVER_VAD
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.llm.provider == LLMProvider.OPENAI
    assert cfg.llm.model == "gpt-4o"
    assert cfg.allow_interruptions is False
    assert cfg.min_interruption_words == 3
    assert cfg.tools == ["web_search", "calculator"]
    assert cfg.mcp_servers == ["context7"]
    assert cfg.max_tool_steps == 20
    assert cfg.preemptive_generation is True
    assert cfg.ivr_detection is True
    assert cfg.dispatcher == "main_agent"
    assert cfg.agents == ["main_agent", "helper"]


##### LLM FIELD VARIANTS #####


async def test_session_config_llm_as_string() -> None:
    cfg = SessionConfig.model_validate({"name": "str_llm", "llm": "gpt-4o"})
    assert cfg.llm == "gpt-4o"


async def test_session_config_llm_as_object() -> None:
    cfg = SessionConfig.model_validate({
        "name": "obj_llm",
        "llm": {"provider": "google", "model": "gemini-2.0-flash"},
    })
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.llm.provider == LLMProvider.GOOGLE


async def test_session_config_llm_default_object() -> None:
    cfg = SessionConfig(name="default_llm")
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.llm.provider == LLMProvider.OPENAI


##### ENUM VALIDATION #####


async def test_session_config_rejects_invalid_stt_backend() -> None:
    with pytest.raises(ValidationError):
        SessionConfig.model_validate({"name": "bad_stt", "stt": "nonexistent"})


async def test_session_config_rejects_invalid_tts_backend() -> None:
    with pytest.raises(ValidationError):
        SessionConfig.model_validate({"name": "bad_tts", "tts": "nonexistent"})


async def test_session_config_rejects_invalid_vad_backend() -> None:
    with pytest.raises(ValidationError):
        SessionConfig.model_validate({"name": "bad_vad", "vad": "nonexistent"})


##### DISPATCHER VALIDATION #####


async def test_session_config_dispatcher_valid() -> None:
    cfg = SessionConfig.model_validate({
        "name": "valid",
        "dispatcher": "agent_a",
        "agents": ["agent_a", "agent_b"],
    })
    assert cfg.dispatcher == "agent_a"


async def test_session_config_dispatcher_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        SessionConfig.model_validate({
            "name": "invalid",
            "dispatcher": "missing_agent",
            "agents": ["agent_a", "agent_b"],
        })


async def test_session_config_dispatcher_empty_no_validation() -> None:
    cfg = SessionConfig.model_validate({"name": "no_dispatch", "agents": ["a", "b"]})
    assert cfg.dispatcher == ""


async def test_session_config_dispatcher_with_empty_agents() -> None:
    cfg = SessionConfig.model_validate({"name": "no_agents", "dispatcher": "any"})
    assert cfg.dispatcher == "any"
    assert cfg.agents == []


##### YAML ROUNDTRIP #####


async def test_session_config_roundtrip_yaml(session_web_raw: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(session_web_raw)
    dumped = cfg.model_dump_yaml()
    restored = SessionConfig.model_validate_yaml(dumped)
    assert restored.name == cfg.name
    assert restored.stt == cfg.stt
    assert restored.dispatcher == cfg.dispatcher
    assert restored.agents == cfg.agents


async def test_session_config_full_roundtrip_yaml(session_full_raw: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(session_full_raw)
    dumped = cfg.model_dump_yaml()
    restored = SessionConfig.model_validate_yaml(dumped)
    assert restored.name == cfg.name
    assert restored.stt == cfg.stt
    assert restored.llm == cfg.llm
    assert restored.task_queue.enabled == cfg.task_queue.enabled


##### FROM YAML FILE #####


async def test_session_config_from_yaml_file(tmp_path: Path) -> None:
    yaml_file = tmp_path / "test_session.yaml"
    yaml_file.write_text(
        "name: file_session\n"
        "stt: whisperlive\n"
        "tts: kokoro\n"
        "llm:\n"
        "  provider: google\n"
        "  model: gemini-2.0-flash\n"
        "dispatcher: main\n"
        "agents:\n"
        "  - main\n"
        "  - helper\n",
    )
    cfg = SessionConfig.from_yaml(yaml_file)
    assert cfg.name == "file_session"
    assert cfg.stt == STTBackend.WHISPERLIVE
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.llm.provider == LLMProvider.GOOGLE
    assert cfg.dispatcher == "main"
    assert cfg.agents == ["main", "helper"]


##### FIXTURE CONFIGS #####


async def test_session_web_fixture(session_web_raw: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(session_web_raw)
    assert cfg.name == "web"
    assert cfg.stt == STTBackend.WHISPERLIVE
    assert cfg.tts == TTSBackend.KOKORO
    assert cfg.dispatcher == "assistant"
    assert len(cfg.agents) == 2


async def test_session_minimal_fixture(session_minimal_raw: dict[str, Any]) -> None:
    cfg = SessionConfig.model_validate(session_minimal_raw)
    assert cfg.name == "minimal"
    assert cfg.stt == STTBackend.WHISPERLIVE
    assert cfg.agents == []


##### VALIDATION ERRORS #####


async def test_session_config_rejects_missing_name() -> None:
    with pytest.raises(ValidationError):
        SessionConfig.model_validate({"stt": "whisperlive"})
