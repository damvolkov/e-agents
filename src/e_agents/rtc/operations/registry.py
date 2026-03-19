"""Provider registry: maps config enums to adapter classes.

LiveKit plugins MUST be imported on the main thread before the worker
spawns job processes. Call ``ProviderRegistry.populate()`` early in the
startup path.
"""

from __future__ import annotations

import importlib
from typing import Any, ClassVar

from livekit.agents import stt, tts

from e_agents.rtc.adapters.stt import EVoiceSTT, FasterWhisperSTT, WhisperLiveSTT
from e_agents.rtc.adapters.tts import EVoiceTTS, KokoroTTS
from e_agents.rtc.core.settings import STTBackend, TTSBackend
from e_agents.shared.core.logger import LogIcon, logger
from e_agents.shared.models import LLMProvider

try:
    from livekit.plugins import silero as _silero
except ImportError:
    _silero = None


class ProviderRegistry:
    """Central registry for STT, TTS, LLM and VAD providers."""

    _stt: ClassVar[dict[STTBackend, type]] = {
        STTBackend.EVOICE: EVoiceSTT,
        STTBackend.FWHISPER: FasterWhisperSTT,
        STTBackend.WHISPERLIVE: WhisperLiveSTT,
    }
    _tts: ClassVar[dict[TTSBackend, type]] = {
        TTSBackend.EVOICE: EVoiceTTS,
        TTSBackend.KOKORO: KokoroTTS,
    }
    _llm: ClassVar[dict[LLMProvider, type]] = {}
    _populated: ClassVar[bool] = False

    ##### POPULATION #####

    @classmethod
    def populate(cls) -> None:
        """Import LiveKit LLM/VAD plugins. Must run on main thread."""
        if cls._populated:
            return

        cls._register_llm_plugin(LLMProvider.OPENAI, "livekit.plugins.openai")
        cls._register_llm_plugin(LLMProvider.GOOGLE, "livekit.plugins.google")
        cls._register_silero()

        cls._populated = True
        logger.info(
            "registry_populated",
            stt=sorted(cls._stt),
            tts=sorted(cls._tts),
            llm=sorted(cls._llm),
            icon=LogIcon.COMPLETE,
            color_range=1,
        )

    @classmethod
    def _register_llm_plugin(cls, provider: LLMProvider, module_path: str) -> None:
        """Import a LiveKit plugin and register only its LLM class."""
        try:
            mod = importlib.import_module(module_path)
        except ImportError:
            logger.warning("plugin_not_installed", provider=str(provider), icon=LogIcon.WARNING)
            return

        if (llm_cls := getattr(mod, "LLM", None)) is not None:
            cls._llm[provider] = llm_cls

        logger.debug("plugin_registered", provider=str(provider), icon=LogIcon.ADAPTER, color_range=1)

    @classmethod
    def _register_silero(cls) -> None:
        """Register Silero VAD plugin."""
        if _silero is not None:
            logger.debug("plugin_registered", provider="silero", icon=LogIcon.ADAPTER, color_range=1)
        else:
            logger.warning("plugin_not_installed", provider="silero", icon=LogIcon.WARNING)

    ##### STT #####

    @classmethod
    def create_stt(cls, backend: STTBackend, **kwargs: Any) -> stt.STT:
        """Instantiate an STT provider by backend enum."""
        provider_cls = cls._stt.get(backend)
        if provider_cls is None:
            raise KeyError(f"Unknown STT backend '{backend}'. Available: {sorted(cls._stt)}")
        return provider_cls(**kwargs)

    ##### TTS #####

    @classmethod
    def create_tts(cls, backend: TTSBackend, **kwargs: Any) -> tts.TTS:
        """Instantiate a TTS provider by backend enum."""
        provider_cls = cls._tts.get(backend)
        if provider_cls is None:
            raise KeyError(f"Unknown TTS backend '{backend}'. Available: {sorted(cls._tts)}")
        return provider_cls(**kwargs)

    ##### LLM #####

    @classmethod
    def create_llm(cls, provider: LLMProvider, *, model: str | None = None, **kwargs: Any) -> Any:
        """Instantiate an LLM provider by enum."""
        provider_cls = cls._llm.get(provider)
        if provider_cls is None:
            raise KeyError(f"Unknown LLM provider '{provider}'. Available: {sorted(cls._llm)}")
        if model:
            kwargs["model"] = model
        return provider_cls(**kwargs)

    ##### VAD #####

    @staticmethod
    def create_vad(**kwargs: Any) -> Any:
        """Instantiate Silero VAD with tuned defaults from settings."""
        if _silero is None:
            raise ImportError("livekit.plugins.silero is required for VAD but not installed")

        from e_agents.shared.core.settings import settings as _st

        defaults: dict[str, Any] = {
            "activation_threshold": _st.VAD_ACTIVATION_THRESHOLD,
            "min_speech_duration": _st.VAD_MIN_SPEECH_DURATION,
            "min_silence_duration": _st.VAD_MIN_SILENCE_DURATION,
            "prefix_padding_duration": _st.VAD_PREFIX_PADDING_DURATION,
            "sample_rate": _st.VAD_SAMPLE_RATE,
        }
        defaults.update(kwargs)
        return _silero.VAD.load(**defaults)

    ##### INTROSPECTION #####

    @classmethod
    def available_stt(cls) -> list[STTBackend]:
        return sorted(cls._stt)

    @classmethod
    def available_tts(cls) -> list[TTSBackend]:
        return sorted(cls._tts)

    @classmethod
    def available_llm(cls) -> list[LLMProvider]:
        return sorted(cls._llm)
