"""CLI command to join a LiveKit room as a participant."""

import asyncio
from typing import Annotated

import typer
from livekit import rtc

from e_template_agents.api.deps import generate_access_token
from e_template_agents.core.logger import LogIcon, logger
from e_template_agents.core.settings import settings as st

app = typer.Typer(help="Join LiveKit rooms as a participant")


async def _join_room(room_name: str, identity: str, ttl: int) -> None:
    """Connect to a LiveKit room as a participant."""
    token = generate_access_token(
        identity=identity,
        room=room_name,
        ttl_minutes=ttl,
        can_publish=True,
        can_subscribe=True,
    )

    logger.info("Connecting to room=%s identity=%s", room_name, identity, icon=LogIcon.START)

    lk_room = rtc.Room()

    @lk_room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant) -> None:
        logger.info("Participant joined: %s", participant.identity, icon=LogIcon.AGENT)

    @lk_room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant) -> None:
        logger.info("Participant left: %s", participant.identity, icon=LogIcon.WARNING)

    @lk_room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        _publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.debug("Audio track from %s", participant.identity, icon=LogIcon.STREAMING)

    @lk_room.on("disconnected")
    def on_disconnected() -> None:
        logger.info("Disconnected from room", icon=LogIcon.WARNING)

    try:
        await lk_room.connect(st.LIVEKIT_WS_URL, token)
        logger.info("Connected to room=%s", room_name, icon=LogIcon.SUCCESS)

        typer.echo("\n" + "=" * 60)
        typer.echo(f"  🎤 Connected to room: {room_name}")
        typer.echo(f"  👤 Identity: {identity}")
        typer.echo(f"  🔗 Server: {st.LIVEKIT_WS_URL}")
        typer.echo("  Press Ctrl+C to disconnect")
        typer.echo("=" * 60 + "\n")

        while lk_room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Disconnecting...", icon=LogIcon.PROCESSING)
    except Exception as e:
        logger.error("Connection error: %s", e, icon=LogIcon.ERROR)
        raise typer.Exit(1) from e
    finally:
        await lk_room.disconnect()
        logger.info("Disconnected", icon=LogIcon.COMPLETE)


@app.callback(invoke_without_command=True)
def join_room(
    ctx: typer.Context,
    room: Annotated[str | None, typer.Option("--room", "-r", help="Room name to join")] = None,
    identity: Annotated[str, typer.Option("--identity", "-i", help="Your identity")] = "user",
    ttl: Annotated[int, typer.Option("--ttl", "-t", help="Token TTL in minutes")] = 60,
) -> None:
    """Join a LiveKit room as a participant to interact with agents."""
    if ctx.invoked_subcommand is None:
        if room is None:
            typer.echo("Error: --room is required", err=True)
            raise typer.Exit(1)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_join_room(room, identity, ttl))
