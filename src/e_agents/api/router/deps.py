"""FastAPI dependencies for LiveKit API operations."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta

from livekit import api

from e_agents.shared.core.settings import settings as st


@asynccontextmanager
async def get_livekit_api() -> AsyncGenerator[api.LiveKitAPI, None]:
    """Dependency that provides a LiveKit API client."""
    lk_api = api.LiveKitAPI(
        url=str(st.LIVEKIT_URL).replace("ws://", "http://").replace("wss://", "https://"),
        api_key=st.LIVEKIT_API_KEY.get_secret_value(),
        api_secret=st.LIVEKIT_API_SECRET.get_secret_value(),
    )
    try:
        yield lk_api
    finally:
        await lk_api.aclose()


def generate_access_token(
    identity: str,
    room: str,
    ttl_minutes: int = 60,
    can_publish: bool = True,
    can_subscribe: bool = True,
    can_publish_data: bool = True,
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
        api.AccessToken(api_key=st.LIVEKIT_API_KEY.get_secret_value(), api_secret=st.LIVEKIT_API_SECRET.get_secret_value())
        .with_identity(identity)
        .with_grants(grants)
        .with_ttl(timedelta(minutes=ttl_minutes))
    )

    return token.to_jwt()
