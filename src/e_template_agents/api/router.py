"""FastAPI router for LiveKit operations."""

import contextlib

from fastapi import APIRouter
from livekit import api

from e_template_agents.api.deps import generate_access_token, get_livekit_api
from e_template_agents.core.settings import settings as st
from e_template_agents.models.api import (
    DispatchRequest,
    DispatchResponse,
    RoomRequest,
    RoomResponse,
    TokenRequest,
    TokenResponse,
)

router = APIRouter(prefix="/api/v1", tags=["livekit"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": st.API_NAME}


@router.post("/tokens", response_model=TokenResponse)
async def create_token(request: TokenRequest) -> TokenResponse:
    """Generate a LiveKit access token for room participation."""
    token = generate_access_token(
        identity=request.identity,
        room=request.room,
        ttl_minutes=request.ttl_minutes,
        can_publish=request.can_publish,
        can_subscribe=request.can_subscribe,
    )
    return TokenResponse(
        token=token,
        room=request.room,
        identity=request.identity,
        livekit_url=st.LIVEKIT_WS_URL,
    )


@router.post("/rooms", response_model=RoomResponse)
async def create_room(request: RoomRequest) -> RoomResponse:
    """Create a new LiveKit room."""
    async with get_livekit_api() as lk:
        room = await lk.room.create_room(
            api.CreateRoomRequest(
                name=request.name,
                max_participants=request.max_participants,
                empty_timeout=request.empty_timeout,
            )
        )
    return RoomResponse(
        name=room.name,
        sid=room.sid,
        max_participants=room.max_participants,
    )


@router.get("/rooms")
async def list_rooms() -> list[RoomResponse]:
    """List all active rooms."""
    async with get_livekit_api() as lk:
        response = await lk.room.list_rooms(api.ListRoomsRequest())
    return [RoomResponse(name=r.name, sid=r.sid, max_participants=r.max_participants) for r in response.rooms]


@router.delete("/rooms/{room_name}")
async def delete_room(room_name: str) -> dict[str, str]:
    """Delete a room."""
    async with get_livekit_api() as lk:
        await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
    return {"status": "deleted", "room": room_name}


@router.get("/rooms/{room_name}/participants")
async def list_participants(room_name: str) -> list[dict]:
    """List participants in a room."""
    async with get_livekit_api() as lk:
        response = await lk.room.list_participants(api.ListParticipantsRequest(room=room_name))
    return [
        {
            "identity": p.identity,
            "sid": p.sid,
            "state": p.state,
            "joined_at": p.joined_at,
        }
        for p in response.participants
    ]


@router.post("/dispatch", response_model=DispatchResponse)
async def dispatch_agent(request: DispatchRequest) -> DispatchResponse:
    """Dispatch an agent to a specific room."""
    async with get_livekit_api() as lk:
        with contextlib.suppress(Exception):
            await lk.room.create_room(api.CreateRoomRequest(name=request.room))

        dispatch = await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=request.room,
                agent_name=request.agent_name,
                metadata=request.metadata,
            )
        )
    return DispatchResponse(agent_id=dispatch.id, room=request.room)


@router.delete("/rooms/{room_name}/participants/{identity}")
async def remove_participant(room_name: str, identity: str) -> dict[str, str]:
    """Remove a participant from a room."""
    async with get_livekit_api() as lk:
        await lk.room.remove_participant(api.RoomParticipantIdentity(room=room_name, identity=identity))
    return {"status": "removed", "identity": identity, "room": room_name}
