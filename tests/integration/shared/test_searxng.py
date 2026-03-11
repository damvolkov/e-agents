"""Integration tests for SearXNG adapter."""

from __future__ import annotations

from typing import Any

import httpx
import orjson
import pytest
import respx

from e_agents.shared.adapters.searxng import SearXNGAdapter, SearXNGQueryParams
from e_agents.shared.core.settings import settings as st
from e_agents.shared.models import Adapter, SearchCategory, SearchResponse

_FAKE_RESULTS: list[dict[str, str]] = [
    {"title": "Python docs", "url": "https://docs.python.org", "content": "Official Python documentation."},
    {"title": "Real Python", "url": "https://realpython.com", "content": "Tutorials and guides for Python."},
    {"title": "PyPI", "url": "https://pypi.org", "content": "The Python Package Index."},
]

_FAKE_RESPONSE: dict[str, Any] = {"results": _FAKE_RESULTS}
_EMPTY_RESPONSE: dict[str, Any] = {"results": []}


def _mock_search(data: dict[str, Any], status: int = 200) -> respx.Route:
    return respx.route(method="GET", path="/search").mock(
        return_value=httpx.Response(status, content=orjson.dumps(data)),
    )


##### CLASS ATTRIBUTES #####


async def test_adapter_name() -> None:
    assert SearXNGAdapter.name == "searxng"


async def test_adapter_timeout_inherited() -> None:
    assert SearXNGAdapter._TIMEOUT == Adapter._TIMEOUT


async def test_adapter_base_url_from_settings() -> None:
    assert SearXNGAdapter._BASE_URL == str(st.SEARXNG_URL)


##### SEARCH RESULT DATACLASS #####


async def test_search_result_str() -> None:
    r = SearchResponse(title="Test", url="http://test.com", snippet="A snippet.")
    assert str(r) == "- Test\n  http://test.com\n  A snippet."


async def test_search_result_frozen() -> None:
    r = SearchResponse(title="Test", url="http://test.com", snippet="A snippet.")
    with pytest.raises(AttributeError):
        r.title = "Changed"  # type: ignore[misc]


##### QUERY PARAMS #####


async def test_query_params_to_params_keys() -> None:
    result = SearXNGQueryParams(query="test").to_params()
    assert set(result) == {"q", "format", "categories", "language", "safesearch"}


@pytest.mark.parametrize(
    "category, expected",
    [
        (SearchCategory.GENERAL, "general"),
        (SearchCategory.NEWS, "news"),
        (SearchCategory.IT, "it"),
        (SearchCategory.SCIENCE, "science"),
    ],
    ids=["general", "news", "it", "science"],
)
async def test_query_params_category_mapping(category: SearchCategory, expected: str) -> None:
    result = SearXNGQueryParams(query="test", category=category).to_params()
    assert result["categories"] == expected


##### QUERY — MOCKED HTTP #####


@respx.mock
async def test_query_returns_search_results() -> None:
    _mock_search(_FAKE_RESPONSE)
    results = await SearXNGAdapter.query("python")
    assert len(results) == 3
    assert all(isinstance(r, SearchResponse) for r in results)


@respx.mock
async def test_query_empty_results() -> None:
    _mock_search(_EMPTY_RESPONSE)
    results = await SearXNGAdapter.query("nonexistent_query_xyz")
    assert results == []


@respx.mock
async def test_query_limits_to_max_results() -> None:
    big_response: dict[str, Any] = {
        "results": [
            {"title": f"R{i}", "url": f"http://r{i}.com", "content": f"Content {i}"}
            for i in range(10)
        ],
    }
    _mock_search(big_response)
    results = await SearXNGAdapter.query("test")
    assert len(results) == st.SEARXNG_MAX_RESULTS


@respx.mock
async def test_query_passes_category() -> None:
    route = _mock_search(_EMPTY_RESPONSE)
    await SearXNGAdapter.query("ai", category=SearchCategory.NEWS)
    assert route.calls[0].request.url.params["categories"] == "news"


@respx.mock
async def test_query_sends_settings_defaults() -> None:
    route = _mock_search(_EMPTY_RESPONSE)
    await SearXNGAdapter.query("test")
    sent = route.calls[0].request.url.params
    assert sent["format"] == st.SEARXNG_FORMAT
    assert sent["language"] == st.SEARXNG_LANGUAGE
    assert sent["safesearch"] == str(st.SEARXNG_SAFESEARCH)


@respx.mock
async def test_query_truncates_long_snippets() -> None:
    data: dict[str, Any] = {"results": [{"title": "Long", "url": "http://x", "content": "a" * 500}]}
    _mock_search(data)
    results = await SearXNGAdapter.query("test")
    assert len(results[0].snippet) == 200


@respx.mock
async def test_query_raises_on_http_error() -> None:
    _mock_search(_EMPTY_RESPONSE, status=500)
    with pytest.raises(httpx.HTTPStatusError):
        await SearXNGAdapter.query("fail")


##### QUERY — LIVE SERVICE #####


@pytest.mark.slow
async def test_query_live_searxng() -> None:
    """Hit real SearXNG — requires service on SEARXNG_URL."""
    results = await SearXNGAdapter.query("python programming")
    assert isinstance(results, list)
    assert all(isinstance(r, SearchResponse) for r in results)
    assert len(results) <= st.SEARXNG_MAX_RESULTS
