"""Integration tests for Kokoro TTS — real service at http://localhost:45130."""

from __future__ import annotations

import numpy as np
import pytest
from livekit.agents import tts

from e_agents.rtc.adapters.tts import KokoroTTS

_TTS_RATE = 24000

##### HELPERS #####


async def _collect_pcm(stream: tts.ChunkedStream) -> bytes:
    """Collect all PCM int16 bytes from a TTS ChunkedStream."""
    chunks: list[bytes] = []
    async with stream:
        async for ev in stream:
            if hasattr(ev, "frame") and ev.frame:
                chunks.append(bytes(ev.frame.data))
    return b"".join(chunks)


##### SYNTHESIS — REAL SERVICE #####


@pytest.mark.slow
@pytest.mark.parametrize(
    "text",
    [
        "hello world",
        "the quick brown fox jumps over the lazy dog",
        "testing one two three four five",
    ],
    ids=["short", "pangram", "numbers"],
)
async def test_tts_synthesize_produces_audio(tts_adapter: KokoroTTS, text: str) -> None:
    """TTS produces non-empty PCM with valid signal."""
    pcm = await _collect_pcm(tts_adapter.synthesize(text))

    assert len(pcm) > 0, "Empty PCM output"
    audio = np.frombuffer(pcm, dtype=np.int16)
    assert len(audio) > _TTS_RATE * 0.1, "Audio shorter than 100ms"
    assert np.any(audio != 0), "Audio is all zeros"


@pytest.mark.slow
async def test_tts_synthesize_long_text(tts_adapter: KokoroTTS) -> None:
    """TTS handles longer text without error."""
    text = "This is a longer sentence to test that the text to speech system can handle multiple words and produce a reasonable amount of audio output."
    pcm = await _collect_pcm(tts_adapter.synthesize(text))

    audio = np.frombuffer(pcm, dtype=np.int16)
    duration = len(audio) / _TTS_RATE
    assert duration > 1.0, f"Long text produced only {duration:.1f}s of audio"


##### VOICE VARIANTS #####


@pytest.mark.slow
@pytest.mark.parametrize(
    "voice",
    ["af_heart", "ef_dora"],
    ids=["af_heart", "ef_dora"],
)
async def test_tts_voice_produces_audio(voice: str) -> None:
    """Different voices produce valid audio."""
    adapter = KokoroTTS(voice=voice)
    pcm = await _collect_pcm(adapter.synthesize("hello world"))

    assert len(pcm) > 0, f"Voice '{voice}' produced empty audio"
    audio = np.frombuffer(pcm, dtype=np.int16)
    assert np.any(audio != 0), f"Voice '{voice}' produced silence"
    await adapter.aclose()


##### AUDIO FORMAT #####


@pytest.mark.slow
async def test_tts_audio_format(tts_adapter: KokoroTTS) -> None:
    """PCM output is valid int16 with expected sample rate."""
    pcm = await _collect_pcm(tts_adapter.synthesize("test"))

    assert len(pcm) % 2 == 0, "PCM byte count must be even (int16)"
    assert tts_adapter.sample_rate == _TTS_RATE
    assert tts_adapter.num_channels == 1


##### CONNECTIVITY #####


@pytest.mark.slow
async def test_tts_service_reachable(tts_adapter: KokoroTTS) -> None:
    """Kokoro HTTP endpoint accepts requests and returns audio."""
    pcm = await _collect_pcm(tts_adapter.synthesize("ping"))
    assert len(pcm) > 0


##### CONSISTENCY #####


@pytest.mark.slow
async def test_tts_deterministic_output(tts_adapter: KokoroTTS) -> None:
    """Two runs with the same text produce audio of similar length."""
    text = "hello world"
    pcm_a = await _collect_pcm(tts_adapter.synthesize(text))
    pcm_b = await _collect_pcm(tts_adapter.synthesize(text))

    len_a, len_b = len(pcm_a), len(pcm_b)
    ratio = min(len_a, len_b) / max(len_a, len_b) if max(len_a, len_b) > 0 else 1.0
    assert ratio > 0.8, f"Audio lengths differ too much: {len_a} vs {len_b}"
