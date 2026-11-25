import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import UtcDateTime


class AdminHealth(BaseModel):
    database_ok: bool
    database_ms: float
    migration: str | None
    started_at: UtcDateTime
    uptime_seconds: int
    loop_last_run_at: UtcDateTime | None  # emails, digests and reminders; should be seconds ago
    loop_last_error_at: UtcDateTime | None
    loop_last_error: str | None  # the error's type only
    emails_waiting: int
    oldest_waiting_email_at: UtcDateTime | None
    emails_sent_7d: int
    emails_failed_7d: int
    push_sent_since_start: int
    push_failed_since_start: int
    push_expired_since_start: int  # browsers that dropped their subscription (cleaned up)


class AdminPeople(BaseModel):
    total: int
    new_7d: int
    new_30d: int
    active_7d: int
    active_30d: int
    with_push: int
    with_calendar: int


class AdminRooms(BaseModel):
    total: int
    new_30d: int
    active_30d: int  # a task made or a chat message sent in the last 30 days
    average_members: float
    pending_join_requests: int
    with_3_members: int = Field(0, description="Rooms with 3 or more active members")
    real: int = Field(0, description="Rooms with 3+ active members and at least one stage done: the growth goal")


class AdminSource(BaseModel):
    source: str = Field(description='The ?ref= word, or "direct" when they came without one')
    people: int
    people_7d: int
    rooms_started: int = Field(description="Rooms made by people who came this way")
    real_rooms: int = Field(description="Of those, rooms with 3+ active members and a stage done")


class AdminWork(BaseModel):
    tasks_total: int
    tasks_open: int
    tasks_created_7d: int
    tasks_finished_7d: int
    proposals_waiting: int
    stages_done_7d: int
    stages_in_progress: int
    stages_overdue: int
    stages_blocked: int
    stages_stuck: int  # To do or In progress for 3+ days


class AdminActivity(BaseModel):
    messages_7d: int
    updates_7d: int
    nudges_30d: int
    nudges_answered_30d: int


class AdminWeek(BaseModel):
    week_start: UtcDateTime
    signups: int
    tasks_created: int
    stages_done: int
    messages: int


class AdminStats(BaseModel):
    generated_at: UtcDateTime
    health: AdminHealth
    people: AdminPeople
    rooms: AdminRooms
    work: AdminWork
    activity: AdminActivity
    calls: "AdminCalls"
    weeks: list[AdminWeek]
    sources: list[AdminSource] = []


class AdminCalls(BaseModel):
    ready: bool = Field(description="LiveKit is configured on this server")
    mode: Literal["off", "staff", "everyone"]
    minutes_this_month: int = Field(description="Participant minutes: one person for one minute")
    free_minutes: int = Field(description="The provider's free monthly allowance (new calls stop past it)")
    calls_this_month: int
    live_now: int
    meetings_upcoming: int


class AdminPerson(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    is_owner: bool


class AdminAdd(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class AdminEventOut(BaseModel):
    id: uuid.UUID
    created_at: UtcDateTime
    actor_name: str
    action: Literal["setting_changed", "admin_added", "admin_removed"]
    detail: dict


class SiteSettings(BaseModel):
    calls: Literal["off", "staff", "everyone"] = Field(description="Who has calls and meetings")
    calls_ready: bool = Field(False, description="LiveKit is configured; calls can't be switched on without it")
    signups_open: bool = Field(description="New accounts can be made (people invited by email always can)")
    notification_emails: bool = Field(description="Notification and meeting emails. Security emails always go.")
    daily_digest: bool
    push: bool = Field(description="Pop-up notifications on devices")
    announcement: str | None = Field(None, description="A banner shown to everyone signed in")


class SiteSettingsUpdate(BaseModel):
    """Send only what changes."""

    calls: Literal["off", "staff", "everyone"] | None = None
    signups_open: bool | None = None
    notification_emails: bool | None = None
    daily_digest: bool | None = None
    push: bool | None = None
    announcement: str | None = Field(None, max_length=300, description="Empty clears it")

    @field_validator("announcement")
    @classmethod
    def tidy(cls, v):
        return (v or "").strip() or None


class SiteInfo(BaseModel):
    """What any visitor may know."""

    signups_open: bool
    announcement: str | None


AdminStats.model_rebuild()
