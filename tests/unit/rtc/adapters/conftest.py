"""Fixtures for adapter unit tests (mocked services)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock

import orjson as json
import pytest
from livekit import rtc

from e_agents.rtc.adapters.stt import FasterWhisperSTT
from e_agents.rtc.adapters.tts import KokoroTTS


##### STT #####


@pytest.fixture
async def stt_adapter() -> AsyncIterator[FasterWhisperSTT]:
    """FasterWhisperSTT adapter with fake URL for mocked tests."""
    adapter = FasterWhisperSTT(base_url="http://test-stt:8000", language="en")
    yield adapter
    await adapter.aclose()


@pytest.fixture
def mock_httpx_post() -> Callable[[str], AsyncMock]:
    """Factory: mock httpx client returning JSON transcription response."""

    def _factory(response_text: str) -> AsyncMock:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = json.dumps({"text": response_text})
        mock_response.raise_for_status = MagicMock()

        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_response)
        return client

    return _factory


@pytest.fixture
def audio_frame() -> rtc.AudioFrame:
    """Silent PCM test audio frame."""
    pcm = b"\x00\x00" * 1600
    return rtc.AudioFrame(data=pcm, sample_rate=16000, num_channels=1, samples_per_channel=1600)


##### TTS #####


@pytest.fixture
async def tts_adapter() -> AsyncIterator[KokoroTTS]:
    """KokoroTTS adapter with fake URL for mocked tests."""
    adapter = KokoroTTS(base_url="http://test-tts:8880/v1")
    yield adapter
    await adapter.aclose()


@pytest.fixture
def mock_pcm_chunk() -> bytes:
    """Mock PCM audio data (100ms at 24kHz mono 16-bit)."""
    return b"\x00\x00" * 2400
