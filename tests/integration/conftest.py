"""Integration test fixtures."""

import struct
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from livekit import rtc

from e_agents.adapters.stt import WhisperSTT
from e_agents.adapters.tts import PiperTTS


@pytest.fixture
def resources_path() -> Path:
    """Path to test resources directory."""
    return Path(__file__).parent.parent / "resources"


@pytest.fixture
def sample_audio_mp3(resources_path: Path) -> bytes:
    """Load sample English MP3 audio."""
    return (resources_path / "sample_english.mp3").read_bytes()


@pytest.fixture
def sample_audio_wav(resources_path: Path) -> bytes:
    """Load sample English WAV audio."""
    return (resources_path / "sample_english2.wav").read_bytes()


@pytest.fixture
def sample_pcm() -> bytes:
    """Generate silent PCM audio for testing."""
    return b"\x00\x00" * 1600


@pytest.fixture
def audio_frame(sample_pcm: bytes) -> rtc.AudioFrame:
    """Create a test audio frame."""
    return rtc.AudioFrame(
        data=sample_pcm,
        sample_rate=16000,
        num_channels=1,
        samples_per_channel=1600,
    )


@pytest.fixture
def sample_wav_bytes() -> bytes:
    """Generate minimal valid WAV for testing."""
    sample_rate = 24000
    channels = 1
    bits_per_sample = 16
    data_size = 4800

    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<I", 16)
    header += struct.pack("<H", 1)
    header += struct.pack("<H", channels)
    header += struct.pack("<I", sample_rate)
    header += struct.pack("<I", sample_rate * channels * bits_per_sample // 8)
    header += struct.pack("<H", channels * bits_per_sample // 8)
    header += struct.pack("<H", bits_per_sample)
    header += b"data"
    header += struct.pack("<I", data_size)
    header += b"\x00" * data_size

    return header


@pytest.fixture
async def stt_adapter() -> AsyncIterator[WhisperSTT]:
    """Create STT adapter with automatic cleanup."""
    adapter = WhisperSTT(base_url="http://test-stt:8000")
    yield adapter
    await adapter.aclose()


@pytest.fixture
async def tts_adapter() -> AsyncIterator[PiperTTS]:
    """Create TTS adapter with automatic cleanup."""
    adapter = PiperTTS(host="localhost", port=10200)
    yield adapter
    await adapter.aclose()
