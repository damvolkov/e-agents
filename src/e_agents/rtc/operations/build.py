"""Builder — assembles LiveKit agents and sessions from loaded config."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livekit.agents import NOT_GIVEN, Agent, AgentSession, RunContext, function_tool
from livekit.agents.llm import FunctionTool

from e_agents.rtc.core.exceptions import SessionBuildError
from e_agents.rtc.models.config import (
    AgentConfig,
    HttpTransport,
    McpTransport,
    SessionConfig,
    StdioTransport,
)
from e_agents.rtc.models.state import SessionState
from e_agents.rtc.operations.load import Loader
from e_agents.rtc.operations.registry import ProviderRegistry
from e_agents.shared.core.logger import LogIcon, logger
from e_agents.shared.models import LLMConfig

try:
    from livekit.agents import mcp as _mcp
except ImportError:
    _mcp = None

if TYPE_CHECKING:
    from e_agents.shared.state import State


class Builder(Loader):
    """Assembles LiveKit Agent and AgentSession instances from loaded config."""

    __slots__ = ()

    def build(
        self,
        session_name: str,
        state: State,
    ) -> tuple[AgentSession[SessionState], Agent]:
        """Build a complete session + dispatcher agent."""
        session_cfg = self.config.sessions.get(session_name)
        if session_cfg is None:
            raise SessionBuildError(
                f"Session '{session_name}' not found. Available: {sorted(self.config.sessions)}"
            )

        logger.info("building_session", session=session_name, icon=LogIcon.PROCESSING)

        session_state = SessionState(
            shared=state,
            data={key: None for key in session_cfg.state},
        )

        agent_session = self._bd_build_session(session_cfg, session_state)

        dispatcher_name = session_cfg.dispatcher or next(iter(session_cfg.agents), "")
        if not dispatcher_name:
            raise SessionBuildError(f"Session '{session_name}' has no agents or dispatcher")

        dispatcher = self._bd_build_agent(dispatcher_name, session_cfg)

        logger.info(
            "session_ready",
            session=session_name,
            dispatcher=dispatcher_name,
            agents=len(session_cfg.agents),
            icon=LogIcon.SUCCESS,
        )

        return agent_session, dispatcher

    ##### AGENT BUILDING #####

    def _bd_build_agent(
        self,
        name: str,
        session_cfg: SessionConfig,
        *,
        chat_ctx: Any = NOT_GIVEN,
    ) -> Agent:
        """Build a single Agent from config with tools, handoffs, and overrides."""
        agent_cfg = self.config.agents.get(name)
        if agent_cfg is None:
            raise SessionBuildError(
                f"Agent '{name}' not found. Available: {sorted(self.config.agents)}"
            )

        tools: list[Any] = [self.tools[t] for t in agent_cfg.tools if t in self.tools]
        handoff_tools = [self._bd_build_handoff(target, session_cfg) for target in agent_cfg.handoffs]
        mcp_servers = self._bd_resolve_mcps(agent_cfg.mcp_servers)

        llm = self._bd_resolve_llm(agent_cfg.llm)
        stt = ProviderRegistry.create_stt(agent_cfg.stt) if agent_cfg.stt else NOT_GIVEN
        tts = ProviderRegistry.create_tts(agent_cfg.tts) if agent_cfg.tts else NOT_GIVEN
        vad = NOT_GIVEN

        agent_cls = self._bd_agent_class(name, agent_cfg)
        agent = agent_cls(
            instructions=agent_cfg.instructions,
            chat_ctx=chat_ctx,
            tools=tools + handoff_tools,
            mcp_servers=mcp_servers if mcp_servers else NOT_GIVEN,
            llm=llm,
            stt=stt,
            tts=tts,
            vad=vad,
            allow_interruptions=(
                agent_cfg.allow_interruptions if agent_cfg.allow_interruptions is not None else NOT_GIVEN
            ),
            min_endpointing_delay=(
                agent_cfg.min_endpointing_delay if agent_cfg.min_endpointing_delay is not None else NOT_GIVEN
            ),
            max_endpointing_delay=(
                agent_cfg.max_endpointing_delay if agent_cfg.max_endpointing_delay is not None else NOT_GIVEN
            ),
        )

        logger.info(
            "agent_built",
            agent=name,
            tools=len(tools),
            handoffs=len(handoff_tools),
            mcps=len(mcp_servers),
            icon=LogIcon.AGENT,
        )
        if agent_cfg.greeting:
            logger.debug("agent_greeting", agent=name, greeting=agent_cfg.greeting[:60])

        return agent

    @staticmethod
    def _bd_agent_class(name: str, cfg: AgentConfig) -> type[Agent]:
        """Return Agent or a dynamic subclass when lifecycle hooks are needed."""
        if not cfg.greeting:
            return Agent

        greeting = cfg.greeting

        class _ConfiguredAgent(Agent):
            async def on_enter(self) -> None:
                await self.session.generate_reply(instructions=greeting)

        _ConfiguredAgent.__name__ = _ConfiguredAgent.__qualname__ = f"Agent_{name}"
        return _ConfiguredAgent

    ##### HANDOFF BUILDING #####

    def _bd_build_handoff(self, target: str, session_cfg: SessionConfig) -> FunctionTool:
        """Create a function_tool that hands off to the target agent."""
        builder = self
        target_cfg = self.config.agents.get(target)
        description = f"Transfer conversation to {target}"
        if target_cfg and target_cfg.instructions:
            description = f"Transfer to {target}: {target_cfg.instructions[:80]}"

        @function_tool(name=f"transfer_to_{target}", description=description)
        async def _transfer(context: RunContext[SessionState]) -> Agent:
            current_ctx = (
                context.session.current_agent.chat_ctx
                if hasattr(context.session, "current_agent")
                else NOT_GIVEN
            )
            return builder._bd_build_agent(target, session_cfg, chat_ctx=current_ctx)

        return _transfer

    ##### SESSION BUILDING #####

    def _bd_build_session(
        self,
        cfg: SessionConfig,
        session_state: SessionState,
    ) -> AgentSession[SessionState]:
        """Create an AgentSession with session-level defaults."""
        llm = self._bd_resolve_llm(cfg.llm)
        session_tools: list[Any] = [self.tools[t] for t in cfg.tools if t in self.tools]
        session_mcps = self._bd_resolve_mcps(cfg.mcp_servers)

        session = AgentSession[SessionState](
            userdata=session_state,
            stt=ProviderRegistry.create_stt(cfg.stt),
            tts=ProviderRegistry.create_tts(cfg.tts),
            vad=ProviderRegistry.create_vad(),
            llm=llm,
            tools=session_tools if session_tools else NOT_GIVEN,
            mcp_servers=session_mcps if session_mcps else NOT_GIVEN,
            max_tool_steps=cfg.max_tool_steps,
            allow_interruptions=cfg.allow_interruptions,
            min_endpointing_delay=cfg.min_endpointing_delay,
            max_endpointing_delay=cfg.max_endpointing_delay,
            min_interruption_words=cfg.min_interruption_words,
            min_interruption_duration=cfg.min_interruption_duration,
            discard_audio_if_uninterruptible=cfg.discard_audio_if_uninterruptible,
            false_interruption_timeout=cfg.false_interruption_timeout,
            resume_false_interruption=cfg.resume_false_interruption,
            min_consecutive_speech_delay=cfg.min_consecutive_speech_delay,
            user_away_timeout=cfg.user_away_timeout,
            preemptive_generation=cfg.preemptive_generation,
            ivr_detection=cfg.ivr_detection,
        )

        logger.info("session_built", stt=str(cfg.stt), tts=str(cfg.tts), llm=str(llm), icon=LogIcon.COMPLETE)

        return session

    ##### RESOLVERS #####

    def _bd_resolve_llm(self, cfg: str | LLMConfig | None) -> Any:
        """Resolve LLM config to a model string or NOT_GIVEN."""
        match cfg:
            case None:
                return NOT_GIVEN
            case str():
                return cfg
            case LLMConfig():
                return f"{cfg.provider}/{cfg.model}"

    def _bd_resolve_mcps(self, names: list[str]) -> list[Any]:
        """Convert MCP config names to livekit MCPServer instances."""
        servers: list[Any] = []
        for name in names:
            transport = self.config.mcps.get(name)
            if transport is None:
                continue
            server = self._bd_transport_to_server(transport)
            if server is not None:
                servers.append(server)
        return servers

    @staticmethod
    def _bd_transport_to_server(transport: McpTransport) -> Any | None:
        """Convert a transport config to a livekit MCPServer instance."""
        if _mcp is None:
            return None

        match transport:
            case StdioTransport():
                return _mcp.MCPServerStdio(
                    command=transport.command,
                    args=transport.args,
                    env=transport.env or None,
                )
            case HttpTransport():
                return _mcp.MCPServerHTTP(
                    url=transport.url,
                    headers=transport.headers or None,
                )
            case _:
                return None
