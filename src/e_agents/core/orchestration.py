"""Double-loop orchestration engine.

Outer loop: always-on agent facing the user, never stops.
Inner loop: background agents/tasks running async, feeding results back.

The orchestrator manages a priority queue so that completed inner-loop
results are delivered to the outer agent at natural pauses without
interrupting mid-sentence.
"""

from __future__ import annotations

from typing import Any

from livekit import agents
from livekit.agents import (
    AgentSession,
    AgentStateChangedEvent,
    ConversationItemAddedEvent,
    FunctionToolsExecutedEvent,
    RoomInputOptions,
    UserStateChangedEvent,
)

from e_agents.core.factory import SessionFactory
from e_agents.core.models import SessionDefinition, SessionState
from e_agents.shared.logger import LogIcon, logger
from e_agents.tasks.models import BackgroundTask
from e_agents.tasks.status import TaskStatus


class Orchestrator:
    """Core double-loop orchestration engine."""

    __slots__ = ("_session", "_session_def", "_state")

    def __init__(self, session_def: SessionDefinition) -> None:
        self._session_def = session_def
        self._session: AgentSession[SessionState] | None = None
        self._state: SessionState | None = None

    # -- event wiring --

    def _wire_events(self, session: AgentSession[SessionState]) -> None:
        """Wire LiveKit session events for tracing and delivery."""

        @session.on("agent_state_changed")
        def _on_agent_state(ev: AgentStateChangedEvent) -> None:
            agent_id = session.current_agent.id if session.current_agent else "none"
            logger.debug(
                "agent_state: %s -> %s [%s]",
                ev.old_state,
                ev.new_state,
                agent_id,
                icon=LogIcon.AGENT,
            )
            match ev.new_state:
                case "listening":
                    self._deliver_pending()
                case "speaking":
                    if self._state:
                        self._state.is_speaking = True
                case _:
                    pass

        @session.on("user_state_changed")
        def _on_user_state(ev: UserStateChangedEvent) -> None:
            logger.debug("user_state: %s -> %s", ev.old_state, ev.new_state, icon=LogIcon.CHAT)

        @session.on("conversation_item_added")
        def _on_conversation_item(ev: ConversationItemAddedEvent) -> None:
            item = ev.item
            match getattr(item, "type", None):
                case "message":
                    content = getattr(item, "text_content", "") or ""
                    logger.debug(
                        "message [%s]: %s",
                        getattr(item, "role", "unknown"),
                        content[:80],
                        icon=LogIcon.CHAT,
                    )
                case item_type if item_type:
                    logger.debug("item: %s", item_type, icon=LogIcon.CHAT)

        @session.on("function_tools_executed")
        def _on_tools(ev: FunctionToolsExecutedEvent) -> None:
            for call, output in ev.zipped():
                is_error = output.is_error if output else False
                icon = LogIcon.ERROR if is_error else LogIcon.TOOL
                logger.debug(
                    "tool: %s (error=%s, handoff=%s)",
                    call.name,
                    is_error,
                    ev.has_agent_handoff,
                    icon=icon,
                )

    # -- result delivery at natural pauses --

    def _deliver_pending(self) -> None:
        """Deliver pending results when the outer agent stops speaking."""
        if not self._state or not self._session:
            return

        self._state.is_speaking = False
        pending = self._state.pending_results
        if not pending:
            return

        results: list[str] = []
        while pending:
            task = pending.pop(0)
            match task.status:
                case TaskStatus.COMPLETED:
                    results.append(f"'{task.name}': {task.result}")
                case _:
                    results.append(f"'{task.name}': could not complete")

        self._session.generate_reply(
            instructions=(
                "New findings just arrived from your background team. "
                "Present them naturally without interrupting the flow. "
                "Findings:\n" + "\n".join(results)
            )
        )

    # -- task completion callback --

    async def _on_task_completed(self, task: BackgroundTask[Any]) -> None:
        """Handle a finished background task."""
        if not self._session or not self._state:
            return

        icon = LogIcon.COMPLETE if task.status == TaskStatus.COMPLETED else LogIcon.ERROR
        logger.info(
            "task_done: %s [%s] %.2fs",
            task.name,
            task.status.value,
            task.duration_seconds or 0,
            icon=icon,
        )

        if self._state.is_speaking:
            self._state.pending_results.append(task)
            return

        match task.status:
            case TaskStatus.COMPLETED:
                self._session.generate_reply(
                    instructions=(
                        "A background research task just finished. Present the findings "
                        f"naturally as your own discovery. Findings: {task.result}"
                    )
                )
            case _:
                self._session.generate_reply(
                    instructions=(
                        "A background task could not be completed. Apologise briefly "
                        "and offer to try a different approach."
                    )
                )

    # -- entrypoint --

    async def run(self, ctx: agents.JobContext) -> None:
        """LiveKit worker entrypoint — boots the double-loop session."""
        await ctx.connect()
        logger.info(
            "session_starting room=%s session=%s",
            ctx.room.name,
            self._session_def.name,
            icon=LogIcon.START,
        )

        factory = SessionFactory(self._session_def)
        self._state, self._session = factory.build(
            on_task_completed=self._on_task_completed,
        )

        self._wire_events(self._session)

        dispatcher_name = self._session_def.dispatcher
        dispatcher = self._state.agents.get(dispatcher_name)
        if dispatcher is None:
            raise RuntimeError(f"Dispatcher '{dispatcher_name}' not found")

        await self._session.start(
            agent=dispatcher,
            room=ctx.room,
            room_input_options=RoomInputOptions(),
        )

        logger.info(
            "session_started room=%s dispatcher=%s",
            ctx.room.name,
            dispatcher_name,
            icon=LogIcon.START,
        )
