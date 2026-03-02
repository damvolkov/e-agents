"""STT plugin for faster-whisper-server HTTP API."""

import httpx
from livekit.agents import stt
from livekit.agents.types import NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer

from e_agents.core.settings import settings as st


class WhisperSTT(stt.STT):
    """STT plugin for faster-whisper-server HTTP API."""

    def __init__(
        self,
        *,
        base_url: str = st.STT_BASE_URL,
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
        self._base_url = base_url.rstrip("/")
        self._language = language
        self._model = model
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "faster-whisper-server"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        """Transcribe audio buffer via HTTP POST."""
        from livekit import rtc

        effective_lang: str = language if isinstance(language, str) else self._language

        combined = rtc.combine_audio_frames(buffer)
        wav_bytes = combined.to_wav_bytes()

        client = await self._get_client()
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {
            "language": effective_lang,
            "response_format": "json",
        }

        response = await client.post("/v1/audio/transcriptions", files=files, data=data)
        response.raise_for_status()
        result = response.json()

        text = result.get("text", "").strip()
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(
                    language=effective_lang,
                    text=text,
                )
            ],
        )

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
