"""CLI module settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class CLISettings(BaseSettings):
    """Settings for the CLI module — ready for future CLI-specific config."""
