"""Streaming STT adapter for Speaches via OpenAI Realtime WebSocket protocol."""

import asyncio
import base64
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

_log = logging.getLogger("e_agents.stt.speaches")

_WS_CLOSE_TIMEOUT = 5
_WS_DRAIN_TIMEOUT = 5
_ECHO_GATE_DURATION = 1.5

##### WHISPER PHANTOM FILTER #####

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)

_WHISPER_PHANTOMS: frozenset[str] = frozenset({
    "gracias",
    "thank you",
    "thanks",
    "thank you for watching",
    "thanks for watching",
    "gracias por ver",
    "subtitulos realizados por la comunidad de amara org",
    "subtitulos por la comunidad de amara org",
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


class SpeachesSTT(stt.STT):
    """STT via Speaches — OpenAI-compatible REST + Realtime WebSocket."""

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
        return "speaches"

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        """Create a streaming recognition session via Realtime WebSocket."""
        effective_lang = language if isinstance(language, str) else self._language
        return SpeachesStream(
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


class SpeachesStream(stt.RecognizeStream):
    """Streaming recognition via Speaches OpenAI Realtime WebSocket.

    Connects to /v1/realtime?intent=transcription&model=<m>&language=<l>.
    Server-side VAD emits clean speech-turn boundaries and final transcripts.
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
            f"{ws_base}/v1/realtime"
            f"?intent=transcription&model={self._model}&language={self._language}"
        )

        try:
            async with websockets.connect(ws_url, close_timeout=_WS_CLOSE_TIMEOUT) as ws:
                init_msg = await asyncio.wait_for(ws.recv(), timeout=10)
                init_data = json.loads(init_msg)
                if init_data.get("type") != "session.created":
                    _log.warning("UNEXPECTED_INIT type=%s", init_data.get("type"))

                _log.debug("STREAM_OPEN lang=%s model=%s", self._language, self._model)

                forward_task = asyncio.create_task(self._sp_forward(ws), name="sp_forward")
                receive_task = asyncio.create_task(self._sp_receive(ws), name="sp_receive")
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

    async def _sp_forward(self, ws: websockets.ClientConnection) -> None:
        """Forward audio frames as base64 PCM16 via Realtime API protocol."""
        async for frame in self._input_ch:
            if isinstance(frame, self._FlushSentinel):
                with contextlib.suppress(Exception):
                    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                continue
            with contextlib.suppress(Exception):
                audio_b64 = base64.b64encode(bytes(frame.data)).decode("ascii")
                await ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64,
                }))

        with contextlib.suppress(Exception):
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

    async def _sp_receive(self, ws: websockets.ClientConnection) -> None:
        """Receive transcription events from Speaches Realtime API."""
        speech_started = False

        try:
            async for msg in ws:
                if not isinstance(msg, (str, bytes)):
                    continue
                data = json.loads(msg)
                event_type = data.get("type", "")

                match event_type:
                    case "input_audio_buffer.speech_started":
                        speech_started = True
                        self._event_ch.send_nowait(
                            stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
                        )

                    case "conversation.item.input_audio_transcription.completed":
                        text = data.get("transcript", "").strip()
                        if not text:
                            continue
                        if _is_echo_suppressed():
                            _log.debug("ECHO_SUPPRESSED text=%r", text)
                            continue
                        if _is_whisper_phantom(text):
                            _log.debug("PHANTOM_FILTERED text=%r", text)
                            continue
                        self._event_ch.send_nowait(stt.SpeechEvent(
                            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                            alternatives=[stt.SpeechData(language=self._language, text=text)],
                        ))
                        _log.debug("FINAL text=%r", text)

                    case "error":
                        _log.error(
                            "REALTIME_ERROR code=%s msg=%s",
                            data.get("code"), data.get("message"),
                        )

        except websockets.exceptions.ConnectionClosed:
            _log.debug("WS_CLOSED")
        finally:
            if speech_started:
                self._event_ch.send_nowait(
                    stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
                )
