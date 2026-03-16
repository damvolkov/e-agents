"""Streaming STT adapter for faster-whisper-server (fedirz) via WebSocket."""

import asyncio
import contextlib
import io
import logging
import re
import struct
import time as _time

import httpx
import orjson as json
import websockets
from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer, aio

from e_agents.shared.core.settings import settings as st

_log = logging.getLogger("e_agents.stt.fwhisper")

_WS_CLOSE_TIMEOUT = 5
_WS_DRAIN_TIMEOUT = 5
_ECHO_GATE_DURATION = 1.5

##### WHISPER PHANTOM FILTER #####

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

_WHISPER_PHANTOMS: frozenset[str] = frozenset({
    "gracias",
    "gracias por ver",
    "gracias por ver el video",
    "suscribete",
    "suscribete al canal",
    "me gusta",
    "subtitulos realizados por la comunidad de amara org",
    "subtitulos por la comunidad de amara org",
    "thank you",
    "thanks",
    "thank you for watching",
    "thanks for watching",
    "subscribe",
    "like and subscribe",
    "you",
})


def _is_whisper_phantom(text: str) -> bool:
    """Detect known Whisper hallucinations (exact match only, not substring)."""
    normalized = _PUNCT_RE.sub("", text.strip().lower()).strip()
    return normalized in _WHISPER_PHANTOMS


##### ECHO / SPEAKING-STATE SUPPRESSION #####

_echo_gate_until: float = 0.0
_agent_speaking: bool = False


def set_agent_speaking(speaking: bool) -> None:
    """Gate STT output while agent speaks, plus post-speech cooldown."""
    global _agent_speaking, _echo_gate_until  # noqa: PLW0603
    _agent_speaking = speaking
    if not speaking:
        _echo_gate_until = _time.monotonic() + _ECHO_GATE_DURATION


def _is_echo_suppressed() -> bool:
    return _agent_speaking or _time.monotonic() < _echo_gate_until


##### AUDIO HELPERS #####


def _pcm_to_wav(
    pcm: bytes, *, sample_rate: int = 16000, channels: int = 1, bits: int = 16,
) -> bytes:
    """Wrap raw PCM int16 in a WAV header for the REST endpoint."""
    buf = io.BytesIO()
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm)))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(pcm)))
    buf.write(pcm)
    return buf.getvalue()


def _base_to_ws(base_url: str) -> str:
    """Convert http(s) base URL to ws(s)."""
    if base_url.startswith("https"):
        return "wss" + base_url[5:]
    return "ws" + base_url[4:]


##### STREAMING STT #####


class FasterWhisperSTT(stt.STT):
    """STT via faster-whisper-server — OpenAI-compatible REST + raw binary WebSocket."""

    def __init__(
        self,
        *,
        base_url: str = str(st.STT_BASE_URL),
        language: str = st.USER_LANGUAGE,
        model: str = st.STT_MODEL,
        timeout: float = st.STT_TIMEOUT,
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=False),
        )
        self._base_url = base_url.rstrip("/")
        self._language = language
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "fwhisper"

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        """Create a streaming recognition session via raw binary WebSocket."""
        effective_lang = language if isinstance(language, str) else self._language
        return FasterWhisperStream(
            self,
            base_url=self._base_url,
            language=effective_lang,
            model=self._model,
            conn_options=conn_options,
        )

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        """Batch recognition via /v1/audio/transcriptions REST endpoint."""
        effective_lang = language if isinstance(language, str) else self._language
        combined = rtc.combine_audio_frames(buffer)
        wav_bytes = _pcm_to_wav(
            bytes(combined.data),
            sample_rate=combined.sample_rate,
            channels=combined.num_channels,
        )

        text = ""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/audio/transcriptions",
                    files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                    data={
                        "model": self._model,
                        "language": effective_lang,
                        "response_format": "json",
                    },
                )
                resp.raise_for_status()
                text = json.loads(resp.content).get("text", "").strip()
        except Exception:
            _log.exception("STT_BATCH_ERROR url=%s", self._base_url)

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language=effective_lang, text=text)],
        )

    async def aclose(self) -> None:
        """No persistent connections to close."""


##### STREAMING RECOGNIZER #####


class FasterWhisperStream(stt.RecognizeStream):
    """Streaming recognition via faster-whisper-server WebSocket.

    Connects to /v1/audio/transcriptions?model=<m>&language=<l>&response_format=json.
    Client sends raw binary PCM16 LE audio (16kHz, mono).
    Server responds with cumulative confirmed transcription via LocalAgreement2.
    """

    def __init__(
        self,
        stt_instance: stt.STT,
        *,
        base_url: str,
        language: str,
        model: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(stt=stt_instance, conn_options=conn_options)
        self._base_url = base_url
        self._language = language
        self._model = model

    async def _run(self) -> None:
        """Single persistent WebSocket for the stream lifetime."""
        ws_base = _base_to_ws(self._base_url)
        ws_url = (
            f"{ws_base}/v1/audio/transcriptions"
            f"?model={self._model}&language={self._language}&response_format=json"
        )

        try:
            async with websockets.connect(ws_url, close_timeout=_WS_CLOSE_TIMEOUT) as ws:
                _log.debug("STREAM_OPEN lang=%s model=%s", self._language, self._model)

                forward_task = asyncio.create_task(self._fw_forward(ws), name="fw_forward")
                receive_task = asyncio.create_task(self._fw_receive(ws), name="fw_receive")
                try:
                    await forward_task
                    with contextlib.suppress(TimeoutError):
                        async with asyncio.timeout(_WS_DRAIN_TIMEOUT):
                            await receive_task
                finally:
                    await aio.cancel_and_wait(forward_task, receive_task)
        except Exception:
            _log.exception("STREAM_ERROR")
        _log.debug("STREAM_DONE")

    async def _fw_forward(self, ws: websockets.ClientConnection) -> None:
        """Forward audio frames as raw binary PCM16 LE."""
        async for frame in self._input_ch:
            if isinstance(frame, self._FlushSentinel):
                continue
            with contextlib.suppress(Exception):
                await ws.send(bytes(frame.data))

    async def _fw_receive(self, ws: websockets.ClientConnection) -> None:
        """Receive cumulative transcriptions and emit diffs as FINAL_TRANSCRIPT."""
        committed_len = 0
        speech_started = False

        try:
            async for msg in ws:
                if not isinstance(msg, (str, bytes)):
                    continue

                data = json.loads(msg)
                cumulative_text = data.get("text", "").strip() if isinstance(data, dict) else str(data).strip()

                if not cumulative_text:
                    continue

                new_text = cumulative_text[committed_len:].strip()
                if not new_text:
                    continue

                if _is_echo_suppressed():
                    _log.debug("ECHO_SUPPRESSED text=%r", new_text)
                    committed_len = len(cumulative_text)
                    continue

                if _is_whisper_phantom(cumulative_text):
                    _log.debug("PHANTOM_FILTERED text=%r", cumulative_text)
                    committed_len = len(cumulative_text)
                    continue

                if not speech_started:
                    speech_started = True
                    self._event_ch.send_nowait(
                        stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
                    )

                self._event_ch.send_nowait(stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[stt.SpeechData(language=self._language, text=new_text)],
                ))
                committed_len = len(cumulative_text)
                _log.debug("FINAL text=%r", new_text)

        except websockets.exceptions.ConnectionClosed:
            _log.debug("WS_CLOSED")
        finally:
            if speech_started:
                self._event_ch.send_nowait(
                    stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
                )
