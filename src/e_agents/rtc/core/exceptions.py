"""RTC-layer exceptions."""

from __future__ import annotations

from e_agents.shared.core.exceptions import RTCError

__all__ = ["RTCError", "ConfigLoadError", "SessionBuildError", "ProviderError"]


class ConfigLoadError(RTCError):
    """Failed to load or validate YAML configuration."""


class SessionBuildError(RTCError):
    """Failed to build an agent session from configuration."""


class ProviderError(RTCError):
    """Unknown or unavailable STT/TTS/LLM/VAD provider."""
