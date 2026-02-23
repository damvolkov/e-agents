"""Audio conversion, detection, and VAD utilities."""

import asyncio
import base64
import io
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from ovld import ovld
from scipy import signal
from ten_vad import TenVad

from e_template_agents.core.settings import settings as st


class AudioFormat(StrEnum):
    """Supported audio formats."""

    WAV = "wav"
    MP3 = "mp3"
    FLAC = "flac"
    OGG = "ogg"
    PCM = "pcm"
    UNKNOWN = "unknown"


@ovld  # type: ignore[misc]
def wav_to_pcm(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to raw PCM int16 bytes."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.readframes(wf.getnframes())


@ovld  # type: ignore[misc]
def wav_to_pcm(wav_bytes: bytes, output: type[str]) -> str:  # noqa: F811
    """Convert WAV bytes to base64-encoded PCM string."""
    pcm = wav_to_pcm(wav_bytes)
    return base64.b64encode(pcm).decode()


@ovld  # type: ignore[misc]
def pcm_to_wav(pcm_input: bytes) -> bytes:
    """Convert raw PCM int16 bytes to WAV format."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(st.AUDIO_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(st.AUDIO_SAMPLE_RATE)
        wf.writeframes(pcm_input)
    return buf.getvalue()


@ovld  # type: ignore[misc]
def pcm_to_wav(pcm_input: str) -> bytes:  # noqa: F811
    """Convert base64-encoded PCM string to WAV format."""
    pcm_bytes = base64.b64decode(pcm_input)
    return pcm_to_wav(pcm_bytes)


@ovld  # type: ignore[misc]
def decode_pcm(data: str) -> bytes:
    """Decode base64 PCM string to raw bytes."""
    return base64.b64decode(data)


@ovld  # type: ignore[misc]
def decode_pcm(data: bytes) -> bytes:  # noqa: F811
    """Pass through raw PCM bytes."""
    return data


class AudioConvertor:
    """Audio format conversion and detection."""

    wav_to_pcm = staticmethod(wav_to_pcm)
    pcm_to_wav = staticmethod(pcm_to_wav)
    decode_pcm = staticmethod(decode_pcm)

    @staticmethod
    def detect(audio_bytes: bytes) -> AudioFormat:
        """Detect audio format from bytes."""
        if len(audio_bytes) < 12:
            return AudioFormat.PCM

        header = audio_bytes[:12]

        if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
            return AudioFormat.WAV

        if header[:3] == b"ID3" or header[:2] == b"\xff\xfb":
            return AudioFormat.MP3

        if header[:4] == b"fLaC":
            return AudioFormat.FLAC

        if header[:4] == b"OggS":
            return AudioFormat.OGG

        return AudioFormat.PCM


def resample_to_vad_rate(audio: np.ndarray, source_rate: int) -> np.ndarray:
    """Resample audio to VAD sample rate for processing."""
    if source_rate == st.VAD_SAMPLE_RATE:
        return audio
    num_samples = int(len(audio) * st.VAD_SAMPLE_RATE / source_rate)
    return signal.resample(audio, num_samples).astype(np.int16)


@dataclass
class VADManager:
    """Manages voice activity detection for streaming audio."""

    source_rate: int | None = None
    hop_size: int | None = None
    threshold: float | None = None
    silence_duration: float | None = None
    _vad: TenVad = field(init=False, repr=False)
    _chunks: list[np.ndarray] = field(default_factory=list, init=False, repr=False)
    _speech_detected: bool = field(default=False, init=False)
    _silence_frames: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.source_rate = self.source_rate or st.AUDIO_SAMPLE_RATE
        self.hop_size = self.hop_size or st.VAD_HOP_SIZE
        self.threshold = self.threshold or st.VAD_SPEECH_THRESHOLD
        self.silence_duration = self.silence_duration or st.VAD_SILENCE_DURATION
        self._vad = TenVad(hop_size=self.hop_size, threshold=self.threshold)
        self._silence_frames_threshold = int((self.silence_duration * st.VAD_SAMPLE_RATE) / self.hop_size)

    def reset(self) -> None:
        """Reset VAD state for new utterance."""
        self._chunks.clear()
        self._speech_detected = False
        self._silence_frames = 0

    def _analyze_frames(self, audio_16k: np.ndarray) -> None:
        """Analyze resampled audio frames for speech activity."""
        hop = self.hop_size
        assert hop is not None
        num_frames = len(audio_16k) // hop

        for i in range(num_frames):
            frame = audio_16k[i * hop : (i + 1) * hop]
            if len(frame) < hop:
                break

            _, is_speech = self._vad.process(frame)

            if is_speech == 1:
                self._speech_detected = True
                self._silence_frames = 0
            elif self._speech_detected:
                self._silence_frames += 1

    def feed(self, audio: np.ndarray) -> bool:
        """Feed audio chunk (original rate), return True if utterance complete."""
        self._chunks.append(audio)
        assert self.source_rate is not None
        audio_16k = resample_to_vad_rate(audio, self.source_rate)
        self._analyze_frames(audio_16k)
        return self._speech_detected and self._silence_frames >= self._silence_frames_threshold

    def get_audio(self) -> np.ndarray:
        """Get accumulated audio (original rate) and reset."""
        if not self._chunks:
            return np.array([], dtype=np.int16)
        audio = np.concatenate(self._chunks)
        self.reset()
        return audio

    async def stream_until_silence(self, audio_source: AsyncIterator[np.ndarray]) -> np.ndarray:
        """Stream audio until silence detected after speech."""
        self.reset()
        async for chunk in audio_source:
            if self.feed(chunk):
                break
            await asyncio.sleep(0)
        return self.get_audio()
