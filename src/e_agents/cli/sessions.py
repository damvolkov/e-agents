"""CLI commands for managing agent sessions."""

import sys
from typing import Literal

import typer
from livekit import agents

from e_agents.core import loader
from e_agents.core.orchestration import Orchestrator
from e_agents.core.registry import ProviderRegistry
from e_agents.shared.logger import LogIcon, logger
from e_agents.shared.settings import settings as st

app = typer.Typer(help="Agent session management")


def run_session(
    session: str = st.DEFAULT_SESSION,
    mode: Literal["dev", "console"] = "dev",
) -> None:
    """Load all configs, resolve the session, and run the agent server."""
    ProviderRegistry.populate()
    loader.load_all()

    session_def = loader.get_session_def(session)

    logger.info(
        "STARTING %s | SESSION=%s | DISPATCHER=%s | AGENTS=%s | MODE=%s | LIVEKIT=%s",
        st.API_NAME,
        session_def.name,
        session_def.dispatcher,
        session_def.all_agent_names,
        mode,
        st.LIVEKIT_URL,
        icon=LogIcon.START,
    )

    server = agents.AgentServer()
    orchestrator = Orchestrator(session_def)
    server.rtc_session()(orchestrator.run)

    sys.argv = [sys.argv[0], mode]
    agents.cli.run_app(server)


@app.command("run")
def cmd_run(
    session: str = typer.Option(st.DEFAULT_SESSION, "--session", "-s", help="Session name"),
) -> None:
    """Run the agent server in dev mode."""
    run_session(session=session, mode="dev")


@app.command("console")
def cmd_console(
    session: str = typer.Option(st.DEFAULT_SESSION, "--session", "-s", help="Session name"),
) -> None:
    """Run the agent in console mode for local testing."""
    run_session(session=session, mode="console")


@app.command("list")
def cmd_list() -> None:
    """List available sessions and agents."""
    loader.load_all()

    typer.echo("Agents:")
    for name in loader.all_agent_names():
        cfg = loader.get_agent_config(name)
        typer.echo(f"  - {name} (tools={cfg.tools})")

    typer.echo("\nSessions:")
    for name in loader.all_session_names():
        session_def = loader.get_session_def(name)
        typer.echo(f"  - {name} ({len(session_def.all_agent_names)} agents, dispatcher={session_def.dispatcher})")
