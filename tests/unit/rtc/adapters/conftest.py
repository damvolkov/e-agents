"""Fixtures for adapter unit tests (mocked services)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest
from livekit import rtc

from e_agents.rtc.adapters.stt import WhisperLiveSTT
from e_agents.rtc.adapters.tts import KokoroTTS


async def _async_iter(items: list[bytes]) -> AsyncIterator[bytes]:
    for item in items:
        yield item


##### STT #####


@pytest.fixture
async def stt_adapter() -> AsyncIterator[WhisperLiveSTT]:
    """WhisperLiveSTT adapter with fake URL for mocked tests."""
    adapter = WhisperLiveSTT(ws_url="ws://test-stt:9090", language="en")
    yield adapter
    await adapter.aclose()


@pytest.fixture
def mock_ws_factory() -> Callable[[list[bytes]], AsyncMock]:
    """Factory: mock WebSocket with async iteration over messages."""

    def _factory(messages: list[bytes]) -> AsyncMock:
        ws = AsyncMock()
        ws.send = AsyncMock()
        ws.__aiter__ = lambda self: _async_iter(messages)
        return ws

    return _factory


@pytest.fixture
def mock_connect_factory() -> Callable[[AsyncMock], AsyncMock]:
    """Factory: mock websockets.connect context manager."""

    def _factory(mock_ws: AsyncMock) -> AsyncMock:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_ws)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

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
