"""Integration tests for Kokoro TTS adapter via OpenAI-compatible API."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from e_agents.adapters.livekit.tts import KokoroChunkedStream, KokoroTTS


@pytest.fixture
def tts_adapter() -> KokoroTTS:
    """Create TTS adapter instance."""
    return KokoroTTS(base_url="http://localhost:45130/v1")


@pytest.fixture
def mock_pcm_chunk() -> bytes:
    """Generate mock PCM audio data (100ms at 24kHz mono 16-bit)."""
    return b"\x00\x00" * 2400


@pytest.mark.parametrize(
    ("base_url", "model", "voice"),
    [
        ("http://localhost:45130/v1", "kokoro", "af_heart"),
        ("http://tts:8880/v1", "kokoro", "bf_emma"),
        ("http://192.168.1.100:8880/v1", "kokoro", "am_michael"),
    ],
    ids=["local", "docker", "remote"],
)
def test_tts_init_config(base_url: str, model: str, voice: str) -> None:
    """Test TTS adapter initialization with different configs."""
    tts = KokoroTTS(base_url=base_url, model=model, voice=voice)
    assert tts._base_url == base_url.rstrip("/")
    assert tts._model == model
    assert tts._voice == voice


async def test_tts_provider_and_model(tts_adapter: KokoroTTS) -> None:
    """Test TTS adapter properties."""
    assert tts_adapter.provider == "kokoro"
    assert tts_adapter.model.startswith("kokoro/")
    await tts_adapter.aclose()


async def test_tts_capabilities(tts_adapter: KokoroTTS) -> None:
    """Test TTS adapter capabilities."""
    assert tts_adapter.capabilities.streaming is False
    await tts_adapter.aclose()


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
    """Test TTS adapter audio properties."""
    tts = KokoroTTS(sample_rate=sample_rate, num_channels=num_channels)
    assert tts.sample_rate == sample_rate
    assert tts.num_channels == num_channels
    await tts.aclose()


@pytest.mark.parametrize(
    "text",
    [
        "Hello world",
        "Test with numbers 123",
        "Special chars: !@#$%",
        "",
    ],
    ids=["simple", "numbers", "special", "empty"],
)
async def test_synthesize_returns_stream(tts_adapter: KokoroTTS, text: str) -> None:
    """Test synthesize method returns a stream object."""
    stream = tts_adapter.synthesize(text)
    assert isinstance(stream, KokoroChunkedStream)
    await tts_adapter.aclose()


async def test_synthesize_stream_with_mock(
    tts_adapter: KokoroTTS,
    mock_pcm_chunk: bytes,
) -> None:
    """Test TTS synthesis streaming with mocked HTTP response."""
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    chunks_sent = [mock_pcm_chunk, mock_pcm_chunk, mock_pcm_chunk]
    chunk_iter_index = 0

    async def mock_aiter_bytes(size: int = 4096):
        nonlocal chunk_iter_index
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

    with patch("e_agents.adapters.livekit.tts.httpx.AsyncClient", return_value=mock_client):
        stream = tts_adapter.synthesize("Hello world")

        chunks_received = []
        async with stream:
            async for event in stream:
                if hasattr(event, "frame") and event.frame:
                    chunks_received.append(event.frame.data)

        assert len(chunks_received) >= 1

    await tts_adapter.aclose()


async def test_aclose_is_noop(tts_adapter: KokoroTTS) -> None:
    """Test aclose method is a no-op (no persistent connections)."""
    await tts_adapter.aclose()
    await tts_adapter.aclose()
