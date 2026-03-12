"""STT transcription quality — WER/CER evaluation via jiwer."""

from __future__ import annotations

import re

import numpy as np
import pytest
from jiwer import cer, process_words
from livekit import rtc
from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from scipy.signal import resample as scipy_resample

from e_agents.rtc.adapters.stt import WhisperLiveSTT
from e_agents.rtc.adapters.tts import KokoroTTS

_WER_THRESHOLD = 0.3
_CER_THRESHOLD = 0.2
_ROUNDTRIP_WER_THRESHOLD = 0.7
_ROUNDTRIP_CER_THRESHOLD = 0.5
_TTS_RATE = 24000
_STT_RATE = 16000

_REFERENCES: dict[str, tuple[str, str]] = {}

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


##### ROUNDTRIP — TTS → STT → WER #####


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
    """Text → TTS → resample → STT → compare WER/CER against original."""
    tts_adapter = KokoroTTS()
    stt_adapter = WhisperLiveSTT(language=language)

    pcm = await _collect_pcm(tts_adapter.synthesize(text))
    assert pcm, "TTS produced no audio"

    pcm_16k = _resample(pcm, _TTS_RATE, _STT_RATE)
    result = await stt_adapter._recognize_impl(
        [_build_frame(pcm_16k)], conn_options=DEFAULT_API_CONNECT_OPTIONS
    )
    hypothesis = _normalize(result.alternatives[0].text)
    reference = _normalize(text)
    alignment = process_words(reference, hypothesis)

    assert alignment.wer < _ROUNDTRIP_WER_THRESHOLD, (
        f"WER {alignment.wer:.1%} — subs={alignment.substitutions} "
        f"ins={alignment.insertions} del={alignment.deletions} | hyp={hypothesis!r}"
    )
    assert cer(reference, hypothesis) < _ROUNDTRIP_CER_THRESHOLD, (
        f"CER {cer(reference, hypothesis):.1%} | hyp={hypothesis!r}"
    )

    await tts_adapter.aclose()
    await stt_adapter.aclose()


##### REFERENCE-BASED WER #####


@pytest.mark.slow
@pytest.mark.parametrize(
    ("fixture_name", "reference", "language"),
    [(k, v[0], v[1]) for k, v in _REFERENCES.items()],
    ids=list(_REFERENCES),
)
async def test_stt_quality_wer_reference(
    fixture_name: str,
    reference: str,
    language: str,
    request: pytest.FixtureRequest,
) -> None:
    """Evaluate WER/CER against known reference transcriptions."""
    audio: bytes = request.getfixturevalue(fixture_name)
    stt_inst = WhisperLiveSTT(language=language)
    result = await stt_inst._recognize_impl(
        [_build_frame(audio)], conn_options=DEFAULT_API_CONNECT_OPTIONS
    )
    hypothesis = _normalize(result.alternatives[0].text)
    ref = _normalize(reference)
    alignment = process_words(ref, hypothesis)

    assert alignment.wer < _WER_THRESHOLD, (
        f"WER {alignment.wer:.1%} — subs={alignment.substitutions} "
        f"ins={alignment.insertions} del={alignment.deletions} | hyp={hypothesis!r}"
    )
    assert cer(ref, hypothesis) < _CER_THRESHOLD, (
        f"CER {cer(ref, hypothesis):.1%} | hyp={hypothesis!r}"
    )

    await stt_inst.aclose()
