"""Fixtures for operations tests."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from textwrap import dedent

import pytest

from e_agents.shared.helpers.scan import Scanner

_PKG = "scantest_pkg"
_TOOLS_PATH = Path(__file__).resolve().parents[3] / "src" / "e_agents" / "rtc" / "tools"


##### PRIVATE HELPERS #####


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip(), encoding="utf-8")


##### FIXTURES #####


@pytest.fixture
def scanner() -> Scanner:
    return Scanner()


@pytest.fixture
def fake_pkg(tmp_path: Path) -> Iterator[Path]:
    """Build a synthetic package tree for scanning tests."""
    root = tmp_path / _PKG
    root.mkdir()

    _write(root / "__init__.py", "")

    _write(
        root / "base.py",
        """\
        import functools

        class Gadget:
            pass

        class ToolWrapper:
            def __init__(self, func):
                self._func = func
                functools.update_wrapper(self, func)

            def __call__(self, *args, **kwargs):
                return self._func(*args, **kwargs)
        """,
    )

    _write(
        root / "devices.py",
        """\
        from scantest_pkg.base import Gadget, ToolWrapper

        class Phone(Gadget):
            pass

        class Tablet(Gadget):
            pass

        class _SecretGadget(Gadget):
            pass

        async def search_web(query: str, limit: int = 10) -> str:
            return ""

        async def fetch_data(url: str, timeout: float = 5.0) -> bytes:
            return b""

        tool_search = ToolWrapper(search_web)
        tool_fetch = ToolWrapper(fetch_data)
        _private_tool = ToolWrapper(search_web)
        """,
    )

    _write(
        root / "unrelated.py",
        """\
        class Standalone:
            pass

        CONSTANT = 42
        """,
    )

    _write(root / "nested" / "__init__.py", "")

    _write(
        root / "nested" / "sensors.py",
        """\
        from scantest_pkg.base import Gadget

        class Thermometer(Gadget):
            pass

        class Barometer(Gadget):
            pass
        """,
    )

    sys.path.insert(0, str(tmp_path))
    yield root

    sys.path.remove(str(tmp_path))
    for key in [k for k in sys.modules if k.startswith(_PKG)]:
        del sys.modules[key]


@pytest.fixture
def gadget_base(fake_pkg: Path) -> type:
    """Gadget base class from the synthetic package."""
    return importlib.import_module(f"{_PKG}.base").Gadget


@pytest.fixture
def wrapper_base(fake_pkg: Path) -> type:
    """ToolWrapper class from the synthetic package."""
    return importlib.import_module(f"{_PKG}.base").ToolWrapper


@pytest.fixture
def real_tools_dir() -> Path:
    """Path to the real app tools directory, skips if missing."""
    if not _TOOLS_PATH.is_dir():
        pytest.skip("tools directory not found")
    return _TOOLS_PATH


@pytest.fixture
def function_tool_cls() -> type:
    """LiveKit FunctionTool class, skips if livekit not installed."""
    return pytest.importorskip("livekit.agents.llm.tool_context").FunctionTool
