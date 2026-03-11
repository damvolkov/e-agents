"""Process-level shared state — adapter registry passed to all modules."""

from __future__ import annotations

import contextlib
import dataclasses
from typing import Any

from e_agents.shared.models import Adapter


@dataclasses.dataclass(slots=True)
class State:
    """Shared state passed to every ``create_app`` factory.

    Holds adapters and any cross-cutting resources that must survive the
    full process lifetime.  Modules that don't need it simply ignore it.
    """

    _adapters: dict[str, Adapter] = dataclasses.field(default_factory=dict)

    def register_adapter(self, adapter: Adapter, **kwargs: Any) -> None:
        """Register an adapter by its canonical name."""
        self._adapters[adapter.name] = adapter

    def get_adapter(self, name: str) -> Adapter:
        """Retrieve an adapter by name."""
        adapter = self._adapters.get(name)
        if adapter is None:
            raise KeyError(f"Adapter '{name}' not registered. Available: {sorted(self._adapters)}")
        return adapter

    @property
    def adapters(self) -> list[Adapter]:
        return list(self._adapters.values())

    @property
    def all_tools(self) -> list[Any]:
        """Aggregate tools from every adapter."""
        return [tool for adapter in self._adapters.values() for tool in adapter.tools]

    @property
    def all_mcp_servers(self) -> list[Any]:
        """Aggregate MCP servers from every adapter."""
        return [srv for adapter in self._adapters.values() for srv in adapter.mcp_servers]

    async def close(self) -> None:
        """Close all adapters that need cleanup."""
        for adapter in self._adapters.values():
            with contextlib.suppress(Exception):
                await adapter.close()
