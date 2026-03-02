"""Tests for the double loop architecture."""

import asyncio

import pytest

from e_agents.tasks.models import BackgroundTask, TaskNotification
from e_agents.tasks.registry import TaskRegistry
from e_agents.tasks.status import TaskPriority, TaskStatus


@pytest.fixture
def task_registry() -> TaskRegistry:
    """Create a fresh task registry."""
    return TaskRegistry()


async def test_task_registry_generates_unique_ids(task_registry: TaskRegistry) -> None:
    """Verify sequential unique ID generation."""
    id1 = task_registry.next_task_id()
    id2 = task_registry.next_task_id()
    id3 = task_registry.next_task_id()

    assert id1 != id2 != id3
    assert id1 == "bg_task_1"
    assert id2 == "bg_task_2"
    assert id3 == "bg_task_3"


async def test_background_task_completion() -> None:
    """Verify BackgroundTask tracks completion correctly."""
    task: BackgroundTask[dict] = BackgroundTask(
        id="test_1",
        name="Test Task",
        description="A test task",
        initiated_by="test_agent",
        status=TaskStatus.RUNNING,
    )

    assert task.status == TaskStatus.RUNNING
    assert task.result is None
    assert task.completed_at is None

    result = {"success": True, "data": [1, 2, 3]}
    task.complete(result)

    assert task.status == TaskStatus.COMPLETED
    assert task.result == result
    assert task.completed_at is not None
    assert task.duration_seconds is not None


async def test_background_task_failure() -> None:
    """Verify BackgroundTask tracks failure correctly."""
    task: BackgroundTask[dict] = BackgroundTask(
        id="test_2",
        name="Failing Task",
        description="A task that fails",
        initiated_by="test_agent",
        status=TaskStatus.RUNNING,
    )

    error = ValueError("Something went wrong")
    task.fail(error)

    assert task.status == TaskStatus.FAILED
    assert task.error == error
    assert task.completed_at is not None


async def test_background_task_default_priority() -> None:
    """Verify BackgroundTask defaults to NORMAL priority."""
    task: BackgroundTask[str] = BackgroundTask(
        id="p1", name="Default", description="", initiated_by="agent", status=TaskStatus.RUNNING
    )
    assert task.priority == TaskPriority.NORMAL
    assert task.priority_order == 1


@pytest.mark.parametrize(
    ("priority", "expected_order"),
    [(TaskPriority.HIGH, 0), (TaskPriority.NORMAL, 1), (TaskPriority.LOW, 2)],
    ids=["high", "normal", "low"],
)
async def test_background_task_priority_ordering(priority: TaskPriority, expected_order: int) -> None:
    """Verify priority numeric ordering."""
    task: BackgroundTask[str] = BackgroundTask(
        id="p", name="T", description="", initiated_by="a", priority=priority, status=TaskStatus.RUNNING
    )
    assert task.priority_order == expected_order


async def test_task_registry_pending_notifications(task_registry: TaskRegistry) -> None:
    """Verify pending notifications are correctly filtered by agent."""
    task1: BackgroundTask[str] = BackgroundTask(
        id="t1", name="Task 1", description="", initiated_by="agent_a", status=TaskStatus.COMPLETED
    )
    task2: BackgroundTask[str] = BackgroundTask(
        id="t2", name="Task 2", description="", initiated_by="agent_b", status=TaskStatus.COMPLETED
    )
    task3: BackgroundTask[str] = BackgroundTask(
        id="t3", name="Task 3", description="", initiated_by="agent_a", status=TaskStatus.COMPLETED
    )

    task_registry.tasks = {"t1": task1, "t2": task2, "t3": task3}
    task_registry.notifications = [
        TaskNotification(task=task1),
        TaskNotification(task=task2),
        TaskNotification(task=task3),
    ]

    all_pending = task_registry.get_pending_notifications()
    assert len(all_pending) == 3

    agent_a_pending = task_registry.get_pending_notifications(agent_id="agent_a")
    assert len(agent_a_pending) == 2
    assert all(n.task.initiated_by == "agent_a" for n in agent_a_pending)

    task_registry.acknowledge_notification("t1")
    all_pending = task_registry.get_pending_notifications()
    assert len(all_pending) == 2


async def test_task_registry_notifications_ordered_by_priority(task_registry: TaskRegistry) -> None:
    """Verify pending notifications return ordered by priority (HIGH first)."""
    low_task: BackgroundTask[str] = BackgroundTask(
        id="low", name="Low", description="", initiated_by="a", priority=TaskPriority.LOW, status=TaskStatus.COMPLETED
    )
    high_task: BackgroundTask[str] = BackgroundTask(
        id="high", name="High", description="", initiated_by="a", priority=TaskPriority.HIGH, status=TaskStatus.COMPLETED
    )
    normal_task: BackgroundTask[str] = BackgroundTask(
        id="normal", name="Normal", description="", initiated_by="a", priority=TaskPriority.NORMAL, status=TaskStatus.COMPLETED
    )

    task_registry.notifications = [
        TaskNotification(task=low_task),
        TaskNotification(task=high_task),
        TaskNotification(task=normal_task),
    ]

    ordered = task_registry.get_pending_notifications()
    assert [n.task.priority for n in ordered] == [TaskPriority.HIGH, TaskPriority.NORMAL, TaskPriority.LOW]


