"""Web content fetcher — extracts readable text from a URL."""

from __future__ import annotations

import logging

import httpx
import trafilatura
from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from e_agents.rtc.models.state import SessionState

logging.getLogger("trafilatura").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_LENGTH = 4000
_ABSOLUTE_MAX_LENGTH = 12000


def _extract_content(html: str, *, max_length: int) -> str:
    """Extract readable text from raw HTML via trafilatura."""
    text = trafilatura.extract(
        html,
        include_links=True,
        include_tables=True,
        favor_recall=True,
        deduplicate=True,
    )
    if not text:
        return ""
    return text[:max_length]


##### TOOLS #####


@function_tool()
async def web_fetch(
    context: RunContext[SessionState],
    url: str,
    max_length: int = _DEFAULT_MAX_LENGTH,
) -> str:
    """Fetch a web page and extract its readable content.

    Use this AFTER web_search to read the full content of a specific result.
    Ideal for in-depth research when snippets are not enough.

    Args:
        url: The URL to fetch.
        max_length: Max characters of extracted content. Use 2000-4000 for summaries, 6000-12000 for deep reads.
    """
    clamped = max(500, min(max_length, _ABSOLUTE_MAX_LENGTH))
    logger.info("🌐 FETCH url=%r max_length=%d", url, clamped, extra={"tags": "TOOL"})

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; e-agents/1.0)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ToolError(f"Fetch failed: HTTP {exc.response.status_code}") from exc
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise ToolError(f"Could not reach {url}. Try another URL.") from exc
    except Exception as exc:
        raise ToolError(f"Fetch error: {type(exc).__name__}") from exc

    content = _extract_content(response.text, max_length=clamped)
    if not content:
        logger.warning("⚠️ FETCH_EMPTY url=%r", url, extra={"tags": "TOOL"})
        return (
            f"<web_content status='empty' url='{url}'>\n"
            "Could not extract readable content from this page. Try a different URL.\n"
            "</web_content>"
        )

    logger.info("✅ FETCH_OK url=%r chars=%d/%d", url, len(content), clamped, extra={"tags": "TOOL"})
    return (
        f"<web_content status='success' url='{url}' chars='{len(content)}'>\n"
        f"{content}\n"
        "</web_content>\n"
        "IMPORTANT: Base your response ONLY on this content. "
        "Synthesize the information into a detailed, factual answer."
    )
