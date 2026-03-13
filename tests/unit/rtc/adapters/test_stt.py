"""Unit tests for Speaches STT adapter (mocked services)."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import orjson as json
import pytest
from livekit import rtc
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN

from e_agents.rtc.adapters.stt import SpeachesSTT

##### TRANSCRIPTION #####


@pytest.mark.parametrize(
    ("response_text", "expected_text"),
    [
        ("Hello world", "Hello world"),
        ("", ""),
        ("  trimmed  ", "trimmed"),
    ],
    ids=["simple", "empty", "trimmed"],
)
async def test_stt_recognize_transcripts(
    stt_adapter: SpeachesSTT,
    audio_frame: rtc.AudioFrame,
    mock_httpx_post: Callable[[str], AsyncMock],
    response_text: str,
    expected_text: str,
) -> None:
    mock_client = mock_httpx_post(response_text)

    with patch("e_agents.rtc.adapters.stt.speaches.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await stt_adapter._recognize_impl(
            [audio_frame], conn_options=DEFAULT_API_CONNECT_OPTIONS,
        )

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
    stt_adapter: SpeachesSTT,
    audio_frame: rtc.AudioFrame,
    mock_httpx_post: Callable[[str], AsyncMock],
    language: str | None,
    expected_lang: str,
) -> None:
    mock_client = mock_httpx_post("test")

    with patch("e_agents.rtc.adapters.stt.speaches.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        lang_arg = language if language else NOT_GIVEN
        result = await stt_adapter._recognize_impl(
            [audio_frame], language=lang_arg, conn_options=DEFAULT_API_CONNECT_OPTIONS,
        )

    assert result.alternatives[0].language == expected_lang


##### PROPERTIES #####


@pytest.mark.parametrize(
    ("model", "expected_model"),
    [
        ("deepdml/faster-whisper-large-v3-turbo-ct2", "deepdml/faster-whisper-large-v3-turbo-ct2"),
        ("Systran/faster-distil-whisper-small.en", "Systran/faster-distil-whisper-small.en"),
    ],
    ids=["turbo-ct2", "distil-small"],
)
async def test_stt_model_property(model: str, expected_model: str) -> None:
    adapter = SpeachesSTT(model=model)

    assert adapter.model == expected_model
    assert adapter.provider == "speaches"

    await adapter.aclose()


async def test_stt_capabilities() -> None:
    adapter = SpeachesSTT()

    assert adapter.capabilities.streaming is True

    await adapter.aclose()
