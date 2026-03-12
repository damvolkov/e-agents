"""Streaming STT adapter for WhisperLive via WebSocket."""

import asyncio
import contextlib
import logging

import numpy as np
import orjson as json
import websockets
from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer, aio, shortuuid

from e_agents.shared.core.settings import settings as st

_log = logging.getLogger("e_agents.stt.whisperlive")

_STABLE_DELAY = 0.8
_WS_DRAIN_TIMEOUT = 5
_WS_CLOSE_TIMEOUT = 5

_HALLUCINATION_PATTERNS: frozenset[str] = frozenset({
    "gracias", "gracias.", "gracias!", "¡gracias!",
    "gracias por ver.", "gracias por ver el vídeo.", "gracias por ver el video.",
    "thank you.", "thank you", "thanks.", "thanks for watching.",
    "merci.", "merci d'avoir regardé.", "danke.", "obrigado.", "obrigada.",
    "adiós.", "bye.", "goodbye.",
    "subtítulos por...", "subtítulos realizados por...",
    "subtitles by...", "subtitles made by...",
    "¡suscríbete!", "subscribe!", "like and subscribe!",
    "...", ".", "!", "?", "¿?",
})
_MIN_HALLUCINATION_WORDS = 2


def _is_hallucination(text: str) -> bool:
    """Detect common Whisper hallucinations on silence/echo."""
    stripped = text.strip().lower()
    return stripped in _HALLUCINATION_PATTERNS or len(stripped.split()) < _MIN_HALLUCINATION_WORDS


def _pcm_int16_to_float32(data: bytes | bytearray | memoryview) -> bytes:
    """Convert PCM int16 audio to float32 normalized [-1, 1] for WhisperLive."""
    return (np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0).tobytes()


##### STREAMING STT #####


class WhisperLiveSTT(stt.STT):
    """Streaming STT via WhisperLive WebSocket protocol."""

    def __init__(
        self,
        *,
        ws_url: str = str(st.STT_WS_URL),
        language: str = st.USER_LANGUAGE,
        model: str = st.STT_MODEL,
        timeout: float = st.STT_TIMEOUT,
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=True,
                interim_results=True,
            )
        )
        self._ws_url = ws_url.rstrip("/")
        self._language = language
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "whisperlive"

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        """Create a streaming recognition session."""
        effective_lang = language if isinstance(language, str) else self._language
        return WhisperLiveStream(
            self,
            ws_url=self._ws_url,
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
        """Batch recognition fallback."""
        effective_lang = language if isinstance(language, str) else self._language
        combined = rtc.combine_audio_frames(buffer)
        audio_bytes = _pcm_int16_to_float32(combined.data)
        uid = shortuuid()

        config_msg = json.dumps({
            "uid": uid,
            "language": effective_lang,
            "model": self._model,
            "task": "transcribe",
            "use_vad": False,
        })

        text = ""
        try:
            async with websockets.connect(self._ws_url, close_timeout=_WS_CLOSE_TIMEOUT) as ws:
                await ws.send(config_msg)
                await ws.recv()
                chunk_size = 8192
                for i in range(0, len(audio_bytes), chunk_size):
                    await ws.send(audio_bytes[i : i + chunk_size])
                    await asyncio.sleep(0.01)
                await asyncio.sleep(0.5)
                await ws.send(json.dumps({"uid": uid, "message": "END"}))

                with contextlib.suppress(TimeoutError):
                    async with asyncio.timeout(self._timeout):
                        async for msg in ws:
                            if not isinstance(msg, (str, bytes)):
                                continue
                            data = json.loads(msg)
                            segments = data.get("segments", [])
                            if segments:
                                text = " ".join(
                                    s.get("text", "").strip()
                                    for s in segments
                                    if s.get("text", "").strip()
                                )
                            if data.get("message") in ("DISCONNECT", "END"):
                                break
        except Exception:
            _log.exception("STT_BATCH_ERROR url=%s", self._ws_url)

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language=effective_lang, text=text.strip())],
        )

    async def aclose(self) -> None:
        """No persistent connections to close."""


##### STREAMING RECOGNIZER #####


