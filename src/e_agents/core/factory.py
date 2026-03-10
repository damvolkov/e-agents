"""Factories for building agents and sessions from configuration.

Agents are defined by separate YAML files (config/agents/).
Sessions reference agents by name and define topology (config/sessions/).
The loader merges AgentConfig + SessionAgentRef → AgentDefinition,
and this factory dynamically builds LiveKit Agent classes from those.
"""

from __future__ import annotations

from typing import Any

from livekit.agents import Agent, AgentSession, RunContext, function_tool

from e_agents.core import loader
from e_agents.core.agents import BaseAgent, DispatcherAgent, SpecialistAgent
from e_agents.core.models import (
    AgentDefinition,
    SessionConfig,
    SessionDefinition,
    SessionState,
    TaskCallback,
)
from e_agents.core.registry import ProviderRegistry
from e_agents.shared.logger import LogIcon, logger
from e_agents.tasks.executor import TaskExecutor
from e_agents.tasks.registry import TaskRegistry
from e_agents.tools.manager import get_tool

##### AGENT CLASS BUILDER #####

_ROLE_BASE: dict[str, type[BaseAgent]] = {
    "outer": DispatcherAgent,
    "inner": SpecialistAgent,
}


def _build_handoff(target_name: str, description: str) -> Any:
    """Create a handoff tool function for the given target agent."""

    async def _handoff(self, context):
        return self._resolve_agent(target_name), description

    # Annotate with actual type objects so LiveKit's is_context_type()
    # recognises RunContext and excludes it from the OpenAI tool schema.
    # Do NOT annotate `self` — the FunctionTool descriptor strips it.
    _handoff.__annotations__ = {"context": RunContext, "return": tuple[Agent, str]}
    _handoff.__name__ = f"transfer_to_{target_name}"
    _handoff.__qualname__ = f"transfer_to_{target_name}"
    _handoff.__doc__ = description
    return function_tool()(_handoff)


def _build_agent_class(definition: AgentDefinition) -> type[BaseAgent]:
    """Dynamically create an Agent subclass from an AgentDefinition.

    Tools, handoffs, and return routes are attached as ``@function_tool``
    decorated methods so LiveKit discovers them at runtime.
    """
    base = _ROLE_BASE.get(definition.role, SpecialistAgent)
    namespace: dict[str, Any] = {}

    for tool_name in definition.tools:
        fn = get_tool(tool_name)
        namespace[tool_name] = function_tool()(fn)

    for handoff in definition.handoffs:
        namespace[f"transfer_to_{handoff.target}"] = _build_handoff(
            handoff.target,
            handoff.description or f"Hand off to {handoff.target}",
        )

    if definition.return_to:
        namespace[f"return_to_{definition.return_to}"] = _build_handoff(
            definition.return_to,
            f"Return control to {definition.return_to}",
        )

    cls_name = "".join(part.capitalize() for part in definition.name.split("_")) + "Agent"
    return type(cls_name, (base,), namespace)


##### AGENT FACTORY #####


class AgentFactory:
    """Creates LiveKit Agent instances from a SessionDefinition."""

    __slots__ = ("_session_def",)

    def __init__(self, session_def: SessionDefinition) -> None:
        self._session_def = session_def

    def create(self, name: str) -> Agent:
        """Instantiate a single agent by name using merged config."""
        ref = self._session_def.agents[name]
        definition = loader.build_agent_definition(name, ref, self._session_def)
        agent_cls = _build_agent_class(definition)
        agent: Agent = agent_cls(definition)
        logger.debug(
            "agent_created: %s role=%s tools=%s handoffs=%s",
            name,
            definition.role,
            definition.tools,
            [h.target for h in definition.handoffs],
            icon=LogIcon.AGENT,
        )
        return agent

    def create_all(self) -> dict[str, Agent]:
        """Create all agents defined in the session and wire cross-references."""
        agents: dict[str, Agent] = {}
        for name in self._session_def.all_agent_names:
            agents[name] = self.create(name)

        for agent in agents.values():
            if isinstance(agent, BaseAgent):
                agent._available_agents = agents

        return agents


##### SESSION FACTORY #####


class SessionFactory:
    """Builds an AgentSession + SessionState from a SessionDefinition."""

    __slots__ = ("_session_def",)

    def __init__(self, session_def: SessionDefinition) -> None:
        self._session_def = session_def

    def build(
        self,
        *,
        on_task_completed: TaskCallback | None = None,
    ) -> tuple[SessionState, AgentSession[SessionState]]:
        """Assemble state, agents, adapters, and session."""
        cfg = self._session_def.session

        agents = AgentFactory(self._session_def).create_all()
        state = SessionState(agents=agents)

        session = self._build_agent_session(cfg, state)

        task_registry = TaskRegistry()
        state.task_registry = task_registry
        state.task_executor = TaskExecutor(
            registry=task_registry,
            session=session,
            on_task_completed=on_task_completed,
        )

        logger.info(
            "session_built: %s agents=%d stt=%s tts=%s llm=%s/%s",
            self._session_def.name,
            len(agents),
            cfg.stt,
            cfg.tts,
            cfg.llm.provider,
            cfg.llm.model,
            icon=LogIcon.START,
        )

        return state, session

    @staticmethod
    def _build_agent_session(
        cfg: SessionConfig,
        state: SessionState,
    ) -> AgentSession[SessionState]:
        """Create an AgentSession with all config-driven parameters."""
        return AgentSession(
            userdata=state,
            stt=ProviderRegistry.create_stt(cfg.stt),
            tts=ProviderRegistry.create_tts(cfg.tts),
            vad=ProviderRegistry.create_vad(),
            llm=ProviderRegistry.create_llm(cfg.llm.provider, model=cfg.llm.model),
            max_tool_steps=cfg.max_tool_steps,
            allow_interruptions=cfg.allow_interruptions,
            discard_audio_if_uninterruptible=cfg.discard_audio_if_uninterruptible,
            min_interruption_duration=cfg.min_interruption_duration,
            min_interruption_words=cfg.min_interruption_words,
            min_endpointing_delay=cfg.min_endpointing_delay,
            max_endpointing_delay=cfg.max_endpointing_delay,
            user_away_timeout=cfg.user_away_timeout,
            false_interruption_timeout=cfg.false_interruption_timeout,
            resume_false_interruption=cfg.resume_false_interruption,
            min_consecutive_speech_delay=cfg.min_consecutive_speech_delay,
            preemptive_generation=cfg.preemptive_generation,
            ivr_detection=cfg.ivr_detection,
        )
