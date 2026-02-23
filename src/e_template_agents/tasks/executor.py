"""Task executor for background task management."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

import structlog

from e_template_agents.tasks.models import BackgroundTask, TaskNotification
from e_template_agents.tasks.registry import TaskRegistry
from e_template_agents.tasks.status import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from livekit.agents import AgentSession

logger = structlog.get_logger(__name__)

T = TypeVar("T")

type TaskCallback = Callable[[BackgroundTask[Any]], Coroutine[Any, Any, None]]


class TaskExecutor:
    """Executes background tasks and manages notifications."""

    __slots__ = ("_on_task_completed", "_registry", "_running_asyncio_tasks", "_session")

    def __init__(
        self,
        registry: TaskRegistry,
        session: AgentSession[Any],
        *,
        on_task_completed: TaskCallback | None = None,
    ) -> None:
        self._registry = registry
        self._session = session
        self._on_task_completed = on_task_completed
        self._running_asyncio_tasks: set[asyncio.Task[Any]] = set()

    def submit(
        self,
        name: str,
        description: str,
        coro: Coroutine[Any, Any, T],
        *,
        initiated_by: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        on_complete: TaskCallback | None = None,
    ) -> BackgroundTask[T]:
        """Submit a task for background execution."""
        task_id = self._registry.next_task_id()

        bg_task: BackgroundTask[T] = BackgroundTask(
            id=task_id,
            name=name,
            description=description,
            initiated_by=initiated_by,
            priority=priority,
            status=TaskStatus.RUNNING,
        )
        self._registry.tasks[task_id] = bg_task

        logger.info("background_task_submitted", task_id=task_id, name=name, priority=priority.value)

        async def _run_task() -> None:
            try:
                result = await coro
                bg_task.complete(result)
                logger.info("background_task_completed", task_id=task_id, name=name, duration=bg_task.duration_seconds)
            except Exception as e:
                bg_task.fail(e)
                logger.exception("background_task_failed", task_id=task_id, name=name, error=str(e))

            self._registry.notifications.append(TaskNotification(task=bg_task))

            callback = on_complete or self._on_task_completed
            if callback:
                try:
                    await callback(bg_task)
                except Exception as cb_err:
                    logger.exception("task_callback_failed", task_id=task_id, error=str(cb_err))

        asyncio_task = asyncio.create_task(_run_task(), name=task_id)
        self._running_asyncio_tasks.add(asyncio_task)
        asyncio_task.add_done_callback(self._running_asyncio_tasks.discard)

        return bg_task

    async def wait_all(self) -> None:
        """Wait for all running tasks to complete."""
        if self._running_asyncio_tasks:
            await asyncio.gather(*self._running_asyncio_tasks, return_exceptions=True)

    @property
    def has_running_tasks(self) -> bool:
        """Check if there are any running tasks."""
        return len(self._running_asyncio_tasks) > 0
