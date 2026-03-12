"""Loader — scans config directories and tool modules at startup."""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import yaml
from livekit.agents.llm import FunctionTool
from pydantic import TypeAdapter

from e_agents.rtc.core.exceptions import ConfigLoadError
from e_agents.rtc.models.config import AgentConfig, McpTransport, SessionConfig
from e_agents.shared.core.logger import LogIcon, logger
from e_agents.shared.core.settings import settings as st
from e_agents.shared.helpers.scan import Scanner

##### CONFIG #####


@dataclasses.dataclass(slots=True)
class Config:
    """Registry of loaded configuration entities."""

    agents: dict[str, AgentConfig] = dataclasses.field(default_factory=dict)
    sessions: dict[str, SessionConfig] = dataclasses.field(default_factory=dict)
    mcps: dict[str, McpTransport] = dataclasses.field(default_factory=dict)


##### LOADER #####

_MCP_ADAPTER: TypeAdapter[McpTransport] = TypeAdapter(McpTransport)


class Loader(Scanner):
    """Scans config directories and tool modules, populates config and tools registries."""

    __slots__ = ("config", "tools")

    def __init__(self) -> None:
        self.config = Config()
        self.tools: dict[str, FunctionTool] = {}

    async def load(self) -> None:
        """Load all config and tools concurrently."""
        try:
            logger.info("loading_config_and_tools", icon=LogIcon.START, color_range=-1)
            await asyncio.gather(self._ld_load_config(), self._ld_load_tools())
        except ConfigLoadError:
            raise
        except Exception as exc:
            raise ConfigLoadError(str(exc)) from exc

    async def _ld_load_config(self) -> None:
        """Scan YAML files from config directories and hydrate models."""
        dirs: dict[str, Path] = {
            "agents": st.AGENTS_DIR,
            "sessions": st.SESSIONS_DIR,
            "mcps": st.MCPS_DIR,
        }
        existing = {k: v for k, v in dirs.items() if v.is_dir()}
        results = await asyncio.gather(*(self.discover(path, "*.yaml") for path in existing.values()))
        files: dict[str, list[Path]] = dict(zip(existing.keys(), results, strict=True))

        agents: dict[str, AgentConfig] = {}
        for f in files.get("agents", []):
            cfg = AgentConfig.from_yaml(f)
            agents[cfg.name] = cfg
            logger.info(
                "agent_config_loaded",
                agent=cfg.name,
                tools=len(cfg.tools),
                handoffs=len(cfg.handoffs),
                icon=LogIcon.AGENT,
                color_range=-1,
            )

        sessions: dict[str, SessionConfig] = {}
        for f in files.get("sessions", []):
            cfg = SessionConfig.from_yaml(f)
            sessions[cfg.name] = cfg
            logger.info(
                "session_config_loaded",
                session=cfg.name,
                agents=len(cfg.agents),
                dispatcher=cfg.dispatcher,
                icon=LogIcon.DEFAULT,
                color_range=-1,
            )

        mcps: dict[str, McpTransport] = {}
        for f in files.get("mcps", []):
            transport = _MCP_ADAPTER.validate_python(yaml.safe_load(f.read_text(encoding="utf-8")))
            mcps[f.stem] = transport
            logger.info("mcp_config_loaded", mcp=f.stem, transport=transport.transport, icon=LogIcon.NETWORK, color_range=-1)

        self._ld_validate_refs(agents, sessions)
        self.config = Config(agents=agents, sessions=sessions, mcps=mcps)

    def _ld_validate_refs(
        self,
        agents: dict[str, AgentConfig],
        sessions: dict[str, SessionConfig],
    ) -> None:
        """Validate agent references and handoff targets within each session."""
        for session_name, session_cfg in sessions.items():
            declared = set(session_cfg.agents)
            for agent_name in session_cfg.agents:
                agent_cfg = agents.get(agent_name)
                if agent_cfg is None:
                    raise ConfigLoadError(
                        f"Session '{session_name}' references agent '{agent_name}' "
                        f"but no config found. Available: {sorted(agents)}"
                    )
                for target in agent_cfg.handoff_targets:
                    if target not in declared:
                        logger.warning(
                            "handoff_target_missing_in_session",
                            agent=agent_name,
                            target=target,
                            session=session_name,
                            icon=LogIcon.WARNING,
                            color_range=-1,
                        )
                    elif target not in agents:
                        raise ConfigLoadError(
                            f"Agent '{agent_name}' declares handoff to '{target}' "
                            f"but no agent config found for '{target}'"
                        )

    async def _ld_load_tools(self) -> None:
        """Scan tool modules for FunctionTool instances."""
        if not st.TOOLS_DIR.is_dir():
            return
        result = await self.scan(st.TOOLS_DIR, bases=(FunctionTool,))
        for tool in result.functions.values():
            name = tool.info.name
            self.tools[name] = tool
            logger.info("tool_loaded", tool=name, type=type(tool).__name__, icon=LogIcon.TOOL, color_range=-1)
