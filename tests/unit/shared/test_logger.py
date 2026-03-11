"""Unit tests for shared.core.logger — structlog processors, color palette, and dev renderer."""

from __future__ import annotations

import pytest

from e_agents.shared.core.logger import (
    LogIcon,
    Service,
    _MAX_EVENT_LEN,
    _resolve_service_and_module,
    dev_renderer,
    drop_internal_keys,
    extract_color_range,
    inject_icon,
    normalize_event,
    resolve_tags,
    shift_color,
)


##### HELPERS #####


def _ed(**kwargs: object) -> dict:
    """Shorthand for creating an EventDict."""
    return kwargs


##### shift_color #####


@pytest.mark.parametrize(
    ("rgb", "levels", "expected"),
    [
        ((80, 140, 220), 0, (80, 140, 220)),
        ((80, 140, 220), -1, (106, 157, 225)),
        ((80, 140, 220), -3, (158, 191, 235)),
        ((80, 140, 220), 1, (68, 119, 187)),
        ((80, 140, 220), 3, (44, 77, 121)),
        ((80, 140, 220), -5, (158, 191, 235)),
        ((80, 140, 220), 5, (44, 77, 121)),
        ((0, 0, 0), -1, (38, 38, 38)),
        ((255, 255, 255), 1, (216, 216, 216)),
        ((100, 100, 100), 0, (100, 100, 100)),
    ],
)
def test_shift_color(
    rgb: tuple[int, int, int],
    levels: int,
    expected: tuple[int, int, int],
) -> None:
    assert shift_color(rgb, levels) == expected


def test_shift_color_clamps_negative() -> None:
    assert shift_color((80, 140, 220), -10) == shift_color((80, 140, 220), -3)


def test_shift_color_clamps_positive() -> None:
    assert shift_color((80, 140, 220), 10) == shift_color((80, 140, 220), 3)


##### _resolve_service_and_module #####


@pytest.mark.parametrize(
    ("module_path", "expected_service", "expected_module"),
    [
        ("e_agents.rtc.builder", "RTC", "BUILDER"),
        ("e_agents.rtc.core.settings", "RTC", "SETTINGS"),
        ("e_agents.rtc.registry", "RTC", "REGISTRY"),
        ("e_agents.api.core.lifespan", "API", "LIFESPAN"),
        ("e_agents.api.router.endpoints", "API", "ENDPOINTS"),
        ("e_agents.cli.app", "CLI", "APP"),
        ("e_agents.cli.core.settings", "CLI", "SETTINGS"),
        ("e_agents.shared.core.logger", "SYSTEM", "LOGGER"),
        ("e_agents.shared.helpers.scan", "SYSTEM", "SCAN"),
        ("__main__", "SYSTEM", "__MAIN__"),
        ("tests.unit.shared.test_logger", "TESTS", "TEST_LOGGER"),
        ("tests.integration.rtc.test_stt", "TESTS", "TEST_STT"),
        ("some_other.package", "SYSTEM", "PACKAGE"),
    ],
)
def test_resolve_service_and_module(
    module_path: str,
    expected_service: str,
    expected_module: str,
) -> None:
    service, module = _resolve_service_and_module(module_path)
    assert service == expected_service
    assert module == expected_module


##### resolve_tags PROCESSOR #####


def test_resolve_tags_extracts_service_and_module() -> None:
    ed = _ed(module="e_agents.rtc.builder", event="test")
    result = resolve_tags(None, "", ed)
    assert result["service"] == "RTC"
    assert result["module"] == "BUILDER"


def test_resolve_tags_pops_callsite_keys() -> None:
    ed = _ed(module="e_agents.api.router", filename="router.py", lineno=42, event="x")
    result = resolve_tags(None, "", ed)
    assert "filename" not in result
    assert "lineno" not in result