async def test_task_registry_get_next_priority_notification(task_registry: TaskRegistry) -> None:
    """Verify get_next_priority_notification returns highest priority."""
    low: BackgroundTask[str] = BackgroundTask(
        id="l", name="L", description="", initiated_by="a", priority=TaskPriority.LOW, status=TaskStatus.COMPLETED
    )
    high: BackgroundTask[str] = BackgroundTask(
        id="h", name="H", description="", initiated_by="a", priority=TaskPriority.HIGH, status=TaskStatus.COMPLETED
    )

    task_registry.notifications = [TaskNotification(task=low), TaskNotification(task=high)]

    nxt = task_registry.get_next_priority_notification()
    assert nxt is not None
    assert nxt.task.priority == TaskPriority.HIGH

    empty = task_registry.get_next_priority_notification(agent_id="nonexistent")
    assert empty is None


async def test_task_registry_running_tasks(task_registry: TaskRegistry) -> None:
    """Verify filtering of running tasks by agent."""
    task1: BackgroundTask[str] = BackgroundTask(
        id="t1", name="Running 1", description="", initiated_by="agent_a", status=TaskStatus.RUNNING
    )
    task2: BackgroundTask[str] = BackgroundTask(
        id="t2", name="Completed", description="", initiated_by="agent_a", status=TaskStatus.COMPLETED
    )
    task3: BackgroundTask[str] = BackgroundTask(
        id="t3", name="Running 2", description="", initiated_by="agent_b", status=TaskStatus.RUNNING
    )

    task_registry.tasks = {"t1": task1, "t2": task2, "t3": task3}

    all_running = task_registry.get_running_tasks()
    assert len(all_running) == 2

    agent_a_running = task_registry.get_running_tasks(agent_id="agent_a")
    assert len(agent_a_running) == 1
    assert agent_a_running[0].name == "Running 1"


async def test_double_loop_scenario_task_completes_during_handoff() -> None:
    """Verify background task results are available after agent handoff cycle."""
    registry = TaskRegistry()

    task_a: BackgroundTask[dict] = BackgroundTask(
        id=registry.next_task_id(),
        name="Deep Research",
        description="Researching topic",
        initiated_by="navigator_agent",
        priority=TaskPriority.HIGH,
        status=TaskStatus.RUNNING,
    )
    registry.tasks[task_a.id] = task_a

    await asyncio.sleep(0.01)

    task_a.complete({"findings": ["insight_1", "insight_2"], "count": 2})
    registry.notifications.append(TaskNotification(task=task_a))

    pending = registry.get_pending_notifications(agent_id="navigator_agent")

    assert len(pending) == 1
    assert pending[0].task.id == task_a.id
    assert pending[0].task.status == TaskStatus.COMPLETED
    assert pending[0].task.result == {"findings": ["insight_1", "insight_2"], "count": 2}

    registry.acknowledge_notification(task_a.id)
    remaining = registry.get_pending_notifications(agent_id="navigator_agent")
    assert len(remaining) == 0


async def test_multiple_agents_multiple_tasks_scenario() -> None:
    """Verify complex multi-agent task lifecycle with priority ordering."""
    registry = TaskRegistry()

    task_1: BackgroundTask[dict] = BackgroundTask(
        id=registry.next_task_id(),
        name="Web Research",
        description="Searching web sources",
        initiated_by="navigator_agent",
        priority=TaskPriority.HIGH,
        status=TaskStatus.RUNNING,
    )
    registry.tasks[task_1.id] = task_1

    task_2: BackgroundTask[dict] = BackgroundTask(
        id=registry.next_task_id(),
        name="Fact Verification",
        description="Verifying claims",
        initiated_by="fact_checker_agent",
        priority=TaskPriority.NORMAL,
        status=TaskStatus.RUNNING,
    )
    registry.tasks[task_2.id] = task_2

    all_running = registry.get_running_tasks()
    assert len(all_running) == 2

    task_2.complete({"verified": True, "confidence": 0.85})
    registry.notifications.append(TaskNotification(task=task_2))

    fc_notifications = registry.get_pending_notifications(agent_id="fact_checker_agent")
    assert len(fc_notifications) == 1
    registry.acknowledge_notification(task_2.id)

    running_for_nav = registry.get_running_tasks(agent_id="navigator_agent")
    assert len(running_for_nav) == 1
    assert running_for_nav[0].name == "Web Research"

    task_1.complete({"results": ["A", "B", "C"], "total": 3})
    registry.notifications.append(TaskNotification(task=task_1))

    nav_notifications = registry.get_pending_notifications(agent_id="navigator_agent")
    assert len(nav_notifications) == 1
    assert nav_notifications[0].task.name == "Web Research"
    assert nav_notifications[0].task.result is not None
    assert nav_notifications[0].task.result["total"] == 3


async def test_background_task_awaitable() -> None:
    """Verify BackgroundTask future is correctly awaitable."""
    task: BackgroundTask[int] = BackgroundTask(
        id="await_test",
        name="Awaitable Task",
        description="Test awaiting",
        initiated_by="test_agent",
        status=TaskStatus.RUNNING,
    )

    async def complete_after_delay() -> None:
        await asyncio.sleep(0.05)
        task.complete(42)

    asyncio.create_task(complete_after_delay())

    result = await task.wait()

    assert result == 42
    assert task.status == TaskStatus.COMPLETED
