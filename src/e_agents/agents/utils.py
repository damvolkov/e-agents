"""Utilities for agent configuration loading."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from livekit.agents import Agent

from e_agents.models.agent import AgentConfig

if TYPE_CHECKING:
    from e_agents.models.agent import AgentsConfig


class ConfigurableAgent(Protocol):
    """Protocol for agents that accept a config parameter."""

    def __init__(self, config: AgentConfig) -> None: ...


def load_agent(agent_class: type[ConfigurableAgent], config: AgentConfig) -> Agent:
    """Instantiate an agent with configuration."""
    return agent_class(config=config)  # type: ignore[return-value]


def load_agents_from_config(
    agents_config: AgentsConfig,
    agent_classes: dict[str, type[ConfigurableAgent]],
) -> dict[str, Agent]:
    """Load all agents from configuration."""
    agents: dict[str, Agent] = {}

    for agent_config in agents_config.agents:
        agent_class = agent_classes.get(agent_config.class_name)
        if agent_class is None:
            available = ", ".join(agent_classes.keys())
            raise ValueError(f"Unknown agent class '{agent_config.class_name}'. Available: {available}")
        agents[agent_config.name] = load_agent(agent_class, agent_config)

    return agents
