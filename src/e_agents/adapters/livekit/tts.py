"""TTS adapter for Kokoro via OpenAI-compatible API."""

import httpx
from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
from livekit.agents.utils import shortuuid

from e_agents.shared.settings import settings as st


class KokoroChunkedStream(tts.ChunkedStream):
    """Stream audio chunks from Kokoro OpenAI-compatible /audio/speech endpoint."""

    def __init__(
        self,
        *,
        tts_instance: "KokoroTTS",
        input_text: str,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts_instance, input_text=input_text, conn_options=conn_options)

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        """Stream PCM audio from Kokoro's OpenAI-compatible endpoint."""
        tts_instance: KokoroTTS = self._tts  # type: ignore

        output_emitter.initialize(
            request_id=shortuuid(),
            sample_rate=tts_instance.sample_rate,
            num_channels=tts_instance.num_channels,
            mime_type="audio/pcm",
        )

        async with (
            httpx.AsyncClient(
                base_url=tts_instance._base_url,
                timeout=httpx.Timeout(30.0),
            ) as client,
            client.stream(
                "POST",
                "/audio/speech",
                json={
                    "model": tts_instance._model,
                    "input": self._input_text,
                    "voice": tts_instance._voice,
                    "response_format": "pcm",
                },
            ) as response,
        ):
            response.raise_for_status()
            async for chunk in response.aiter_bytes(4096):
                output_emitter.push(chunk)


class KokoroTTS(tts.TTS):
    """TTS adapter for Kokoro via OpenAI-compatible API."""

    def __init__(
        self,
        *,
        base_url: str = st.TTS_BASE_URL,
        model: str = st.TTS_MODEL,
        voice: str = st.TTS_VOICE,
        sample_rate: int = st.AUDIO_SAMPLE_RATE,
        num_channels: int = st.AUDIO_CHANNELS,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=num_channels,
        )
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voice = voice

    @property
    def model(self) -> str:
        return f"kokoro/{self._voice}"

    @property
    def provider(self) -> str:
        return "kokoro"

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        """Synthesize text to streaming PCM audio via Kokoro."""
        return KokoroChunkedStream(
            tts_instance=self,
            input_text=text,
            conn_options=conn_options,
        )

    async def aclose(self) -> None:
        """No persistent connections to close."""
