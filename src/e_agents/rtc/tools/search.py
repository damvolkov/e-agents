"""SearXNG search tool — discovers results, returns metadata."""

from __future__ import annotations

import logging

import httpx
from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from e_agents.rtc.models.state import SessionState
from e_agents.shared.adapters.searxng import SearXNGAdapter
from e_agents.shared.models import SearchCategory, SearchResponse

logger = logging.getLogger(__name__)


def _format_results(query: str, category: str, results: list[SearchResponse], max_results: int) -> str:
    """Structured output so the LLM knows exactly what it received."""
    if not results:
        return (
            f"<search_result status='empty' query='{query}' category='{category}'>\n"
            "No results found. Try a different query or category.\n"
            "</search_result>"
        )
    body = "\n\n".join(str(r) for r in results)
    return (
        f"<search_result status='success' query='{query}' category='{category}' "
        f"count='{len(results)}' requested='{max_results}'>\n"
        f"{body}\n"
        "</search_result>\n"
        "IMPORTANT: Base your response ONLY on these search results. "
        "Do NOT use your training data for facts. "
        "Synthesize ALL results into a comprehensive, detailed answer. "
        "Include specific facts, names, dates, and events mentioned in the results. "
        "NEVER say 'check the links' — YOU are the one who must inform the user. "
        "If the user wants more depth, use web_fetch on the most relevant URLs."
    )


##### TOOLS #####


@function_tool()
async def web_search(
    context: RunContext[SessionState],
    query: str,
    category: SearchCategory = SearchCategory.GENERAL,
    max_results: int = 5,
) -> str:
    """Search the web using SearXNG metasearch engine.

    Returns titles, URLs, and snippets. For full article content, follow up
    with web_fetch on the most relevant URLs.

    Args:
        query: The search query.
        category: Search category — general, web, news, images, videos, music, it, science, scientific publications, files, social media, map, apps, books, packages, repos, software wikis, shopping, weather, dictionaries, translate, lyrics, movies, radio, currency, icons, q&a, wikimedia, cargo, define, other.
        max_results: Number of results to fetch. Use 3-5 for quick lookups, 8-15 for in-depth research.
    """
    clamped = max(1, min(max_results, 20))
    logger.info("🔍 SEARCH query=%r category=%r max_results=%d", query, category, clamped, extra={"tags": "TOOL"})

    searxng: SearXNGAdapter = context.userdata.get_adapter("searxng")  # type: ignore[assignment]
    try:
        results = await searxng.query(query, category=category, max_results=clamped)
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

    logger.info(
        "✅ SEARCH_OK query=%r results=%d/%d category=%s",
        query, len(results), clamped, category.value,
        extra={"tags": "TOOL"},
    )
    return _format_results(query, category.value, results, clamped)
