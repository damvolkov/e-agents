"""System tools (task status, etc.)."""

from __future__ import annotations

from livekit.agents import RunContext


async def check_background_tasks(self, context: RunContext) -> str:
    """Check status of running background tasks."""
    running = self._registry.get_running_tasks()
    pending = self._registry.get_pending_notifications()

    parts: list[str] = []
    if running:
        parts.append(f"{len(running)} task(s) processing:")
        parts.extend(f"  - {t.name}" for t in running)
    if pending:
        parts.append(f"{len(pending)} result(s) ready:")
        parts.extend(f"  - {n.task.name}: {n.task.status.value}" for n in pending)

    return "\n".join(parts) if parts else "No pending work."
