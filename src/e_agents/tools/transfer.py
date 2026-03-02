"""Transfer tools for agent handoffs."""

from livekit.agents import Agent, RunContext, function_tool


@function_tool()
async def transfer_to_agent(
    context: RunContext,
    agent_name: str,
) -> Agent | None:
    """Transfer to a different agent by name."""
    agents: dict[str, Agent] = context.userdata.agents
    if target := agents.get(agent_name):
        context.session.update_agent(target)
        return target
    return None
