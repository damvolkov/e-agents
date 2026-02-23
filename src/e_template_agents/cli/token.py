"""CLI commands for LiveKit token generation."""

from datetime import timedelta

import typer
from livekit import api

from e_template_agents.core.settings import settings as st

app = typer.Typer(help="LiveKit token management")


def _generate_token(
    identity: str,
    room: str,
    ttl_minutes: int,
    can_publish: bool,
    can_subscribe: bool,
    can_publish_data: bool,
) -> str:
    """Generate a LiveKit access token."""
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=can_publish,
        can_subscribe=can_subscribe,
        can_publish_data=can_publish_data,
    )
    token = (
        api.AccessToken(api_key=st.LIVEKIT_API_KEY, api_secret=st.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_grants(grants)
        .with_ttl(timedelta(minutes=ttl_minutes))
    )
    return token.to_jwt()


@app.command("generate")
def cmd_generate(
    identity: str = typer.Option("user", "--identity", "-i", help="Participant identity"),
    room: str = typer.Option("test-room", "--room", "-r", help="Room name"),
    ttl: int = typer.Option(60, "--ttl", "-t", help="Token TTL in minutes"),
    no_publish: bool = typer.Option(False, "--no-publish", help="Disable publish permission"),
    no_subscribe: bool = typer.Option(False, "--no-subscribe", help="Disable subscribe permission"),
    no_data: bool = typer.Option(False, "--no-data", help="Disable data publish permission"),
) -> None:
    """Generate a LiveKit access token."""
    token = _generate_token(
        identity=identity,
        room=room,
        ttl_minutes=ttl,
        can_publish=not no_publish,
        can_subscribe=not no_subscribe,
        can_publish_data=not no_data,
    )

    livekit_url = st.LIVEKIT_WS_URL.replace("ws://", "wss://").replace("localhost", "your-server")

    typer.echo()
    typer.secho("LiveKit Access Token", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Identity: {identity}")
    typer.echo(f"Room: {room}")
    typer.echo(f"TTL: {ttl} minutes")
    typer.echo()
    typer.secho("Token:", fg=typer.colors.YELLOW)
    typer.echo(token)
    typer.echo()
    typer.secho("Meet URL:", fg=typer.colors.CYAN)
    typer.echo(f"https://meet.livekit.io?liveKitUrl={livekit_url}&token={token}")
    typer.echo()
