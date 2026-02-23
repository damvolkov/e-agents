"""CLI commands for managing agent sessions."""

import sys
from typing import Literal

import typer
from livekit import agents

from e_template_agents.core.logger import LogIcon, logger
from e_template_agents.core.settings import settings as st
from e_template_agents.sessions.double_loop import DoubleLoopSession

app = typer.Typer(help="Agent session management")

SESSIONS: dict[str, type[DoubleLoopSession]] = {
    "double_loop": DoubleLoopSession,
}


def run_session(
    session: str = "double_loop",
    mode: Literal["dev", "console"] = "dev",
) -> None:
    """Run the voice agent server."""
    if session not in SESSIONS:
        available = ", ".join(SESSIONS.keys())
        raise typer.BadParameter(f"Unknown session: {session}. Available: {available}")

    logger.info(
        "STARTING %s | SESSION=%s | MODE=%s | LIVEKIT=%s",
        st.API_NAME,
        session,
        mode,
        st.LIVEKIT_URL,
        icon=LogIcon.START,
    )

    server = agents.AgentServer()
    session_instance = SESSIONS[session]()
    server.rtc_session()(session_instance.entrypoint)

    sys.argv = [sys.argv[0], mode]
    agents.cli.run_app(server)


@app.command("run")
def cmd_run(
    session: str = typer.Option("double_loop", "--session", "-s", help="Session type"),
) -> None:
    """Run the agent server in dev mode."""
    run_session(session=session, mode="dev")


@app.command("console")
def cmd_console(
    session: str = typer.Option("double_loop", "--session", "-s", help="Session type"),
) -> None:
    """Run the agent in console mode for local testing."""
    run_session(session=session, mode="console")


@app.command("list")
def cmd_list() -> None:
    """List available sessions."""
    typer.echo("Available sessions:")
    for name in SESSIONS:
        typer.echo(f"  - {name}")
