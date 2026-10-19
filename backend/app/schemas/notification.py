import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

NotificationType = Literal[
    "join_requested", "proposal_submitted", "stages_unassigned",
    "join_approved", "proposal_approved", "proposal_rejected", "temp_head_granted", "head_transferred",
    "removed_from_room", "room_deleted",
    "stage_ready", "stage_assigned",
    "mentioned",
]


class NamedRef(BaseModel):
    id: uuid.UUID
    name: str


class TitledRef(BaseModel):
    id: uuid.UUID
    title: str


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: NotificationType
    title: str = Field(description="Ready to show, e.g. “Femi asked to join Studio Alpha”.")
    room: NamedRef | None = Field(None, description="May point at a room that's gone (room_deleted, removed_from_room).")
    task: TitledRef | None = None
    stage: TitledRef | None = None
    actor: NamedRef | None = None
    data: dict | None = Field(
        None,
        description="Extra details by type. proposal_rejected: {reason}. temp_head_granted: {expires_at}. "
                    "stages_unassigned: {stages: [{task_id, task_title, stage_id, stage_title}]}. "
                    "mentioned: {message_id, preview}.",
    )
    created_at: datetime
    read: bool


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    has_more: bool = Field(description="Pass the last item's id as `before` to get the next page.")


class MarkReadRequest(BaseModel):
    up_to: uuid.UUID | None = Field(None, description="Marks this one and everything older. Leave out to mark all.")


class NotificationSettingsOut(BaseModel):
    email_enabled: bool = Field(description="Master switch for notification emails. Security emails always go.")
    requests: bool
    decisions: bool
    assignments: bool
    daily_digest: bool
    mentions: bool = Field(description="Someone @mentions you in chat: bell, email and push.")
    all_messages: bool = Field(description="A push for every chat message in your rooms (push only, off by default).")
    muted_rooms: list[uuid.UUID] = Field(description="Silenced on both channels. Change with PUT/DELETE muted-rooms/{room_id}.")


class NotificationSettingsUpdate(BaseModel):
    """Send only the switches that change."""

    email_enabled: bool | None = None
    requests: bool | None = None
    decisions: bool | None = None
    assignments: bool | None = None
    daily_digest: bool | None = None
    mentions: bool | None = None
    all_messages: bool | None = None

    @field_validator("*", mode="before")
    @classmethod
    def not_null(cls, v):
        if v is None:
            raise ValueError("Can't be null. Leave it out to keep it.")
        return v
