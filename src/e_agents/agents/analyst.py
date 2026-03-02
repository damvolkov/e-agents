"""Analyst agent - Inner-loop specialist for information synthesis and analysis."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from livekit.agents import Agent, RunContext, function_tool

from e_agents.tasks.status import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from e_agents.models.agent import AgentConfig
    from e_agents.sessions.double_loop import DoubleLoopUserData
    from e_agents.tasks.executor import TaskExecutor


class AnalystAgent(Agent):
    """Inner-loop specialist for synthesizing and analyzing complex topics."""

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
        """Handle activation."""
        pending = self._userdata.task_registry.get_pending_notifications()

        for notification in pending:
            if notification.task.initiated_by != self.id and not notification.acknowledged:
                self._userdata.task_registry.acknowledge_notification(notification.task.id)

        self.session.generate_reply(
            instructions=(
                "You are now in analysis mode. Ask the user what they want analyzed "
                "in depth, or begin analyzing based on the conversation context."
            )
        )

    @function_tool()
    async def compare_sources(self, topics: list[str], context: RunContext) -> str:
        """Compare and contrast multiple topics or viewpoints. Heavy background operation.

        Args:
            topics: List of topics or viewpoints to compare.
        """

        async def _compare() -> dict:
            await asyncio.sleep(5)
            return {
                "topics": topics,
                "comparison": {
                    "similarities": [f"Both {topics[0]} and others share common foundations"],
                    "differences": ["Key distinction: each topic has unique implications"],
                    "synthesis": f"Comparing {len(topics)} perspectives reveals complementary insights.",
                },
                "recommendation": "A balanced view considers all perspectives.",
            }

        self._executor.submit(
            name=f"comparison: {', '.join(topics[:3])}",
            description=f"Comparing {len(topics)} topics",
            coro=_compare(),
            initiated_by=self.id,
            priority=TaskPriority.NORMAL,
        )

        return "Comparative analysis initiated. Continue the conversation."

    @function_tool()
    async def summarize_topic(self, content: str, context: RunContext) -> str:
        """Summarize a topic or content concisely. Light operation.

        Args:
            content: The content or topic to summarize.
        """
        await asyncio.sleep(0.5)
        return (
            f"Summary: The topic '{content[:100]}' can be understood through its core principles, "
            "practical applications, and broader implications. The key takeaway is that "
            "understanding requires both theoretical knowledge and practical context."
        )

    @function_tool()
    async def generate_report(self, topic: str, context: RunContext) -> str:
        """Generate a comprehensive analytical report. Heavy background operation.

        Args:
            topic: The topic for the report.
        """

        async def _build_report() -> dict:
            await asyncio.sleep(7)
            return {
                "topic": topic,
                "sections": [
                    {"title": "Overview", "content": f"Comprehensive overview of {topic}"},
                    {"title": "Key Findings", "content": "Three major findings emerged from the analysis"},
                    {"title": "Implications", "content": "These findings have significant practical implications"},
                    {
                        "title": "Recommendations",
                        "content": "Based on the analysis, several actionable steps are recommended",
                    },
                ],
                "word_count": 1200,
                "quality": "high",
            }

        self._executor.submit(
            name=f"report: {topic}",
            description=f"Generating comprehensive report on: {topic}",
            coro=_build_report(),
            initiated_by=self.id,
            priority=TaskPriority.HIGH,
        )

        return "Report generation initiated. Keep the conversation flowing."

    @function_tool()
    async def transfer_to_navigator(self, context: RunContext) -> tuple[Agent, str]:
        """Return to the main conversation flow."""
        agents: dict[str, Agent] = context.userdata.agents
        registry = self._userdata.task_registry
        completed = [
            t for t in registry.tasks.values() if t.initiated_by == self.id and t.status == TaskStatus.COMPLETED
        ]

        msg = "Returning to main conversation."
        if completed:
            msg += f" {len(completed)} analysis task(s) completed."
        return agents["navigator"], msg

    @function_tool()
    async def transfer_to_researcher(self, context: RunContext) -> tuple[Agent, str]:
        """Hand off to the researcher for additional information gathering."""
        agents: dict[str, Agent] = context.userdata.agents
        return agents["web_searcher"], "Transitioning to research mode."

    @function_tool()
    async def transfer_to_fact_checker(self, context: RunContext) -> tuple[Agent, str]:
        """Hand off to the fact checker for verification."""
        agents: dict[str, Agent] = context.userdata.agents
        return agents["fact_checker"], "Transitioning to verification mode."
