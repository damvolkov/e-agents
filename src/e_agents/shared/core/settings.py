"""Unified settings — composes module-specific settings via multi-inheritance."""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path
from typing import ClassVar, Literal

import git
from pydantic import AnyHttpUrl, AnyUrl, RedisDsn, SecretStr, computed_field
from pydantic_settings import SettingsConfigDict

from e_agents.api.core.settings import APISettings
from e_agents.cli.core.settings import CLISettings
from e_agents.rtc.core.settings import RTCSettings


def _read_pyproject(pyproject_path: Path) -> dict:
    """Read pyproject.toml into a dict."""
    with pyproject_path.open("rb") as fh:
        return tomllib.load(fh)


def _get_version(base_dir: Path) -> str:
    """Get version from git tags or fallback to package metadata."""
    try:
        repo = git.Repo(base_dir, search_parent_directories=True)
        latest_tag = max(repo.tags, key=lambda t: t.commit.committed_datetime, default=None)
        return str(latest_tag) if latest_tag else "0.0.0"
    except Exception:
        try:
            return importlib.metadata.version("e_agents")
        except Exception:
            return "0.0.0"


class Settings(RTCSettings, APISettings, CLISettings):
    """Unified settings — inherits all module settings and adds cross-cutting concerns."""

    ENVIRONMENT: Literal["DEV", "PROD"] = "DEV"

    ##### CLASS-LEVEL PATHS #####

    BASE_DIR: ClassVar[Path] = Path(__file__).parent.parent.parent.parent.parent
    PROJECT: ClassVar[dict] = _read_pyproject(BASE_DIR / "pyproject.toml")
    API_NAME: ClassVar[str] = PROJECT.get("project", {}).get("name", "e_agents")
    API_DESCRIPTION: ClassVar[str] = PROJECT.get("project", {}).get("description", "e-agents")
    API_VERSION: ClassVar[str] = _get_version(BASE_DIR)

    CONFIG_DIR: ClassVar[Path] = BASE_DIR / "src" / "e_agents" / "rtc" / "config"
    AGENTS_DIR: ClassVar[Path] = CONFIG_DIR / "agents"
    SESSIONS_DIR: ClassVar[Path] = CONFIG_DIR / "sessions"
    MCPS_DIR: ClassVar[Path] = CONFIG_DIR / "mcps"
    DEFAULT_SESSION: str = "web"

    TOOLS_DIR: ClassVar[Path] = BASE_DIR / "src" / "e_agents" / "rtc" / "tools"
    ##### LANGUAGE #####

    USER_LANGUAGE: str = "es"

    ##### SHARED INFRASTRUCTURE #####

    # Redis
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"

    # LiveKit (used by api, cli, and rtc)
    LIVEKIT_URL: AnyUrl = "ws://localhost:7880"
    LIVEKIT_WS_URL: AnyUrl = "ws://localhost:7880"
    LIVEKIT_API_KEY: SecretStr = "devkey"
    LIVEKIT_API_SECRET: SecretStr = "secret"

    # Adapters
    ADAPTERS_TIMEOUT: float = 15.0

    # SearXNG (used by shared/adapters and rtc/tools)
    SEARXNG_URL: AnyHttpUrl = "http://localhost:45600"
    SEARXNG_FORMAT: ClassVar[str] = "json"
    SEARXNG_LANGUAGE: ClassVar[str] = "all"
    SEARXNG_SAFESEARCH: ClassVar[int] = 0
    SEARXNG_MAX_RESULTS: ClassVar[int] = 5
    SEARXNG_SNIPPET_LENGTH: ClassVar[int] = 300

    ##### COMPUTED #####

    @computed_field
    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT == "DEV"

    @computed_field
    @property
    def log_level(self) -> str:
        return "debug" if self.is_dev else "info"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
