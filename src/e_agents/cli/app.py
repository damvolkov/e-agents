"""CLI application factory — cyclopts with LiveKit passthrough."""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import TYPE_CHECKING

import uvicorn
from cyclopts import App
from livekit import agents

from e_agents.shared.core.settings import settings as st

if TYPE_CHECKING:
    from fastapi import FastAPI
    from livekit.agents import AgentServer

    from e_agents.shared.state import State


def _serve_api(app: FastAPI) -> None:
    """Run FastAPI / uvicorn in a daemon thread."""
    config = uvicorn.Config(app=app, host="0.0.0.0", port=st.API_PORT, log_level="warning")
    asyncio.run(uvicorn.Server(config).serve())


def create_app(state: State, *, api: FastAPI, rtc: AgentServer) -> App:
    """Build the cyclopts CLI with ``create`` and ``lk`` commands."""
    app = App(name="e-agents", help="Multi-agent voice AI system")

    @app.command(name="create")
    def create() -> None:
        """Create agent / session / tool configurations."""
        print("TODO")

    @app.command(name="lk")
    def lk() -> None:
        """Run any LiveKit agent CLI command (dev, start, console, connect, download-files)."""
        idx = sys.argv.index("lk")
        lk_args = sys.argv[idx + 1 :]

        threading.Thread(target=_serve_api, args=(api,), daemon=True).start()
        sys.argv = [sys.argv[0], *lk_args]
        agents.cli.run_app(rtc)

    return app


if __name__ == "__main__":
    from e_agents.api.app import create_app as create_api_app
    from e_agents.rtc.app import create_app as create_rtc_app
    from e_agents.shared.adapters.searxng import SearXNGAdapter
    from e_agents.shared.state import State

    _state = State()
    _state.register_adapter(SearXNGAdapter(base_url=str(st.SEARXNG_URL)))
    _api = create_api_app(_state)
    _rtc = create_rtc_app(_state)
    _cli = create_app(_state, api=_api, rtc=_rtc)
    _cli()
