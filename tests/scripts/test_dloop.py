"""Double-loop agent architecture.

Outer agent: user-facing, conversational, delegates long-running tasks.
Inner worker: background async processor, updates shared state,
notifies outer agent on completion via ``session.generate_reply()``.

Architecture::

    ┌─────────────────────────────────────────────┐
    │  AgentSession (userdata=SessionState)        │
    │                                              │
    │  ┌──────────────┐    dispatch    ┌────────┐ │
    │  │  OuterAgent   │──────────────▶│ Inner  │ │
    │  │  (active,     │               │ Worker │ │
    │  │   user-facing)│◀──────────────│ (bg    │ │
    │  └──────────────┘  generate_reply│ task)  │ │
    │        ▲                         └────────┘ │
    │        │ voice                               │
    │        ▼                                     │
    │     [User]                                   │
    └─────────────────────────────────────────────┘

The inner worker is NOT a LiveKit Agent — it's an ``asyncio.Task``
that holds a session reference.  Only one Agent can be active at a
time in LiveKit; the outer agent stays active while the worker runs
in the background.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import sys
from typing import Any, Literal
from uuid import uuid4

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    RunContext,
    cli,
    function_tool,
    room_io,
)
from livekit.agents.llm import ChatContext, ChatMessage

from e_agents.rtc.operations.registry import ProviderRegistry

logger = logging.getLogger(__name__)

type TaskStatus = Literal["pending", "running", "completed", "failed"]


# ── Shared State ─────────────────────────────────────────────────────────


@dataclasses.dataclass
class TaskRecord:
    """Single background task tracked by the session."""

    task_id: str
    description: str
    status: TaskStatus = "pending"
    result: Any = None
    error: str | None = None


@dataclasses.dataclass
class SessionState:
    """Mutable state shared between outer agent and inner workers."""

    tasks: dict[str, TaskRecord] = dataclasses.field(default_factory=dict)
    bg_tasks: dict[str, asyncio.Task[None]] = dataclasses.field(default_factory=dict)


# ── Inner Worker ─────────────────────────────────────────────────────────


class InnerWorker:
    """Background async processor that updates shared state on completion.

    Not a LiveKit Agent — runs as a detached ``asyncio.Task``.
    Holds a session reference to push notifications via ``generate_reply``.
    """

    __slots__ = ("_session", "_delay")

    def __init__(self, session: AgentSession[SessionState], *, delay: float = 8.0):
        self._session = session
        self._delay = delay

    async def execute(self, record: TaskRecord) -> None:
        """Run the long-running task, update state, notify outer agent."""
        state: SessionState = self._session.userdata
        record.status = "running"
        logger.info("🔄 TASK_STARTED", extra={"task_id": record.task_id})

        try:
            await asyncio.sleep(self._delay)
            record.result = {
                "analysis": f"Processed '{record.description}' successfully",
                "confidence": 0.95,
                "items_found": 42,
            }
            record.status = "completed"
            logger.info("✅ TASK_COMPLETED", extra={"task_id": record.task_id})

            self._session.generate_reply(
                instructions=(
                    f"IMPORTANT: The background task '{record.description}' "
                    f"just finished. Inform the user of the result: {record.result}. "
                    f"Be concise and natural about it."
                ),
            )

        except asyncio.CancelledError:
            record.status = "failed"
            record.error = "Task was cancelled"
            logger.warning("⚠️ TASK_CANCELLED", extra={"task_id": record.task_id})
            raise

        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
            logger.exception("❌ TASK_FAILED", extra={"task_id": record.task_id})

            self._session.generate_reply(
                instructions=(
                    f"The background task '{record.description}' failed "
                    f"with error: {record.error}. Apologize and offer to retry."
                ),
            )

        finally:
            state.bg_tasks.pop(record.task_id, None)


# ── Outer Agent ──────────────────────────────────────────────────────────


class OuterAgent(Agent):
    """User-facing conversational agent that dispatches to inner workers."""

    def __init__(self, *, worker_delay: float = 8.0):
        super().__init__(
            instructions=(
                "You are a friendly assistant. You can delegate research tasks "
                "that take time to process in the background.\n\n"
                "While a task runs, keep chatting with the user normally — "
                "talk about anything they want. When a task completes, you will "
                "receive its results automatically and should share them.\n\n"
                "If the user asks about task status, use the check_task tool."
            ),
        )
        self._worker_delay = worker_delay

    async def on_enter(self) -> None:
        """Greet on activation."""
        await self.session.generate_reply(
            instructions="Greet the user. Mention you can handle background research tasks.",
        )

    # ── Tools ────────────────────────────────────────────────────────

    @function_tool()
    async def delegate_task(
        self,
        context: RunContext[SessionState],
        description: str,
    ) -> str:
        """Dispatch a research task to the background worker. Use when the user asks you to investigate, analyze, or process something that takes time."""
        state = context.userdata
        task_id = uuid4().hex[:8]
        record = TaskRecord(task_id=task_id, description=description)
        state.tasks[task_id] = record

        worker = InnerWorker(context.session, delay=self._worker_delay)
        bg = asyncio.create_task(worker.execute(record), name=f"inner:{task_id}")
        state.bg_tasks[task_id] = bg

        logger.info("📤 TASK_DISPATCHED", extra={"task_id": task_id, "desc": description})
        return f"Task '{description}' dispatched (id={task_id}). Results will arrive shortly."

    @function_tool()
    async def check_task(
        self,
        context: RunContext[SessionState],
        task_id: str = "",
    ) -> str:
        """Check the status of a background task. Leave task_id empty to see all."""
        state = context.userdata

        match task_id:
            case "" if not state.tasks:
                return "No tasks have been dispatched yet."
            case "":
                lines = [
                    f"- {r.task_id}: {r.description} → {r.status}"
                    for r in state.tasks.values()
                ]
                return "Active tasks:\n" + "\n".join(lines)
            case tid if (record := state.tasks.get(tid)):
                match record.status:
                    case "completed":
                        return f"Task {tid} completed: {record.result}"
                    case "failed":
                        return f"Task {tid} failed: {record.error}"
                    case status:
                        return f"Task {tid} is {status}."
            case _:
                return f"Unknown task id: {task_id}"

    @function_tool()
    async def cancel_task(
        self,
        context: RunContext[SessionState],
        task_id: str,
    ) -> str:
        """Cancel a running background task."""
        state = context.userdata

        if not (bg := state.bg_tasks.get(task_id)):
            return f"No running task with id {task_id}."

        bg.cancel()
        return f"Task {task_id} cancellation requested."

    # ── Input guardrail ──────────────────────────────────────────────

    async def on_user_turn_completed(
        self,
        turn_ctx: ChatContext,
        new_message: ChatMessage,
    ) -> None:
        """Light input guardrail — log user turns."""
        logger.info(
            "🗣️ USER_TURN",
            extra={"text": (new_message.text_content() or "")[:120]},
        )


# ── Server ───────────────────────────────────────────────────────────────


server = AgentServer()


def prewarm(proc: agents.JobProcess) -> None:
    """Register providers and load VAD once per worker process."""
    ProviderRegistry.populate()
    proc.userdata["vad"] = ProviderRegistry.create_vad()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="double-loop")
async def entrypoint(ctx: agents.JobContext) -> None:
    """Wire session with shared state and start the outer agent."""
    session = AgentSession[SessionState](
        userdata=SessionState(),
        stt=ProviderRegistry.create_stt("whisperlive"),
        llm=ProviderRegistry.create_llm("google", model="gemini-2.0-flash"),
        tts=ProviderRegistry.create_tts("kokoro"),
        vad=ctx.proc.userdata["vad"],
        max_tool_steps=5,
        allow_interruptions=True,
        min_endpointing_delay=0.5,
        max_endpointing_delay=3.0,
    )

    await session.start(
        agent=OuterAgent(worker_delay=8.0),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
            text_input=True,
        ),
    )
    await ctx.connect()


if __name__ == "__main__":
    sys.argv = [sys.argv[0], "dev"]
    cli.run_app(server)
