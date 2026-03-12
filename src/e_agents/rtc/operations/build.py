"""Builder — assembles LiveKit agents and sessions from loaded config."""

from __future__ import annotations

import asyncio
import functools
import uuid
from typing import TYPE_CHECKING, Any

from livekit.agents import NOT_GIVEN, Agent, AgentSession, RunContext, function_tool
from livekit.agents.llm import FunctionTool
from livekit.agents.llm.tool_context import FunctionToolInfo

from e_agents.rtc.adapters.stt.whisperlive import set_agent_speaking
from e_agents.rtc.core.exceptions import SessionBuildError
from e_agents.rtc.models.config import (
    AgentConfig,
    ExecutionConfig,
    HandoffConfig,
    HttpTransport,
    McpTransport,
    SessionConfig,
    StdioTransport,
    ToolRef,
)
from e_agents.rtc.models.state import SessionState
from e_agents.rtc.operations.load import Loader
from e_agents.rtc.operations.queue import TaskQueue, TaskResult
from e_agents.rtc.operations.registry import ProviderRegistry
from e_agents.shared.core.logger import LogIcon, logger
from e_agents.shared.core.settings import settings as st
from e_agents.shared.models import LLMConfig

try:
    from livekit.agents import mcp as _mcp
except ImportError:
    _mcp = None

if TYPE_CHECKING:
    from e_agents.rtc.models.config import OnCompleteConfig
    from e_agents.shared.state import State

_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "ru": "Russian",
    "nl": "Dutch",
    "ca": "Catalan",
}


##### PROACTIVE NOTIFICATION #####


def _try_proactive_notify(
    session: AgentSession[SessionState],
    result: TaskResult,
    on_complete: OnCompleteConfig,
) -> None:
    """Proactively notify the agent — only when the pipeline is idle."""
    if not on_complete.notify:
        return

    agent_state = getattr(session, "agent_state", None)
    if agent_state not in ("idle", "listening"):
        return

    queue = session.userdata.task_queue
    if queue is None:
        return

    agent = session.current_agent
    chat_ctx = agent.chat_ctx.copy()

    match result.status:
        case "done":
            content = f"<task_complete name='{result.name}'>{result.result}</task_complete>"
        case "error":
            content = f"<task_error name='{result.name}'>{result.error}</task_error>"
        case "cancelled":
            content = f"<task_cancelled name='{result.name}'/>"
        case _:
            return

    chat_ctx.add_message(role="system", content=content)
    asyncio.create_task(agent.update_chat_ctx(chat_ctx))
    asyncio.create_task(session.generate_reply(instructions=on_complete.instructions))
    queue.mark_notified(result.task_id)
    logger.info(
        "proactive_notify",
        task=result.name,
        status=result.status,
        icon=LogIcon.AGENT,
        tags="BACKGROUND",
    )


