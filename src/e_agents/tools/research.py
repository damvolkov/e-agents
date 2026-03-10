"""Research tool implementations.

Standalone functions attached dynamically to agents via YAML config.
Each receives ``self`` (the agent instance) as first param because
the factory mounts them as methods on dynamically-built agent classes.
"""

from __future__ import annotations

import asyncio

from livekit.agents import RunContext

from e_agents.tasks.status import TaskPriority


async def research_topic(self, topic: str, context: RunContext) -> str:
    """Dispatch a deep research task to the background team.

    Args:
        topic: The topic or question to research.
    """

    async def _work() -> dict:
        await asyncio.sleep(5)
        return {
            "topic": topic,
            "summary": f"Comprehensive findings on '{topic}'.",
            "key_points": [f"Primary insight about {topic}", f"Current trends in {topic}"],
            "confidence": "high",
        }

    self._executor.submit(
        name=topic,
        description=f"Deep research: {topic}",
        coro=_work(),
        initiated_by=self.id,
        priority=TaskPriority.HIGH,
    )
    return "Research initiated in background. Keep chatting naturally."


async def quick_lookup(self, query: str, context: RunContext) -> str:
    """Fast factual lookup – returns immediately.

    Args:
        query: A simple factual question.
    """
    await asyncio.sleep(0.3)
    return f"Quick result for '{query}': placeholder answer. Present naturally."


async def search_web(self, query: str, context: RunContext) -> str:
    """Search the web for information. Background operation.

    Args:
        query: Search query string.
    """

    async def _search() -> dict:
        await asyncio.sleep(4)
        return {
            "query": query,
            "results": [
                {"title": f"Top result: {query}", "relevance": 0.95},
                {"title": f"Expert analysis: {query}", "relevance": 0.87},
            ],
        }

    self._executor.submit(
        name=f"web: {query}",
        description=f"Web search: {query}",
        coro=_search(),
        initiated_by=self.id,
        priority=TaskPriority.HIGH,
    )
    return "Web search launched. Continue the conversation."


async def search_academic(self, query: str, context: RunContext) -> str:
    """Search academic sources. Background operation.

    Args:
        query: Academic search query.
    """

    async def _academic() -> dict:
        await asyncio.sleep(5)
        return {
            "query": query,
            "papers": [
                {"title": f"Paper on {query}", "year": 2025, "citations": 42},
                {"title": f"Meta-analysis: {query}", "year": 2024, "citations": 128},
            ],
        }

    self._executor.submit(
        name=f"academic: {query}",
        description=f"Academic search: {query}",
        coro=_academic(),
        initiated_by=self.id,
        priority=TaskPriority.NORMAL,
    )
    return "Academic search launched. Keep engaging the user."
