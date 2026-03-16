"""Integration tests for FasterWhisper STT — real service at http://localhost:45120."""

from __future__ import annotations

import numpy as np
import pytest
from livekit import rtc
from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from scipy.signal import resample as scipy_resample

from e_agents.rtc.adapters.stt import FasterWhisperSTT
from e_agents.rtc.adapters.tts import KokoroTTS

_TTS_RATE = 24000
_STT_RATE = 16000

##### HELPERS #####


def _build_frame(pcm: bytes, rate: int = _STT_RATE, channels: int = 1) -> rtc.AudioFrame:
    size = len(pcm) - (len(pcm) % 2)
    pcm = pcm[:size]
    return rtc.AudioFrame(
        data=pcm,
        sample_rate=rate,
        num_channels=channels,
        samples_per_channel=size // (2 * channels),
    )


async def _tts_to_pcm(text: str) -> bytes:
    """Generate speech via Kokoro TTS and return raw PCM."""
    adapter = KokoroTTS()
    chunks: list[bytes] = []
    async with adapter.synthesize(text) as stream:
        async for ev in stream:
            if hasattr(ev, "frame") and ev.frame:
                chunks.append(bytes(ev.frame.data))
    await adapter.aclose()
    return b"".join(chunks)


def _resample(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample PCM int16 between sample rates."""
    if from_rate == to_rate:
        return pcm
    audio = np.frombuffer(pcm, dtype=np.int16)
    target_len = int(len(audio) * to_rate / from_rate)
    return scipy_resample(audio, target_len).astype(np.int16).tobytes()


def _generate_tone(freq: float = 440.0, duration: float = 1.0, rate: int = _STT_RATE) -> bytes:
    """Generate a sine wave tone as PCM int16."""
    t = np.linspace(0, duration, int(rate * duration), endpoint=False)
    return (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16).tobytes()


##### BATCH RECOGNITION — TTS→STT ROUNDTRIP #####


@pytest.mark.slow
@pytest.mark.parametrize(
    "text",
    [
        "hello world how are you today",
        "the quick brown fox jumps over the lazy dog",
        "one two three four five",
    ],
    ids=["greeting", "pangram", "counting"],
)
async def test_stt_batch_recognize_speech(text: str) -> None:
    """TTS→resample→STT roundtrip produces non-empty transcript."""
    pcm_24k = await _tts_to_pcm(text)
    pcm_16k = _resample(pcm_24k, _TTS_RATE, _STT_RATE)
    frame = _build_frame(pcm_16k)

    adapter = FasterWhisperSTT(language="en")
    result = await adapter._recognize_impl([frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"
    assert len(result.alternatives) > 0
    assert len(result.alternatives[0].text) > 0
    await adapter.aclose()


@pytest.mark.slow
async def test_stt_batch_recognize_silence(stt_adapter: FasterWhisperSTT) -> None:
    """Batch recognition of silence returns without error."""
    silence = b"\x00\x00" * _STT_RATE
    frame = _build_frame(silence)

    result = await stt_adapter._recognize_impl([frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"


@pytest.mark.slow
async def test_stt_batch_recognize_tone(stt_adapter: FasterWhisperSTT) -> None:
    """Batch recognition of a pure tone completes without error."""
    tone = _generate_tone(440.0, 1.0)
    frame = _build_frame(tone)

    result = await stt_adapter._recognize_impl([frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"


##### LANGUAGE OVERRIDE #####


@pytest.mark.slow
@pytest.mark.parametrize("language", ["en", "es"], ids=["english", "spanish"])
async def test_stt_batch_language_override(language: str) -> None:
    """Batch recognition respects explicit language parameter."""
    pcm_24k = await _tts_to_pcm("hello world")
    pcm_16k = _resample(pcm_24k, _TTS_RATE, _STT_RATE)
    frame = _build_frame(pcm_16k)

    adapter = FasterWhisperSTT(language=language)
    result = await adapter._recognize_impl([frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.alternatives[0].language == language
    await adapter.aclose()


##### CONNECTIVITY #####


@pytest.mark.slow
async def test_stt_service_reachable(stt_adapter: FasterWhisperSTT, sample_pcm_frame: rtc.AudioFrame) -> None:
    """FasterWhisper REST endpoint accepts connection and responds."""
    result = await stt_adapter._recognize_impl([sample_pcm_frame], conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"
    assert len(result.alternatives) > 0


##### MULTIPLE FRAMES #####


@pytest.mark.slow
async def test_stt_batch_multiple_frames() -> None:
    """Batch recognition handles multiple audio frames."""
    pcm_24k = await _tts_to_pcm("testing multiple audio frames together")
    pcm_16k = _resample(pcm_24k, _TTS_RATE, _STT_RATE)

    chunk_size = (len(pcm_16k) // 3) & ~1
    frames = [
        _build_frame(pcm_16k[:chunk_size]),
        _build_frame(pcm_16k[chunk_size : chunk_size * 2]),
        _build_frame(pcm_16k[chunk_size * 2 :]),
    ]

    adapter = FasterWhisperSTT(language="en")
    result = await adapter._recognize_impl(frames, conn_options=DEFAULT_API_CONNECT_OPTIONS)

    assert result.type.name == "FINAL_TRANSCRIPT"
    assert len(result.alternatives) > 0
    await adapter.aclose()
