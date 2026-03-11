"""SearXNG search tool using LiveKit native function_tool."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from e_agents.rtc.models.state import SessionState
from e_agents.shared.adapters.searxng import SearXNGAdapter
from e_agents.shared.models import SearchCategory, SearchResponse


def _format_results(results: list[SearchResponse]) -> str:
    if not results:
        return "No results found."
    return "\n\n".join(str(r) for r in results)


##### TOOLS #####


@function_tool()
async def web_search(
    context: RunContext[SessionState],
    query: str,
    category: str = "general",
) -> str:
    """Search the web using SearXNG metasearch engine.

    Args:
        query: The search query.
        category: Search category (general, it, news, images, videos, science, map, music, files, social media).
    """
    searxng: SearXNGAdapter = context.userdata.get_adapter("searxng")  # type: ignore[assignment]
    return _format_results(
        await searxng.query(query, category=SearchCategory(category)),
    )
