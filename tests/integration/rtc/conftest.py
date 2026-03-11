"""Fixtures for adapter integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest

from e_agents.rtc.adapters.tts import KokoroTTS

##### PRIVATE HELPERS #####


async def _async_iter(items: list[bytes]) -> AsyncIterator[bytes]:
    for item in items:
        yield item


##### FIXTURES — TTS #####


@pytest.fixture
async def tts_adapter() -> AsyncIterator[KokoroTTS]:
    """KokoroTTS adapter scoped to adapter tests (localhost)."""
    adapter = KokoroTTS(base_url="http://localhost:45130/v1")
    yield adapter
    await adapter.aclose()


@pytest.fixture
def mock_pcm_chunk() -> bytes:
    """Mock PCM audio data (100ms at 24kHz mono 16-bit)."""
    return b"\x00\x00" * 2400


##### FIXTURES — STT MOCK FACTORIES #####


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
