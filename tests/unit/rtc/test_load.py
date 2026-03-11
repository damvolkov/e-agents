"""Tests for Loader — config discovery and YAML parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from e_agents.rtc.operations.load import Loader
from e_agents.shared.core.settings import Settings


##### LOADER CONFIG #####


async def test_loader_load_config_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Loader discovers and parses YAML config files."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "bot.yaml").write_text("name: bot\ninstructions: Help.\n")

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "s.yaml").write_text("name: s\ndispatcher: bot\nagents:\n  - bot\n")

    mcps_dir = tmp_path / "mcps"
    mcps_dir.mkdir()

    monkeypatch.setattr(Settings, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(Settings, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(Settings, "MCPS_DIR", mcps_dir)
    monkeypatch.setattr(Settings, "TOOLS_DIR", tmp_path / "no_tools")

    loader = Loader()
    await loader._ld_load_config()

    assert "bot" in loader.config.agents
    assert loader.config.agents["bot"].instructions == "Help."
    assert "s" in loader.config.sessions
    assert loader.config.sessions["s"].dispatcher == "bot"


async def test_loader_load_config_skips_missing_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Loader gracefully handles non-existent config directories."""
    monkeypatch.setattr(Settings, "AGENTS_DIR", tmp_path / "no_agents")
    monkeypatch.setattr(Settings, "SESSIONS_DIR", tmp_path / "no_sessions")
    monkeypatch.setattr(Settings, "MCPS_DIR", tmp_path / "no_mcps")
    monkeypatch.setattr(Settings, "TOOLS_DIR", tmp_path / "no_tools")

    loader = Loader()
    await loader._ld_load_config()

    assert loader.config.agents == {}
    assert loader.config.sessions == {}
    assert loader.config.mcps == {}


async def test_loader_load_tools_skips_missing_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Loader does nothing when TOOLS_DIR doesn't exist."""
    monkeypatch.setattr(Settings, "TOOLS_DIR", tmp_path / "no_tools")

    loader = Loader()
    await loader._ld_load_tools()

    assert loader.tools == {}
