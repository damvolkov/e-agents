"""Project-wide exception hierarchy.

Root service errors live here to avoid circular imports between modules.
Each service ``exceptions.py`` imports its root and extends it.
"""

from __future__ import annotations

##### BASE #####


class BaseError(Exception):
    """Root exception for the entire e-agents project."""

    def __init__(self, message: str = "", *, context: dict[str, object] | None = None) -> None:
        self.context: dict[str, object] = context or {}
        super().__init__(message)


##### SERVICE ROOTS #####


class SharedError(BaseError):
    """Errors from shared infrastructure."""


class CLIError(BaseError):
    """Errors from the CLI layer."""


class RTCError(BaseError):
    """Errors from the RTC layer."""


class APIError(BaseError):
    """Errors from the API layer."""


##### CROSS-CUTTING #####


class SystemError(CLIError, RTCError, APIError):
    """Cross-cutting error catchable by any service-level handler.

    NOTE: Shadows the builtin ``SystemError``.  Always use a qualified import.
    """
