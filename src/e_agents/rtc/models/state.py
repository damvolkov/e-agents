"""Runtime models for the RTC module."""

from __future__ import annotations

import dataclasses
from typing import Any

from e_agents.shared.models import Adapter
from e_agents.shared.state import State


@dataclasses.dataclass(slots=True)
class SessionState:
    """Per-session state injected as ``AgentSession[SessionState].userdata``.

    Combines process-level shared resources (adapters, …) with
    session-specific dynamic data defined in config.
    """

    shared: State
    data: dict[str, Any] = dataclasses.field(default_factory=dict)

    def get_adapter(self, name: str) -> Adapter:
        """Delegate to shared State."""
        return self.shared.get_adapter(name)

    @property
    def adapters(self) -> list[Adapter]:
        return self.shared.adapters

    @property
    def all_tools(self) -> list[Any]:
        return self.shared.all_tools

    @property
    def all_mcp_servers(self) -> list[Any]:
        return self.shared.all_mcp_servers
