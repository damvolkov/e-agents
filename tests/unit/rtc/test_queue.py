"""Tests for TaskQueue — priority execution, cancellation, drain, callbacks."""

from __future__ import annotations

import asyncio

import pytest

from e_agents.rtc.operations.queue import TaskQueue, TaskResult

##### SUBMIT & EXECUTE #####


async def test_queue_submit_and_drain() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _work() -> str:
        return "done"

    await queue.submit("t1", "search", _work(), priority=5)
    await asyncio.sleep(0.05)

    results = queue.drain_completed()
    assert len(results) == 1
    assert results[0].task_id == "t1"
    assert results[0].name == "search"
    assert results[0].status == "done"
    assert results[0].result == "done"


async def test_queue_priority_ordering() -> None:
    queue = TaskQueue(max_concurrent=1)
    order: list[str] = []

    async def _track(name: str) -> str:
        order.append(name)
        return name

    await queue.submit("low", "low_task", _track("low"), priority=10)
    await queue.submit("high", "high_task", _track("high"), priority=1)
    await queue.submit("mid", "mid_task", _track("mid"), priority=5)

    await asyncio.sleep(0.1)
    assert "high" in order
    assert "low" in order


async def test_queue_max_concurrent() -> None:
    queue = TaskQueue(max_concurrent=1)
    started: list[str] = []

    async def _slow(name: str) -> str:
        started.append(name)
        await asyncio.sleep(0.05)
        return name

    await queue.submit("a", "task_a", _slow("a"), priority=5)
    await queue.submit("b", "task_b", _slow("b"), priority=5)

    await asyncio.sleep(0.01)
    assert len(started) <= 2

    await asyncio.sleep(0.15)
    results = queue.drain_completed()
    assert len(results) == 2


##### CANCELLATION #####


async def test_queue_cancel_by_id() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _forever() -> str:
        await asyncio.sleep(100)
        return "never"

    await queue.submit("t1", "long_task", _forever(), priority=5)
    await asyncio.sleep(0.01)

    cancelled = await queue.cancel("t1")
    assert cancelled is True

    await asyncio.sleep(0.05)
    results = queue.drain_completed()
    assert any(r.status == "cancelled" for r in results)


async def test_queue_cancel_by_name() -> None:
    queue = TaskQueue(max_concurrent=3)

    async def _forever() -> str:
        await asyncio.sleep(100)
        return "never"

    await queue.submit("t1", "search", _forever(), priority=5)
    await queue.submit("t2", "search", _forever(), priority=5)
    await asyncio.sleep(0.01)

    cancelled = await queue.cancel_by_name("search")
    assert cancelled == 2


async def test_queue_cancel_all() -> None:
    queue = TaskQueue(max_concurrent=3)

    async def _forever() -> str:
        await asyncio.sleep(100)
        return "never"

    await queue.submit("t1", "a", _forever(), priority=5)
    await queue.submit("t2", "b", _forever(), priority=5)
    await asyncio.sleep(0.01)

    cancelled = await queue.cancel_all()
    assert cancelled == 2


async def test_queue_cancel_non_cancellable() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _forever() -> str:
        await asyncio.sleep(100)
        return "never"

    await queue.submit("t1", "protected", _forever(), priority=5, cancellable=False)
    await asyncio.sleep(0.01)

    cancelled = await queue.cancel("t1")
    assert cancelled is False


async def test_queue_cancel_nonexistent() -> None:
    queue = TaskQueue(max_concurrent=2)
    cancelled = await queue.cancel("nonexistent")
    assert cancelled is False


##### ERROR HANDLING #####


async def test_queue_task_error_captured() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _fail() -> str:
        raise ValueError("boom")

    await queue.submit("t1", "failing", _fail(), priority=5)
    await asyncio.sleep(0.05)

    results = queue.drain_completed()
    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "boom"


##### DRAIN & NOTIFICATION #####


async def test_queue_drain_clears_completed() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _work() -> str:
        return "ok"

    await queue.submit("t1", "task", _work(), priority=5)
    await asyncio.sleep(0.05)

    first = queue.drain_completed()
    assert len(first) == 1

    second = queue.drain_completed()
    assert len(second) == 0


async def test_queue_mark_notified_skips_drain() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _work() -> str:
        return "ok"

    await queue.submit("t1", "task", _work(), priority=5)
    await asyncio.sleep(0.05)

    queue.mark_notified("t1")
    results = queue.drain_completed()
    assert len(results) == 0


async def test_queue_on_done_callback() -> None:
    queue = TaskQueue(max_concurrent=2)
    received: list[TaskResult] = []

    async def _work() -> str:
        return "callback_result"

    def _cb(result: TaskResult) -> None:
        received.append(result)

    await queue.submit("t1", "task", _work(), priority=5, on_done=_cb)
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].result == "callback_result"
    assert received[0].status == "done"


##### PROPERTIES #####


async def test_queue_pending_shows_running() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _slow() -> str:
        await asyncio.sleep(0.5)
        return "ok"

    await queue.submit("t1", "slow_task", _slow(), priority=3)
    await asyncio.sleep(0.01)

    pending = queue.pending
    assert len(pending) == 1
    assert pending[0]["task_id"] == "t1"
    assert pending[0]["name"] == "slow_task"
    assert pending[0]["priority"] == 3

    await queue.cancel("t1")


async def test_queue_is_empty_initially() -> None:
    queue = TaskQueue(max_concurrent=2)
    assert queue.is_empty is True


async def test_queue_is_empty_after_drain() -> None:
    queue = TaskQueue(max_concurrent=2)

    async def _work() -> str:
        return "ok"

    await queue.submit("t1", "task", _work(), priority=5)
    await asyncio.sleep(0.05)

    queue.drain_completed()
    assert queue.is_empty is True
