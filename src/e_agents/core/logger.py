"""Logging configuration using LiveKit's native logger with custom icons."""

from enum import StrEnum

from livekit.agents.log import logger as lk_logger


class LogIcon(StrEnum):
    """Icon mappings for different log categories."""

    DEFAULT = "📋"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    CRITICAL = "🔴"
    INFO = "ℹ️"
    START = "🚀"
    PROCESSING = "🔄"
    DETECTION = "🔍"
    COMPLETE = "✨"
    AGENT = "🤖"
    MODEL = "🧠"
    TOOL = "🔧"
    ADAPTER = "🔌"
    NETWORK = "🌐"
    STREAMING = "📡"
    CHAT = "💬"
    TIMER = "🕒"
    LATENCY = "⚡"


class IconLogger:
    """Wrapper around LiveKit logger that prepends icons to messages."""

    def __init__(self, base_logger) -> None:
        self._logger = base_logger

    def _format(self, msg: str, icon: LogIcon | None = None) -> str:
        prefix = icon.value if icon else LogIcon.DEFAULT.value
        return f"{prefix} {msg}"

    def debug(self, msg: str, *args, icon: LogIcon | None = None, **_kwargs) -> None:
        self._logger.debug(self._format(msg, icon), *args)

    def info(self, msg: str, *args, icon: LogIcon | None = None, **_kwargs) -> None:
        self._logger.info(self._format(msg, icon), *args)

    def warning(self, msg: str, *args, icon: LogIcon | None = None, **_kwargs) -> None:
        self._logger.warning(self._format(msg, icon), *args)

    def error(self, msg: str, *args, icon: LogIcon | None = None, **_kwargs) -> None:
        self._logger.error(self._format(msg, icon), *args)

    def critical(self, msg: str, *args, icon: LogIcon | None = None, **_kwargs) -> None:
        self._logger.critical(self._format(msg, icon), *args)


logger = IconLogger(lk_logger)