def test_resolve_tags_missing_module_defaults_system() -> None:
    ed = _ed(event="x")
    result = resolve_tags(None, "", ed)
    assert result["service"] == "SYSTEM"


##### normalize_event PROCESSOR #####


@pytest.mark.parametrize(
    ("raw_event", "expected"),
    [
        ("server_started", "SERVER_STARTED"),
        ("lifespan_up", "LIFESPAN_UP"),
        ("ALREADY_UPPER", "ALREADY_UPPER"),
        ("", ""),
    ],
)
def test_normalize_event(raw_event: str, expected: str) -> None:
    ed = _ed(event=raw_event)
    result = normalize_event(None, "", ed)
    assert result["event"] == expected


def test_normalize_event_truncates_long_events() -> None:
    ed = _ed(event="x" * 200)
    result = normalize_event(None, "", ed)
    assert len(result["event"]) == _MAX_EVENT_LEN


##### inject_icon PROCESSOR #####


@pytest.mark.parametrize(
    ("icon", "event_before", "expected_prefix"),
    [
        (LogIcon.START, "SERVER_STARTED", f"{LogIcon.START.value} SERVER_STARTED"),
        (LogIcon.ERROR, "TIMEOUT", f"{LogIcon.ERROR.value} TIMEOUT"),
        (LogIcon.TOOL, "TOOL_CALLED", f"{LogIcon.TOOL.value} TOOL_CALLED"),
    ],
)
def test_inject_icon_prepends(icon: LogIcon, event_before: str, expected_prefix: str) -> None:
    ed = _ed(event=event_before, icon=icon)
    result = inject_icon(None, "", ed)
    assert result["event"] == expected_prefix
    assert "icon" not in result


def test_inject_icon_no_icon_passthrough() -> None:
    ed = _ed(event="PLAIN_EVENT")
    result = inject_icon(None, "", ed)
    assert result["event"] == "PLAIN_EVENT"


def test_inject_icon_string_icon() -> None:
    ed = _ed(event="EVT", icon="🔥")
    result = inject_icon(None, "", ed)
    assert result["event"] == "🔥 EVT"


##### extract_color_range PROCESSOR #####


@pytest.mark.parametrize(
    ("color_range", "expected_cr"),
    [
        (0, 0),
        (-1, -1),
        (2, 2),
        (-3, -3),
        (3, 3),
        (-10, -3),
        (10, 3),
    ],
)
def test_extract_color_range(color_range: int, expected_cr: int) -> None:
    ed = _ed(event="x", color_range=color_range)
    result = extract_color_range(None, "", ed)
    assert result["_cr"] == expected_cr
    assert "color_range" not in result


def test_extract_color_range_default_zero() -> None:
    ed = _ed(event="x")
    result = extract_color_range(None, "", ed)
    assert result["_cr"] == 0


##### drop_internal_keys PROCESSOR #####


def test_drop_internal_keys_removes_underscore_prefixed() -> None:
    ed = _ed(event="x", _cr=0, _internal="y", public="z")
    result = drop_internal_keys(None, "", ed)
    assert "_cr" not in result
    assert "_internal" not in result
    assert result["public"] == "z"
    assert result["event"] == "x"


def test_drop_internal_keys_preserves_public() -> None:
    ed = _ed(event="x", host="0.0.0.0", port=8000)
    result = drop_internal_keys(None, "", ed)
    assert result["host"] == "0.0.0.0"
    assert result["port"] == 8000


##### dev_renderer #####


def test_dev_renderer_contains_service_module_event() -> None:
    ed = _ed(
        timestamp="14:32:01",
        level="info",
        service="RTC",
        module="BUILDER",
        event="🚀 SERVER_STARTED",
        _cr=0,
        host="0.0.0.0",
        port=8000,
    )
    output = dev_renderer(None, "", ed)
    assert "[RTC]" in output
    assert "[BUILDER]" in output
    assert "SERVER_STARTED" in output
    assert "host=" in output
    assert "port=" in output


