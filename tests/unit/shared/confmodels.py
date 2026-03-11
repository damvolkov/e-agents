"""Polyfactory factories for shared models and external API response schemas."""

from __future__ import annotations

from pydantic import BaseModel
from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.factories.pydantic_factory import ModelFactory

from e_agents.shared.adapters.searxng import SearXNGQueryParams
from e_agents.shared.models import LLMConfig, SearchResponse


##### SHARED MODEL FACTORIES #####


class SearchResponseFactory(DataclassFactory):
    """Factory for SearchResponse dataclass."""

    __model__ = SearchResponse


class SearXNGQueryParamsFactory(DataclassFactory):
    """Factory for SearXNGQueryParams dataclass."""

    __model__ = SearXNGQueryParams


class LLMConfigFactory(ModelFactory):
    """Factory for LLMConfig pydantic model."""

    __model__ = LLMConfig


##### SEARXNG API SCHEMAS #####


class SearxResultResponse(BaseModel):
    """Raw result item as returned by the SearXNG API."""

    title: str
    url: str
    content: str
    engine: str = "google"


class SearxSearchResponse(BaseModel):
    """Raw SearXNG /search JSON response."""

    query: str
    results: list[SearxResultResponse]


##### SEARXNG API FACTORIES #####


class SearxResultResponseFactory(ModelFactory):
    """Factory for SearxResultResponse."""

    __model__ = SearxResultResponse


class SearxSearchResponseFactory(ModelFactory):
    """Factory for SearxSearchResponse."""

    __model__ = SearxSearchResponse
