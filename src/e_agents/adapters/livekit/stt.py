"""STT adapter for WhisperLive via WebSocket."""

import asyncio
import contextlib

import orjson as json
import websockets
from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer, shortuuid

from e_agents.shared.settings import settings as st


class WhisperLiveSTT(stt.STT):
    """STT adapter for WhisperLive via WebSocket protocol."""

    def __init__(
        self,
        *,
        ws_url: str = st.STT_WS_URL,
        language: str = st.STT_LANGUAGE,
        model: str = st.STT_MODEL,
        timeout: float = st.STT_TIMEOUT,
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
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

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        """Transcribe audio buffer via WhisperLive WebSocket."""
        effective_lang: str = language if isinstance(language, str) else self._language

        combined = rtc.combine_audio_frames(buffer)
        audio_bytes = bytes(combined.data)

        uid = shortuuid()
        config_msg = json.dumps(
            {
                "uid": uid,
                "language": effective_lang,
                "model": self._model,
                "task": "transcribe",
                "use_vad": False,
            }
        )

        text = ""
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
                            text = " ".join(s.get("text", "").strip() for s in segments if s.get("text", "").strip())
                        if data.get("message") in ("DISCONNECT", "END"):
                            break

        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(
                    language=effective_lang,
                    text=text.strip(),
                )
            ],
        )

    async def aclose(self) -> None:
        """No persistent connections to close."""
