"""Unified settings for e_agents."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from e_agents.models.agent import AgentsConfig


def read_pyproject(pyproject_path: Path) -> dict:
    """Read pyproject.toml into a dict."""
    with pyproject_path.open("rb") as file_handle:
        return tomllib.load(file_handle)


def get_version(base_dir: Path) -> str:
    """Get version from git tags or fallback to package metadata."""
    try:
        import git

        repo = git.Repo(base_dir, search_parent_directories=True)
        latest_tag = max(repo.tags, key=lambda t: t.commit.committed_datetime, default=None)
        return str(latest_tag) if latest_tag else "0.0.0"
    except Exception:
        try:
            import importlib.metadata

            return importlib.metadata.version("e_agents")
        except Exception:
            return "0.0.0"


class Settings(BaseSettings):
    """Unified settings for e_agents service."""

    ENVIRONMENT: Literal["DEV", "PROD"] = "DEV"

    # ClassVar to prevent Pydantic from trying to load from env
    BASE_DIR: ClassVar[Path] = Path(__file__).parent.parent.parent.parent
    PROJECT: ClassVar[dict] = read_pyproject(BASE_DIR / "pyproject.toml")
    API_NAME: ClassVar[str] = PROJECT.get("project", {}).get("name", "e_agents")
    API_DESCRIPTION: ClassVar[str] = PROJECT.get("project", {}).get("description", "e-agents")
    API_VERSION: ClassVar[str] = get_version(BASE_DIR)

    # Paths
    DATA_PATH: ClassVar[Path] = BASE_DIR / "data"
    MODELS_PATH: ClassVar[Path] = DATA_PATH / "models"
    AGENTS_CONFIG_PATH: ClassVar[Path] = BASE_DIR / "src" / "e_agents" / "agents" / "config.yaml"

    # Redis
    REDIS_PASSWORD: str = ""
    REDIS_ADDRESS: str = "localhost:6379"

    # LiveKit
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_WS_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "secret"

    # STT Service
    STT_BASE_URL: str = "http://localhost:4100"
    STT_WS_URL: str = "ws://localhost:4100/v1/audio/transcriptions"
    STT_MODEL: str = "Systran/faster-whisper-small"
    STT_LANGUAGE: str = "en"
    STT_TIMEOUT: float = 30.0

    # TTS Service
    TTS_HOST: str = "localhost"
    TTS_PORT: int = 10200
    TTS_SAMPLE_RATE: int = 22050
    TTS_SILENCE_PADDING: float = 0.15
    PIPER_VOICE: str = "en_US-lessac-medium"

    # LLM
    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # API
    API_PORT: int = 8000

    # Audio
    AUDIO_SAMPLE_RATE: int = 24000
    AUDIO_CHANNELS: int = 1

    # Agent Session
    AGENT_MAX_TOOL_STEPS: int = 10

    # VAD
    VAD_SAMPLE_RATE: int = 16000
    VAD_HOP_SIZE: int = 256
    VAD_SPEECH_THRESHOLD: float = 0.5
    VAD_SILENCE_DURATION: float = 1.5

    @computed_field
    @property
    def is_dev(self) -> bool:
        """Check if running in development mode."""
        return self.ENVIRONMENT == "DEV"

    @computed_field
    @property
    def log_level(self) -> str:
        """Get log level based on environment."""
        return "debug" if self.is_dev else "info"

    @property
    def AGENTS_CONFIG(self) -> AgentsConfig:  # noqa: N802
        """Get agents configuration (lazy loaded)."""
        if not hasattr(self, "_agents_config"):
            self._agents_config = AgentsConfig.from_yaml(self.AGENTS_CONFIG_PATH)
        return self._agents_config

    @model_validator(mode="after")
    def sync_google_api_key(self) -> Settings:
        """Sync GOOGLE_API_KEY from GEMINI_API_KEY if not set."""
        if not self.GOOGLE_API_KEY and self.GEMINI_API_KEY:
            self.GOOGLE_API_KEY = self.GEMINI_API_KEY
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