class WhisperLiveStream(stt.RecognizeStream):
    """Streaming recognition via a single persistent WhisperLive WebSocket.

    Emits FINAL_TRANSCRIPT after text stabilises for ``_STABLE_DELAY`` seconds,
    which matches livekit-agents 1.3.x expectations (no FlushSentinel from the
    framework during normal streaming).
    """

    def __init__(
        self,
        stt_instance: stt.STT,
        *,
        ws_url: str,
        language: str,
        model: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(stt=stt_instance, conn_options=conn_options)
        self._ws_url = ws_url
        self._language = language
        self._model = model

    async def _run(self) -> None:
        """Single persistent WebSocket for the stream lifetime."""
        uid = shortuuid()
        try:
            async with websockets.connect(self._ws_url, close_timeout=_WS_CLOSE_TIMEOUT) as ws:
                config = json.dumps({
                    "uid": uid,
                    "language": self._language,
                    "model": self._model,
                    "task": "transcribe",
                    "use_vad": True,
                })
                await ws.send(config)
                _log.debug("STREAM_OPEN uid=%s lang=%s", uid, self._language)

                forward_task = asyncio.create_task(
                    self._wl_forward(ws, uid), name="wl_forward",
                )
                receive_task = asyncio.create_task(
                    self._wl_receive(ws), name="wl_receive",
                )
                try:
                    await forward_task
                    with contextlib.suppress(TimeoutError):
                        async with asyncio.timeout(_WS_DRAIN_TIMEOUT):
                            await receive_task
                finally:
                    await aio.cancel_and_wait(forward_task, receive_task)
        except Exception:
            _log.exception("STREAM_ERROR uid=%s", uid)
        _log.debug("STREAM_DONE uid=%s", uid)

    async def _wl_forward(self, ws: websockets.ClientConnection, uid: str) -> None:
        """Forward audio frames to WhisperLive; ignore FlushSentinels."""
        async for frame in self._input_ch:
            if isinstance(frame, self._FlushSentinel):
                continue
            with contextlib.suppress(Exception):
                await ws.send(_pcm_int16_to_float32(frame.data))
        with contextlib.suppress(Exception):
            await ws.send(json.dumps({"uid": uid, "message": "END"}))

    async def _wl_receive(self, ws: websockets.ClientConnection) -> None:
        """Receive transcriptions; debounce-emit FINAL after text stabilises."""
        last_text = ""
        committed_len = 0
        speech_started = False
        debounce: asyncio.Task[None] | None = None

        async def _try_finalize(target_text: str, guard_len: int) -> None:
            nonlocal committed_len
            await asyncio.sleep(_STABLE_DELAY)
            if committed_len != guard_len:
                return
            new = target_text[committed_len:].strip()
            if not new:
                return
            if _is_hallucination(new):
                _log.debug("HALLUCINATION_FILTERED text=%r", new)
                committed_len = len(target_text)
                return
            self._event_ch.send_nowait(stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(language=self._language, text=new)],
            ))
            committed_len = len(target_text)
            _log.debug("FINAL text=%r", new)

        try:
            async for msg in ws:
                if not isinstance(msg, (str, bytes)):
                    continue
                data = json.loads(msg)
                segments = data.get("segments", [])
                text = " ".join(
                    s.get("text", "").strip()
                    for s in segments
                    if s.get("text", "").strip()
                )

                if text and not speech_started:
                    speech_started = True
                    self._event_ch.send_nowait(
                        stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
                    )

                if text and text != last_text:
                    last_text = text
                    if debounce and not debounce.done():
                        debounce.cancel()
                    new = text[committed_len:].strip()
                    if new:
                        self._event_ch.send_nowait(stt.SpeechEvent(
                            type=stt.SpeechEventType.INTERIM_TRANSCRIPT,
                            alternatives=[
                                stt.SpeechData(language=self._language, text=new),
                            ],
                        ))
                    debounce = asyncio.create_task(
                        _try_finalize(text, committed_len),
                    )

                if data.get("message") in ("DISCONNECT", "END"):
                    break
        finally:
            if debounce and not debounce.done():
                debounce.cancel()
            if last_text:
                remaining = last_text[committed_len:].strip()
                if remaining and not _is_hallucination(remaining):
                    self._event_ch.send_nowait(stt.SpeechEvent(
                        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                        alternatives=[
                            stt.SpeechData(language=self._language, text=remaining),
                        ],
                    ))
            if speech_started:
                self._event_ch.send_nowait(
                    stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
                )
