"""Double Loop Session - Background tasks with agent handoffs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    AgentStateChangedEvent,
    ConversationItemAddedEvent,
    FunctionToolsExecutedEvent,
    RoomInputOptions,
    UserStateChangedEvent,
)
from livekit.plugins import google, silero

from e_template_agents.adapters.stt import WhisperSTT
from e_template_agents.adapters.tts import PiperTTS
from e_template_agents.agents.analyst import AnalystAgent
from e_template_agents.agents.fact_checker import FactCheckerAgent
from e_template_agents.agents.navigator import NavigatorAgent
from e_template_agents.agents.utils import load_agents_from_config
from e_template_agents.agents.web_searcher import WebSearcherAgent
from e_template_agents.core.logger import LogIcon, logger
from e_template_agents.core.settings import settings as st
from e_template_agents.tasks.executor import TaskExecutor
from e_template_agents.tasks.models import BackgroundTask
from e_template_agents.tasks.registry import TaskRegistry
from e_template_agents.tasks.status import TaskStatus

AGENT_CLASSES = {
    "NavigatorAgent": NavigatorAgent,
    "WebSearcherAgent": WebSearcherAgent,
    "AnalystAgent": AnalystAgent,
    "FactCheckerAgent": FactCheckerAgent,
}


@dataclass
class DoubleLoopUserData:
    """Shared state for the double loop session."""

    agents: dict[str, Agent] = field(default_factory=dict)
    task_registry: TaskRegistry = field(default_factory=TaskRegistry)
    task_executor: TaskExecutor = field(init=False)
    handoff_history: list[str] = field(default_factory=list)
    conversation_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        pass


class DoubleLoopSession:
    """Session implementing double loop architecture with background tasks."""

    def __init__(self) -> None:
        self._session: AgentSession[DoubleLoopUserData] | None = None

    def _setup_event_handlers(self, session: AgentSession[DoubleLoopUserData]) -> None:
        """Configure native LiveKit event handlers for tracing."""

        @session.on("agent_state_changed")
        def on_agent_state(ev: AgentStateChangedEvent) -> None:
            agent_id = session.current_agent.id if session.current_agent else "none"
            logger.debug("agent_state: %s -> %s [%s]", ev.old_state, ev.new_state, agent_id, icon=LogIcon.AGENT)

        @session.on("user_state_changed")
        def on_user_state(ev: UserStateChangedEvent) -> None:
            logger.debug("user_state: %s -> %s", ev.old_state, ev.new_state, icon=LogIcon.CHAT)

        @session.on("conversation_item_added")
        def on_conversation_item(ev: ConversationItemAddedEvent) -> None:
            item = ev.item
            match getattr(item, "type", None):
                case "message":
                    content = getattr(item, "text_content", "") or ""
                    logger.debug("message [%s]: %s", getattr(item, "role", "unknown"), content[:80], icon=LogIcon.CHAT)
                case item_type if item_type:
                    logger.debug("item: %s", item_type, icon=LogIcon.CHAT)

        @session.on("function_tools_executed")
        def on_tools_executed(ev: FunctionToolsExecutedEvent) -> None:
            for call, output in ev.zipped():
                is_error = output.is_error if output else False
                icon = LogIcon.ERROR if is_error else LogIcon.TOOL
                logger.debug("tool: %s (error=%s, handoff=%s)", call.name, is_error, ev.has_agent_handoff, icon=icon)

    async def _on_task_completed(self, task: BackgroundTask[Any]) -> None:
        """Callback when any background task completes. Presents results naturally."""
        if self._session is None:
            return

        icon = LogIcon.COMPLETE if task.status == TaskStatus.COMPLETED else LogIcon.ERROR
        logger.info("task_completed: %s [%s] duration=%.2fs", task.name, task.status.value, task.duration_seconds or 0, icon=icon)

        current_agent = self._session.current_agent

        match (task.initiated_by == current_agent.id, task.status):
            case (True, TaskStatus.COMPLETED):
                self._session.generate_reply(
                    instructions=(
                        "You just finished researching something the user asked about. "
                        "Present these findings naturally as your own discovery. Be enthusiastic. "
                        f"Findings: {task.result}"
                    )
                )
            case (True, _):
                self._session.generate_reply(
                    instructions=(
                        "You tried to look into something but couldn't find detailed information. "
                        "Apologize naturally and suggest alternative approaches or offer to try "
                        "a different angle."
                    )
                )
            case (False, _):
                logger.debug(
                    "task from different agent: %s (initiated_by=%s, current=%s)",
                    task.id,
                    task.initiated_by,
                    current_agent.id,
                    icon=LogIcon.PROCESSING,
                )

    async def entrypoint(self, ctx: agents.JobContext) -> None:
        """Entry point for the double loop voice agent session."""
        await ctx.connect()

        logger.info("session_starting room=%s", ctx.room.name, icon=LogIcon.START)

        userdata = DoubleLoopUserData()
        userdata.agents = load_agents_from_config(st.AGENTS_CONFIG, AGENT_CLASSES)

        self._session = AgentSession[DoubleLoopUserData](
            userdata=userdata,
            stt=WhisperSTT(),
            llm=google.LLM(model=st.GEMINI_MODEL),
            tts=PiperTTS(),
            vad=silero.VAD.load(),
            max_tool_steps=st.AGENT_MAX_TOOL_STEPS,
        )

        self._setup_event_handlers(self._session)

        userdata.task_executor = TaskExecutor(
            registry=userdata.task_registry,
            session=self._session,
            on_task_completed=self._on_task_completed,
        )

        await self._session.start(
            agent=userdata.agents["navigator"],
            room=ctx.room,
            room_input_options=RoomInputOptions(),
        )

        logger.info("session_started room=%s agent=navigator", ctx.room.name, icon=LogIcon.START)
