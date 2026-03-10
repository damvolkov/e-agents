"""Config loader: reads ALL agent, tool, and session YAMLs at startup.

Startup flow:
  1. ``load_all()`` scans ``config/agents/``, ``config/tools/``, ``config/sessions/``
  2. Agents and tools are cached in module-level registries
  3. When a session is requested, its YAML references agents by name
     → the factory merges AgentConfig + SessionAgentRef → AgentDefinition
"""

from __future__ import annotations

from pathlib import Path

from e_agents.core.models import (
    AgentBehavior,
    AgentConfig,
    AgentDefinition,
    SessionAgentRef,
    SessionDefinition,
    ToolCatalog,
)
from e_agents.shared.logger import LogIcon, logger
from e_agents.shared.settings import settings as st

_AGENT_CONFIGS: dict[str, AgentConfig] = {}
_TOOL_CATALOGS: dict[str, ToolCatalog] = {}
_SESSION_DEFS: dict[str, SessionDefinition] = {}


##### INDIVIDUAL LOADERS #####


def _load_agents(agents_dir: Path) -> dict[str, AgentConfig]:
    """Load every agent YAML from the agents directory."""
    configs: dict[str, AgentConfig] = {}
    if not agents_dir.is_dir():
        logger.warning("agents_dir not found: %s", agents_dir, icon=LogIcon.WARNING)
        return configs

    for path in sorted(agents_dir.glob("*.yaml")):
        agent_cfg = AgentConfig.from_yaml(path)
        configs[agent_cfg.name] = agent_cfg
        logger.debug(
            "agent_loaded: %s tools=%s",
            agent_cfg.name,
            agent_cfg.tools,
            icon=LogIcon.AGENT,
        )
    return configs


def _load_tools(tools_dir: Path) -> dict[str, ToolCatalog]:
    """Load every tool catalog YAML from the tools directory."""
    catalogs: dict[str, ToolCatalog] = {}
    if not tools_dir.is_dir():
        logger.warning("tools_dir not found: %s", tools_dir, icon=LogIcon.WARNING)
        return catalogs

    for path in sorted(tools_dir.glob("*.yaml")):
        catalog = ToolCatalog.from_yaml(path)
        catalogs[path.stem] = catalog
        logger.debug(
            "tools_loaded: %s (%d tools)",
            path.stem,
            len(catalog.tools),
            icon=LogIcon.TOOL,
        )
    return catalogs


def _load_sessions(sessions_dir: Path) -> dict[str, SessionDefinition]:
    """Load every session YAML from the sessions directory."""
    defs: dict[str, SessionDefinition] = {}
    if not sessions_dir.is_dir():
        logger.warning("sessions_dir not found: %s", sessions_dir, icon=LogIcon.WARNING)
        return defs

    for path in sorted(sessions_dir.glob("*.yaml")):
        session_def = SessionDefinition.from_yaml(path)
        defs[session_def.name] = session_def
        logger.debug(
            "session_loaded: %s agents=%s dispatcher=%s",
            session_def.name,
            session_def.all_agent_names,
            session_def.dispatcher,
            icon=LogIcon.START,
        )
    return defs


##### STARTUP LOADER #####


def load_all() -> None:
    """Load ALL agent, tool, and session configs from disk. Call once at startup."""
    global _AGENT_CONFIGS, _TOOL_CATALOGS, _SESSION_DEFS  # noqa: PLW0603

    _AGENT_CONFIGS = _load_agents(st.CONFIG_DIR / "agents")
    _TOOL_CATALOGS = _load_tools(st.CONFIG_DIR / "tools")
    _SESSION_DEFS = _load_sessions(st.SESSIONS_DIR)

    logger.info(
        "config_loaded: %d agents, %d tool_catalogs, %d sessions",
        len(_AGENT_CONFIGS),
        len(_TOOL_CATALOGS),
        len(_SESSION_DEFS),
        icon=LogIcon.COMPLETE,
    )

    _validate_sessions()


def _validate_sessions() -> None:
    """Cross-validate that every agent referenced in sessions exists."""
    for session_name, session_def in _SESSION_DEFS.items():
        for agent_name in session_def.all_agent_names:
            if agent_name not in _AGENT_CONFIGS:
                raise ValueError(
                    f"Session '{session_name}' references agent '{agent_name}' "
                    f"but no config/agents/{agent_name}.yaml found. "
                    f"Available agents: {sorted(_AGENT_CONFIGS)}"
                )


##### ACCESSORS #####


def get_agent_config(name: str) -> AgentConfig:
    """Retrieve a pre-loaded agent config by name."""
    cfg = _AGENT_CONFIGS.get(name)
    if cfg is None:
        raise KeyError(f"Agent '{name}' not loaded. Available: {sorted(_AGENT_CONFIGS)}")
    return cfg


def get_session_def(name: str) -> SessionDefinition:
    """Retrieve a pre-loaded session definition by name."""
    session = _SESSION_DEFS.get(name)
    if session is None:
        raise KeyError(f"Session '{name}' not loaded. Available: {sorted(_SESSION_DEFS)}")
    return session


def get_tool_catalog(name: str) -> ToolCatalog | None:
    """Retrieve a pre-loaded tool catalog by name."""
    return _TOOL_CATALOGS.get(name)


def all_agent_names() -> list[str]:
    return sorted(_AGENT_CONFIGS)


def all_session_names() -> list[str]:
    return sorted(_SESSION_DEFS)


##### MERGE: AgentConfig + SessionAgentRef → AgentDefinition #####


def build_agent_definition(
    agent_name: str,
    ref: SessionAgentRef,
    session_def: SessionDefinition,
) -> AgentDefinition:
    """Merge a pre-loaded AgentConfig with a SessionAgentRef into an AgentDefinition."""
    cfg = get_agent_config(agent_name)
    return AgentDefinition(
        name=cfg.name,
        role=ref.role,
        llm=cfg.llm or session_def.session.llm,
        prompt=cfg.prompt,
        greeting=cfg.greeting,
        tools=cfg.tools,
        handoffs=ref.handoffs,
        return_to=ref.return_to,
        mcp_servers=cfg.mcp_servers,
        guardrails=cfg.guardrails,
        behavior=cfg.behavior or AgentBehavior(),
    )
