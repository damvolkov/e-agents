"""SearXNG search tool using LiveKit native function_tool."""

from __future__ import annotations

import httpx
from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from e_agents.rtc.models.state import SessionState
from e_agents.shared.adapters.searxng import SearXNGAdapter
from e_agents.shared.models import SearchCategory, SearchResponse


def _format_results(query: str, category: str, results: list[SearchResponse]) -> str:
    """Structured output so the LLM knows exactly what it received."""
    if not results:
        return (
            f"<search_result status='empty' query='{query}' category='{category}'>\n"
            "No results found. Try a different query or category.\n"
            "</search_result>"
        )
    body = "\n\n".join(str(r) for r in results)
    return (
        f"<search_result status='success' query='{query}' category='{category}' count='{len(results)}'>\n"
        f"{body}\n"
        "</search_result>\n"
        "IMPORTANT: Base your response ONLY on these search results. "
        "Do NOT use your training data for facts."
    )


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
    try:
        cat = SearchCategory(category)
    except ValueError:
        cat = SearchCategory.GENERAL

    searxng: SearXNGAdapter = context.userdata.get_adapter("searxng")  # type: ignore[assignment]
    try:
        results = await searxng.query(query, category=cat)
    except httpx.HTTPStatusError as exc:
        raise ToolError(
            f"Search failed: HTTP {exc.response.status_code}. Try again later."
        ) from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise ToolError(
            "Search service unreachable. Try again in a moment."
        ) from exc
    except Exception as exc:
        raise ToolError(f"Search error: {type(exc).__name__}") from exc

    return _format_results(query, cat.value, results)
