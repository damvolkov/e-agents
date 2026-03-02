"""Pydantic models for agent configuration."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class AgentConfig(BaseModel):
    """Individual agent configuration."""

    name: str = Field(..., description="Agent identifier key")
    class_name: str = Field(..., description="Python class name")
    instructions: str = Field(..., description="System prompt/instructions for the agent")
    greeting_prompt: str = Field(default="", description="Optional greeting prompt")
    mcp_servers: list[dict] = Field(default_factory=list, description="MCP servers config")
    routes_to: list[str] = Field(default_factory=list, description="Agents this one can route to")


class AgentsConfig(BaseModel):
    """Collection of agent configurations."""

    agents: list[AgentConfig] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> AgentsConfig:
        """Load agents configuration from a YAML file."""
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.model_validate(raw)

    def get(self, name: str) -> AgentConfig | None:
        """Get agent config by name."""
        return next((a for a in self.agents if a.name == name), None)

    def __getitem__(self, name: str) -> AgentConfig:
        """Get agent config by name, raises KeyError if not found."""
        config = self.get(name)
        if config is None:
            available = ", ".join(a.name for a in self.agents)
            raise KeyError(f"Agent '{name}' not found. Available: {available}")
        return config

    @model_validator(mode="after")
    def validate_routes(self) -> AgentsConfig:
        """Validate that all routes_to references exist."""
        names = {a.name for a in self.agents}
        for agent in self.agents:
            invalid = [r for r in agent.routes_to if r not in names]
            if invalid:
                raise ValueError(f"Agent '{agent.name}' routes to unknown agents: {invalid}")
        return self
