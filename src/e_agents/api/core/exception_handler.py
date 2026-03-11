"""Structured exception handling for the FastAPI layer."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import ORJSONResponse

from e_agents.api.core.exceptions import HTTPError

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = logging.getLogger("e_agents.api")

_KNOWN_MODULE_PREFIXES = ("openai", "httpx", "aiohttp", "livekit")


##### ROOT CAUSE #####


def extract_root_cause(exc: Exception) -> str:
    """Walk the exception chain to find the most informative root cause."""
    seen: set[int] = set()
    chain: list[Exception] = []
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, Exception):
            chain.append(current)
        current = current.__cause__ or (
            current.__context__ if not getattr(current, "__suppress_context__", False) else None
        )

    for e in reversed(chain):
        module = getattr(type(e), "__module__", "") or ""
        if any(module.startswith(p) for p in _KNOWN_MODULE_PREFIXES):
            return f"{type(e).__name__}: {e}"

    for e in reversed(chain):
        if isinstance(e, TimeoutError):
            return "Operation timed out"

    for e in reversed(chain):
        msg = str(e)
        if msg:
            return msg

    return str(exc)


##### RESPONSE BUILDER #####


def build_error_response(exc: Exception) -> dict[str, object]:
    """Build an RFC 9457-shaped error dict."""
    match exc:
        case HTTPError():
            return {
                "type": type(exc).__name__,
                "status": exc.status_code,
                "title": exc.title,
                "detail": str(exc) or extract_root_cause(exc),
            }
        case _:
            return {
                "type": "InternalServerError",
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "title": "Internal Server Error",
                "detail": extract_root_cause(exc),
            }


##### HANDLER #####


async def exception_handler(_request: Request, exc: Exception) -> ORJSONResponse:
    """Unified FastAPI exception handler for HTTPError and unexpected exceptions."""
    body = build_error_response(exc)
    status_code: int = body["status"]  # type: ignore[assignment]

    log = logger.warning if status_code < 500 else logger.error
    log("❌ %s", type(exc).__name__, extra={"detail": body["detail"], "status_code": status_code})

    return ORJSONResponse(status_code=status_code, content=body)


##### REGISTRATION #####


def register_exception_handlers(app: FastAPI) -> None:
    """Wire exception handlers into the FastAPI app."""
    app.add_exception_handler(HTTPError, exception_handler)
    app.add_exception_handler(Exception, exception_handler)
