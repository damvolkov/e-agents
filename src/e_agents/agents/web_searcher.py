"""Web searcher agent - Inner-loop specialist for web-based research."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from livekit.agents import Agent, RunContext, function_tool

from e_agents.tasks.status import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from e_agents.models.agent import AgentConfig
    from e_agents.sessions.double_loop import DoubleLoopUserData
    from e_agents.tasks.executor import TaskExecutor


class WebSearcherAgent(Agent):
    """Inner-loop specialist for web search and information retrieval."""

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
        """Handle activation, check for pending results."""
        pending = self._userdata.task_registry.get_pending_notifications()

        for notification in pending:
            task = notification.task
            if task.initiated_by != self.id and not notification.acknowledged:
                self._userdata.task_registry.acknowledge_notification(task.id)

        self.session.generate_reply(
            instructions=(
                "You are now in research mode. Ask the user what specific information "
                "they need you to search for, or start searching based on context."
            )
        )

    @function_tool()
    async def search_web(self, query: str, context: RunContext) -> str:
        """Search the web for information on a topic. Heavy background operation.

        Args:
            query: Search query string.
        """

        async def _web_search() -> dict:
            await asyncio.sleep(4)
            return {
                "query": query,
                "results": [
                    {
                        "title": f"Top result for '{query}'",
                        "snippet": f"Comprehensive coverage of {query}...",
                        "relevance": 0.95,
                    },
                    {
                        "title": f"Expert analysis: {query}",
                        "snippet": f"In-depth expert perspective on {query}...",
                        "relevance": 0.87,
                    },
                    {
                        "title": f"Recent developments in {query}",
                        "snippet": f"Latest news and updates about {query}...",
                        "relevance": 0.82,
                    },
                ],
                "total_results": 3,
            }

        self._executor.submit(
            name=f"web search: {query}",
            description=f"Searching the web for: {query}",
            coro=_web_search(),
            initiated_by=self.id,
            priority=TaskPriority.HIGH,
        )

        return "Web search initiated. Continue conversing naturally."

    @function_tool()
    async def search_academic(self, query: str, context: RunContext) -> str:
        """Search academic and scholarly sources. Heavy background operation.

        Args:
            query: Academic search query.
        """

        async def _academic_search() -> dict:
            await asyncio.sleep(5)
            return {
                "query": query,
                "papers": [
                    {"title": f"Research paper on {query}", "authors": "Smith et al.", "year": 2025, "citations": 42},
                    {"title": f"Meta-analysis: {query}", "authors": "Johnson et al.", "year": 2024, "citations": 128},
                ],
                "total_found": 2,
            }

        self._executor.submit(
            name=f"academic search: {query}",
            description=f"Searching scholarly sources for: {query}",
            coro=_academic_search(),
            initiated_by=self.id,
            priority=TaskPriority.NORMAL,
        )

        return "Academic search initiated. Engage the user naturally."

    @function_tool()
    async def get_page_summary(self, url: str, context: RunContext) -> str:
        """Get a quick summary of a web page. Light operation.

        Args:
            url: URL of the page to summarize.
        """
        await asyncio.sleep(0.5)
        return (
            f"Summary of {url}: This page covers the main aspects of the topic "
            "with detailed explanations and references. Key points include "
            "foundational concepts, practical applications, and current research."
        )

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
            msg += f" {len(completed)} search(es) completed."
        return agents["navigator"], msg

    @function_tool()
    async def transfer_to_analyst(self, context: RunContext) -> tuple[Agent, str]:
        """Hand off to the analyst for deeper synthesis."""
        agents: dict[str, Agent] = context.userdata.agents
        return agents["analyst"], "Transitioning to analysis."
