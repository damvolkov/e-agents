"""Zero-config structured logging with [SERVICE] [MODULE] tags and Rich color palette.

DEV  → flat colored lines:  14:32:01 [RTC] [BUILDER] 🚀 SERVER_STARTED host=0.0.0.0
PROD → JSON lines (orjson) with correlation-id.

Each service owns a base color. Pass `color_range=` (-3..+3) to shift it:
    logger.info("EVENT", icon=LogIcon.TOOL, color_range=-2)   # lighter
    logger.info("EVENT", icon=LogIcon.TOOL, color_range=2)    # darker
"""

from __future__ import annotations

import logging
import os
import sys
from enum import StrEnum

import orjson
import structlog
from rich.color import Color as RichColor
from rich.console import Console
from rich.style import Style
from structlog.typing import EventDict, WrappedLogger

try:
    from asgi_correlation_id import correlation_id as _correlation_id
except ImportError:
    _correlation_id = None


# ── Enums ──


class Service(StrEnum):
    """Top-level subservice resolved from caller module path."""

    API = "API"
    CLI = "CLI"
    RTC = "RTC"
    TESTS = "TESTS"
    SYSTEM = "SYSTEM"


class LogIcon(StrEnum):
    """Semantic icons for log events."""

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
    GUARDRAIL = "🛡️"
    PROCESSOR = "⚙️"
    ADAPTER = "🔌"
    AUTH = "🔐"
    TOKEN = "🎫"
    DATABASE = "💾"
    NETWORK = "🌐"
    STREAMING = "📡"
    CACHE = "📦"
    TIMER = "🕒"
    TIMEOUT = "⏱️"
    LATENCY = "⚡"
    RETRY = "🔁"
    IMAGE = "🖼️"
    FILE = "📄"
    UPLOAD = "📤"
    DOWNLOAD = "📥"
    VALIDATION = "✓"
    SECURITY = "🔒"
    FORBIDDEN = "🚫"


# ── Rich Color Palette ──

_console = Console(force_terminal=True, color_system="truecolor", highlight=False)

_SERVICE_RGB: dict[str, tuple[int, int, int]] = {
    Service.API: (180, 180, 180),
    Service.CLI: (80, 200, 120),
    Service.RTC: (80, 140, 220),
    Service.SYSTEM: (160, 100, 220),
    Service.TESTS: (180, 120, 60),
}

_LEVEL_RGB: dict[str, tuple[int, int, int]] = {
    "warning": (220, 180, 50),
    "error": (220, 80, 80),
    "critical": (255, 50, 50),
}

_LEVEL_INDICATOR: dict[str, str] = {
    "warning": "▲",
    "error": "■",
    "critical": "■",
}


def shift_color(rgb: tuple[int, int, int], levels: int) -> tuple[int, int, int]:
    """Blend toward white (negative) or black (positive). Clamped [-3, +3]."""
    levels = max(-3, min(3, levels))
    match levels:
        case 0:
            return rgb
        case n if n > 0:
            f = 1 - n * 0.15
            return (int(rgb[0] * f), int(rgb[1] * f), int(rgb[2] * f))
        case n:
            f = abs(n) * 0.15
            return (int(rgb[0] + (255 - rgb[0]) * f), int(rgb[1] + (255 - rgb[1]) * f), int(rgb[2] + (255 - rgb[2]) * f))


def styled(text: str, r: int, g: int, b: int, *, bold: bool = False, dim: bool = False) -> str:
    """Render text with Rich truecolor style → ANSI string."""
    with _console.capture() as cap:
        _console.print(text, style=Style(color=RichColor.from_rgb(r, g, b), bold=bold, dim=dim), end="")
    return cap.get()


# ── Service Resolution ──

_SERVICE_NAMES: frozenset[str] = frozenset(s.value.lower() for s in Service if s is not Service.SYSTEM)


def _resolve_service_and_module(module_path: str) -> tuple[str, str]:
    """Extract (SERVICE, MODULE) from dotted module path. O(n) n=segments."""
    parts = module_path.split(".")
    service = Service.SYSTEM.value
    for part in parts:
        if part in _SERVICE_NAMES:
            service = part.upper()
            break
    return service, parts[-1].upper() if parts else "UNKNOWN"


# ── Processors ──

_MAX_EVENT_LEN = 120


def resolve_tags(_: WrappedLogger, __: str, ed: EventDict) -> EventDict:
    """Replace callsite module with [SERVICE] [MODULE] tags."""
    ed["service"], ed["module"] = _resolve_service_and_module(ed.pop("module", ""))
    ed.pop("filename", None)
    ed.pop("lineno", None)
    return ed


