"""Integration tests for WhisperLive STT adapter."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import orjson as json
import pytest
from livekit import rtc

from e_agents.adapters.livekit.stt import WhisperLiveSTT


async def _async_iter(items: list[bytes]) -> AsyncIterator[bytes]:
    """Yield items as an async iterator."""
    for item in items:
        yield item


def _make_mock_ws(messages: list[bytes]) -> AsyncMock:
    """Create a mock WebSocket with async iteration support."""
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.__aiter__ = lambda self: _async_iter(messages)
    return mock_ws


def _make_mock_connect(mock_ws: AsyncMock) -> AsyncMock:
    """Create a mock websockets.connect context manager."""
    mock_connect = AsyncMock()
    mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_connect.__aexit__ = AsyncMock(return_value=None)
    return mock_connect


@pytest.mark.slow
async def test_stt_recognize_with_real_service(sample_audio_wav: bytes) -> None:
    """Test STT recognition against real WhisperLive server."""
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

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
    response_segments: list[dict],
    expected_text: str,
) -> None:
    """Test STT transcription with various WebSocket responses."""
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

    messages = [
        json.dumps({"uid": "test", "message": "SERVER_READY"}),
        json.dumps({"uid": "test", "segments": response_segments}),
        json.dumps({"uid": "test", "message": "DISCONNECT"}),
    ]

    mock_ws = _make_mock_ws(messages)
    mock_connect = _make_mock_connect(mock_ws)

    with patch("e_agents.adapters.livekit.stt.websockets.connect", return_value=mock_connect):
        result = await stt_adapter._recognize_impl([audio_frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"
    assert result.alternatives[0].text == expected_text


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
async def test_stt_recognize_with_language(
    stt_adapter: WhisperLiveSTT,
    audio_frame: rtc.AudioFrame,
    language: str | None,
    expected_lang: str,
) -> None:
    """Test STT transcription with explicit language."""
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN

    messages = [
        json.dumps({"uid": "test", "segments": [{"text": "test"}]}),
        json.dumps({"uid": "test", "message": "DISCONNECT"}),
    ]

    mock_ws = _make_mock_ws(messages)
    mock_connect = _make_mock_connect(mock_ws)

    with patch("e_agents.adapters.livekit.stt.websockets.connect", return_value=mock_connect):
        lang_arg = language if language else NOT_GIVEN
        result = await stt_adapter._recognize_impl(
            [audio_frame], language=lang_arg, conn_options=DEFAULT_API_CONNECT_OPTIONS
        )

    assert result.alternatives[0].language == expected_lang


@pytest.mark.parametrize(
    ("model", "expected_model"),
    [
        ("large-v3-turbo", "large-v3-turbo"),
        ("large-v3", "large-v3"),
    ],
    ids=["turbo", "standard"],
)
async def test_stt_model_property(model: str, expected_model: str) -> None:
    """Test STT adapter model property."""
    stt = WhisperLiveSTT(model=model)

    assert stt.model == expected_model
    assert stt.provider == "whisperlive"

    await stt.aclose()


async def test_stt_capabilities() -> None:
    """Test STT adapter capabilities."""
    stt = WhisperLiveSTT()

    assert stt.capabilities.streaming is False
    assert stt.capabilities.interim_results is False

    await stt.aclose()
