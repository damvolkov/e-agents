"""LiveKit RTC application factory — standalone-capable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livekit import agents

from e_agents.rtc.operations.build import Builder
from e_agents.rtc.operations.registry import ProviderRegistry
from e_agents.shared.core.logger import LogIcon, logger
from e_agents.shared.core.settings import settings as st

if TYPE_CHECKING:
    from e_agents.shared.state import State


def create_app(state: State, *, session: str = st.DEFAULT_SESSION) -> agents.AgentServer:
    """Create a fully configured LiveKit AgentServer, ready for ``run_app``."""
    server = agents.AgentServer()
    builder = Builder()

    logger.info("registering_providers", icon=LogIcon.START)
    ProviderRegistry.populate()

    logger.info("rtc_ready", session=session, livekit=str(st.LIVEKIT_URL), icon=LogIcon.SUCCESS)

    @server.rtc_session()
    async def _entrypoint(ctx: agents.JobContext) -> None:
        await builder.load()
        agent_session, dispatcher = builder.build(session, state)
        await agent_session.start(dispatcher, room=ctx.room)

    return server


if __name__ == "__main__":
    from e_agents.shared.adapters.searxng import SearXNGAdapter
    from e_agents.shared.state import State

    _state = State()
    _state.register_adapter(SearXNGAdapter())
    _server = create_app(_state)
    agents.cli.run_app(_server)
