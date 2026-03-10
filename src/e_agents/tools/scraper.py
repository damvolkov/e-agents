"""Web scraping tool implementations."""

from __future__ import annotations

import asyncio

from livekit.agents import RunContext

from e_agents.tasks.status import TaskPriority


async def scrape_url(self, url: str, context: RunContext) -> str:
    """Scrape a web page and extract its main content.

    Args:
        url: The URL to scrape.
    """

    async def _scrape() -> dict:
        await asyncio.sleep(3)
        return {
            "url": url,
            "title": f"Page title for {url}",
            "content": f"Extracted content from {url} (first 500 chars)...",
            "links": [f"{url}/related-1", f"{url}/related-2"],
        }

    self._executor.submit(
        name=f"scrape: {url}",
        description=f"Scraping {url}",
        coro=_scrape(),
        initiated_by=self.id,
        priority=TaskPriority.HIGH,
    )
    return f"Scraping {url} in background. I'll have results shortly."


async def scrape_search(self, query: str, context: RunContext) -> str:
    """Search the web for a query and scrape top results.

    Args:
        query: What to search for.
    """

    async def _search_and_scrape() -> dict:
        await asyncio.sleep(5)
        return {
            "query": query,
            "pages": [
                {"url": f"https://example.com/{query.replace(' ', '-')}", "snippet": f"Result 1 for {query}"},
                {"url": f"https://docs.example.com/{query.replace(' ', '-')}", "snippet": f"Result 2 for {query}"},
                {"url": f"https://blog.example.com/{query.replace(' ', '-')}", "snippet": f"Result 3 for {query}"},
            ],
        }

    self._executor.submit(
        name=f"search+scrape: {query}",
        description=f"Web search + scrape: {query}",
        coro=_search_and_scrape(),
        initiated_by=self.id,
        priority=TaskPriority.HIGH,
    )
    return f"Searching and scraping results for '{query}'. Keep chatting."


async def extract_links(self, url: str, context: RunContext) -> str:
    """Extract all links from a web page.

    Args:
        url: The URL to extract links from.
    """
    await asyncio.sleep(1)
    return (
        f"Links found on {url}:\n"
        f"  - {url}/about\n"
        f"  - {url}/docs\n"
        f"  - {url}/blog\n"
        "(placeholder — real implementation uses httpx + selectolax)"
    )
