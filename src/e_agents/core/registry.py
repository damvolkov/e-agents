"""Provider registry: maps config strings to adapter classes.

LiveKit plugins MUST be imported on the main thread before the worker
spawns job processes. Call ``ProviderRegistry.populate()`` early in the
startup path.
"""

from __future__ import annotations

import importlib
from typing import Any, ClassVar

from livekit.agents import stt, tts

from e_agents.adapters.livekit.stt import WhisperLiveSTT
from e_agents.adapters.livekit.tts import KokoroTTS
from e_agents.shared.logger import LogIcon, logger


class ProviderRegistry:
    """Central registry for STT, TTS, LLM and VAD providers.

    All methods are class-level — no instance needed.
    """

    _stt: ClassVar[dict[str, type]] = {"whisperlive": WhisperLiveSTT}
    _tts: ClassVar[dict[str, type]] = {"kokoro": KokoroTTS}
    _llm: ClassVar[dict[str, type]] = {}
    _populated: ClassVar[bool] = False

    # -- population --

    @classmethod
    def populate(cls) -> None:
        """Import LiveKit LLM/VAD plugins. Must run on main thread."""
        if cls._populated:
            return

        cls._register_plugin("openai", "livekit.plugins.openai")
        cls._register_plugin("google", "livekit.plugins.google")
        cls._register_silero()

        cls._populated = True
        logger.info(
            "registry_populated: stt=%s tts=%s llm=%s",
            sorted(cls._stt),
            sorted(cls._tts),
            sorted(cls._llm),
            icon=LogIcon.COMPLETE,
        )

    @classmethod
    def _register_plugin(cls, name: str, module_path: str) -> None:
        """Dynamically import a plugin and register all provider classes."""
        try:
            mod = importlib.import_module(module_path)
        except ImportError:
            logger.warning("%s plugin not installed", name, icon=LogIcon.WARNING)
            return

        _registry_map: dict[str, dict[str, type]] = {
            "LLM": cls._llm,
            "STT": cls._stt,
            "TTS": cls._tts,
        }
        for attr, registry in _registry_map.items():
            if (provider_cls := getattr(mod, attr, None)) is not None:
                registry[name] = provider_cls

        logger.debug("plugin_registered: %s", name, icon=LogIcon.ADAPTER)

    @classmethod
    def _register_silero(cls) -> None:
        """Register Silero VAD plugin."""
        try:
            from livekit.plugins import silero  # noqa: F401

            logger.debug("plugin_registered: silero", icon=LogIcon.ADAPTER)
        except ImportError:
            logger.warning("silero plugin not installed", icon=LogIcon.WARNING)

    # -- STT --

    @classmethod
    def create_stt(cls, name: str, **kwargs: Any) -> stt.STT:
        """Instantiate an STT provider by registry name."""
        provider_cls = cls._stt.get(name)
        if provider_cls is None:
            raise KeyError(f"Unknown STT provider '{name}'. Available: {sorted(cls._stt)}")
        return provider_cls(**kwargs)

    # -- TTS --

    @classmethod
    def create_tts(cls, name: str, **kwargs: Any) -> tts.TTS:
        """Instantiate a TTS provider by registry name."""
        provider_cls = cls._tts.get(name)
        if provider_cls is None:
            raise KeyError(f"Unknown TTS provider '{name}'. Available: {sorted(cls._tts)}")
        return provider_cls(**kwargs)

    # -- LLM --

    @classmethod
    def create_llm(cls, provider: str, *, model: str | None = None, **kwargs: Any) -> Any:
        """Instantiate an LLM provider by registry name."""
        provider_cls = cls._llm.get(provider)
        if provider_cls is None:
            raise KeyError(f"Unknown LLM provider '{provider}'. Available: {sorted(cls._llm)}")
        if model:
            kwargs["model"] = model
        return provider_cls(**kwargs)

    # -- VAD --

    @staticmethod
    def create_vad(**kwargs: Any) -> Any:
        """Instantiate the default Silero VAD."""
        from livekit.plugins import silero

        return silero.VAD.load(**kwargs)

    # -- introspection --

    @classmethod
    def available_stt(cls) -> list[str]:
        return sorted(cls._stt)

    @classmethod
    def available_tts(cls) -> list[str]:
        return sorted(cls._tts)

    @classmethod
    def available_llm(cls) -> list[str]:
        return sorted(cls._llm)
