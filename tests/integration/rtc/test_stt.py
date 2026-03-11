"""Integration tests for WhisperLive STT adapter."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import orjson as json
import pytest
from livekit import rtc
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN

from e_agents.rtc.adapters.stt import WhisperLiveSTT

##### REAL SERVICE #####


@pytest.mark.slow
async def test_stt_recognize_real_service(sample_audio_wav: bytes) -> None:
    """Against real WhisperLive server — requires running service."""
    stt = WhisperLiveSTT()
    frame = rtc.AudioFrame(
        data=sample_audio_wav,
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=len(sample_audio_wav) // 2,
    )

    result = await stt._recognize_impl([frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"
    assert len(result.alternatives) > 0
    assert result.alternatives[0].text

    await stt.aclose()


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

    with patch("e_agents.rtc.adapters.stt.websockets.connect", return_value=mock_connect):
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

    with patch("e_agents.rtc.adapters.stt.websockets.connect", return_value=mock_connect):
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
    stt = WhisperLiveSTT(model=model)

    assert stt.model == expected_model
    assert stt.provider == "whisperlive"

    await stt.aclose()


async def test_stt_capabilities() -> None:
    stt = WhisperLiveSTT()

    assert stt.capabilities.streaming is False
    assert stt.capabilities.interim_results is False

    await stt.aclose()
