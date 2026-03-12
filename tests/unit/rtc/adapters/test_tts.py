"""Unit tests for Kokoro TTS adapter (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from e_agents.rtc.adapters.tts import KokoroChunkedStream, KokoroTTS

##### INIT & PROPERTIES #####


@pytest.mark.parametrize(
    ("base_url", "model", "voice"),
    [
        ("http://localhost:45130/v1", "kokoro", "af_heart"),
        ("http://tts:8880/v1", "kokoro", "bf_emma"),
        ("http://192.168.1.100:8880/v1", "kokoro", "am_michael"),
    ],
    ids=["local", "docker", "remote"],
)
async def test_tts_init_config(base_url: str, model: str, voice: str) -> None:
    tts = KokoroTTS(base_url=base_url, model=model, voice=voice)
    assert tts._base_url == base_url.rstrip("/")
    assert tts._model == model
    assert tts._voice == voice


async def test_tts_provider_and_model(tts_adapter: KokoroTTS) -> None:
    assert tts_adapter.provider == "kokoro"
    assert tts_adapter.model.startswith("kokoro/")


async def test_tts_capabilities(tts_adapter: KokoroTTS) -> None:
    assert tts_adapter.capabilities.streaming is False


@pytest.mark.parametrize(
    ("sample_rate", "num_channels"),
    [
        (24000, 1),
        (16000, 1),
        (44100, 2),
    ],
    ids=["24k-mono", "16k-mono", "44k-stereo"],
)
async def test_tts_audio_properties(sample_rate: int, num_channels: int) -> None:
    tts = KokoroTTS(sample_rate=sample_rate, num_channels=num_channels)
    assert tts.sample_rate == sample_rate
    assert tts.num_channels == num_channels
    await tts.aclose()


##### SYNTHESIS #####


@pytest.mark.parametrize(
    "text",
    ["Hello world", "Test with numbers 123", "Special chars: !@#$%", ""],
    ids=["simple", "numbers", "special", "empty"],
)
async def test_synthesize_returns_stream(tts_adapter: KokoroTTS, text: str) -> None:
    stream = tts_adapter.synthesize(text)
    assert isinstance(stream, KokoroChunkedStream)


async def test_synthesize_stream_with_mock(
    tts_adapter: KokoroTTS,
    mock_pcm_chunk: bytes,
) -> None:
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    chunks_sent = [mock_pcm_chunk, mock_pcm_chunk, mock_pcm_chunk]

    async def mock_aiter_bytes(size: int = 4096):
        for chunk in chunks_sent:
            yield chunk

    mock_response.aiter_bytes = mock_aiter_bytes

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("e_agents.rtc.adapters.tts.kokoro.httpx.AsyncClient", return_value=mock_client):
        stream = tts_adapter.synthesize("Hello world")

        chunks_received = []
        async with stream:
            async for event in stream:
                if hasattr(event, "frame") and event.frame:
                    chunks_received.append(event.frame.data)

        assert len(chunks_received) >= 1


##### LIFECYCLE #####


async def test_aclose_is_noop(tts_adapter: KokoroTTS) -> None:
    await tts_adapter.aclose()
    await tts_adapter.aclose()
