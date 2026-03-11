"""Tests for the API exception handler module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status

from e_agents.api.core.exception_handler import (
    build_error_response,
    exception_handler,
    extract_root_cause,
    register_exception_handlers,
)
from e_agents.api.core.exceptions import (
    BadRequestError,
    ConflictError,
    ExternalServiceError,
    HTTPError,
    NotFoundError,
)

##### EXTRACT ROOT CAUSE #####


async def test_extract_root_cause_simple_message() -> None:
    assert extract_root_cause(ValueError("something broke")) == "something broke"


async def test_extract_root_cause_chained_cause() -> None:
    try:
        try:
            raise ConnectionError("conn refused")
        except ConnectionError as inner:
            raise RuntimeError("wrapper") from inner
    except RuntimeError as outer:
        assert extract_root_cause(outer) == "conn refused"


async def test_extract_root_cause_implicit_context() -> None:
    try:
        try:
            raise KeyError("missing_key")
        except KeyError:
            raise ValueError("bad value")  # noqa: B904
    except ValueError as outer:
        result = extract_root_cause(outer)
        assert result in ("missing_key", "'missing_key'", "bad value")


async def test_extract_root_cause_timeout_in_chain() -> None:
    try:
        try:
            raise TimeoutError("took too long")
        except TimeoutError as inner:
            raise RuntimeError("failed") from inner
    except RuntimeError as outer:
        assert extract_root_cause(outer) == "Operation timed out"


async def test_extract_root_cause_known_module_prefix() -> None:

    class FakeHttpxError(Exception):
        pass

    FakeHttpxError.__module__ = "httpx.errors"
    try:
        try:
            raise FakeHttpxError("connection pool exhausted")
        except FakeHttpxError as inner:
            raise RuntimeError("request failed") from inner
    except RuntimeError as outer:
        result = extract_root_cause(outer)
        assert "FakeHttpxError" in result
        assert "connection pool exhausted" in result


async def test_extract_root_cause_empty_message() -> None:
    assert extract_root_cause(RuntimeError("")) == ""


_ROOT_CAUSE_CASES = [
    pytest.param(ValueError("x"), "x", id="simple-value-error"),
    pytest.param(TypeError("bad type"), "bad type", id="type-error"),
    pytest.param(OSError("disk full"), "disk full", id="os-error"),
]


@pytest.mark.parametrize(("exc", "expected"), _ROOT_CAUSE_CASES)
async def test_extract_root_cause_parametrized(exc: Exception, expected: str) -> None:
    assert extract_root_cause(exc) == expected


##### BUILD ERROR RESPONSE #####


async def test_build_error_response_http_error() -> None:
    exc = BadRequestError("invalid field")
    body = build_error_response(exc)
    assert body == {
        "type": "BadRequestError",
        "status": status.HTTP_400_BAD_REQUEST,
        "title": "Bad Request",
        "detail": "invalid field",
    }


async def test_build_error_response_not_found() -> None:
    body = build_error_response(NotFoundError("session xyz"))
    assert body["status"] == 404
    assert body["title"] == "Not Found"


async def test_build_error_response_conflict() -> None:
    body = build_error_response(ConflictError("duplicate"))
    assert body["status"] == 409


async def test_build_error_response_external_service() -> None:
    body = build_error_response(ExternalServiceError("upstream timeout"))
    assert body["status"] == 502
    assert body["title"] == "Bad Gateway"


async def test_build_error_response_generic_http_error() -> None:
    exc = HTTPError("server fault")
    body = build_error_response(exc)
    assert body["status"] == 500
    assert body["type"] == "HTTPError"


async def test_build_error_response_plain_exception() -> None:
    body = build_error_response(RuntimeError("unexpected"))
    assert body == {
        "type": "InternalServerError",
        "status": 500,
        "title": "Internal Server Error",
        "detail": "unexpected",
    }


async def test_build_error_response_http_error_empty_message_uses_root_cause() -> None:
    try:
        try:
            raise ConnectionError("upstream died")
        except ConnectionError as inner:
            raise HTTPError() from inner
    except HTTPError as exc:
        body = build_error_response(exc)
        assert body["detail"] == "upstream died"


async def test_build_error_response_custom_status_and_title() -> None:
    exc = HTTPError("teapot", status_code=418, title="I'm a Teapot")
    body = build_error_response(exc)
    assert body["status"] == 418
    assert body["title"] == "I'm a Teapot"


##### EXCEPTION HANDLER #####


async def test_exception_handler_returns_orjson_response() -> None:
    request = AsyncMock()
    exc = BadRequestError("bad input")
    response = await exception_handler(request, exc)
    assert response.status_code == 400


async def test_exception_handler_500_for_plain_exception() -> None:
    request = AsyncMock()
    response = await exception_handler(request, RuntimeError("boom"))
    assert response.status_code == 500


_HANDLER_STATUS_CASES = [
    pytest.param(BadRequestError("x"), 400, id="bad-request"),
    pytest.param(NotFoundError("x"), 404, id="not-found"),
    pytest.param(ConflictError("x"), 409, id="conflict"),
    pytest.param(ExternalServiceError("x"), 502, id="external-service"),
    pytest.param(HTTPError("x"), 500, id="generic-http"),
    pytest.param(ValueError("x"), 500, id="plain-exception"),
]


@pytest.mark.parametrize(("exc", "expected_status"), _HANDLER_STATUS_CASES)
async def test_exception_handler_status_codes(exc: Exception, expected_status: int) -> None:
    request = AsyncMock()
    response = await exception_handler(request, exc)
    assert response.status_code == expected_status


##### REGISTER EXCEPTION HANDLERS #####


async def test_register_exception_handlers_wires_app() -> None:
    app = MagicMock()
    register_exception_handlers(app)
    assert app.add_exception_handler.call_count == 2
    calls = [c.args[0] for c in app.add_exception_handler.call_args_list]
    assert HTTPError in calls
    assert Exception in calls
