import uuid
from typing import Literal

from pydantic import BaseModel


class RoomSummary(BaseModel):
    """One entry in the room switcher (GET /me)."""

    id: uuid.UUID
    name: str
    my_role: Literal["head", "temp_head", "member"]
    pending_count: int = 0  # join requests + proposals waiting on this user
