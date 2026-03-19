"""TTS output quality — audio validation and PESQ evaluation via pytest-audioeval."""

from __future__ import annotations

import numpy as np
import pytest
from livekit.agents import tts
from pytest_audioeval.metrics.audio import AudioMetrics
from scipy.signal import resample as scipy_resample

from e_agents.rtc.adapters.tts import EVoiceTTS

_TTS_RATE = 24000
_PESQ_RATE = 16000
_PESQ_THRESHOLD = 3.0


##### HELPERS #####


async def _collect_pcm(stream: tts.ChunkedStream) -> bytes:
    """Collect all PCM int16 bytes from a TTS ChunkedStream."""
    chunks: list[bytes] = []
    async with stream:
        async for ev in stream:
            if hasattr(ev, "frame") and ev.frame:
                chunks.append(bytes(ev.frame.data))
    return b"".join(chunks)


def _resample_float(pcm: bytes, from_rate: int, to_rate: int) -> np.ndarray:
    """Resample PCM int16 to float64 normalized [-1, 1]."""
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0
    if from_rate == to_rate:
        return audio
    target_len = int(len(audio) * to_rate / from_rate)
    return scipy_resample(audio, target_len)


##### AUDIO FORMAT VALIDATION #####


@pytest.mark.slow
@pytest.mark.parametrize(
    "text",
    [
        "hello world",
        "the quick brown fox jumps over the lazy dog",
        "testing one two three",
    ],
    ids=["short", "medium", "numbers"],
)
async def test_tts_audio_valid_pcm(text: str) -> None:
    """TTS produces non-empty PCM with reasonable amplitude and duration."""
    adapter = EVoiceTTS()
    pcm = await _collect_pcm(adapter.synthesize(text))
    audio = np.frombuffer(pcm, dtype=np.int16)

    assert len(pcm) > 0, "Empty PCM output"
    assert len(audio) > _TTS_RATE * 0.1, "Audio shorter than 100ms"
    assert np.any(audio != 0), "Audio is all zeros (silence)"
    assert np.abs(audio).max() > 100, "Audio amplitude too low"

    await adapter.aclose()


##### PESQ — CONSISTENCY #####


@pytest.mark.slow
async def test_tts_pesq_consistency() -> None:
    """Two TTS runs of same text produce perceptually similar audio (PESQ >= threshold)."""
    adapter = EVoiceTTS()
    text = "the quick brown fox jumps over the lazy dog"

    pcm_a = await _collect_pcm(adapter.synthesize(text))
    pcm_b = await _collect_pcm(adapter.synthesize(text))

    ref = _resample_float(pcm_a, _TTS_RATE, _PESQ_RATE)
    deg = _resample_float(pcm_b, _TTS_RATE, _PESQ_RATE)

    min_len = min(len(ref), len(deg))
    AudioMetrics.compute(
        ref[:min_len], deg[:min_len], sample_rate=_PESQ_RATE,
    ).assert_quality(min_mos=_PESQ_THRESHOLD)

    await adapter.aclose()
