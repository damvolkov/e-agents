"""Unit test fixtures for shared module."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pytest_httpserver import HTTPServer

from e_agents.shared.adapters.searxng import SearXNGAdapter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from confmodels import SearxResultResponseFactory, SearxSearchResponse, SearxSearchResponseFactory  # noqa: E402


##### MOCK SERVER UTILITIES #####


def create_mock_server(
    httpserver: HTTPServer,
    *,
    path: str,
    data: dict[str, Any],
    status: int = 200,
) -> HTTPServer:
    """Configure a mock endpoint on the given server."""
    httpserver.expect_request(path).respond_with_json(data, status=status)
    return httpserver


##### FIXTURES — MOCK SERVERS #####


@pytest.fixture
def mock_searxng(httpserver: HTTPServer, monkeypatch: pytest.MonkeyPatch) -> Callable[..., SearxSearchResponse]:
    """Factory fixture: configure SearXNG mock on /search endpoint."""
    monkeypatch.setattr(SearXNGAdapter, "_BASE_URL", httpserver.url_for(""))

    def _setup(*, num_results: int = 3, status: int = 200) -> SearxSearchResponse:
        fake = SearxSearchResponseFactory.build(
            results=SearxResultResponseFactory.batch(num_results),
        )
        create_mock_server(
            httpserver,
            path="/search",
            data=fake.model_dump(mode="json"),
            status=status,
        )
        return fake

    return _setup