##### BUILDER #####


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

        task_queue: TaskQueue | None = None
        if session_cfg.task_queue.enabled:
            task_queue = TaskQueue(max_concurrent=session_cfg.task_queue.max_concurrent)

        session_state = SessionState(
            shared=state,
            data=dict.fromkeys(session_cfg.state),
            task_queue=task_queue,
        )

        agent_session = self._bd_build_session(session_cfg, session_state)
        self._bd_attach_hooks(agent_session, session_name)

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

    ##### EVENT HOOKS #####

    @staticmethod
    def _bd_attach_hooks(session: AgentSession[SessionState], session_name: str) -> None:
        """Register event listeners for runtime observability."""
        _prev_agent: dict[str, str] = {"name": ""}

        def _active_agent() -> str:
            agent = session.current_agent
            return type(agent).__name__ if agent else "?"

        def _on_state(ev: Any) -> None:
            if ev.new_state == "speaking":
                set_agent_speaking(True)
            elif ev.old_state == "speaking":
                set_agent_speaking(False)
            agent_name = _active_agent()
            if agent_name != _prev_agent["name"]:
                if _prev_agent["name"]:
                    logger.info(
                        "agent_switched",
                        active=agent_name,
                        prev=_prev_agent["name"],
                        icon=LogIcon.PROCESSING,
                        tags="HANDOFF",
                    )
                _prev_agent["name"] = agent_name
            logger.info(
                "agent_state",
                agent=agent_name,
                state=ev.new_state,
                prev=ev.old_state,
                icon=LogIcon.AGENT,
                tags="LIVE",
            )

        def _on_user_state(ev: Any) -> None:
            logger.debug(
                "user_state",
                state=ev.new_state,
                prev=ev.old_state,
                tags="LIVE",
            )

        def _on_transcript(ev: Any) -> None:
            if not ev.is_final:
                return
            logger.info(
                "user_speech",
                text=ev.transcript[:80],
                lang=ev.language,
                icon=LogIcon.STREAMING,
                tags="LIVE",
            )

        def _on_tools(ev: Any) -> None:
            for call, output in ev.zipped():
                result = str(output.output)[:60] if output else "—"
                is_handoff = ev.has_agent_handoff
                logger.info(
                    "tool_executed",
                    agent=_active_agent(),
                    tool=call.name,
                    args=call.arguments[:80] if call.arguments else "",
                    result=result,
                    handoff=is_handoff,
                    icon=LogIcon.TOOL,
                    tags="HANDOFF" if is_handoff else "LIVE",
                )

        def _on_conversation_item(ev: Any) -> None:
            item = ev.item
            role = getattr(item, "role", "?")
            content = ""
            if hasattr(item, "text_content"):
                content = (item.text_content or "")[:60]
            elif hasattr(item, "content") and isinstance(item.content, str):
                content = item.content[:60]
            logger.debug(
                "chat_item_added",
                agent=_active_agent(),
                role=role,
                content=content,
                icon=LogIcon.DEFAULT,
                tags="CTX",
            )

        def _on_false_interruption(ev: Any) -> None:
            logger.debug(
                "false_interruption",
                resumed=ev.resumed,
                icon=LogIcon.WARNING,
                tags="LIVE",
            )

        def _on_error(ev: Any) -> None:
            logger.error(
                "session_error",
                source=type(ev.source).__name__,
                error=str(ev.error)[:120],
                icon=LogIcon.ERROR,
                tags="LIVE",
            )

        def _on_close(ev: Any) -> None:
            logger.info(
                "session_closed",
                reason=ev.reason.value if hasattr(ev.reason, "value") else str(ev.reason),
                session=session_name,
                icon=LogIcon.COMPLETE,
                tags="LIVE",
            )

        session.on("agent_state_changed", _on_state)
        session.on("user_state_changed", _on_user_state)
        session.on("user_input_transcribed", _on_transcript)
        session.on("function_tools_executed", _on_tools)
        session.on("conversation_item_added", _on_conversation_item)
        session.on("agent_false_interruption", _on_false_interruption)
        session.on("error", _on_error)
        session.on("close", _on_close)

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

        tools = self._bd_resolve_tools(agent_cfg, session_cfg)
        handoff_tools = [self._bd_build_handoff(h, session_cfg) for h in agent_cfg.handoffs]
        mcp_servers = self._bd_resolve_mcps(agent_cfg.mcp_servers)

        if agent_cfg.execution.cancellation.enabled:
            auto_names = set(agent_cfg.execution.cancellation.auto_tools)
            cancel_tools = self._bd_build_cancel_tools()
            tools.extend(t for t in cancel_tools if t.info.name in auto_names)

        llm = self._bd_resolve_llm(agent_cfg.llm)
        stt = ProviderRegistry.create_stt(agent_cfg.stt) if agent_cfg.stt else NOT_GIVEN
        tts = ProviderRegistry.create_tts(agent_cfg.tts) if agent_cfg.tts else NOT_GIVEN
        vad = NOT_GIVEN

        lang = st.USER_LANGUAGE
        instructions = agent_cfg.instructions
        if lang != "en":
            lang_name = _LANG_NAMES.get(lang, lang)
            instructions = (
                f"LANGUAGE: You MUST respond in {lang_name} at ALL times, "
                f"including your very first message. Never respond in English.\n\n"
                f"{instructions}"
            )

        has_queue = session_cfg.task_queue.enabled
        agent_cls = self._bd_agent_class(name, agent_cfg, has_queue=has_queue)
        agent = agent_cls(
            instructions=instructions,
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

        bg_count = sum(1 for ref in agent_cfg.tools if isinstance(ref, ToolRef) and ref.execution and ref.execution.mode == "background")
        logger.info(
            "agent_built",
            agent=name,
            tools=len(tools),
            handoffs=len(handoff_tools),
            mcps=len(mcp_servers),
            background=bg_count,
            icon=LogIcon.AGENT,
        )
        if agent_cfg.greeting:
            logger.debug("agent_greeting", agent=name, greeting=agent_cfg.greeting[:60])

        return agent

    ##### DYNAMIC AGENT CLASS #####

    @staticmethod
    def _bd_agent_class(
        name: str, cfg: AgentConfig, *, has_queue: bool,
    ) -> type[Agent]:
        """Always return a dynamic Agent subclass with on_enter for handoff support."""
        raw_greeting = cfg.greeting
        lang = st.USER_LANGUAGE
        lang_prefix = (
            f"You MUST respond in {_LANG_NAMES.get(lang, lang)}. "
            if lang != "en" else ""
        )
        greeting = f"{lang_prefix}{raw_greeting}" if raw_greeting else ""
        on_complete_instructions = cfg.execution.on_complete.instructions

        class _ConfiguredAgent(Agent):
            async def on_enter(self) -> None:
                is_handoff = bool(self.chat_ctx.items)
                match (is_handoff, bool(greeting)):
                    case (False, True):
                        await self.session.generate_reply(instructions=greeting)
                    case (False, False):
                        await self.session.generate_reply()
                    case (True, True):
                        await self.session.generate_reply()
                    case (True, False):
                        await self.session.generate_reply(instructions=(
                            f"{lang_prefix}"
                            "You were just transferred a task by the previous agent. "
                            "Fulfill the user's most recent request using your available tools. "
                            "Share your findings with the user BEFORE transferring back. "
                            "Do NOT transfer back until you have actually completed your work."
                        ))

            async def on_user_turn_completed(
                self, turn_ctx: Any, new_message: Any = None,
            ) -> None:
                queue: TaskQueue | None = self.session.userdata.task_queue
                if queue is None:
                    return
                results = queue.drain_completed()
                if not results:
                    return

                for r in results:
                    match r.status:
                        case "done":
                            content = f"<task_complete name='{r.name}'>{r.result}</task_complete>"
                        case "error":
                            content = f"<task_error name='{r.name}'>{r.error}</task_error>"
                        case "cancelled":
                            content = f"<task_cancelled name='{r.name}'/>"
                        case _:
                            continue
                    turn_ctx.add_message(role="system", content=content)

                await self.session.generate_reply(instructions=on_complete_instructions)

        _ConfiguredAgent.__name__ = _ConfiguredAgent.__qualname__ = f"Agent_{name}"
        return _ConfiguredAgent

    ##### TOOL RESOLUTION #####

    def _bd_resolve_tools(
        self,
        agent_cfg: AgentConfig,
        session_cfg: SessionConfig,
    ) -> list[Any]:
        """Resolve ToolRefs to FunctionTools, wrapping background tools."""
        resolved: list[Any] = []
        for ref in agent_cfg.tools:
            if not isinstance(ref, ToolRef):
                continue
            tool = self.tools.get(ref.name)
            if tool is None:
                continue

            exec_cfg = ref.execution or agent_cfg.execution
            if exec_cfg.mode == "background" and session_cfg.task_queue.enabled:
                resolved.append(self._bd_wrap_background(tool, ref, exec_cfg, session_cfg))
            else:
                resolved.append(tool)
        return resolved

    ##### BACKGROUND WRAPPING #####

    @staticmethod
    def _bd_wrap_background(
        tool: FunctionTool,
        ref: ToolRef,
        exec_cfg: ExecutionConfig,
        session_cfg: SessionConfig,
    ) -> FunctionTool:
        """Wrap a tool for background execution — returns immediately, runs in queue."""
        original_fn = tool._func  # noqa: SLF001
        pre_msg = exec_cfg.pre_response.message or f"Working on '{tool.info.name}'..."
        on_complete = exec_cfg.on_complete

        @functools.wraps(original_fn)
        async def _background(*args: Any, **kwargs: Any) -> str:
            context: RunContext[SessionState] = args[0]
            queue = context.userdata.task_queue
            if queue is None:
                return str(await original_fn(*args, **kwargs))

            task_id = uuid.uuid4().hex[:8]
            coro = original_fn(*args, **kwargs)
            session = context.session

            def _on_done(result: TaskResult) -> None:
                _try_proactive_notify(session, result, on_complete)

            await queue.submit(
                task_id=task_id,
                name=tool.info.name,
                coro=coro,
                priority=ref.priority,
                cancellable=ref.cancellable,
                on_done=_on_done,
            )
            logger.info(
                "background_task_submitted",
                task_id=task_id,
                tool=tool.info.name,
                priority=ref.priority,
                icon=LogIcon.PROCESSING,
                tags="BACKGROUND",
            )
            return pre_msg

        info = FunctionToolInfo(
            name=tool.info.name,
            description=tool.info.description,
            flags=tool.info.flags,
        )
        return FunctionTool(_background, info)

    ##### CANCEL TOOLS #####

    @staticmethod
    def _bd_build_cancel_tools() -> list[FunctionTool]:
        """Generate task management tools (cancel, list)."""
        tools: list[FunctionTool] = []

        @function_tool(
            name="cancel_task",
            description="Cancel a running background task by name.",
        )
        async def _cancel(context: RunContext[SessionState], task_name: str) -> str:
            """Cancel a task. Args: task_name: Name of the task to cancel."""
            queue = context.userdata.task_queue
            if queue is None:
                return "No task queue available."
            cancelled = await queue.cancel_by_name(task_name)
            return f"Cancelled {cancelled} task(s) named '{task_name}'." if cancelled else f"No running task named '{task_name}'."

        tools.append(_cancel)

        @function_tool(
            name="cancel_all_tasks",
            description="Cancel all running background tasks.",
        )
        async def _cancel_all(context: RunContext[SessionState]) -> str:
            """Cancel every cancellable background task."""
            queue = context.userdata.task_queue
            if queue is None:
                return "No task queue available."
            cancelled = await queue.cancel_all()
            return f"Cancelled {cancelled} task(s)."

        tools.append(_cancel_all)

        @function_tool(
            name="list_tasks",
            description="List all running and queued background tasks.",
        )
        async def _list(context: RunContext[SessionState]) -> str:
            """List active background tasks with status."""
            queue = context.userdata.task_queue
            if queue is None:
                return "No task queue available."
            tasks = queue.pending
            if not tasks:
                return "No tasks currently running."
            return "\n".join(
                f"- {t['name']} (priority: {t['priority']}, status: {t['status']})"
                for t in tasks
            )

        tools.append(_list)
        return tools

    ##### HANDOFF BUILDING #####

    def _bd_build_handoff(
        self, handoff: HandoffConfig, session_cfg: SessionConfig,
    ) -> FunctionTool:
        """Create a function_tool that hands off to the target agent."""
        builder = self
        target = handoff.target
        ctx_mode = handoff.context
        truncate = handoff.truncate_items
        target_cfg = self.config.agents.get(target)

        desc = handoff.description or f"Transfer conversation to {target}"
        if target_cfg and target_cfg.instructions and not handoff.description:
            desc = f"Transfer to {target}: {target_cfg.instructions[:80]}"

        @function_tool(name=f"transfer_to_{target}", description=desc)
        async def _transfer(context: RunContext[SessionState]) -> Agent:
            match ctx_mode:
                case "carry":
                    chat_ctx = (
                        context.session.current_agent.chat_ctx
                        if hasattr(context.session, "current_agent")
                        else NOT_GIVEN
                    )
                case "truncated":
                    if hasattr(context.session, "current_agent"):
                        chat_ctx = context.session.current_agent.chat_ctx.truncate(
                            max_items=truncate,
                        )
                    else:
                        chat_ctx = NOT_GIVEN
                case "fresh":
                    chat_ctx = NOT_GIVEN
                case _:
                    chat_ctx = NOT_GIVEN
            logger.info(
                "handoff_transfer",
                source=context.session.current_agent.__class__.__name__,
                target=target,
                context_mode=ctx_mode,
                icon=LogIcon.AGENT,
                tags="HANDOFF",
            )
            return builder._bd_build_agent(target, session_cfg, chat_ctx=chat_ctx)

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

    @staticmethod
    def _bd_resolve_llm(cfg: str | LLMConfig | None) -> Any:
        """Resolve LLM config to a plugin instance or NOT_GIVEN."""
        match cfg:
            case None:
                return NOT_GIVEN
            case str():
                return cfg
            case LLMConfig():
                return ProviderRegistry.create_llm(cfg.provider, model=cfg.model)

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