def test_dev_renderer_warning_indicator() -> None:
    ed = _ed(
        timestamp="14:32:04",
        level="warning",
        service="API",
        module="MIDDLEWARE",
        event="⚠️ RATE_LIMIT_NEAR",
        _cr=0,
        usage=0.92,
    )
    output = dev_renderer(None, "", ed)
    assert "▲" in output
    assert "[API]" in output
    assert "usage=" in output


def test_dev_renderer_error_indicator() -> None:
    ed = _ed(
        timestamp="14:32:05",
        level="error",
        service="RTC",
        module="ADAPTER",
        event="❌ ADAPTER_TIMEOUT",
        _cr=0,
    )
    output = dev_renderer(None, "", ed)
    assert "■" in output
    assert "[RTC]" in output


def test_dev_renderer_critical_indicator() -> None:
    ed = _ed(
        timestamp="14:32:05",
        level="critical",
        service="SYSTEM",
        module="MAIN",
        event="🔴 FATAL",
        _cr=0,
    )
    output = dev_renderer(None, "", ed)
    assert "■" in output


def test_dev_renderer_info_no_indicator() -> None:
    ed = _ed(
        timestamp="14:32:01",
        level="info",
        service="CLI",
        module="COMMANDS",
        event="TOOL_CALLED",
        _cr=0,
    )
    output = dev_renderer(None, "", ed)
    assert "▲" not in output
    assert "■" not in output


def test_dev_renderer_excludes_reserved_keys_from_extras() -> None:
    ed = _ed(
        timestamp="14:32:01",
        level="info",
        service="RTC",
        module="BUILDER",
        event="EVT",
        _cr=0,
    )
    output = dev_renderer(None, "", ed)
    assert "timestamp=" not in output
    assert "level=" not in output
    assert "_cr=" not in output


@pytest.mark.parametrize("cr", [-3, -2, -1, 0, 1, 2, 3])
def test_dev_renderer_accepts_all_color_ranges(cr: int) -> None:
    ed = _ed(timestamp="T", level="info", service="RTC", module="BUILDER", event="EVT", _cr=cr)
    output = dev_renderer(None, "", ed)
    assert "[RTC]" in output
    assert "EVT" in output


##### Service ENUM #####


def test_service_enum_values() -> None:
    assert Service.API == "API"
    assert Service.CLI == "CLI"
    assert Service.RTC == "RTC"
    assert Service.TESTS == "TESTS"
    assert Service.SYSTEM == "SYSTEM"


##### LogIcon ENUM #####


def test_log_icon_default_is_clipboard() -> None:
    assert LogIcon.DEFAULT == "📋"


@pytest.mark.parametrize(
    "icon",
    [LogIcon.SUCCESS, LogIcon.ERROR, LogIcon.WARNING, LogIcon.START, LogIcon.AGENT, LogIcon.TOOL],
)
def test_log_icon_members_are_non_empty(icon: LogIcon) -> None:
    assert len(icon.value) > 0


##### PROCESSOR PIPELINE ORDER #####


def test_full_processor_pipeline() -> None:
    """Simulate the processor chain order: resolve_tags → normalize → inject_icon → extract_cr."""
    ed = _ed(
        module="e_agents.rtc.registry",
        event="plugin_registered",
        icon=LogIcon.ADAPTER,
        color_range=1,
        provider="openai",
    )
    ed = resolve_tags(None, "", ed)
    ed = normalize_event(None, "", ed)
    ed = inject_icon(None, "", ed)
    ed = extract_color_range(None, "", ed)

    assert ed["service"] == "RTC"
    assert ed["module"] == "REGISTRY"
    assert ed["event"] == f"{LogIcon.ADAPTER.value} PLUGIN_REGISTERED"
    assert ed["_cr"] == 1
    assert ed["provider"] == "openai"
    assert "icon" not in ed
    assert "color_range" not in ed
