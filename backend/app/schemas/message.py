import uuid
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

from app.schemas.room import UserBrief


class Ref(BaseModel):
    id: uuid.UUID
    title: str


# ------------------------------------------------------------------ events (discriminated on `type`)

class _Event(BaseModel):
    actor: UserBrief | None = None
    subject: UserBrief | None = None


class StageBlockedDetail(BaseModel):
    reason: str


class TempHeadGrantedDetail(BaseModel):
    expires_at: datetime


class MemberJoinedEvent(_Event):
    type: Literal["member_joined"]
    detail: None = None


class TaskCreatedEvent(_Event):
    type: Literal["task_created"]
    detail: None = None


class TaskApprovedEvent(_Event):
    type: Literal["task_approved"]
    detail: None = None


class StageDoneEvent(_Event):
    type: Literal["stage_done"]
    detail: None = None


class StageBlockedEvent(_Event):
    type: Literal["stage_blocked"]
    detail: StageBlockedDetail


class StageReopenedEvent(_Event):
    type: Literal["stage_reopened"]
    detail: None = None


class TaskCompletedEvent(_Event):
    type: Literal["task_completed"]
    detail: None = None


class TempHeadGrantedEvent(_Event):
    type: Literal["temp_head_granted"]
    detail: TempHeadGrantedDetail


class TempHeadRevokedEvent(_Event):
    type: Literal["temp_head_revoked"]
    detail: None = None


MessageEvent = Annotated[
    Union[
        MemberJoinedEvent, TaskCreatedEvent, TaskApprovedEvent, StageDoneEvent, StageBlockedEvent,
        StageReopenedEvent, TaskCompletedEvent, TempHeadGrantedEvent, TempHeadRevokedEvent,
    ],
    Field(discriminator="type"),
]

EVENT_MODELS = {
    m.model_fields["type"].annotation.__args__[0]: m
    for m in (
        MemberJoinedEvent, TaskCreatedEvent, TaskApprovedEvent, StageDoneEvent, StageBlockedEvent,
        StageReopenedEvent, TaskCompletedEvent, TempHeadGrantedEvent, TempHeadRevokedEvent,
    )
}


# ------------------------------------------------------------------ messages

class MessageOut(BaseModel):
    id: uuid.UUID
    type: Literal["user", "system"]
    sender: UserBrief | None
    body: str | None
    task: Ref | None
    stage: Ref | None
    event: MessageEvent | None
    created_at: datetime
    deleted: bool
    can_delete: bool


class MessagePage(BaseModel):
    items: list[MessageOut]
    has_more: bool
    last_read_message_id: uuid.UUID | None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    task_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None

    @field_validator("body")
    @classmethod
    def strip_body(cls, v: str) -> str:
        v = v.strip()  # keep inner newlines: it's chat
        if not v:
            raise ValueError("Message can't be empty.")
        return v


class MarkRead(BaseModel):
    up_to: uuid.UUID | None = None
