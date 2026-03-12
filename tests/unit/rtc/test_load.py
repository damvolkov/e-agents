"""Tests for Loader — config discovery, YAML parsing, and cross-reference validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from e_agents.rtc.core.exceptions import ConfigLoadError
from e_agents.rtc.models.config import AgentConfig, SessionConfig
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


##### CROSS-REFERENCE VALIDATION #####


async def test_loader_validates_handoff_target_exists() -> None:
    """Handoff target must exist as an agent config."""
    agents = {
        "alpha": AgentConfig.model_validate({"name": "alpha", "handoffs": ["beta"]}),
    }
    sessions = {
        "s": SessionConfig.model_validate({"name": "s", "agents": ["alpha", "beta"]}),
    }
    loader = Loader()
    with pytest.raises(ConfigLoadError, match="no agent config found for 'beta'"):
        loader._ld_validate_refs(agents, sessions)


async def test_loader_validates_handoff_target_in_session() -> None:
    """Handoff target must be declared in the session's agent list."""
    agents = {
        "alpha": AgentConfig.model_validate({"name": "alpha", "handoffs": ["gamma"]}),
        "gamma": AgentConfig.model_validate({"name": "gamma"}),
    }
    sessions = {
        "s": SessionConfig.model_validate({"name": "s", "agents": ["alpha"]}),
    }
    loader = Loader()
    with pytest.raises(ConfigLoadError, match="not in session"):
        loader._ld_validate_refs(agents, sessions)


async def test_loader_validates_agent_exists_in_session() -> None:
    """Session must not reference an agent that has no config file."""
    agents = {
        "alpha": AgentConfig.model_validate({"name": "alpha"}),
    }
    sessions = {
        "s": SessionConfig.model_validate({"name": "s", "agents": ["alpha", "missing"]}),
    }
    loader = Loader()
    with pytest.raises(ConfigLoadError, match="no config found"):
        loader._ld_validate_refs(agents, sessions)


async def test_loader_validates_valid_config() -> None:
    """No error for valid cross-references."""
    agents = {
        "a": AgentConfig.model_validate({"name": "a", "handoffs": ["b"]}),
        "b": AgentConfig.model_validate({"name": "b", "handoffs": ["a"]}),
    }
    sessions = {
        "s": SessionConfig.model_validate({"name": "s", "agents": ["a", "b"]}),
    }
    loader = Loader()
    loader._ld_validate_refs(agents, sessions)


async def test_loader_validates_no_handoffs_passes() -> None:
    """Agent without handoffs passes validation."""
    agents = {
        "solo": AgentConfig.model_validate({"name": "solo"}),
    }
    sessions = {
        "s": SessionConfig.model_validate({"name": "s", "agents": ["solo"]}),
    }
    loader = Loader()
    loader._ld_validate_refs(agents, sessions)


async def test_loader_validates_empty_session_passes() -> None:
    """Session with no agents passes validation."""
    agents = {}
    sessions = {
        "empty": SessionConfig.model_validate({"name": "empty"}),
    }
    loader = Loader()
    loader._ld_validate_refs(agents, sessions)
