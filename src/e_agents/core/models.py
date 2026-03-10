"""Configuration models for agents, sessions, and tools.

Three-layer config architecture:

1. ``AgentConfig``      — loaded from ``config/agents/<name>.yaml``
                          (identity: prompt, tools, greeting, LLM overrides, behavior)
2. ``SessionAgentRef``  — inline in ``config/sessions/<name>.yaml``
                          (topology: role, handoffs, return_to)
3. ``AgentDefinition``  — merged at runtime by the loader
                          (AgentConfig + SessionAgentRef → ready for factory)

Also contains ``SessionState`` — the shared session dataclass used
across orchestration and factory without circular imports.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Coroutine
from typing import Any, Literal

from livekit.agents import Agent
from pydantic import Field, model_validator

from e_agents.shared.base import BaseModelYAML
from e_agents.tasks.executor import TaskExecutor
from e_agents.tasks.models import BackgroundTask
from e_agents.tasks.registry import TaskRegistry

type AgentRole = Literal["outer", "inner"]
type TurnDetectionMode = Literal["stt", "vad", "realtime_llm", "manual"]
type TaskCallback = Callable[[BackgroundTask[Any]], Coroutine[Any, Any, None]]


##### LLM #####


class LLMConfig(BaseModelYAML):
    """LLM provider + model pair."""

    provider: str = "openai"
    model: str = "gpt-4o-mini"


##### TOOL CATALOG #####


class ToolParam(BaseModelYAML):
    """Single tool parameter schema."""

    name: str
    type: str = "str"
    description: str = ""
    optional: bool = False
    default: str | None = None


class ToolDefinition(BaseModelYAML):
    """Declarative tool definition (tool catalog docs)."""

    name: str
    description: str = ""
    parameters: list[ToolParam] = Field(default_factory=list)


class ToolCatalog(BaseModelYAML):
    """Collection of tool definitions loaded from config/tools/."""

    tools: list[ToolDefinition] = Field(default_factory=list)

    def get(self, name: str) -> ToolDefinition | None:
        """O(n) lookup — catalogs are small."""
        return next((t for t in self.tools if t.name == name), None)


##### HANDOFF #####


class HandoffConfig(BaseModelYAML):
    """Routing rule from one agent to another."""

    target: str
    description: str = ""


##### MCP SERVER #####


class MCPServerConfig(BaseModelYAML):
    """MCP server attached to an agent."""

    name: str
    fn: str
    adapter: str = ""


##### GUARDRAIL #####


class GuardrailConfig(BaseModelYAML):
    """Guardrail rule attached to an agent."""

    name: str
    type: Literal["input", "output", "tool"] = "output"
    config: dict[str, Any] = Field(default_factory=dict)


##### INTERRUPTION BEHAVIOR #####


class InterruptionConfig(BaseModelYAML):
    """Controls how the agent handles user interruptions."""

    allow: bool = True
    discard_audio_if_uninterruptible: bool = True
    min_duration: float = 0.5
    min_words: int = 0


##### ENDPOINTING #####


class EndpointingConfig(BaseModelYAML):
    """Controls silence detection for end-of-turn."""

    min_delay: float = 0.5
    max_delay: float = 3.0


##### AGENT BEHAVIOR #####


class AgentBehavior(BaseModelYAML):
    """Runtime behavior settings for a LiveKit Agent.

    Maps directly to LiveKit Agent constructor params.
    All fields optional — NOT_GIVEN semantics at factory level.
    """

    turn_detection: TurnDetectionMode | None = None
    interruption: InterruptionConfig = Field(default_factory=InterruptionConfig)
    endpointing: EndpointingConfig = Field(default_factory=EndpointingConfig)
    min_consecutive_speech_delay: float = 0.0
    use_tts_aligned_transcript: bool | None = None


##### AGENT CONFIG (from config/agents/<name>.yaml) #####


class AgentConfig(BaseModelYAML):
    """Agent identity loaded from an individual YAML file.

    Contains everything that defines *what* an agent IS:
    prompt, tools, greeting, mcp servers, guardrails, LLM override, behavior.
    Does NOT contain topology (role, handoffs, return_to).
    """

    name: str
    prompt: str = ""
    prompt_file: str | None = None
    greeting: str = ""
    tools: list[str] = Field(default_factory=list)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    guardrails: list[GuardrailConfig] = Field(default_factory=list)
    llm: LLMConfig | None = None
    behavior: AgentBehavior | None = None


##### SESSION AGENT REF (inline in config/sessions/<name>.yaml) #####


class SessionAgentRef(BaseModelYAML):
    """Agent reference within a session — topology only.

    Defines *how* a pre-loaded agent participates in THIS session:
    its role, handoff targets, and return path.
    """

    role: AgentRole
    handoffs: list[HandoffConfig] = Field(default_factory=list)
    return_to: str = ""


##### AGENT DEFINITION (merged at runtime) #####


class AgentDefinition(BaseModelYAML):
    """Materialised agent definition ready for the factory.

    Merges AgentConfig + SessionAgentRef + session-level defaults.
    """

    name: str
    role: AgentRole
    llm: LLMConfig = Field(default_factory=LLMConfig)
    prompt: str = ""
    greeting: str = ""
    tools: list[str] = Field(default_factory=list)
    handoffs: list[HandoffConfig] = Field(default_factory=list)
    return_to: str = ""
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    guardrails: list[GuardrailConfig] = Field(default_factory=list)
    behavior: AgentBehavior = Field(default_factory=AgentBehavior)


##### SESSION-LEVEL CONFIG #####


class SessionConfig(BaseModelYAML):
    """Session-level adapter and behavior wiring.

    Maps to AgentSession constructor parameters.
    """

    # -- adapters --
    stt: str = "whisper"
    tts: str = "piper"
    vad: str = "silero"
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # -- tool execution --
    max_tool_steps: int = 10

    # -- interruption --
    allow_interruptions: bool = True
    discard_audio_if_uninterruptible: bool = True
    min_interruption_duration: float = 0.5
    min_interruption_words: int = 0

    # -- endpointing --
    min_endpointing_delay: float = 0.5
    max_endpointing_delay: float = 3.0

    # -- turn detection --
    turn_detection: TurnDetectionMode | None = None

    # -- timeouts --
    user_away_timeout: float | None = 15.0
    false_interruption_timeout: float | None = 2.0
    resume_false_interruption: bool = True

    # -- speech --
    min_consecutive_speech_delay: float = 0.0
    use_tts_aligned_transcript: bool | None = None

    # -- generation --
    preemptive_generation: bool = False
    ivr_detection: bool = False


##### ROOM I/O #####


class AudioInputConfig(BaseModelYAML):
    """Audio input options for room I/O."""

    enabled: bool = True
    sample_rate: int = 24000
    num_channels: int = 1
    noise_cancellation: bool = False


class AudioOutputConfig(BaseModelYAML):
    """Audio output options for room I/O."""

    enabled: bool = True
    sample_rate: int = 24000
    num_channels: int = 1


class TextIOConfig(BaseModelYAML):
    """Text input/output options."""

    input_enabled: bool = True
    output_enabled: bool = True
    sync_transcription: bool = True


class RoomIOConfig(BaseModelYAML):
    """Room I/O configuration."""

    audio_input: AudioInputConfig = Field(default_factory=AudioInputConfig)
    audio_output: AudioOutputConfig = Field(default_factory=AudioOutputConfig)
    text: TextIOConfig = Field(default_factory=TextIOConfig)
    video_input_enabled: bool = False
    close_on_disconnect: bool = True
    delete_room_on_close: bool = False


##### SESSION DEFINITION #####


class SessionDefinition(BaseModelYAML):
    """Complete session definition loaded from ``config/sessions/<name>.yaml``."""

    name: str
    session: SessionConfig = Field(default_factory=SessionConfig)
    room_io: RoomIOConfig = Field(default_factory=RoomIOConfig)
    dispatcher: str = ""
    agents: dict[str, SessionAgentRef] = Field(default_factory=dict)

    # -- derived helpers --

    @property
    def outer_agents(self) -> list[str]:
        return [n for n, a in self.agents.items() if a.role == "outer"]

    @property
    def inner_agents(self) -> list[str]:
        return [n for n, a in self.agents.items() if a.role == "inner"]

    @property
    def all_agent_names(self) -> list[str]:
        return list(self.agents.keys())

    # -- validation --

    @model_validator(mode="after")
    def validate_graph(self) -> SessionDefinition:
        """Ensure dispatcher exists and handoff/return_to targets are valid."""
        names = set(self.agents)
        if self.dispatcher and self.dispatcher not in names:
            raise ValueError(f"Dispatcher '{self.dispatcher}' not in agents: {names}")

        for agent_name, agent_ref in self.agents.items():
            for handoff in agent_ref.handoffs:
                if handoff.target not in names:
                    raise ValueError(f"Agent '{agent_name}' handoff to unknown '{handoff.target}'. Available: {names}")
            if agent_ref.return_to and agent_ref.return_to not in names:
                raise ValueError(f"Agent '{agent_name}' return_to unknown '{agent_ref.return_to}'. Available: {names}")
        return self


##### SESSION STATE #####


@dataclasses.dataclass
class SessionState:
    """Shared state for the entire session."""

    agents: dict[str, Agent] = dataclasses.field(default_factory=dict)
    task_registry: TaskRegistry = dataclasses.field(default_factory=TaskRegistry)
    task_executor: TaskExecutor | None = None
    handoff_history: list[str] = dataclasses.field(default_factory=list)
    context: dict[str, Any] = dataclasses.field(default_factory=dict)
    is_speaking: bool = False
    pending_results: list[BackgroundTask[Any]] = dataclasses.field(default_factory=list)
