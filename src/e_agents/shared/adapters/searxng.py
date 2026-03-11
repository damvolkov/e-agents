"""SearXNG metasearch adapter."""

from __future__ import annotations

import dataclasses
from typing import ClassVar

import httpx
import orjson

from e_agents.shared.core.settings import settings as st
from e_agents.shared.models import Adapter, SearchCategory, SearchResponse


@dataclasses.dataclass(slots=True, frozen=True)
class SearXNGQueryParams:
    """Typed query parameters for the SearXNG /search API."""

    query: str
    category: SearchCategory = SearchCategory.GENERAL

    def to_params(self) -> dict[str, str | int]:
        """Build HTTP query params from typed fields + settings defaults."""
        return {
            "q": self.query,
            "format": st.SEARXNG_FORMAT,
            "categories": self.category.value,
            "language": st.SEARXNG_LANGUAGE,
            "safesearch": st.SEARXNG_SAFESEARCH,
        }


class SearXNGAdapter(Adapter):
    """Stateless adapter for SearXNG metasearch engine."""

    name = "searxng"
    _BASE_URL: ClassVar[str] = str(st.SEARXNG_URL)

    @classmethod
    async def query(
        cls,
        query: str,
        *,
        category: SearchCategory = SearchCategory.GENERAL,
    ) -> list[SearchResponse]:
        """Execute a SearXNG search and return structured results."""
        params = SearXNGQueryParams(query=query, category=category).to_params()
        async with httpx.AsyncClient(
            base_url=cls._BASE_URL,
            timeout=httpx.Timeout(cls._TIMEOUT),
            headers={"Accept": "application/json"},
        ) as client:
            response = await client.get("/search", params=params)
        response.raise_for_status()
        results: list[dict[str, str]] = orjson.loads(response.content).get("results", [])
        return [
            SearchResponse(
                title=r.get("title", "No title"),
                url=r.get("url", ""),
                snippet=r.get("content", "")[:200],
            )
            for r in results[: st.SEARXNG_MAX_RESULTS]
        ]
