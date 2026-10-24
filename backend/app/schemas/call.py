import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Page
from app.schemas.room import UserBrief


class TaskRef(BaseModel):
    id: uuid.UUID
    title: str


class StartCall(BaseModel):
    task_id: uuid.UUID | None = Field(None, description="A call about this task. Leave out for a call in the room.")


class CallOut(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    task: TaskRef | None
    kind: Literal["instant", "scheduled"]
    status: Literal["scheduled", "live", "ended", "cancelled"]
    missed: bool
    title: str
    description: str | None
    starts_at: datetime | None = Field(description="Scheduled meetings (C2)")
    ends_at_planned: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    joinable_from: datetime
    created_by: UserBrief | None
    participants: list[UserBrief] = Field(description="Who's in right now. Empty unless live.")
    external_url: str | None
    can_end: bool = Field(description="May press End for everyone: whoever started it, the head or a temp head")
    can_edit: bool


class CallPage(Page[CallOut]):
    """Named subclass so the OpenAPI schema is `CallPage`."""


class JoinPass(BaseModel):
    """This person's own pass into the call. The call is private: the room link alone lets nobody in."""

    provider: Literal["daily"]
    room_url: str
    token: str
    expires_at: datetime


class LiveCall(BaseModel):
    """On /me rooms and task detail: a call is live here."""

    id: uuid.UUID
    participant_count: int
