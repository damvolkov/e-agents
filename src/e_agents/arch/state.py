"""Reactive agent architecture — stateful container.

Framework-agnostic. This object IS the RunContext/userdata.
Manages: agent registry, event queue, background tasks, k/v store, thread ref.

── Naming Convention ──────────────────────────────────────────────────────────
Methods follow verb_entity pattern:
  Agent ops:  register_agent, register_agents, get_agent, set_current
  Event ops:  push_event, wait_event, drain_events
  Task ops:   submit_task, cancel_task
  Store ops:  set, get, put, drop, has  (short — dict-like k/v interface)

── Extending ──────────────────────────────────────────────────────────────────
    class ClinicState(ReactiveState):
        def __init__(self, *, patient_id: str | None = None, **kwargs):
            super().__init__(**kwargs)
            self.patient_id = patient_id
────────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from e_agents.arch.models import (
    AgentEntry,
    Event,
    EventEffect,
    EventPolicy,
    Priority,
    TaskConfig,
    TaskStatus,
)


class ReactiveState:
    __slots__ = (
        "_agents",
        "_current_name",
        "_prev_name",
        "_queue",
        "_store",
        "_tasks",
        "_task_handles",
        "_semaphore",
        "_policy",
        "_lock",
        "_thread",
    )

    def __init__(
        self,
        *,
        policy: EventPolicy | None = None,
        max_concurrency: int = 5,
    ) -> None:
        # Agent registry
        self._agents: dict[str, AgentEntry] = {}
        self._current_name: str | None = None
        self._prev_name: str | None = None

        # Event queue (inner → outer bridge)
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

        # Dynamic k/v store
        self._store: dict[str, Any] = {}

        # Background tasks
        self._tasks: dict[str, TaskConfig] = {}
        self._task_handles: dict[str, asyncio.Task[None]] = {}
        self._semaphore = asyncio.Semaphore(max_concurrency)

        # Policy + sync
        self._policy = policy or EventPolicy()
        self._lock = asyncio.Lock()

        # Conversation thread (framework provides its own type)
        self._thread: Any = None

    # ═════════════════════════════════════════════════════════════════════════
    #  AGENT OPS — register_agent, register_agents, get_agent, set_current
    # ═════════════════════════════════════════════════════════════════════════

    def register_agent(self, name: str, ref: Any, *, role: str = "inner", **meta: Any) -> None:
        """Register an agent instance. O(1)."""
        self._agents[name] = AgentEntry(name=name, ref=ref, role=role, meta=meta)

    def register_agents(self, agents: dict[str, Any], *, role: str = "inner") -> None:
        """Batch register. O(n)."""
        for name, ref in agents.items():
            self.register_agent(name, ref, role=role)

    def get_agent(self, name: str) -> Any:
        """Retrieve agent ref by name. O(1). Raises KeyError."""
        return self._agents[name].ref

    def set_current(self, name: str) -> None:
        """Mark an agent as active. Tracks previous automatically."""
        if self._current_name and self._current_name != name:
            self._prev_name = self._current_name
            if slot := self._agents.get(self._prev_name):
                slot.active = False
        self._current_name = name
        if slot := self._agents.get(name):
            slot.active = True

    @property
    def current(self) -> Any | None:
        return self._agents[self._current_name].ref if self._current_name else None

    @property
    def current_name(self) -> str | None:
        return self._current_name

    @property
    def prev(self) -> Any | None:
        return self._agents[self._prev_name].ref if self._prev_name else None

    @property
    def prev_name(self) -> str | None:
        return self._prev_name

    @property
    def agent_names(self) -> list[str]:
        return list(self._agents)

    @property
    def agent_entries(self) -> dict[str, AgentEntry]:
        return dict(self._agents)

    # ═════════════════════════════════════════════════════════════════════════
    #  EVENT OPS — push_event, wait_event, drain_events
    # ═════════════════════════════════════════════════════════════════════════

    async def push_event(self, event: Event) -> None:
        """Push an event into the queue. Called by inner agents/tools. O(1)."""
        await self._queue.put(event)

    async def wait_event(self, timeout: float | None = None) -> Event | None:
        """Block until next event or timeout."""
        with suppress(asyncio.TimeoutError):
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        return None

    def drain_events(self) -> list[Event]:
        """Non-blocking: grab all pending events sorted by priority. O(k log k)."""
        pending: list[Event] = []
        while not self._queue.empty():
            with suppress(asyncio.QueueEmpty):
                pending.append(self._queue.get_nowait())
        return sorted(pending, key=lambda e: (e.priority, e.created_at))

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    # ═════════════════════════════════════════════════════════════════════════
    #  TASK OPS — submit_task, cancel_task
    # ═════════════════════════════════════════════════════════════════════════

    async def submit_task(
        self,
        config: TaskConfig,
        handler: Callable[..., Awaitable[dict[str, Any]]],
        **kwargs: Any,
    ) -> str:
        """Submit a background task. Returns task_id."""
        self._tasks[config.id] = config

        await self.push_event(Event(
            task_id=config.id,
            source=config.source,
            priority=Priority.BACKGROUND,
            status=TaskStatus.RUNNING,
            effect=EventEffect.NOOP,
            payload={"task_name": config.name},
        ))

        self._task_handles[config.id] = asyncio.create_task(
            self._run_task(config, handler, kwargs),
        )
        return config.id

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task. Returns True if cancelled."""
        if handle := self._task_handles.pop(task_id, None):
            handle.cancel()
            self._tasks.pop(task_id, None)
            await self.push_event(Event(
                task_id=task_id,
                source="system",
                priority=Priority.BACKGROUND,
                status=TaskStatus.CANCELLED,
                effect=EventEffect.NOOP,
            ))
            return True
        return False

    @property
    def running_tasks(self) -> dict[str, TaskConfig]:
        return dict(self._tasks)

    @property
    def running_count(self) -> int:
        return len(self._tasks)

    # ─── Task runner (private) ───────────────────────────────────────────

    async def _run_task(
        self,
        config: TaskConfig,
        handler: Callable[..., Awaitable[dict[str, Any]]],
        kwargs: dict[str, Any],
    ) -> None:
        """Execute task with semaphore-bounded concurrency."""
        async with self._semaphore:
            try:
                result = await handler(**kwargs)
                await self.push_event(Event(
                    task_id=config.id,
                    source=config.source,
                    priority=config.priority,
                    status=TaskStatus.COMPLETED,
                    effect=config.effect,
                    payload=result,
                ))
            except Exception as exc:
                await self.push_event(Event(
                    task_id=config.id,
                    source=config.source,
                    priority=max(config.priority, Priority.HIGH),
                    status=TaskStatus.FAILED,
                    effect=EventEffect.INTERRUPT,
                    payload={"error": str(exc), "error_type": type(exc).__name__},
                ))
            finally:
                self._tasks.pop(config.id, None)
                self._task_handles.pop(config.id, None)

    # ═════════════════════════════════════════════════════════════════════════
    #  STORE OPS — set, get, put, drop, has (dict-like k/v interface)
    # ═════════════════════════════════════════════════════════════════════════

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def has(self, key: str) -> bool:
        return key in self._store

    async def put(self, data: dict[str, Any]) -> None:
        """Batch upsert."""
        async with self._lock:
            self._store.update(data)

    async def drop(self, key: str) -> Any | None:
        async with self._lock:
            return self._store.pop(key, None)

    @property
    def keys(self) -> list[str]:
        return list(self._store)

    # ═════════════════════════════════════════════════════════════════════════
    #  THREAD — conversation context (framework sets its own type)
    # ═════════════════════════════════════════════════════════════════════════

    @property
    def thread(self) -> Any:
        return self._thread

    @thread.setter
    def thread(self, value: Any) -> None:
        self._thread = value

    # ═════════════════════════════════════════════════════════════════════════
    #  POLICY
    # ═════════════════════════════════════════════════════════════════════════

    @property
    def policy(self) -> EventPolicy:
        return self._policy

    @policy.setter
    def policy(self, value: EventPolicy) -> None:
        self._policy = value

    # ═════════════════════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═════════════════════════════════════════════════════════════════════════

    async def shutdown(self) -> None:
        """Cancel all active tasks. Call on session teardown."""
        for handle in self._task_handles.values():
            handle.cancel()
        if self._task_handles:
            await asyncio.gather(*self._task_handles.values(), return_exceptions=True)
        self._task_handles.clear()
        self._tasks.clear()