"""API module settings — FastAPI server configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class APISettings(BaseSettings):
    """Settings for the FastAPI API module."""

    API_PORT: int = 8000
