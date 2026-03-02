"""Task registry for managing background tasks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from e_agents.tasks.models import BackgroundTask, TaskNotification
from e_agents.tasks.status import TaskStatus


@dataclass
class TaskRegistry:
    """Central registry for all background tasks and notifications."""

    tasks: dict[str, BackgroundTask[Any]] = field(default_factory=dict)
    notifications: list[TaskNotification] = field(default_factory=list)
    _task_counter: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_task_id(self) -> str:
        """Generate next task ID."""
        self._task_counter += 1
        return f"bg_task_{self._task_counter}"

    def get_pending_notifications(self, agent_id: str | None = None) -> list[TaskNotification]:
        """Get unacknowledged notifications ordered by priority."""
        pending = [
            n
            for n in self.notifications
            if not n.acknowledged and (agent_id is None or n.task.initiated_by == agent_id)
        ]
        return sorted(pending, key=lambda n: n.priority_order)

    def get_next_priority_notification(self, agent_id: str | None = None) -> TaskNotification | None:
        """Get the highest-priority unacknowledged notification."""
        pending = self.get_pending_notifications(agent_id)
        return pending[0] if pending else None

    def acknowledge_notification(self, task_id: str) -> bool:
        """Mark a notification as acknowledged."""
        for notification in self.notifications:
            if notification.task.id == task_id:
                notification.acknowledged = True
                return True
        return False

    def get_running_tasks(self, agent_id: str | None = None) -> list[BackgroundTask[Any]]:
        """Get currently running tasks, optionally filtered by agent."""
        return [
            t
            for t in self.tasks.values()
            if t.status == TaskStatus.RUNNING and (agent_id is None or t.initiated_by == agent_id)
        ]
