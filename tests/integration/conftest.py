"""Integration test fixtures — real services via settings."""

from __future__ import annotations

import struct
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from livekit import rtc

from e_agents.rtc.adapters.stt import EVoiceSTT
from e_agents.rtc.adapters.tts import EVoiceTTS

_RESOURCES = Path(__file__).parent.parent / "resources"


@pytest.fixture
def resources_path() -> Path:
    return _RESOURCES


@pytest.fixture
def sample_audio_wav(resources_path: Path) -> bytes:
    """Real WAV audio for STT integration."""
    return (resources_path / "sample_english2.wav").read_bytes()


@pytest.fixture
def sample_audio_mp3(resources_path: Path) -> bytes:
    """Real MP3 audio for STT integration."""
    return (resources_path / "sample_english.mp3").read_bytes()


@pytest.fixture
def sample_pcm_frame() -> rtc.AudioFrame:
    """Minimal silent PCM frame for connectivity tests."""
    pcm = b"\x00\x00" * 1600
    return rtc.AudioFrame(data=pcm, sample_rate=16000, num_channels=1, samples_per_channel=1600)


@pytest.fixture
def sample_wav_bytes() -> bytes:
    """Minimal valid WAV for testing."""
    sample_rate, channels, bps, data_size = 24000, 1, 16, 4800

    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, sample_rate * channels * bps // 8, channels * bps // 8, bps)
    header += b"data"
    header += struct.pack("<I", data_size)
    header += b"\x00" * data_size

    return header


##### ADAPTERS — REAL SERVICES #####


@pytest.fixture
async def stt_adapter() -> AsyncIterator[EVoiceSTT]:
    """EVoiceSTT pointing to real local service."""
    adapter = EVoiceSTT()
    yield adapter
    await adapter.aclose()


@pytest.fixture
async def tts_adapter() -> AsyncIterator[EVoiceTTS]:
    """EVoiceTTS pointing to real local service."""
    adapter = EVoiceTTS()
    yield adapter
    await adapter.aclose()
