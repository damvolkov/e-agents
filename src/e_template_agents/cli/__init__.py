"""CLI commands for e_template_agents."""

import typer

from e_template_agents.cli.join import app as join_app
from e_template_agents.cli.sessions import app as sessions_app
from e_template_agents.cli.sessions import run_session
from e_template_agents.cli.token import app as token_app

cli = typer.Typer(
    name="e_template_agents",
    help="Multi-agent voice AI system",
    no_args_is_help=True,
)

cli.add_typer(sessions_app, name="session", help="Agent session commands")
cli.add_typer(join_app, name="join", help="Join LiveKit rooms")
cli.add_typer(token_app, name="token", help="LiveKit token management")


@cli.command("run")
def run(
    session: str = typer.Option("double_loop", "--session", "-s", help="Session type"),
) -> None:
    """Run the agent server in dev mode."""
    run_session(session=session, mode="dev")


@cli.command("console")
def console(
    session: str = typer.Option("double_loop", "--session", "-s", help="Session type"),
) -> None:
    """Run agent in console mode for local testing."""
    run_session(session=session, mode="console")
