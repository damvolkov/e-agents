"""Unit tests for EVoice STT adapter (mocked services)."""

from __future__ import annotations

import pytest
from livekit.agents.types import NOT_GIVEN

from e_agents.rtc.adapters.stt import EVoiceSTT

##### PROPERTIES #####


@pytest.mark.parametrize(
    ("model", "expected_model"),
    [
        ("large-v3-turbo", "large-v3-turbo"),
        ("large-v3", "large-v3"),
        ("small", "small"),
    ],
    ids=["turbo", "large-v3", "small"],
)
async def test_stt_model_property(model: str, expected_model: str) -> None:
    adapter = EVoiceSTT(base_url="http://test:8000", model=model)

    assert adapter.model == expected_model
    assert adapter.provider == "evoice"

    await adapter.aclose()


async def test_stt_capabilities() -> None:
    adapter = EVoiceSTT(base_url="http://test:8000")

    assert adapter.capabilities.streaming is True
    assert adapter.capabilities.interim_results is False

    await adapter.aclose()


##### WS URL CONSTRUCTION #####


@pytest.mark.parametrize(
    ("base_url", "expected_ws"),
    [
        ("http://localhost:4100", "ws://localhost:4100"),
        ("https://stt.example.com", "wss://stt.example.com"),
        ("http://localhost:4100/", "ws://localhost:4100"),
    ],
    ids=["http-to-ws", "https-to-wss", "trailing-slash"],
)
async def test_stt_ws_url_from_base(base_url: str, expected_ws: str) -> None:
    from e_agents.rtc.adapters.stt.evoice import _base_to_ws
    base = base_url.rstrip("/")
    ws_url = _base_to_ws(base)

    assert ws_url == expected_ws


##### STREAM CREATION #####


async def test_stt_stream_returns_recognize_stream() -> None:
    adapter = EVoiceSTT(base_url="http://test:8000", language="en")

    stream = adapter.stream()

    assert stream is not None
    await adapter.aclose()


@pytest.mark.parametrize(
    ("language", "expected_lang"),
    [
        ("en", "en"),
        ("es", "es"),
        ("fr", "fr"),
    ],
    ids=["english", "spanish", "french"],
)
async def test_stt_stream_language(language: str, expected_lang: str) -> None:
    adapter = EVoiceSTT(base_url="http://test:8000", language=language)

    stream = adapter.stream(language=NOT_GIVEN)

    assert stream is not None
    await adapter.aclose()
