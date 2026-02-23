"""Task data models."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

from e_template_agents.tasks.status import TaskPriority, TaskStatus

T = TypeVar("T")

_PRIORITY_ORDER: dict[TaskPriority, int] = {
    TaskPriority.HIGH: 0,
    TaskPriority.NORMAL: 1,
    TaskPriority.LOW: 2,
}


@dataclass
class BackgroundTask(Generic[T]):  # noqa: UP046
    """Represents a background task with callback support."""

    id: str
    name: str
    description: str
    initiated_by: str
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    result: T | None = None
    error: Exception | None = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    _future: asyncio.Future[T] = field(default_factory=asyncio.Future)

    async def wait(self) -> T:
        """Wait for task completion."""
        return await self._future

    def complete(self, result: T) -> None:
        """Mark task as completed with result."""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()
        if not self._future.done():
            self._future.set_result(result)

    def fail(self, error: Exception) -> None:
        """Mark task as failed with error."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
        if not self._future.done():
            self._future.set_exception(error)

    @property
    def duration_seconds(self) -> float | None:
        """Get task duration in seconds."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def priority_order(self) -> int:
        """Numeric priority for sorting (lower = higher priority)."""
        return _PRIORITY_ORDER.get(self.priority, 1)


@dataclass
class TaskNotification:
    """Notification about a completed task."""

    task: BackgroundTask[Any]
    acknowledged: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def priority_order(self) -> int:
        """Numeric priority for sorting (lower = higher priority)."""
        return self.task.priority_order
