"""Navigator agent - Main outer-loop dispatcher with background task capabilities."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from livekit.agents import Agent, RunContext, function_tool

from e_template_agents.tasks.status import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from e_template_agents.models.agent import AgentConfig
    from e_template_agents.sessions.double_loop import DoubleLoopUserData
    from e_template_agents.tasks.executor import TaskExecutor


class NavigatorAgent(Agent):
    """Main outer-loop agent that manages conversation and delegates research."""

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(instructions=config.instructions)
        self._config = config

    @property
    def _userdata(self) -> DoubleLoopUserData:
        return self.session.userdata

    @property
    def _executor(self) -> TaskExecutor:
        return self._userdata.task_executor

    async def on_enter(self) -> None:
        """Handle agent activation and pending notifications."""
        pending = self._userdata.task_registry.get_pending_notifications(agent_id=self.id)

        if pending:
            results: list[str] = []
            for notification in pending:
                task = notification.task
                self._userdata.task_registry.acknowledge_notification(task.id)
                match task.status:
                    case TaskStatus.COMPLETED:
                        results.append(f"Topic '{task.name}': {task.result}")
                    case _:
                        results.append(f"Topic '{task.name}': could not find detailed information")

            self.session.generate_reply(
                instructions=(
                    "You have just gathered new information. Present these findings naturally "
                    "as if you just finished thinking about it. Findings:\n"
                    + "\n".join(results)
                )
            )
            return

        if not hasattr(self, "_entered_before"):
            self._entered_before = True
            self.session.generate_reply(
                instructions=(
                    "Greet the user warmly. You are a research assistant ready to help them "
                    "explore any topic. Be friendly and conversational. Ask what they would "
                    "like to learn about today."
                )
            )
        else:
            running = self._userdata.task_registry.get_running_tasks(agent_id=self.id)
            if running:
                self.session.generate_reply(
                    instructions="Welcome the user back naturally. You are still thinking about some topics."
                )
            else:
                self.session.generate_reply(instructions="Welcome the user back and ask how you can help.")

    @function_tool()
    async def research_topic(self, topic: str, context: RunContext) -> str:
        """Research a topic thoroughly. Use this for any question requiring deep investigation.

        Args:
            topic: The topic or question to research.
        """

        async def _deep_research() -> dict:
            await asyncio.sleep(5)
            return {
                "topic": topic,
                "summary": f"Comprehensive findings on '{topic}' covering key aspects, recent developments, and expert perspectives.",
                "key_points": [
                    f"Primary insight about {topic}",
                    f"Historical context of {topic}",
                    f"Current trends related to {topic}",
                ],
                "sources_consulted": 7,
                "confidence": "high",
            }

        self._executor.submit(
            name=topic,
            description=f"Deep research on: {topic}",
            coro=_deep_research(),
            initiated_by=self.id,
            priority=TaskPriority.HIGH,
        )

        return "Research initiated. Engage the user naturally while processing completes."

    @function_tool()
    async def quick_lookup(self, query: str, context: RunContext) -> str:
        """Quick factual lookup for simple questions that need a fast answer.

        Args:
            query: A simple factual question.
        """
        await asyncio.sleep(0.5)
        return (
            f"Quick lookup result for '{query}': This is a template response. "
            "In production, connect to a real knowledge API or search engine. "
            "Present the answer naturally to the user."
        )

    @function_tool()
    async def deep_analysis(self, topic: str, context: RunContext) -> str:
        """Perform deep analysis on a complex topic. Heavy background operation.

        Args:
            topic: The complex topic requiring detailed analysis.
        """

        async def _analyze() -> dict:
            await asyncio.sleep(6)
            return {
                "topic": topic,
                "analysis": f"Multi-dimensional analysis of '{topic}'",
                "dimensions": ["technical", "historical", "practical", "theoretical"],
                "conclusion": f"Key takeaway: {topic} has significant implications across multiple domains.",
                "depth": "comprehensive",
            }

        self._executor.submit(
            name=f"analysis of {topic}",
            description=f"Deep multi-dimensional analysis: {topic}",
            coro=_analyze(),
            initiated_by=self.id,
            priority=TaskPriority.HIGH,
        )

        return "Analysis initiated. Continue the conversation naturally."

    @function_tool()
    async def verify_claim(self, claim: str, context: RunContext) -> str:
        """Verify a specific claim or statement. Heavy background operation.

        Args:
            claim: The claim or statement to verify.
        """

        async def _verify() -> dict:
            await asyncio.sleep(4)
            return {
                "claim": claim,
                "verdict": "partially_supported",
                "explanation": f"The claim '{claim}' has supporting evidence but requires nuance.",
                "sources_checked": 5,
                "confidence": "moderate",
            }

        self._executor.submit(
            name=f"verification: {claim[:50]}",
            description=f"Fact-checking: {claim}",
            coro=_verify(),
            initiated_by=self.id,
            priority=TaskPriority.NORMAL,
        )

        return "Verification initiated. Keep the conversation going naturally."

    @function_tool()
    async def transfer_to_researcher(self, context: RunContext) -> tuple[Agent, str]:
        """Hand off to the research specialist for thorough web-based investigation."""
        agents: dict[str, Agent] = context.userdata.agents
        return agents["web_searcher"], "Transitioning to deeper research mode."

    @function_tool()
    async def transfer_to_analyst(self, context: RunContext) -> tuple[Agent, str]:
        """Hand off to the analyst for complex topic synthesis."""
        agents: dict[str, Agent] = context.userdata.agents
        return agents["analyst"], "Transitioning to analysis mode."

    @function_tool()
    async def transfer_to_fact_checker(self, context: RunContext) -> tuple[Agent, str]:
        """Hand off to the fact checker for claim verification."""
        agents: dict[str, Agent] = context.userdata.agents
        return agents["fact_checker"], "Transitioning to verification mode."

    @function_tool()
    async def check_background_tasks(self, context: RunContext) -> str:
        """Check status of all running background tasks."""
        registry = self._userdata.task_registry

        running = registry.get_running_tasks()
        pending_notifications = registry.get_pending_notifications()

        parts: list[str] = []

        if running:
            parts.append(f"{len(running)} task(s) still processing:")
            parts.extend(f"  - {task.name}" for task in running)

        if pending_notifications:
            parts.append(f"{len(pending_notifications)} result(s) ready:")
            for notif in pending_notifications:
                parts.append(f"  - {notif.task.name}: {notif.task.status.value}")

        return "\n".join(parts) if parts else "No pending work."
