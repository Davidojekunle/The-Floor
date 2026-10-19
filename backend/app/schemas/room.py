import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Page

RoleName = Literal["head", "temp_head", "member"]


class RoomSummary(BaseModel):
    """One entry in the room switcher (GET /me and GET /rooms)."""

    id: uuid.UUID
    name: str
    my_role: RoleName
    pending_count: int = 0  # pending_join_requests + pending_proposals
    pending_join_requests: int = 0  # only where the user has join.manage
    pending_proposals: int = 0  # only where the user has task.approve
    mine_actionable: int = 0  # tasks here where one of MY stages is todo, in_progress, or blocked
    temp_head_expires_at: datetime | None = None  # set while I'm an active temp head in this room
    unread_messages: int = 0  # chat messages after my read position (not mine, not about my own actions)


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
    status: Literal["pending", "active", "rejected", "removed", "left"]


class UserBrief(BaseModel):
    id: uuid.UUID
    name: str


class JoinRequestItem(BaseModel):
    membership_id: uuid.UUID
    user: UserBrief
    requested_at: datetime


class InviteOut(BaseModel):
    invite_code: str


class RoomSummaryPage(Page[RoomSummary]):
    """Named subclass so the OpenAPI schema is `RoomSummaryPage`, not `Page_RoomSummary_`."""


class JoinRequestPage(Page[JoinRequestItem]):
    pass


class TransferHead(BaseModel):
    membership_id: uuid.UUID


class DeleteRoom(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=100)
