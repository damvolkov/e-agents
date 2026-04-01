"""Streaming STT adapter for e-voice via WebSocket + HTTP batch.

Protocol (e-voice WS):
  Audio:    PCM16-LE, 16kHz, mono, binary frames, ~200ms chunks
  End:      text "END_OF_AUDIO" for final flush
  Response: {"type": "transcript_update|transcript_final|session_end",
             "text": "confirmed", "partial": "provisional", "is_final": bool}
"""

import asyncio
import contextlib
import io
import logging
import struct

import httpx
import orjson as json
import websockets
from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer, aio

from e_agents.shared.core.settings import settings as st

_log = logging.getLogger("e_agents.stt.evoice")

_WS_CLOSE_TIMEOUT = 5
_WS_DRAIN_TIMEOUT = 5
_EVOICE_SAMPLE_RATE = 16000
_CHUNK_BYTES = 6400  # ~200ms at 16kHz mono PCM16 (16000 * 2 * 0.2)


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


class EVoiceSTT(stt.STT):
    """STT via e-voice — OpenAI-compatible HTTP batch + WebSocket streaming."""

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
        return "evoice"

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        """Create a streaming recognition session via e-voice WebSocket."""
        effective_lang = language if isinstance(language, str) else self._language
        return EVoiceStream(
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


class EVoiceStream(stt.RecognizeStream):
    """Single persistent WS for the stream lifetime.

    e-voice accumulates text across the session. Each progressive confirmation
    emits FINAL_TRANSCRIPT with the full accumulated text so the agent pipeline
    always has complete context via preemptive_generation.
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
        super().__init__(
            stt=stt_instance,
            conn_options=conn_options,
            sample_rate=_EVOICE_SAMPLE_RATE,
        )
        self._base_url = base_url
        self._language = language
        self._model = model

    async def _run(self) -> None:
        """Single persistent WebSocket for the stream lifetime."""
        ws_base = _base_to_ws(self._base_url)
        ws_url = (
            f"{ws_base}/v1/stt/ws"
            f"?model={self._model}&language={self._language}&response_format=json"
        )

        try:
            async with websockets.connect(ws_url, close_timeout=_WS_CLOSE_TIMEOUT) as ws:
                _log.debug("STREAM_OPEN lang=%s model=%s sr=%d", self._language, self._model, _EVOICE_SAMPLE_RATE)

                forward_task = asyncio.create_task(self._ev_forward(ws), name="ev_forward")
                receive_task = asyncio.create_task(self._ev_receive(ws), name="ev_receive")
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

    async def _ev_forward(self, ws: websockets.ClientConnection) -> None:
        """Buffer audio frames into ~200ms chunks and send as binary."""
        buf = bytearray()
        first = True
        async for frame in self._input_ch:
            if isinstance(frame, self._FlushSentinel):
                continue
            if first:
                _log.debug("AUDIO_FMT sr=%d ch=%d", frame.sample_rate, frame.num_channels)
                first = False
            buf.extend(frame.data)
            if len(buf) >= _CHUNK_BYTES:
                with contextlib.suppress(Exception):
                    await ws.send(bytes(buf))
                buf.clear()
        if buf:
            with contextlib.suppress(Exception):
                await ws.send(bytes(buf))
        with contextlib.suppress(Exception):
            await ws.send("END_OF_AUDIO")

    async def _ev_receive(self, ws: websockets.ClientConnection) -> None:
        """Emit FINAL_TRANSCRIPT with full accumulated text on each confirmation."""
        full_text = ""
        speech_started = False

        try:
            async for msg in ws:
                if not isinstance(msg, (str, bytes)):
                    continue

                raw = msg if isinstance(msg, str) else msg.decode("utf-8", errors="ignore")
                if not raw.strip():
                    continue

                data = json.loads(raw)
                if not isinstance(data, dict):
                    continue

                event_type = data.get("type", "")
                confirmed = data.get("text", "").strip()
                is_final = data.get("is_final", False)

                if confirmed and confirmed != full_text:
                    full_text = confirmed

                    if not speech_started:
                        speech_started = True
                        self._event_ch.send_nowait(
                            stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
                        )

                    self._event_ch.send_nowait(stt.SpeechEvent(
                        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                        alternatives=[stt.SpeechData(language=self._language, text=full_text)],
                    ))
                    _log.debug("FINAL text=%r", full_text)

                if event_type == "session_end" or is_final:
                    break

        except websockets.exceptions.ConnectionClosed:
            _log.debug("WS_CLOSED")
        finally:
            if speech_started:
                self._event_ch.send_nowait(
                    stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
                )
