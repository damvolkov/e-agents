"""Configuration models for agent and session YAML files."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, ConfigDict, Discriminator, Field, Tag, model_validator

from e_agents.rtc.core.settings import STTBackend, TTSBackend, TurnDetection, VADBackend
from e_agents.shared.core.settings import settings as st
from e_agents.shared.models import BaseModelYAML, LLMConfig

##### AGENT #####


class AgentConfig(BaseModelYAML):
    """Agent identity and behavior — loaded from config/agents/<name>.yaml."""

    name: str
    instructions: str = Field(
        default="",
        validation_alias=AliasChoices("instructions", "prompt"),
    )
    greeting: str = ""

    tools: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    handoffs: list[str] = Field(default_factory=list)

    stt: STTBackend | None = None
    llm: str | LLMConfig | None = None
    tts: TTSBackend | None = None
    vad: VADBackend | None = None

    turn_detection: TurnDetection | None = None
    allow_interruptions: bool | None = None
    min_endpointing_delay: float | None = None
    max_endpointing_delay: float | None = None
    min_consecutive_speech_delay: float | None = None
    use_tts_aligned_transcript: bool | None = None


##### SESSION #####


class SessionConfig(BaseModelYAML):
    """Session definition — loaded from config/sessions/<name>.yaml."""

    name: str

    stt: STTBackend = STTBackend.WHISPERLIVE
    tts: TTSBackend = TTSBackend.KOKORO
    vad: VADBackend = VADBackend.SILERO
    llm: str | LLMConfig = Field(default_factory=LLMConfig)

    turn_detection: TurnDetection | None = None
    min_endpointing_delay: float = 0.5
    max_endpointing_delay: float = 3.0
    allow_interruptions: bool = True
    min_interruption_words: int = 0
    min_interruption_duration: float = 0.5
    discard_audio_if_uninterruptible: bool = True
    false_interruption_timeout: float = 2.0
    resume_false_interruption: bool = True

    tools: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    max_tool_steps: int = 3

    min_consecutive_speech_delay: float = 0.0
    user_away_timeout: float | None = 15.0

    tts_text_transforms: list[str] | None = Field(
        default_factory=lambda: ["filter_markdown", "filter_emoji"],
    )
    use_tts_aligned_transcript: bool = False

    preemptive_generation: bool = False
    ivr_detection: bool = False

    dispatcher: str = ""
    agents: list[str] = Field(default_factory=list)
    state: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_dispatcher(self) -> SessionConfig:
        if self.dispatcher and self.agents and self.dispatcher not in self.agents:
            msg = f"Dispatcher '{self.dispatcher}' not in agents: {self.agents}"
            raise ValueError(msg)
        return self


##### MCP TRANSPORT #####

_ENV_REF = re.compile(r"\$\{(\w+)\}")


def _resolve_env_refs(mapping: dict[str, str]) -> dict[str, str]:
    """Resolve ${SETTING_NAME} placeholders via getattr on Settings."""
    missing: list[str] = []

    def _replace(m: re.Match[str]) -> str:
        name = m.group(1)
        value = getattr(st, name, None)
        if not value:
            missing.append(name)
            return m.group(0)
        return str(value)

    resolved = {key: _ENV_REF.sub(_replace, val) for key, val in mapping.items()}
    if missing:
        raise ValueError(
            f"MCP env references not found in Settings: {missing}. "
            f"Add them to the MCP section in settings.py"
        )
    return resolved


class BaseTransport(BaseModelYAML):
    """Common transport config."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class StdioTransport(BaseTransport):
    """Local process via stdin/stdout."""

    transport: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _resolve_env(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("env"):
            data = {**data, "env": _resolve_env_refs(data["env"])}
        return data


class HttpTransport(BaseTransport):
    """Shared base for HTTP-based transports."""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _resolve_headers(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("headers"):
            data = {**data, "headers": _resolve_env_refs(data["headers"])}
        return data


class StreamableHttpTransport(HttpTransport):
    """Modern bidirectional HTTP streaming."""

    transport: Literal["streamable-http"] = "streamable-http"


class SseTransport(HttpTransport):
    """Legacy Server-Sent Events (deprecated)."""

    transport: Literal["sse"] = "sse"


type McpTransport = Annotated[
    Annotated[StdioTransport, Tag("stdio")]
    | Annotated[StreamableHttpTransport, Tag("streamable-http")]
    | Annotated[SseTransport, Tag("sse")],
    Discriminator("transport"),
]


class McpConfig(BaseModelYAML):
    """Top-level MCP server registry."""

    mcp_servers: dict[str, McpTransport] = Field(alias="mcpServers")
