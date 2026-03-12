"""Configuration models for agent and session YAML files."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, ConfigDict, Discriminator, Field, SecretStr, Tag, model_validator

from e_agents.rtc.core.settings import STTBackend, TTSBackend, TurnDetection, VADBackend
from e_agents.shared.core.settings import settings as st
from e_agents.shared.models import BaseModelYAML, LLMConfig

##### EXECUTION #####


class PreResponseConfig(BaseModelYAML):
    """Pre-response / filler message when a background task launches."""

    enabled: bool = False
    message: str | None = None
    model: str | None = None
    prompt: str = "Generate a brief acknowledgment in 5-10 words."


class OnCompleteConfig(BaseModelYAML):
    """Behavior when a background task completes."""

    notify: bool = True
    instructions: str = "Background task completed. Share the results with the user."


class CancellationConfig(BaseModelYAML):
    """Task cancellation and management tools."""

    enabled: bool = False
    auto_tools: list[Literal["cancel_task", "cancel_all_tasks", "list_tasks"]] = Field(
        default_factory=lambda: ["cancel_task", "cancel_all_tasks", "list_tasks"],
    )


class ExecutionConfig(BaseModelYAML):
    """Controls how tools are executed — blocking vs background."""

    mode: Literal["background", "blocking"] = "blocking"
    pre_response: PreResponseConfig = Field(default_factory=PreResponseConfig)
    on_complete: OnCompleteConfig = Field(default_factory=OnCompleteConfig)
    cancellation: CancellationConfig = Field(default_factory=CancellationConfig)


##### HANDOFF #####


class HandoffConfig(BaseModelYAML):
    """Per-handoff configuration."""

    target: str
    context: Literal["carry", "fresh", "truncated"] = "carry"
    truncate_items: int = 6
    description: str | None = None


##### TOOL REF #####


class ToolRef(BaseModelYAML):
    """Tool reference with optional per-tool execution override."""

    name: str
    execution: ExecutionConfig | None = None
    priority: int = 5
    cancellable: bool = True
    interruptible: bool = True


##### TASK QUEUE #####


class TaskQueueConfig(BaseModelYAML):
    """Session-level background task queue configuration."""

    enabled: bool = False
    max_concurrent: int = 3
    default_priority: int = 5


##### AGENT #####


class AgentConfig(BaseModelYAML):
    """Agent identity and behavior — loaded from config/agents/<name>.yaml."""

    name: str
    instructions: str = Field(
        default="",
        validation_alias=AliasChoices("instructions", "prompt"),
    )
    greeting: str = ""

    tools: list[str | ToolRef] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    handoffs: list[str | HandoffConfig] = Field(default_factory=list)

    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

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

    @model_validator(mode="after")
    def _normalize_refs(self) -> AgentConfig:
        """Normalize tools and handoffs to their typed forms."""
        self.tools = [ToolRef(name=t) if isinstance(t, str) else t for t in self.tools]
        self.handoffs = [HandoffConfig(target=h) if isinstance(h, str) else h for h in self.handoffs]
        return self

    @property
    def tool_names(self) -> list[str]:
        """Flat list of tool names for loader-level checks."""
        return [t.name if isinstance(t, ToolRef) else t for t in self.tools]

    @property
    def handoff_targets(self) -> list[str]:
        """Flat list of handoff target names for loader-level checks."""
        return [h.target if isinstance(h, HandoffConfig) else h for h in self.handoffs]


##### SESSION #####


class SessionConfig(BaseModelYAML):
    """Session definition — loaded from config/sessions/<name>.yaml."""

    name: str

    stt: STTBackend = STTBackend.WHISPERLIVE
    tts: TTSBackend = TTSBackend.KOKORO
    vad: VADBackend = VADBackend.SILERO
    llm: str | LLMConfig = Field(default_factory=LLMConfig)
    llm_fast: str | LLMConfig | None = None

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

    task_queue: TaskQueueConfig = Field(default_factory=TaskQueueConfig)

    dispatcher: str = ""
    agents: list[str] = Field(default_factory=list)
    state: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_session(self) -> SessionConfig:
        if self.dispatcher and self.agents and self.dispatcher not in self.agents:
            msg = f"Dispatcher '{self.dispatcher}' not in agents: {self.agents}"
            raise ValueError(msg)
        if self.llm_fast is None:
            self.llm_fast = self.llm
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
        return value.get_secret_value() if isinstance(value, SecretStr) else str(value)

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
