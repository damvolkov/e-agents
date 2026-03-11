"""API-layer exceptions with FastAPI HTTP semantics."""

from __future__ import annotations

from enum import StrEnum

from fastapi import status

from e_agents.shared.core.exceptions import APIError

__all__ = [
    "APIError",
    "BadRequestError",
    "ConflictError",
    "ErrorTitle",
    "ExternalServiceError",
    "HTTPError",
    "NotFoundError",
]


##### ENUMS #####


class ErrorTitle(StrEnum):
    """Canonical HTTP error titles for structured responses."""

    BAD_REQUEST = "Bad Request"
    NOT_FOUND = "Not Found"
    CONFLICT = "Conflict"
    INTERNAL = "Internal Server Error"
    BAD_GATEWAY = "Bad Gateway"


##### HTTP ERRORS #####


class HTTPError(APIError):
    """API error carrying HTTP status and structured response metadata."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str = ErrorTitle.INTERNAL

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int | None = None,
        title: str | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code or self.__class__.status_code
        self.title = title or self.__class__.title
        super().__init__(message, context=context)


class BadRequestError(HTTPError):
    """400 — invalid client input."""

    status_code = status.HTTP_400_BAD_REQUEST
    title = ErrorTitle.BAD_REQUEST


class NotFoundError(HTTPError):
    """404 — resource not found."""

    status_code = status.HTTP_404_NOT_FOUND
    title = ErrorTitle.NOT_FOUND


class ConflictError(HTTPError):
    """409 — resource state conflict."""

    status_code = status.HTTP_409_CONFLICT
    title = ErrorTitle.CONFLICT


class ExternalServiceError(HTTPError):
    """502 — upstream service failure."""

    status_code = status.HTTP_502_BAD_GATEWAY
    title = ErrorTitle.BAD_GATEWAY
