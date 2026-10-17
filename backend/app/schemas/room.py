import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RoleName = Literal["head", "temp_head", "member"]


class RoomSummary(BaseModel):
    """One entry in the room switcher (GET /me and GET /rooms)."""

    id: uuid.UUID
    name: str
    my_role: RoleName
    pending_count: int = 0  # join requests waiting on this user (proposals get added in phase 4)


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Room name can't be empty.")
        return v


class RoomOut(BaseModel):
    id: uuid.UUID
    name: str
    my_role: RoleName
    temp_head_expires_at: datetime | None = None
    permissions: list[str]
    member_count: int
    invite_code: str | None = None  # only for users with invite.manage
    created_at: datetime


class JoinPreview(BaseModel):
    room_name: str
    member_count: int
    already_requested: bool
    already_member: bool


class MembershipOut(BaseModel):
    membership_id: uuid.UUID
    room_id: uuid.UUID
    status: Literal["pending", "active", "rejected", "removed"]


class UserBrief(BaseModel):
    id: uuid.UUID
    name: str


class JoinRequestItem(BaseModel):
    membership_id: uuid.UUID
    user: UserBrief
    requested_at: datetime


class InviteOut(BaseModel):
    invite_code: str
