"""RTC module settings — STT, TTS, LLM, Audio, VAD, MCP, Agent."""

from __future__ import annotations

from enum import StrEnum, auto

from pydantic import AnyHttpUrl, AnyUrl, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings

##### ENUMS #####


class STTBackend(StrEnum):
    EVOICE = auto()
    FWHISPER = auto()
    WHISPERLIVE = auto()
    OPENAI = auto()
    GOOGLE = auto()


class TTSBackend(StrEnum):
    EVOICE = auto()
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

    # STT (e-voice — WebSocket streaming + HTTP batch)
    STT_BASE_URL: AnyHttpUrl = "http://localhost:45140"
    STT_MODEL: str = "large-v3-turbo"
    STT_TIMEOUT: float = 30.0

    # TTS (e-voice — OpenAI-compatible chunked streaming)
    TTS_BASE_URL: AnyHttpUrl = "http://localhost:45140/v1"
    TTS_MODEL: str = "kokoro"
    TTS_VOICE: str = "ef_dora"

    # LLM
    OPENAI_API_KEY: SecretStr = ""
    GOOGLE_API_KEY: SecretStr = ""
    GOOGLE_MODEL: str = "gemini-2.0-flash"

    # Audio
    AUDIO_SAMPLE_RATE: int = 24000
    AUDIO_CHANNELS: int = 1

    # Agent Session
    AGENT_MAX_TOOL_STEPS: int = 10

    # MCP
    MCP_CONTEXT7_API_KEY: SecretStr = ""
    MCP_PG_URL: PostgresDsn | None = None
    MCP_N8N_TOKEN: SecretStr = ""
    MCP_API_TOKEN: SecretStr = ""
    MCP_PROJECT_ID: str = ""

    # VAD (Silero)
    VAD_SAMPLE_RATE: int = 16000
    VAD_ACTIVATION_THRESHOLD: float = 0.6
    VAD_MIN_SPEECH_DURATION: float = 0.15
    VAD_MIN_SILENCE_DURATION: float = 0.8
    VAD_PREFIX_PADDING_DURATION: float = 0.4
