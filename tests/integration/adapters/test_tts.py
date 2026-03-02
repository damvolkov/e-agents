"""Integration tests for Piper TTS adapter via Wyoming protocol."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wyoming.audio import AudioChunk
from wyoming.event import Event

from e_agents.adapters.tts import PiperChunkedStream, PiperTTS


@pytest.fixture
def tts_adapter() -> PiperTTS:
    """Create TTS adapter instance."""
    return PiperTTS(host="localhost", port=10200)


@pytest.fixture
def mock_audio_chunk() -> bytes:
    """Generate mock PCM audio data."""
    return b"\x00\x00" * 2205  # 100ms at 22050Hz mono 16-bit


@pytest.mark.parametrize(
    ("host", "port"),
    [
        ("localhost", 10200),
        ("piper", 10200),
        ("192.168.1.100", 5000),
    ],
)
def test_tts_init_config(host: str, port: int) -> None:
    """Test TTS adapter initialization with different configs."""
    tts = PiperTTS(host=host, port=port)
    assert tts._host == host
    assert tts._port == port


async def test_tts_provider_and_model(tts_adapter: PiperTTS) -> None:
    """Test TTS adapter properties."""
    assert tts_adapter.provider == "piper-wyoming"
    assert tts_adapter.model == "piper"
    await tts_adapter.aclose()


async def test_tts_capabilities(tts_adapter: PiperTTS) -> None:
    """Test TTS adapter capabilities."""
    assert tts_adapter.capabilities.streaming is True
    await tts_adapter.aclose()


@pytest.mark.parametrize(
    ("sample_rate", "num_channels"),
    [
        (22050, 1),
        (16000, 1),
        (44100, 2),
    ],
)
async def test_tts_audio_properties(sample_rate: int, num_channels: int) -> None:
    """Test TTS adapter audio properties."""
    tts = PiperTTS(sample_rate=sample_rate, num_channels=num_channels)
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
)
async def test_synthesize_returns_stream(tts_adapter: PiperTTS, text: str) -> None:
    """Test synthesize method returns a stream object."""
    stream = tts_adapter.synthesize(text)
    assert isinstance(stream, PiperChunkedStream)
    await tts_adapter.aclose()


async def test_synthesize_stream_with_mock(
    tts_adapter: PiperTTS,
    mock_audio_chunk: bytes,
) -> None:
    """Test TTS synthesis streaming with mocked Wyoming connection."""
    # Create mock events
    audio_events: list[Event | None] = []
    for _ in range(3):
        event = MagicMock(spec=Event)
        event.type = "audio-chunk"
        event.data = {"rate": 22050, "width": 2, "channels": 1}
        event.payload = mock_audio_chunk
        audio_events.append(event)
    audio_events.append(None)

    call_count = 0

    async def mock_read_event() -> Event | None:
        nonlocal call_count
        if call_count >= len(audio_events):
            return None
        event = audio_events[call_count]
        call_count += 1
        return event

    # Create mock client
    mock_client = MagicMock()
    mock_client.write_event = AsyncMock()
    mock_client.read_event = mock_read_event
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("e_agents.adapters.tts.AsyncTcpClient", return_value=mock_client),
        patch.object(AudioChunk, "is_type", side_effect=lambda t: t == "audio-chunk"),
        patch.object(
            AudioChunk,
            "from_event",
            side_effect=lambda e: MagicMock(audio=mock_audio_chunk),
        ),
    ):
        stream = tts_adapter.synthesize("Hello world")

        chunks_received = []
        async with stream:
            async for event in stream:
                if hasattr(event, "frame") and event.frame:
                    chunks_received.append(event.frame.data)

        assert len(chunks_received) >= 1  # At least one chunk should be received

    await tts_adapter.aclose()


async def test_aclose_is_noop(tts_adapter: PiperTTS) -> None:
    """Test aclose method is a no-op (no persistent connections)."""
    await tts_adapter.aclose()
    await tts_adapter.aclose()  # Should not raise
