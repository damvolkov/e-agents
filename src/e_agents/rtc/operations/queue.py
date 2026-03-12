"""Priority-based async task queue with cancellation and completion callbacks."""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable, Coroutine
from typing import Any


@dataclasses.dataclass(order=True)
class QueuedTask:
    """Single entry in the priority queue."""

    priority: int
    task_id: str = dataclasses.field(compare=False)
    name: str = dataclasses.field(compare=False)
    coro: Coroutine[Any, Any, Any] = dataclasses.field(compare=False, repr=False)
    cancellable: bool = dataclasses.field(default=True, compare=False)
    on_done: Callable[[TaskResult], None] | None = dataclasses.field(
        default=None, compare=False, repr=False,
    )
    _handle: asyncio.Task[Any] | None = dataclasses.field(
        default=None, compare=False, repr=False,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class TaskResult:
    """Immutable snapshot of a completed task."""

    task_id: str
    name: str
    status: str
    priority: int
    result: Any = None
    error: str | None = None


class TaskQueue:
    """Async task queue with priority ordering, concurrency limits, and cancellation."""

    __slots__ = (
        "_queue", "_running", "_completed", "_notified",
        "_semaphore", "_max_concurrent",
    )

    def __init__(self, max_concurrent: int = 3) -> None:
        self._queue: asyncio.PriorityQueue[QueuedTask] = asyncio.PriorityQueue()
        self._running: dict[str, QueuedTask] = {}
        self._completed: list[TaskResult] = []
        self._notified: set[str] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent

    async def submit(
        self,
        task_id: str,
        name: str,
        coro: Coroutine[Any, Any, Any],
        *,
        priority: int = 5,
        cancellable: bool = True,
        on_done: Callable[[TaskResult], None] | None = None,
    ) -> None:
        """Submit a coroutine for prioritized background execution."""
        entry = QueuedTask(
            priority=priority,
            task_id=task_id,
            name=name,
            coro=coro,
            cancellable=cancellable,
            on_done=on_done,
        )
        await self._queue.put(entry)
        asyncio.create_task(self._process())

    async def _process(self) -> None:
        """Dequeue and execute the next task within semaphore limits."""
        await self._semaphore.acquire()
        try:
            entry = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            self._semaphore.release()
            return
        self._running[entry.task_id] = entry
        entry._handle = asyncio.create_task(self._execute(entry))

    async def _execute(self, entry: QueuedTask) -> None:
        """Run a single task, record result, fire callback."""
        try:
            result = await entry.coro
            task_result = TaskResult(
                task_id=entry.task_id, name=entry.name,
                status="done", priority=entry.priority, result=result,
            )
        except asyncio.CancelledError:
            task_result = TaskResult(
                task_id=entry.task_id, name=entry.name,
                status="cancelled", priority=entry.priority,
            )
        except Exception as exc:
            task_result = TaskResult(
                task_id=entry.task_id, name=entry.name,
                status="error", priority=entry.priority, error=str(exc),
            )
        finally:
            self._running.pop(entry.task_id, None)
            self._semaphore.release()

        self._completed.append(task_result)
        if entry.on_done:
            entry.on_done(task_result)

    async def cancel(self, task_id: str) -> bool:
        """Cancel a running task by ID."""
        entry = self._running.get(task_id)
        if entry and entry.cancellable and entry._handle:
            entry._handle.cancel()
            return True
        return False

    async def cancel_by_name(self, name: str) -> int:
        """Cancel all running tasks matching a name."""
        cancelled = 0
        for entry in list(self._running.values()):
            if entry.name == name and entry.cancellable and entry._handle:
                entry._handle.cancel()
                cancelled += 1
        return cancelled

    async def cancel_all(self) -> int:
        """Cancel every cancellable running task."""
        cancelled = 0
        for entry in list(self._running.values()):
            if entry.cancellable and entry._handle:
                entry._handle.cancel()
                cancelled += 1
        return cancelled

    def mark_notified(self, task_id: str) -> None:
        """Mark a task as proactively delivered (skip in drain)."""
        self._notified.add(task_id)

    def drain_completed(self) -> list[TaskResult]:
        """Pop and return completed results not yet proactively delivered."""
        results = [r for r in self._completed if r.task_id not in self._notified]
        self._completed.clear()
        self._notified.clear()
        return results

    @property
    def pending(self) -> list[dict[str, Any]]:
        """Snapshot of running tasks."""
        return [
            {"task_id": e.task_id, "name": e.name, "priority": e.priority, "status": "running"}
            for e in self._running.values()
        ]

    @property
    def is_empty(self) -> bool:
        return self._queue.empty() and not self._running
