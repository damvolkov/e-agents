"""RTC module settings — STT, TTS, LLM, Audio, VAD, MCP, Agent."""

from __future__ import annotations

from enum import StrEnum, auto
from pathlib import Path
from typing import ClassVar

import os

from pydantic import AnyHttpUrl, AnyUrl, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings

_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent

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

    # Model paths
    DATA_PATH: ClassVar[Path] = _BASE_DIR / "data"
    MODELS_PATH: ClassVar[Path] = DATA_PATH / "models"
    VAD_MODEL_PATH: ClassVar[Path] = MODELS_PATH / "vad" / "silero_vad.onnx"
    TURN_MODEL_CACHE: ClassVar[Path] = MODELS_PATH / "turn"

    def model_post_init(self, __context: object) -> None:
        os.environ.setdefault("HF_HUB_CACHE", str(self.TURN_MODEL_CACHE))

    # VAD (Silero)
    VAD_SAMPLE_RATE: int = 16000
    VAD_ACTIVATION_THRESHOLD: float = 0.6
    VAD_MIN_SPEECH_DURATION: float = 0.15
    VAD_MIN_SILENCE_DURATION: float = 0.8
    VAD_PREFIX_PADDING_DURATION: float = 0.4

    # Turn Detector (MultilingualModel)
    TURN_DETECTOR_MODEL: str = "multilingual"
