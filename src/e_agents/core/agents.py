"""Agent base classes for the double-loop architecture.

These classes are NEVER subclassed per-agent. Each agent is defined
entirely by its YAML config. The factory dynamically builds concrete
agent types by attaching tools and handoffs from the AgentDefinition.

Hierarchy:
    Agent (LiveKit)
    └── BaseAgent          — shared state access, agent resolution
        ├── DispatcherAgent — user-facing, delivers greeting + pending results
        └── SpecialistAgent — background worker, acknowledges foreign tasks
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livekit.agents import Agent

if TYPE_CHECKING:
    from e_agents.core.models import AgentDefinition, SessionState
    from e_agents.tasks.executor import TaskExecutor
    from e_agents.tasks.registry import TaskRegistry


class BaseAgent(Agent):
    """Common base with access to session state and task system."""

    def __init__(self, definition: AgentDefinition) -> None:
        super().__init__(instructions=definition.prompt)
        self._definition = definition
        self._available_agents: dict[str, Agent] = {}

    @property
    def _state(self) -> SessionState:
        return self.session.userdata

    @property
    def _executor(self) -> TaskExecutor:
        executor = self._state.task_executor
        if executor is None:
            raise RuntimeError("TaskExecutor not initialised on session state")
        return executor

    @property
    def _registry(self) -> TaskRegistry:
        return self._state.task_registry

    def _resolve_agent(self, name: str) -> Agent:
        """Resolve a handoff target by name. O(1) dict lookup."""
        agent = self._available_agents.get(name) or self._state.agents.get(name)
        if agent is None:
            raise KeyError(f"Agent '{name}' not found. Available: {list(self._state.agents)}")
        return agent


class DispatcherAgent(BaseAgent):
    """User-facing agent. Always attends the user."""

    async def on_enter(self) -> None:
        """Deliver pending results or greeting on activation."""
        pending = self._registry.get_pending_notifications(agent_id=self.id)

        if pending:
            findings = self._format_notifications(pending)
            self.session.generate_reply(
                instructions=(
                    "You just received new findings from your background team. "
                    "Present them naturally. Findings:\n" + "\n".join(findings)
                )
            )
            return

        if self._definition.greeting:
            self.session.say(self._definition.greeting)

    def _format_notifications(self, notifications: list) -> list[str]:
        """Format pending task notifications into presentable strings."""
        findings: list[str] = []
        for notification in notifications:
            self._registry.acknowledge_notification(notification.task.id)
            match notification.task.status.value:
                case "completed":
                    findings.append(f"'{notification.task.name}': {notification.task.result}")
                case _:
                    findings.append(f"'{notification.task.name}': no detailed info available")
        return findings


class SpecialistAgent(BaseAgent):
    """Background specialist. Performs focused tasks and returns control."""

    async def on_enter(self) -> None:
        """Acknowledge foreign notifications and introduce self."""
        for notification in self._registry.get_pending_notifications():
            if notification.task.initiated_by != self.id and not notification.acknowledged:
                self._registry.acknowledge_notification(notification.task.id)

        self.session.generate_reply(instructions=f"You are now active as {self._definition.name}. Offer to help.")
