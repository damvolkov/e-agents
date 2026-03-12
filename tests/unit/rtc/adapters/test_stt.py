"""Unit tests for WhisperLive STT adapter (mocked WebSocket)."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import orjson as json
import pytest
from livekit import rtc
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN

from e_agents.rtc.adapters.stt import WhisperLiveSTT

##### TRANSCRIPTION #####


@pytest.mark.parametrize(
    ("response_segments", "expected_text"),
    [
        ([{"text": "Hello world"}], "Hello world"),
        ([], ""),
        ([{"text": "  trimmed  "}], "trimmed"),
        ([{"text": "Hola"}, {"text": "mundo"}], "Hola mundo"),
    ],
    ids=["simple", "empty", "trimmed", "multi-segment"],
)
async def test_stt_recognize_transcripts(
    stt_adapter: WhisperLiveSTT,
    audio_frame: rtc.AudioFrame,
    mock_ws_factory: Callable[[list[bytes]], AsyncMock],
    mock_connect_factory: Callable[[AsyncMock], AsyncMock],
    response_segments: list[dict],
    expected_text: str,
) -> None:
    messages = [
        json.dumps({"uid": "test", "message": "SERVER_READY"}),
        json.dumps({"uid": "test", "segments": response_segments}),
        json.dumps({"uid": "test", "message": "DISCONNECT"}),
    ]

    mock_ws = mock_ws_factory(messages)
    mock_connect = mock_connect_factory(mock_ws)

    with patch("e_agents.rtc.adapters.stt.whisperlive.websockets.connect", return_value=mock_connect):
        result = await stt_adapter._recognize_impl([audio_frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"
    assert result.alternatives[0].text == expected_text


##### LANGUAGE #####


@pytest.mark.parametrize(
    ("language", "expected_lang"),
    [
        ("en", "en"),
        ("es", "es"),
        ("fr", "fr"),
        (None, "en"),
    ],
    ids=["english", "spanish", "french", "default"],
)
async def test_stt_recognize_language(
    stt_adapter: WhisperLiveSTT,
    audio_frame: rtc.AudioFrame,
    mock_ws_factory: Callable[[list[bytes]], AsyncMock],
    mock_connect_factory: Callable[[AsyncMock], AsyncMock],
    language: str | None,
    expected_lang: str,
) -> None:
    messages = [
        json.dumps({"uid": "test", "segments": [{"text": "test"}]}),
        json.dumps({"uid": "test", "message": "DISCONNECT"}),
    ]

    mock_ws = mock_ws_factory(messages)
    mock_connect = mock_connect_factory(mock_ws)

    with patch("e_agents.rtc.adapters.stt.whisperlive.websockets.connect", return_value=mock_connect):
        lang_arg = language if language else NOT_GIVEN
        result = await stt_adapter._recognize_impl(
            [audio_frame], language=lang_arg, conn_options=DEFAULT_API_CONNECT_OPTIONS
        )

    assert result.alternatives[0].language == expected_lang


##### PROPERTIES #####


@pytest.mark.parametrize(
    ("model", "expected_model"),
    [
        ("large-v3-turbo", "large-v3-turbo"),
        ("large-v3", "large-v3"),
    ],
    ids=["turbo", "standard"],
)
async def test_stt_model_property(model: str, expected_model: str) -> None:
    adapter = WhisperLiveSTT(model=model)

    assert adapter.model == expected_model
    assert adapter.provider == "whisperlive"

    await adapter.aclose()


async def test_stt_capabilities() -> None:
    adapter = WhisperLiveSTT()

    assert adapter.capabilities.streaming is True
    assert adapter.capabilities.interim_results is True

    await adapter.aclose()
