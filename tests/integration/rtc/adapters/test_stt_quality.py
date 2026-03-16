"""STT transcription quality — WER/CER evaluation via pytest-audioeval."""

from __future__ import annotations

import io
import re

import numpy as np
import pytest
import soundfile as sf
from livekit import rtc
from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from pytest_audioeval.client import AudioEval
from pytest_audioeval.metrics.text import TextMetrics
from scipy.signal import resample as scipy_resample

from e_agents.rtc.adapters.stt import FasterWhisperSTT
from e_agents.rtc.adapters.tts import KokoroTTS

_ROUNDTRIP_WER_THRESHOLD = 0.7
_ROUNDTRIP_CER_THRESHOLD = 0.5
_WER_THRESHOLD = 0.3
_CER_THRESHOLD = 0.2
_TTS_RATE = 24000
_STT_RATE = 16000

_STRIP_RE = re.compile(r"[^\w\s]")


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return _STRIP_RE.sub("", text.lower()).strip()


##### HELPERS #####


async def _collect_pcm(stream: tts.ChunkedStream) -> bytes:
    """Collect all PCM int16 bytes from a TTS ChunkedStream."""
    chunks: list[bytes] = []
    async with stream:
        async for ev in stream:
            if hasattr(ev, "frame") and ev.frame:
                chunks.append(bytes(ev.frame.data))
    return b"".join(chunks)


def _resample(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample PCM int16 between sample rates."""
    if from_rate == to_rate:
        return pcm
    audio = np.frombuffer(pcm, dtype=np.int16)
    target_len = int(len(audio) * to_rate / from_rate)
    return scipy_resample(audio, target_len).astype(np.int16).tobytes()


def _build_frame(pcm: bytes, rate: int = _STT_RATE, channels: int = 1) -> rtc.AudioFrame:
    """Build AudioFrame from raw PCM int16 bytes."""
    return rtc.AudioFrame(
        data=pcm,
        sample_rate=rate,
        num_channels=channels,
        samples_per_channel=len(pcm) // (2 * channels),
    )


def _wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int]:
    """Extract PCM int16 and sample rate from WAV bytes."""
    data, rate = sf.read(io.BytesIO(wav_bytes), dtype="int16")
    return data.tobytes(), rate


##### ROUNDTRIP — TTS -> STT -> WER #####


@pytest.mark.slow
@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("she had your dark suit in greasy wash water all year", "en"),
        ("the quick brown fox jumps over the lazy dog", "en"),
        ("please open the door and come inside", "en"),
        ("good morning have a nice day", "en"),
    ],
    ids=["harvard", "pangram", "request", "morning"],
)
async def test_stt_quality_roundtrip_wer(text: str, language: str) -> None:
    """Text -> TTS -> resample -> STT -> compare WER/CER against original."""
    tts_adapter = KokoroTTS()
    stt_adapter = FasterWhisperSTT(language=language)

    pcm = await _collect_pcm(tts_adapter.synthesize(text))
    assert pcm, "TTS produced no audio"

    pcm_16k = _resample(pcm, _TTS_RATE, _STT_RATE)
    result = await stt_adapter._recognize_impl(
        [_build_frame(pcm_16k)], conn_options=DEFAULT_API_CONNECT_OPTIONS,
    )

    TextMetrics.compute(
        _normalize(text), _normalize(result.alternatives[0].text),
    ).assert_quality(max_wer=_ROUNDTRIP_WER_THRESHOLD, max_cer=_ROUNDTRIP_CER_THRESHOLD)

    await tts_adapter.aclose()
    await stt_adapter.aclose()


##### EMBEDDED SAMPLES — GROUND-TRUTH AUDIO -> STT -> WER #####


@pytest.mark.slow
@pytest.mark.parametrize(
    "sample_key",
    ["en_hello_world", "en_counting", "en_quick_brown_fox"],
    ids=["hello-world", "counting", "pangram"],
)
async def test_stt_quality_embedded_en(audioeval: AudioEval, sample_key: str) -> None:
    """Evaluate STT against embedded English ground-truth audio."""
    sample = getattr(audioeval.samples, sample_key)
    stt_adapter = FasterWhisperSTT(language="en")

    pcm, rate = _wav_to_pcm(sample.audio_bytes())
    result = await stt_adapter._recognize_impl(
        [_build_frame(pcm, rate=rate)], conn_options=DEFAULT_API_CONNECT_OPTIONS,
    )

    TextMetrics.compute(
        _normalize(sample.reference_text), _normalize(result.alternatives[0].text),
    ).assert_quality(max_wer=_WER_THRESHOLD, max_cer=_CER_THRESHOLD)

    await stt_adapter.aclose()


@pytest.mark.slow
@pytest.mark.parametrize(
    "sample_key",
    ["es_hola_mundo", "es_conteo", "es_pangrama"],
    ids=["hola-mundo", "conteo", "pangrama"],
)
async def test_stt_quality_embedded_es(audioeval: AudioEval, sample_key: str) -> None:
    """Evaluate STT against embedded Spanish ground-truth audio."""
    sample = getattr(audioeval.samples, sample_key)
    stt_adapter = FasterWhisperSTT(language="es")

    pcm, rate = _wav_to_pcm(sample.audio_bytes())
    result = await stt_adapter._recognize_impl(
        [_build_frame(pcm, rate=rate)], conn_options=DEFAULT_API_CONNECT_OPTIONS,
    )

    TextMetrics.compute(
        _normalize(sample.reference_text), _normalize(result.alternatives[0].text),
    ).assert_quality(max_wer=_WER_THRESHOLD, max_cer=_CER_THRESHOLD)

    await stt_adapter.aclose()