def normalize_event(_: WrappedLogger, __: str, ed: EventDict) -> EventDict:
    """Uppercase event, enforce max length."""
    ed["event"] = str(ed.get("event", ""))[:_MAX_EVENT_LEN].upper()
    return ed


def inject_icon(_: WrappedLogger, __: str, ed: EventDict) -> EventDict:
    """Pop `icon` kwarg → prepend to event."""
    if raw := ed.pop("icon", None):
        ed["event"] = f"{(raw.value if isinstance(raw, LogIcon) else str(raw))} {ed['event']}"
    return ed


def extract_color_range(_: WrappedLogger, __: str, ed: EventDict) -> EventDict:
    """Pop `color_range` kwarg → store as internal `_cr`."""
    ed["_cr"] = max(-3, min(3, int(ed.pop("color_range", 0))))
    return ed


def drop_internal_keys(_: WrappedLogger, __: str, ed: EventDict) -> EventDict:
    """Remove _prefixed internal keys before serialization."""
    for k in [k for k in ed if k.startswith("_")]:
        ed.pop(k)
    return ed


def add_correlation_id(_: WrappedLogger, __: str, ed: EventDict) -> EventDict:
    """Inject correlation-id from asgi-correlation-id if available."""
    if _correlation_id is not None and (cid := _correlation_id.get()):
        ed["correlation_id"] = cid
    return ed


# ── Dev Renderer ──

_RESERVED = frozenset({"timestamp", "level", "event", "service", "module", "_cr"})


def dev_renderer(_: WrappedLogger, __: str, ed: EventDict) -> str:
    """Flat render: `HH:MM:SS [SERVICE] [MODULE] <indicator> EVENT extras`."""
    ts = ed.get("timestamp", "")
    level = ed.get("level", "info")
    service = ed.get("service", Service.SYSTEM.value)
    module = ed.get("module", "UNKNOWN")
    event = ed.get("event", "")
    cr = ed.get("_cr", 0)

    # Service tag in its palette color (shifted by color_range)
    sr, sg, sb = shift_color(_SERVICE_RGB.get(service, _SERVICE_RGB[Service.SYSTEM]), cr)
    svc_tag = styled(f"[{service}]", sr, sg, sb, bold=True)
    mod_tag = styled(f"[{module}]", sr, sg, sb, dim=True)

    # Level indicator (only for warning+)
    indicator = ""
    if (ind := _LEVEL_INDICATOR.get(level)) and (lrgb := _LEVEL_RGB.get(level)):
        indicator = f" {styled(ind, *lrgb, bold=level == 'critical')}"

    # Timestamp dim
    ts_str = styled(ts, 130, 130, 130, dim=True)

    # Extras: key dim, value normal
    extras = " ".join(
        f"{styled(f'{k}=', 130, 130, 130)}{v}"
        for k, v in ed.items()
        if k not in _RESERVED and v is not None
    )

    return f"{ts_str} {svc_tag} {mod_tag}{indicator} {event}{f' {extras}' if extras else ''}"


# ── Banner ──


def log_banner(app_name: str, version: str) -> None:
    """Print startup banner via Rich."""
    _console.print(f"\n  [bold cyan]{app_name}[/] [dim]v{version}[/]\n")


# ── Setup ──


def _is_debug() -> bool:
    return os.getenv("DEBUG", "").lower() in {"1", "true", "yes"}


def setup_logging(*, debug: bool | None = None, log_level: int | None = None) -> None:
    """Configure structlog pipeline. Idempotent."""
    _debug = debug if debug is not None else _is_debug()
    _level = log_level or getattr(logging, os.getenv("LOG_LEVEL", "DEBUG" if _debug else "INFO").upper(), logging.INFO)

    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S" if _debug else "iso", utc=not _debug),
        structlog.processors.CallsiteParameterAdder(
            parameters=[structlog.processors.CallsiteParameter.MODULE],
            additional_ignores=["e_agents.shared.core.logger"],
        ),
        resolve_tags,
        normalize_event,
        inject_icon,
        extract_color_range,
    ]

    match _debug:
        case True:
            final: list[structlog.types.Processor] = [*shared, dev_renderer]
        case _:
            final = [
                *shared,
                drop_internal_keys,
                add_correlation_id,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(serializer=orjson.dumps),
            ]

    structlog.configure(
        processors=final,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(_level),
        context_class=dict,
        cache_logger_on_first_use=True,
    )


# ── Auto-configure & export ──

setup_logging()
logger: structlog.stdlib.BoundLogger = structlog.get_logger()