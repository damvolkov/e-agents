"""Integration tests for STT adapter."""

import pytest
import respx
from httpx import Response
from livekit import rtc

from e_agents.adapters.stt import WhisperSTT


@pytest.mark.slow
async def test_stt_recognize_with_real_service(sample_audio_wav: bytes) -> None:
    """Test STT recognition against real faster-whisper-server."""
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

    stt = WhisperSTT()
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


@respx.mock
@pytest.mark.parametrize(
    ("response_text", "expected_text"),
    [
        ("Hello world", "Hello world"),
        ("", ""),
        ("  trimmed  ", "trimmed"),
        ("Hola mundo", "Hola mundo"),
    ],
)
async def test_stt_recognize_transcripts(
    stt_adapter: WhisperSTT,
    audio_frame: rtc.AudioFrame,
    response_text: str,
    expected_text: str,
) -> None:
    """Test STT transcription with various responses."""
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

    respx.post("http://test-stt:8000/v1/audio/transcriptions").mock(
        return_value=Response(200, json={"text": response_text})
    )

    result = await stt_adapter._recognize_impl([audio_frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"
    assert result.alternatives[0].text == expected_text


@respx.mock
@pytest.mark.parametrize(
    ("language", "expected_lang"),
    [
        ("en", "en"),
        ("es", "es"),
        ("fr", "fr"),
        (None, "en"),
    ],
)
async def test_stt_recognize_with_language(
    stt_adapter: WhisperSTT,
    audio_frame: rtc.AudioFrame,
    language: str | None,
    expected_lang: str,
) -> None:
    """Test STT transcription with explicit language."""
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN

    respx.post("http://test-stt:8000/v1/audio/transcriptions").mock(return_value=Response(200, json={"text": "test"}))

    lang_arg = language if language else NOT_GIVEN
    result = await stt_adapter._recognize_impl(
        [audio_frame], language=lang_arg, conn_options=DEFAULT_API_CONNECT_OPTIONS
    )

    assert result.alternatives[0].language == expected_lang


@pytest.mark.parametrize(
    ("model", "expected_model"),
    [
        ("Systran/faster-whisper-small", "Systran/faster-whisper-small"),
        ("Systran/faster-whisper-large-v3", "Systran/faster-whisper-large-v3"),
    ],
)
async def test_stt_model_property(model: str, expected_model: str) -> None:
    """Test STT adapter model property."""
    stt = WhisperSTT(model=model)

    assert stt.model == expected_model
    assert stt.provider == "faster-whisper-server"

    await stt.aclose()


async def test_stt_capabilities() -> None:
    """Test STT adapter capabilities."""
    stt = WhisperSTT()

    assert stt.capabilities.streaming is False
    assert stt.capabilities.interim_results is False

    await stt.aclose()
