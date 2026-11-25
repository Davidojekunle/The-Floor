import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.schemas.common import Page
from app.schemas.room import LiveCall, UserBrief  # noqa: F401  (LiveCall lives with the room switcher)


class TaskRef(BaseModel):
    id: uuid.UUID
    title: str


class StartCall(BaseModel):
    task_id: uuid.UUID | None = Field(None, description="A call about this task. Leave out for a call in the room.")


class TagRef(BaseModel):
    id: uuid.UUID
    name: str


class InviteIn(BaseModel):
    """Everyone in the room (now and as it grows), or some people and/or tags."""

    everyone: bool = False
    user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    tag_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class InviteOut(BaseModel):
    everyone: bool
    users: list[UserBrief]
    tags: list[TagRef]


class RepeatIn(BaseModel):
    every: Literal["week", "2weeks"]
    until: date = Field(description="The last day a meeting may fall on (the organiser's calendar). At most 26 meetings.")


def _https(v: str | None) -> str | None:
    v = (v or "").strip() or None
    if v and not v.startswith("https://"):
        raise ValueError("Paste a full link starting with https://")
    return v


class MeetingIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    starts_at: AwareDatetime = Field(description="In the future, with a timezone")
    duration_minutes: int = Field(ge=15, le=180)
    task_id: uuid.UUID | None = None
    invite: InviteIn
    external_url: str | None = Field(None, max_length=2000, description="A Meet or Zoom link: joining opens it instead")
    repeat: RepeatIn | None = None

    _check_url = field_validator("external_url")(classmethod(lambda cls, v: _https(v)))


class MeetingUpdate(BaseModel):
    """Send only what changes. Changing the time or link tells the invitees, with an updated calendar file."""

    title: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    starts_at: AwareDatetime | None = None
    duration_minutes: int | None = Field(None, ge=15, le=180)
    task_id: uuid.UUID | None = None
    invite: InviteIn | None = None
    external_url: str | None = Field(None, max_length=2000)

    _check_url = field_validator("external_url")(classmethod(lambda cls, v: _https(v)))


class ClashCheck(BaseModel):
    starts_at: AwareDatetime
    duration_minutes: int = Field(ge=15, le=180)
    invite: InviteIn
    exclude_call_id: uuid.UUID | None = Field(None, description="The meeting being edited")


class Clash(BaseModel):
    user: UserBrief
    title: str
    starts_at: datetime
    room_name: str


class ClashOut(BaseModel):
    clashes: list[Clash]


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
    attended: list[UserBrief] = Field(default_factory=list, description="Everyone who joined (the call log)")
    duration_minutes: int | None = Field(None, description="How long it ran, once ended; planned length while scheduled")
    invite: InviteOut | None = Field(None, description="Meetings only")
    repeats: bool = Field(False, description="Part of a repeating series")
    rsvp: "RsvpOut | None" = Field(None, description="Meetings: who's going, who can't, and my answer")
    external_url: str | None
    can_end: bool = Field(description="May press End for everyone: whoever started it, the head or a temp head")
    can_edit: bool


class CallPage(Page[CallOut]):
    """Named subclass so the OpenAPI schema is `CallPage`."""


class JoinPass(BaseModel):
    """This person's own pass into the call. The call is private: the room link alone lets nobody in."""

    provider: Literal["livekit", "link"]
    server_url: str | None = Field(None, description="livekit: where the browser connects (wss://…)")
    token: str | None = None
    expires_at: datetime | None = None
    url: str | None = Field(None, description="link: a pasted Meet or Zoom link to open instead")


class RsvpOut(BaseModel):
    going: list[UserBrief]
    declined: list[UserBrief]
    mine: Literal["going", "declined"] | None = None
    invited: bool = Field(description="I'm invited, so I can answer")


class RsvpIn(BaseModel):
    response: Literal["going", "declined"] | None = Field(description="null takes the answer back")


CallOut.model_rebuild()
