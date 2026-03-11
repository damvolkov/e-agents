"""Base models, adapter protocol, YAML serialization, and shared config primitives."""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from enum import StrEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

import yaml
from pydantic import BaseModel, ConfigDict

from e_agents.shared.core.settings import settings as st

if TYPE_CHECKING:
    from livekit.agents.llm import Tool, Toolset
    from livekit.agents.llm.mcp import MCPServer


##### YAML MODEL #####


class BaseModelYAML(BaseModel):
    """Base for YAML-backed configuration models."""

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """Load model from a YAML file."""
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    @classmethod
    def model_validate_yaml(cls, data: str | bytes) -> Self:
        """Validate and parse YAML string into model instance."""
        raw = data if isinstance(data, str) else data.decode()
        return cls.model_validate(yaml.safe_load(raw))

    def model_dump_yaml(self, **kwargs) -> str:
        """Serialize model to a YAML string."""
        kwargs.setdefault("exclude_none", True)
        kwargs.setdefault("mode", "json")
        return yaml.dump(self.model_dump(**kwargs), sort_keys=False)


##### ADAPTER #####


class Adapter(ABC):
    """Base for all adapters — service clients and LiveKit pipeline components.

    Subclass and override ``close`` for adapters with persistent connections.
    Expose tools and MCP servers via the corresponding properties so ``State``
    can aggregate them across all registered adapters.
    """

    _TIMEOUT: ClassVar[float] = st.ADAPTERS_TIMEOUT

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def tools(self) -> list[Tool | Toolset]:
        return []

    @property
    def mcp_servers(self) -> list[MCPServer]:
        return []

    async def close(self) -> None:  # noqa: B027
        """Release resources. Override for adapters with persistent connections."""


##### DATA #####


@dataclasses.dataclass(slots=True, frozen=True)
class SearchResponse:
    """Single search result from a metasearch engine."""

    title: str
    url: str
    snippet: str

    def __str__(self) -> str:
        return f"- {self.title}\n  {self.url}\n  {self.snippet}"


##### ENUMS #####


class SearchCategory(StrEnum):
    """SearXNG search categories."""

    @staticmethod
    def _generate_next_value_(name: str, *_: object) -> str:
        return name.lower().replace("_", " ")

    GENERAL = auto()
    IT = auto()
    NEWS = auto()
    MAP = auto()
    MUSIC = auto()
    FILES = auto()
    IMAGES = auto()
    VIDEOS = auto()
    SOCIAL_MEDIA = auto()
    SCIENCE = auto()


class LLMProvider(StrEnum):
    OPENAI = auto()
    GOOGLE = auto()


##### SHARED CONFIG PRIMITIVES #####


class LLMConfig(BaseModelYAML):
    """LLM provider + model pair."""

    provider: LLMProvider = LLMProvider.OPENAI
    model: str = "gpt-4o-mini"
