"""Unit tests for SearXNG adapter with mock HTTP server."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpserver import HTTPServer

from e_agents.shared.adapters.searxng import SearXNGAdapter, SearXNGQueryParams
from e_agents.shared.core.settings import settings as st
from e_agents.shared.models import Adapter, SearchCategory, SearchResponse

from confmodels import SearchResponseFactory, SearXNGQueryParamsFactory, SearxResultResponseFactory


##### SEARCH CATEGORY ENUM #####


@pytest.mark.parametrize(
    "member, expected",
    [
        (SearchCategory.GENERAL, "general"),
        (SearchCategory.IT, "it"),
        (SearchCategory.NEWS, "news"),
        (SearchCategory.SOCIAL_MEDIA, "social media"),
        (SearchCategory.SCIENCE, "science"),
    ],
    ids=["general", "it", "news", "social-media", "science"],
)
async def test_search_category_value(member: SearchCategory, expected: str) -> None:
    assert member.value == expected


##### QUERY PARAMS #####


async def test_query_params_frozen() -> None:
    params = SearXNGQueryParamsFactory.build()
    with pytest.raises(AttributeError):
        params.query = "changed"  # type: ignore[misc]


async def test_query_params_to_params_maps_query_to_q() -> None:
    result = SearXNGQueryParams(query="python asyncio").to_params()
    assert result["q"] == "python asyncio"
    assert "query" not in result


async def test_query_params_to_params_uses_settings_defaults() -> None:
    result = SearXNGQueryParams(query="test").to_params()
    assert result["format"] == st.SEARXNG_FORMAT
    assert result["language"] == st.SEARXNG_LANGUAGE
    assert result["safesearch"] == st.SEARXNG_SAFESEARCH


async def test_query_params_to_params_maps_category() -> None:
    result = SearXNGQueryParams(query="test", category=SearchCategory.NEWS).to_params()
    assert result["categories"] == "news"


##### SEARCH RESPONSE DATACLASS #####


async def test_search_response_frozen() -> None:
    r = SearchResponseFactory.build()
    with pytest.raises(AttributeError):
        r.title = "Changed"  # type: ignore[misc]


async def test_search_response_str_format() -> None:
    r = SearchResponse(title="Test", url="http://test.com", snippet="A snippet.")
    assert str(r) == "- Test\n  http://test.com\n  A snippet."


async def test_search_response_slots() -> None:
    r = SearchResponseFactory.build()
    assert hasattr(r, "__slots__")


##### CLASS ATTRIBUTES #####


async def test_adapter_name() -> None:
    assert SearXNGAdapter.name == "searxng"


async def test_adapter_inherits_timeout() -> None:
    assert SearXNGAdapter._TIMEOUT == Adapter._TIMEOUT


async def test_adapter_base_url_from_settings() -> None:
    assert SearXNGAdapter._BASE_URL == str(st.SEARXNG_URL)


##### QUERY — MOCK HTTP SERVER #####


async def test_query_returns_search_responses(mock_searxng) -> None:
    mock_searxng(num_results=3)
    results = await SearXNGAdapter.query("test")
    assert len(results) == 3
    assert all(isinstance(r, SearchResponse) for r in results)


async def test_query_maps_factory_data(mock_searxng) -> None:
    fake = mock_searxng(num_results=1)
    results = await SearXNGAdapter.query("test")
    assert results[0].title == fake.results[0].title


async def test_query_empty_results(mock_searxng) -> None:
    mock_searxng(num_results=0)
    results = await SearXNGAdapter.query("test")
    assert results == []


async def test_query_limits_to_max_results(mock_searxng) -> None:
    mock_searxng(num_results=10)
    results = await SearXNGAdapter.query("test")
    assert len(results) == st.SEARXNG_MAX_RESULTS


async def test_query_passes_category(mock_searxng) -> None:
    mock_searxng(num_results=1)
    await SearXNGAdapter.query("ai", category=SearchCategory.SCIENCE)


async def test_query_truncates_long_snippets(
    httpserver: HTTPServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SearXNGAdapter, "_BASE_URL", httpserver.url_for(""))
    long_result = SearxResultResponseFactory.build(content="x" * 500)
    httpserver.expect_request("/search").respond_with_json(
        {"results": [long_result.model_dump(mode="json")]},
    )
    results = await SearXNGAdapter.query("test")
    assert len(results[0].snippet) == 200


async def test_query_raises_on_http_error(mock_searxng) -> None:
    mock_searxng(num_results=0, status=500)
    with pytest.raises(httpx.HTTPStatusError):
        await SearXNGAdapter.query("fail")
