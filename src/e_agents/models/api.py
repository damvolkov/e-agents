"""API request/response models."""

from pydantic import BaseModel


class TokenRequest(BaseModel):
    """Request to generate a LiveKit access token."""

    identity: str
    room: str
    ttl_minutes: int = 60
    can_publish: bool = True
    can_subscribe: bool = True


class TokenResponse(BaseModel):
    """Response containing a LiveKit access token."""

    token: str
    room: str
    identity: str
    livekit_url: str


class RoomRequest(BaseModel):
    """Request to create a LiveKit room."""

    name: str
    max_participants: int = 20
    empty_timeout: int = 300


class RoomResponse(BaseModel):
    """Response containing room information."""

    name: str
    sid: str
    max_participants: int


class DispatchRequest(BaseModel):
    """Request to dispatch an agent to a room."""

    room: str
    agent_name: str = "default"
    metadata: str = ""


class DispatchResponse(BaseModel):
    """Response containing dispatch information."""

    agent_id: str
    room: str
