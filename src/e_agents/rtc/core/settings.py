"""RTC module settings — STT, TTS, LLM, Audio, VAD, MCP, Agent."""

from __future__ import annotations

from enum import StrEnum, auto

from pydantic import AnyHttpUrl, AnyUrl, PostgresDsn, model_validator
from pydantic_settings import BaseSettings

##### ENUMS #####


class STTBackend(StrEnum):
    WHISPERLIVE = auto()
    OPENAI = auto()
    GOOGLE = auto()


class TTSBackend(StrEnum):
    KOKORO = auto()
    OPENAI = auto()
    GOOGLE = auto()


class VADBackend(StrEnum):
    SILERO = auto()


class TurnDetection(StrEnum):
    SERVER_VAD = "server_vad"


class AgentRole(StrEnum):
    OUTER = auto()
    INNER = auto()


##### SETTINGS #####


class RTCSettings(BaseSettings):
    """Settings for the LiveKit WebRTC server module."""

    # STT (WhisperLive WebSocket)
    STT_WS_URL: AnyUrl = "ws://localhost:45120"
    STT_MODEL: str = "large-v3-turbo"
    STT_LANGUAGE: str = "en"
    STT_TIMEOUT: float = 30.0

    # TTS (Kokoro OpenAI-compatible)
    TTS_BASE_URL: AnyHttpUrl = "http://localhost:45130/v1"
    TTS_MODEL: str = "kokoro"
    TTS_VOICE: str = "af_heart"

    # LLM
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Audio
    AUDIO_SAMPLE_RATE: int = 24000
    AUDIO_CHANNELS: int = 1

    # Agent Session
    AGENT_MAX_TOOL_STEPS: int = 10

    # MCP
    MCP_CONTEXT7_API_KEY: str = ""
    MCP_PG_URL: PostgresDsn | None = None
    MCP_N8N_TOKEN: str = ""
    MCP_API_TOKEN: str = ""
    MCP_PROJECT_ID: str = ""

    # VAD
    VAD_SAMPLE_RATE: int = 16000
    VAD_HOP_SIZE: int = 256
    VAD_SPEECH_THRESHOLD: float = 0.5
    VAD_SILENCE_DURATION: float = 1.5

    @model_validator(mode="after")
    def sync_google_api_key(self) -> RTCSettings:
        """Sync GOOGLE_API_KEY from GEMINI_API_KEY if not set."""
        if not self.GOOGLE_API_KEY and self.GEMINI_API_KEY:
            self.GOOGLE_API_KEY = self.GEMINI_API_KEY
        return self
