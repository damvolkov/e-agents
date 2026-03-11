"""Streaming STT adapter for WhisperLive via WebSocket."""

import asyncio
import contextlib
import logging

import orjson as json
import websockets
from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer, aio, shortuuid

from e_agents.shared.core.settings import settings as st

_log = logging.getLogger("e_agents.stt.whisperlive")


##### STREAMING STT #####


class WhisperLiveSTT(stt.STT):
    """Streaming STT via WhisperLive WebSocket protocol."""

    def __init__(
        self,
        *,
        ws_url: str = str(st.STT_WS_URL),
        language: str = st.STT_LANGUAGE,
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
        audio_bytes = bytes(combined.data)
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
            async with websockets.connect(self._ws_url, close_timeout=5) as ws:
                await ws.send(config_msg)
                chunk_size = 4096
                for i in range(0, len(audio_bytes), chunk_size):
                    await ws.send(audio_bytes[i : i + chunk_size])
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
    """Streaming recognition via WhisperLive WebSocket."""

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
        """Main loop: handle utterances until input channel closes."""
        while True:
            match await self._handle_utterance():
                case "closed":
                    break

    async def _handle_utterance(self) -> str:
        """Process one utterance over a fresh WebSocket. Returns 'flush' or 'closed'."""
        uid = shortuuid()
        last_text = ""
        speech_started = False
        result = "closed"

        try:
            async with websockets.connect(self._ws_url, close_timeout=5) as ws:
                config = json.dumps({
                    "uid": uid,
                    "language": self._language,
                    "model": self._model,
                    "task": "transcribe",
                    "use_vad": False,
                })
                await ws.send(config)
                _log.debug("STREAM_OPEN uid=%s lang=%s", uid, self._language)

                async def _forward() -> str:
                    """Forward audio frames to WhisperLive WebSocket."""
                    async for frame in self._input_ch:
                        if isinstance(frame, self._FlushSentinel):
                            with contextlib.suppress(Exception):
                                await ws.send(json.dumps({"uid": uid, "message": "END"}))
                            return "flush"
                        with contextlib.suppress(Exception):
                            await ws.send(bytes(frame.data))
                    with contextlib.suppress(Exception):
                        await ws.send(json.dumps({"uid": uid, "message": "END"}))
                    return "closed"

                async def _receive() -> None:
                    """Receive transcription results from WhisperLive."""
                    nonlocal last_text, speech_started
                    with contextlib.suppress(TimeoutError):
                        async with asyncio.timeout(30):
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
                                    self._event_ch.send_nowait(stt.SpeechEvent(
                                        type=stt.SpeechEventType.INTERIM_TRANSCRIPT,
                                        alternatives=[
                                            stt.SpeechData(language=self._language, text=text)
                                        ],
                                    ))
                                    last_text = text

                                if data.get("message") in ("DISCONNECT", "END"):
                                    break

                forward_task = asyncio.create_task(_forward(), name="ws_forward")
                receive_task = asyncio.create_task(_receive(), name="ws_receive")

                try:
                    result = await forward_task
                    with contextlib.suppress(TimeoutError):
                        async with asyncio.timeout(5):
                            await receive_task
                finally:
                    await aio.cancel_and_wait(forward_task, receive_task)

                if last_text:
                    self._event_ch.send_nowait(stt.SpeechEvent(
                        type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                        alternatives=[
                            stt.SpeechData(language=self._language, text=last_text)
                        ],
                    ))
                if speech_started:
                    self._event_ch.send_nowait(
                        stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
                    )

        except Exception:
            _log.exception("STREAM_ERROR uid=%s", uid)

        _log.debug("STREAM_DONE uid=%s result=%s text=%r", uid, result, last_text)
        return result
